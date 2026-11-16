"""Cuentas: el token de Supabase identifica a la persona para darle su propio cupo de IA."""

import asyncio

import httpx
import pytest

from app import cuentas
from app.config import settings


class _Respuesta:
    def __init__(self, status: int, cuerpo: dict):
        self.status_code, self._cuerpo = status, cuerpo

    def json(self):
        return self._cuerpo


@pytest.fixture
def supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "clave-publica")
    cuentas._memoria.clear()
    llamadas = []

    async def get(self, url, headers=None):
        llamadas.append(headers["Authorization"])
        return _Respuesta(200, {"id": "u-123"}) if headers["Authorization"] == "Bearer bueno" else _Respuesta(401, {})

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    return llamadas


def test_token_valido_da_el_usuario_y_se_recuerda(supabase):
    assert asyncio.run(cuentas.usuario_de("Bearer bueno")) == "u-123"
    assert asyncio.run(cuentas.usuario_de("Bearer bueno")) == "u-123"
    assert len(supabase) == 1  # la segunda vez sale de la memoria


def test_token_malo_o_sin_sesion_no_da_usuario(supabase):
    assert asyncio.run(cuentas.usuario_de("Bearer malo")) is None
    assert asyncio.run(cuentas.usuario_de(None)) is None


def test_sin_supabase_configurado_no_consulta(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    assert asyncio.run(cuentas.usuario_de("Bearer bueno")) is None


@pytest.mark.parametrize("pegada", ["https://abc.supabase.co/rest/v1/", "https://abc.supabase.co/", " https://abc.supabase.co"])
def test_la_url_de_supabase_queda_en_la_raiz(pegada):
    from app.config import _solo_dominio
    assert _solo_dominio(pegada) == "https://abc.supabase.co"
