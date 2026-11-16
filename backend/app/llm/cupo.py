"""Cupo de uso de la IA, para que un link público no se coma las llamadas gratis del día.

- Por persona: máximo IA_POR_HORA llamadas en la última hora (la persona es su usuario si inició
  sesión o, si no, su dirección IP).
- En total: máximo IA_TOPE_DIARIO llamadas por día (hora de Colombia), un poco por debajo del
  cupo gratis de OpenRouter.
Cuando se pasa cualquiera de los dos, el agente responde sin IA (con reglas), que también funciona.
Los contadores viven en memoria: se reinician si el servidor se reinicia, y eso está bien.
"""

import os
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

POR_HORA = int(os.getenv("IA_POR_HORA", "15"))
TOPE_DIARIO = int(os.getenv("IA_TOPE_DIARIO", "45"))

_COLOMBIA = timezone(timedelta(hours=-5))

# Quién hace la solicitud y si en esta solicitud ya se negó la IA (los pone el middleware de main.py)
quien: ContextVar[str] = ContextVar("quien", default="anonimo")
sin_ia: ContextVar[bool] = ContextVar("sin_ia", default=False)  # el modo demo pide respuestas sin IA
limitado: ContextVar[bool] = ContextVar("limitado", default=False)

_por_persona: dict[str, deque[float]] = defaultdict(deque)
_dia = {"fecha": "", "usadas": 0}


def _hoy() -> str:
    return datetime.now(_COLOMBIA).date().isoformat()


def reservar() -> bool:
    """Cuenta una llamada a la IA si hay cupo. Devuelve False si no hay (y marca la solicitud como limitada)."""
    if sin_ia.get():
        return False
    ahora = time.monotonic()
    if _dia["fecha"] != _hoy():
        _dia.update(fecha=_hoy(), usadas=0)
    llamadas = _por_persona[quien.get()]
    while llamadas and ahora - llamadas[0] > 3600:
        llamadas.popleft()
    if len(llamadas) >= POR_HORA or _dia["usadas"] >= TOPE_DIARIO:
        limitado.set(True)
        return False
    llamadas.append(ahora)
    _dia["usadas"] += 1
    return True


def restante_hoy() -> int:
    return TOPE_DIARIO if _dia["fecha"] != _hoy() else max(0, TOPE_DIARIO - _dia["usadas"])


def reiniciar() -> None:
    """Para las pruebas."""
    _por_persona.clear()
    _dia.update(fecha="", usadas=0)
