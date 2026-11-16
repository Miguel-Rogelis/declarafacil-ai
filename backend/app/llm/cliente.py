"""Cliente de modelos vía OpenRouter (API compatible con OpenAI).

- Prueba los modelos configurados para cada agente en orden; si uno falla
  (límite de uso, modelo retirado, caída), pasa al siguiente.
- En modo "simulado" no hace llamadas: cada agente usa su ruta sin IA.
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from app.agents import configuracion
from app.config import settings
from app.llm import cupo

log = logging.getLogger(__name__)


@dataclass
class RespuestaLLM:
    texto: str
    modelo: str


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


async def _pedir(modelo: str, mensajes: list[dict[str, str]], cfg: dict[str, Any], max_tokens: int, extra: dict[str, Any],
                 al_escribir: AlEscribir | None) -> tuple[str, str]:
    """Una llamada a un modelo. Con al_escribir, el texto llega por partes mientras el modelo escribe."""
    pedido = dict(model=modelo, messages=mensajes, temperature=cfg.get("temperatura", 0), max_tokens=max_tokens, **extra)
    if al_escribir is None:
        r = await _get_cliente().chat.completions.create(**pedido)
        return r.choices[0].message.content or "", getattr(r, "model", None) or modelo
    partes: list[str] = []
    servido = modelo
    flujo = await _get_cliente().chat.completions.create(**pedido, stream=True)
    async for ev in flujo:
        servido = getattr(ev, "model", None) or servido
        delta = ev.choices[0].delta.content if ev.choices else None
        if delta:
            partes.append(delta)
            await al_escribir(delta)
    return "".join(partes), servido


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
    if not cupo.reservar():
        raise LLMNoDisponible("Sin cupo de IA para esta solicitud")
    razonamiento = cfg.get("razonamiento")
    errores = []
    for modelo in cfg.get("modelos", []):
        for con_extras in (True, False):
            extra: dict[str, Any] = {}
            if con_extras and json_mode:
                extra["response_format"] = {"type": "json_object"}
            if con_extras and razonamiento == "no":
                # Sin razonamiento: responde ~6 veces más rápido; sirve para el chat, donde el código valida todo
                extra["extra_body"] = {"reasoning": {"enabled": False}}
            elif con_extras and razonamiento:
                extra["extra_body"] = {"reasoning": {"effort": razonamiento, "exclude": True}}
            if not con_extras and not (json_mode or razonamiento):
                break
            try:
                mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
                crudo, servido = await _pedir(modelo, mensajes, cfg, max_tokens, extra, al_escribir)
                texto = _limpiar_salida(crudo)
                if not texto:
                    raise ValueError("respuesta vacía")
                return RespuestaLLM(texto=texto, modelo=servido)
            except BadRequestError as e:
                log.warning("Modelo %s rechazó la solicitud de %s: %s", modelo, agente, e)
                errores.append(f"{modelo}: parámetros")
                continue  # reintenta sin modo JSON ni razonamiento
            except Exception as e:  # noqa: BLE001 - cualquier otra falla pasa al siguiente modelo
                log.warning("Modelo %s falló para %s: %s", modelo, agente, e)
                errores.append(f"{modelo}: {type(e).__name__}")
                break
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
