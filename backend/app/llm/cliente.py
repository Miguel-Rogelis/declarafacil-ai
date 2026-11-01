"""Cliente de modelos vía OpenRouter (API compatible con OpenAI).

- Prueba los modelos configurados para cada agente en orden; si uno falla
  (límite de uso, modelo retirado, caída), pasa al siguiente.
- En modo "simulado" no hace llamadas: cada agente usa su ruta sin IA.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.agents import configuracion
from app.config import settings

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
            timeout=45,
            max_retries=0,
            default_headers={"HTTP-Referer": settings.app_url, "X-Title": "DeclaraFacil AI"},
        )
    return _cliente


def disponible() -> bool:
    return settings.modo_llm == "openrouter" and bool(settings.openrouter_api_key)


async def completar(agente: str, sistema: str, usuario: str, json_mode: bool = False, max_tokens: int = 1200) -> RespuestaLLM:
    if not disponible():
        raise LLMNoDisponible("Modo simulado: sin llamadas a modelos")
    cfg = configuracion.obtener(agente)
    if not cfg.get("activo", True):
        raise LLMNoDisponible(f"El agente {agente} está desactivado")
    errores = []
    for modelo in cfg.get("modelos", []):
        try:
            extra: dict[str, Any] = {}
            if json_mode:
                extra["response_format"] = {"type": "json_object"}
            r = await _get_cliente().chat.completions.create(
                model=modelo,
                messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                temperature=cfg.get("temperatura", 0),
                max_tokens=max_tokens,
                **extra,
            )
            texto = (r.choices[0].message.content or "").strip()
            if not texto:
                raise ValueError("respuesta vacía")
            return RespuestaLLM(texto=texto, modelo=getattr(r, "model", None) or modelo)
        except Exception as e:  # noqa: BLE001 - cualquier falla pasa al siguiente modelo
            log.warning("Modelo %s falló para %s: %s", modelo, agente, e)
            errores.append(f"{modelo}: {type(e).__name__}")
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
