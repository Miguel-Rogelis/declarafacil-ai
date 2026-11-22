"""Cuentas con Supabase (opcional): saber quién llama para darle su propio cupo de IA.

El navegador inicia sesión directo con Supabase (Google o correo) y manda su token en
«Authorization: Bearer …». Aquí solo se pregunta a Supabase de quién es ese token, con una
memoria de 10 minutos para no consultarlo en cada mensaje. Sin SUPABASE_URL todo esto se apaga.
"""

import logging
import time

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_memoria: dict[str, tuple[dict[str, str] | None, float]] = {}
_DURA = 600


def activas() -> bool:
    return bool(settings.supabase_url and settings.supabase_anon_key)


async def _quien(autorizacion: str | None) -> dict[str, str] | None:
    """{id, email} del dueño del token, o None si no hay sesión o el token no sirve."""
    if not activas() or not autorizacion or not autorizacion.lower().startswith("bearer "):
        return None
    token = autorizacion[7:].strip()
    guardado = _memoria.get(token)
    if guardado and time.monotonic() - guardado[1] < _DURA:
        return guardado[0]
    persona: dict[str, str] | None = None
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"})
        if r.status_code == 200 and r.json().get("id"):
            j = r.json()
            persona = {"id": j["id"], "email": (j.get("email") or "").lower()}
    except httpx.HTTPError as e:
        log.warning("No pude verificar la sesión con Supabase: %s", e)
        return None  # sin guardar: se reintenta en el próximo mensaje
    if len(_memoria) > 5000:
        _memoria.clear()
    _memoria[token] = (persona, time.monotonic())
    return persona


async def usuario_de(autorizacion: str | None) -> str | None:
    """El id del usuario dueño del token, o None si no hay sesión o el token no sirve."""
    p = await _quien(autorizacion)
    return p["id"] if p else None


async def correo_de(autorizacion: str | None) -> str | None:
    p = await _quien(autorizacion)
    return (p or {}).get("email") or None
