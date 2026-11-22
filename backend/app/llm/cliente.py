"""Cliente de modelos vía OpenRouter (API compatible con OpenAI).

- Prueba los modelos configurados para cada agente en orden; si uno falla
  (límite de uso, modelo retirado, caída), pasa al siguiente.
- En modo "simulado" no hace llamadas: cada agente usa su ruta sin IA.
- Caché: las respuestas de los agentes deterministas (Clasificador, Intérprete y Explicador) se
  reutilizan si llega exactamente la misma entrada; no gastan cupo ni dinero.
- Cada llamada deja un evento de métricas con tokens, costo (según data/precios.json) y tiempo,
  sin el contenido de la conversación.
- Con OPENROUTER_SIN_RETENCION (o «sin_retencion» en el agente) solo se usan proveedores que no
  guardan ni entrenan con lo que reciben.
"""

import hashlib
import json
import logging
import math
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from app import metricas
from app.agents import configuracion
from app.config import settings
from app.llm import cupo

log = logging.getLogger(__name__)

CACHEABLES = {"clasificador", "interprete", "explicador"}
_CACHE_MAX = 500
_CACHE_TTL = 24 * 3600
_cache: OrderedDict[str, tuple[float, "RespuestaLLM"]] = OrderedDict()
_precios: dict[str, dict[str, float]] | None = None


@dataclass
class RespuestaLLM:
    texto: str
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    desde_cache: bool = False
    llave: str | None = None  # para olvidar la respuesta si quien la pidió la descarta


def precios() -> dict[str, dict[str, float]]:
    """USD por millón de tokens de entrada y salida de cada modelo (los «:free» cuestan 0)."""
    global _precios
    if _precios is None:
        ruta = settings.data_dir / "precios.json"
        _precios = json.loads(ruta.read_text(encoding="utf-8")).get("modelos", {}) if ruta.exists() else {}
    return _precios


def costo(modelo: str, entrada: int, salida: int) -> float:
    if modelo.endswith(":free") or modelo == "openrouter/free":
        return 0.0
    p = precios().get(modelo) or next((v for k, v in precios().items() if modelo.startswith(k)), None)
    if not p:
        return 0.0
    return (entrada * p["entrada"] + salida * p["salida"]) / 1_000_000


def estimar_tokens(texto: str) -> int:
    """Aproximación (≈ 4 caracteres por token) para cuando el proveedor no informa el uso."""
    return math.ceil(len(texto) / 4)


def reiniciar_cache() -> None:
    _cache.clear()


def olvidar(r: "RespuestaLLM") -> None:
    """Quita de la caché una respuesta que el código descartó (no se vuelve a servir)."""
    if r.llave:
        _cache.pop(r.llave, None)


class LLMNoDisponible(Exception):
    pass


_cliente: AsyncOpenAI | None = None


def _get_cliente() -> AsyncOpenAI:
    global _cliente
    if _cliente is None:
        _cliente = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=30,
            max_retries=0,
            default_headers={"HTTP-Referer": settings.app_url, "X-Title": "DeclaraFacil AI"},
        )
    return _cliente


def disponible() -> bool:
    return settings.modo_llm == "openrouter" and bool(settings.openrouter_api_key)


def _limpiar_salida(texto: str | None) -> str:
    """Quita el razonamiento que algunos modelos dejan dentro del texto (<think>…</think>)."""
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.DOTALL)
    return re.sub(r"^.*?</think>", "", t, flags=re.DOTALL).strip()


AlEscribir = Callable[[str], Awaitable[None]]


def _uso(obj: Any) -> tuple[int, int] | None:
    u = getattr(obj, "usage", None)
    if u is None:
        return None
    try:
        return int(getattr(u, "prompt_tokens", 0) or 0), int(getattr(u, "completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        return None


async def _pedir(modelo: str, mensajes: list[dict[str, str]], cfg: dict[str, Any], max_tokens: int, extra: dict[str, Any],
                 al_escribir: AlEscribir | None) -> tuple[str, str, tuple[int, int] | None]:
    """Una llamada a un modelo. Con al_escribir, el texto llega por partes mientras el modelo escribe."""
    pedido = dict(model=modelo, messages=mensajes, temperature=cfg.get("temperatura", 0), max_tokens=max_tokens, **extra)
    if al_escribir is None:
        r = await _get_cliente().chat.completions.create(**pedido)
        return r.choices[0].message.content or "", getattr(r, "model", None) or modelo, _uso(r)
    partes: list[str] = []
    servido = modelo
    uso = None
    flujo = await _get_cliente().chat.completions.create(**pedido, stream=True, stream_options={"include_usage": True})
    async for ev in flujo:
        servido = getattr(ev, "model", None) or servido
        uso = _uso(ev) or uso
        delta = ev.choices[0].delta.content if ev.choices else None
        if delta:
            partes.append(delta)
            await al_escribir(delta)
    return "".join(partes), servido, uso


async def completar(agente: str, sistema: str, usuario: str, json_mode: bool = False, max_tokens: int = 1200,
                    al_escribir: AlEscribir | None = None) -> RespuestaLLM:
    """Prueba los modelos del agente en orden.

    Los modelos gratuitos casi siempre "piensan" antes de responder y ese razonamiento
    gasta los tokens de salida; por eso se pide razonamiento corto y oculto
    (reasoning.effort / exclude). Si un proveedor rechaza esos parámetros o el modo
    JSON, se reintenta una vez sin ellos con el mismo modelo.
    """
    if not disponible():
        raise LLMNoDisponible("Modo simulado: sin llamadas a modelos")
    cfg = configuracion.obtener(agente)
    if not cfg.get("activo", True):
        raise LLMNoDisponible(f"El agente {agente} está desactivado")
    usar_cache = agente in CACHEABLES and al_escribir is None and cfg.get("cache", True)
    llave = hashlib.sha256(json.dumps([agente, cfg.get("modelos"), sistema, usuario, json_mode, max_tokens]).encode()).hexdigest()
    if usar_cache and (guardada := _cache.get(llave)) and time.monotonic() - guardada[0] < _CACHE_TTL:
        _cache.move_to_end(llave)
        metricas.registrar("ia", agente=agente, modelo=guardada[1].modelo, resultado="cache", tokens_entrada=0, tokens_salida=0, costo_usd=0, ms=0)
        r = guardada[1]
        return RespuestaLLM(texto=r.texto, modelo=r.modelo, desde_cache=True, llave=llave)
    if not cupo.reservar():
        metricas.registrar("ia", agente=agente, resultado="sin_cupo")
        raise LLMNoDisponible("Sin cupo de IA para esta solicitud")
    razonamiento = cfg.get("razonamiento")
    sin_retencion = settings.sin_retencion or bool(cfg.get("sin_retencion"))
    errores = []
    mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
    t0 = time.perf_counter()
    for modelo in cfg.get("modelos", []):
        for con_extras in (True, False):
            extra: dict[str, Any] = {}
            cuerpo: dict[str, Any] = {}
            if sin_retencion:
                # Solo proveedores que no guardan ni entrenan con los datos (política de OpenRouter)
                cuerpo["provider"] = {"data_collection": "deny"}
            if con_extras and json_mode:
                extra["response_format"] = {"type": "json_object"}
            if con_extras and razonamiento == "no":
                # Sin razonamiento: responde ~6 veces más rápido; sirve para el chat, donde el código valida todo
                cuerpo["reasoning"] = {"enabled": False}
            elif con_extras and razonamiento:
                cuerpo["reasoning"] = {"effort": razonamiento, "exclude": True}
            if cuerpo:
                extra["extra_body"] = cuerpo
            if not con_extras and not (json_mode or razonamiento):
                break
            try:
                crudo, servido, uso = await _pedir(modelo, mensajes, cfg, max_tokens, extra, al_escribir)
                texto = _limpiar_salida(crudo)
                if not texto:
                    raise ValueError("respuesta vacía")
                entrada, salida = uso or (estimar_tokens(sistema + usuario), estimar_tokens(crudo))
                r = RespuestaLLM(texto=texto, modelo=servido, tokens_entrada=entrada, tokens_salida=salida, costo_usd=costo(modelo, entrada, salida),
                                 llave=llave if usar_cache else None)
                metricas.registrar("ia", agente=agente, modelo=servido, resultado="ok", tokens_entrada=entrada, tokens_salida=salida,
                                   costo_usd=r.costo_usd, ms=(time.perf_counter() - t0) * 1000)
                if usar_cache:
                    _cache[llave] = (time.monotonic(), r)
                    while len(_cache) > _CACHE_MAX:
                        _cache.popitem(last=False)
                return r
            except BadRequestError as e:
                log.warning("Modelo %s rechazó la solicitud de %s: %s", modelo, agente, e)
                errores.append(f"{modelo}: parámetros")
                continue  # reintenta sin modo JSON ni razonamiento
            except Exception as e:  # noqa: BLE001 - cualquier otra falla pasa al siguiente modelo
                log.warning("Modelo %s falló para %s: %s", modelo, agente, e)
                errores.append(f"{modelo}: {type(e).__name__}")
                break
    metricas.registrar("ia", agente=agente, resultado="error", ms=(time.perf_counter() - t0) * 1000)
    raise LLMNoDisponible("Ningún modelo respondió (" + "; ".join(errores) + ")")


def extraer_json(texto: str) -> Any:
    """Saca el primer objeto JSON de una respuesta (los modelos a veces agregan texto o ```)."""
    limpio = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass
    inicio = limpio.find("{")
    if inicio < 0:
        raise ValueError("La respuesta no contiene JSON")
    profundidad = 0
    for i in range(inicio, len(limpio)):
        if limpio[i] == "{":
            profundidad += 1
        elif limpio[i] == "}":
            profundidad -= 1
            if profundidad == 0:
                return json.loads(limpio[inicio : i + 1])
    raise ValueError("JSON incompleto")
