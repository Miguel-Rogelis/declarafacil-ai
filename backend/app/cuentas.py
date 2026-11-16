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

_memoria: dict[str, tuple[str | None, float]] = {}
_DURA = 600


def activas() -> bool:
    return bool(settings.supabase_url and settings.supabase_anon_key)


async def usuario_de(autorizacion: str | None) -> str | None:
    """El id del usuario dueño del token, o None si no hay sesión o el token no sirve."""
    if not activas() or not autorizacion or not autorizacion.lower().startswith("bearer "):
        return None
    token = autorizacion[7:].strip()
    guardado = _memoria.get(token)
    if guardado and time.monotonic() - guardado[1] < _DURA:
        return guardado[0]
    usuario: str | None = None
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            usuario = r.json().get("id")
    except httpx.HTTPError as e:
        log.warning("No pude verificar la sesión con Supabase: %s", e)
        return None  # sin guardar: se reintenta en el próximo mensaje
    if len(_memoria) > 5000:
        _memoria.clear()
    _memoria[token] = (usuario, time.monotonic())
    return usuario
