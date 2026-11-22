"""Operación: reglas y agentes que persisten con historial (HU-36), administradores con autor (RG-08),
cupo que sobrevive a un reinicio (RG-07), métricas sin datos personales y KPI (HU-41), caché y costo de
la IA (HU-40) y proveedores sin retención de datos (RG-01)."""

import asyncio
import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import almacen, cuentas, kpis, metricas
from app.agents import configuracion
from app.config import settings
from app.llm import cliente, cupo
from app.main import app
from app.tax import reglas as repo_reglas

DEMO = settings.data_dir / "demo"


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    almacen.reiniciar()
    cupo.reiniciar()
    cliente.reiniciar_cache()
    monkeypatch.setattr(settings, "admin_token", "secreto")
    monkeypatch.setattr(settings, "admin_emails", [])
    yield
    almacen.reiniciar()


ADMIN = {"x-admin-token": "secreto"}


# ---------- HU-36: reglas y agentes persistentes, con historial y reversión ----------


def test_reglas_editadas_sobreviven_a_un_reinicio_y_se_pueden_revertir(tmp_path):
    almacen.reiniciar(almacen._Archivo(tmp_path))
    c = TestClient(app)
    reglas = c.get("/api/reglas/2025").json()
    reglas["topes_obligacion_uvt"]["ingresos_brutos"] = 1500
    assert c.put("/api/reglas/2025", json=reglas).status_code == 401  # sin clave no se edita
    r = c.put("/api/reglas/2025", json=reglas, headers=ADMIN)
    assert r.status_code == 200 and r.json()["topes_obligacion_uvt"]["ingresos_brutos"] == 1500

    almacen.reiniciar(almacen._Archivo(tmp_path))  # «reinicio»: el almacén se vuelve a leer del disco
    assert repo_reglas.cargar(2025)["topes_obligacion_uvt"]["ingresos_brutos"] == 1500
    historial = c.get("/api/reglas/2025/historial", headers=ADMIN).json()
    assert historial[0]["autor"] == "clave de administrador"

    r = c.post("/api/reglas/2025/revertir", json={"version": None}, headers=ADMIN)
    assert r.status_code == 200 and repo_reglas.cargar(2025)["topes_obligacion_uvt"]["ingresos_brutos"] == 1400
    r = c.post("/api/reglas/2025/revertir", json={"version": historial[0]["id"]}, headers=ADMIN)
    assert repo_reglas.cargar(2025)["topes_obligacion_uvt"]["ingresos_brutos"] == 1500
    assert len(c.get("/api/reglas/2025/historial", headers=ADMIN).json()) == 3


def test_agentes_editados_persisten_y_se_revierten():
    c = TestClient(app)
    r = c.put("/api/agentes/asistente", json={"modelos": ["modelo/uno:free"]}, headers=ADMIN)
    assert r.status_code == 200 and configuracion.obtener("asistente")["modelos"] == ["modelo/uno:free"]
    assert c.post("/api/agentes/revertir", json={"version": None}, headers=ADMIN).status_code == 200
    assert configuracion.obtener("asistente")["modelos"] != ["modelo/uno:free"]
    assert len(c.get("/api/agentes/historial", headers=ADMIN).json()) == 2


# ---------- RG-08: administradores por correo, con autor en el historial ----------


def test_administrador_por_correo_queda_como_autor(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["miguel@ejemplo.co"])

    async def correo(autorizacion):
        return {"Bearer bueno": "miguel@ejemplo.co", "Bearer otro": "intruso@ejemplo.co"}.get(autorizacion)

    monkeypatch.setattr(cuentas, "correo_de", correo)
    c = TestClient(app)
    assert c.put("/api/agentes/explicador", json={"temperatura": 0.2}, headers={"authorization": "Bearer otro"}).status_code == 401
    assert c.put("/api/agentes/explicador", json={"temperatura": 0.2}, headers={"authorization": "Bearer bueno"}).status_code == 200
    assert c.get("/api/agentes/historial", headers=ADMIN).json()[0]["autor"] == "miguel@ejemplo.co"


# ---------- RG-07: el cupo de IA sobrevive a un reinicio ----------


def test_cupo_del_dia_se_recupera_del_almacen():
    cupo._estado["guardado"] = 0
    for _ in range(3):
        assert cupo.reservar()
    cupo._guardar(forzar=True)
    usadas = cupo._dia["usadas"]
    cupo._por_persona.clear()
    cupo._dia.update(fecha="", usadas=0)
    cupo._estado["cargado"] = False  # como si el servidor arrancara de nuevo
    cupo.reservar()
    assert cupo._dia["usadas"] == usadas + 1
    guardado = almacen.obtener().leer("cupo:estado")
    assert all(len(h) == 16 for h in guardado["personas"])  # solo huellas, nunca la IP


# ---------- HU-41: métricas sin datos personales y KPI ----------


def _sse(texto):
    evs, ev = [], None
    for linea in texto.splitlines():
        if linea.startswith("event:"):
            ev = linea[6:].strip()
        elif linea.startswith("data:"):
            evs.append((ev, json.loads(linea[5:].strip())))
    return evs


def _sesion_completa(c: TestClient, sesion: str) -> None:
    h = {"x-sesion": sesion}
    archivos = [("archivos", (n, (DEMO / n).read_bytes())) for n in ("exogena_demo_2025.xlsx", "certificado_220_demo_2025.pdf", "certificado_banco_demo_2025.pdf")]
    r = c.post("/api/documentos/analizar", files=archivos, data={"anio_gravable": "2025"}, headers=h)
    ext = _sse(r.text)[-1][1]["extraccion"]
    sol = {"anio_gravable": 2025, "filas": ext["filas"], "topes": ext["topes"], "ultimos_dos_digitos_nit": ext["ultimos_dos_digitos_nit"]}
    assert _sse(c.post("/api/declaracion/liquidar", json=sol, headers=h).text)[-1][0] == "resultado"
    for m in ("mi cédula es 1012345678 y mi correo laura@correo.com", "¿cuándo vence?", "calcula"):
        assert c.post("/api/chat", json={"mensaje": m}, headers=h).status_code == 200


def test_eventos_no_llevan_datos_personales_ni_montos():
    c = TestClient(app)
    _sesion_completa(c, "abc12345-0000-4000-8000-000000000001")
    eventos = almacen.obtener().eventos()
    assert {e["tipo"] for e in eventos} >= {"documentos", "liquidacion", "chat", "http"}
    for e in eventos:
        permitidos = set(metricas.ESQUEMA[e["tipo"]]) | {"tipo", "sesion", "creado"}
        assert set(e) <= permitidos, e
        texto = json.dumps({k: v for k, v in e.items() if k not in ("creado", "sesion")}, ensure_ascii=False)
        assert "1012345678" not in texto and "laura" not in texto.lower()
        assert not re.search(r"\d{6,}(?!\.\d)", texto.replace(".", "")) or e["tipo"] in ("liquidacion", "documentos", "chat", "http", "ia")
        for v in e.values():
            assert not isinstance(v, str) or len(v) <= 80


def test_kpi_desde_una_sesion_real_y_csv():
    c = TestClient(app)
    for i in range(5):
        _sesion_completa(c, f"abc12345-0000-4000-8000-00000000001{i}")
    r = c.get("/api/metricas?dias=7", headers=ADMIN)
    assert r.status_code == 200
    datos = r.json()
    k = {x["id"]: x for x in datos["kpis"]}
    assert datos["sesiones"] == 5 and datos["sesiones_con_borrador"] == 5
    assert k["KPI-02"]["valor"] == 0 and k["KPI-02"]["estado"] == "cumple"  # ninguna casilla sin origen
    assert k["KPI-07"]["valor"] == 100 and k["KPI-07"]["estado"] == "cumple"
    assert k["KPI-04"]["estado"] == "cumple"  # chat sin IA en menos de 0,1 s
    assert k["KPI-14"]["estado"] == "sin_datos" and k["KPI-14"]["fuente"] == "piloto"
    assert c.get("/api/metricas", headers={}).status_code == 401
    csv = c.get("/api/metricas/eventos.csv", headers=ADMIN).text
    assert csv.startswith("creado,sesion,tipo") and "liquidacion" in csv


def test_kpi_manual_del_piloto():
    c = TestClient(app)
    assert c.put("/api/metricas/manuales/KPI-16", json={"valor": 72.5, "n": 12, "nota": "Piloto B"}, headers=ADMIN).status_code == 200
    assert c.put("/api/metricas/manuales/KPI-02", json={"valor": 0, "n": 1}, headers=ADMIN).status_code == 404  # los del sistema no se escriben a mano
    k = {x["id"]: x for x in c.get("/api/metricas", headers=ADMIN).json()["kpis"]}
    assert k["KPI-16"]["valor"] == 72.5 and k["KPI-16"]["estado"] == "cumple"


def _ev(tipo, sesion="s1", creado="2026-11-22T10:00:00+00:00", **campos):
    return {"tipo": tipo, "sesion": sesion, "creado": creado, **campos}


def test_calculo_de_kpi_con_eventos_sinteticos():
    eventos = []
    for i in range(10):
        s = f"s{i}"
        eventos.append(_ev("documentos", s, "2026-11-22T10:00:00+00:00", n=1, n_ok=1, ms=800 + i, asalariado=i < 5, independiente=i >= 5))
        if i < 8:  # 8 de 10 llegan al borrador
            eventos.append(_ev("liquidacion", s, "2026-11-22T10:12:00+00:00", ms=10, casillas_sin_origen=0, asalariado=i < 5, independiente=i >= 5))
        eventos.append(_ev("chat", s, ms=2000 + 100 * i, ia_intento=True, con_ia=i != 0, descartada=i == 0, tokens_entrada=4000))
        eventos.append(_ev("ia", s, agente="asistente", resultado="ok", costo_usd=0.02))
    k = {x["id"]: x for x in kpis.calcular(eventos)["kpis"]}
    assert k["KPI-01"]["valor"] == pytest.approx(10.0) and k["KPI-01"]["estado"] == "cumple"
    assert k["KPI-06"]["valor"] == pytest.approx(12.0)
    assert k["KPI-07"]["valor"] == pytest.approx(80.0) and k["KPI-07"]["estado"] == "cumple"
    assert k["KPI-09"]["valor"] == pytest.approx(0.02 * 8 / 8) and k["KPI-09"]["estado"] == "cumple"
    assert k["KPI-12"]["valor"] == 4000 and k["KPI-12"]["estado"] == "cumple"
    assert k["KPI-13"]["valor"] == pytest.approx(40.0)  # asalariados 100 %, independientes 60 %
    assert k["KPI-13"]["estado"] == "no_cumple"


def test_esquema_descarta_lo_que_no_esta_permitido():
    e = metricas.registrar("chat", ms=12, con_ia=True, mensaje="mi cédula es 1012345678", valor=5_000_000)
    assert "mensaje" not in e and "valor" not in e and e["ms"] == 12
    assert metricas.registrar("inventado", x=1) is None


# ---------- HU-40 y RG-01: caché, costo y proveedores sin retención ----------


class _Falso:
    def __init__(self):
        self.llamadas = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, model, messages, **kw):
        self.llamadas.append({"model": model, **kw})
        uso = SimpleNamespace(prompt_tokens=1000, completion_tokens=200)
        return SimpleNamespace(model=model, usage=uso, choices=[SimpleNamespace(message=SimpleNamespace(content='{"tipo": "certificado_220"}'))])


def _con_ia(monkeypatch, falso):
    monkeypatch.setattr(settings, "llm_mode", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-prueba")
    monkeypatch.setattr(cliente, "_get_cliente", lambda: falso)


def test_cache_evita_repetir_llamadas_identicas_y_no_gasta_cupo(monkeypatch):
    falso = _Falso()
    _con_ia(monkeypatch, falso)
    r1 = asyncio.run(cliente.completar("clasificador", "sistema", "títulos del documento", json_mode=True))
    usadas = cupo._dia["usadas"]
    r2 = asyncio.run(cliente.completar("clasificador", "sistema", "títulos del documento", json_mode=True))
    assert len(falso.llamadas) == 1 and r2.desde_cache and r2.texto == r1.texto
    assert cupo._dia["usadas"] == usadas
    tipos = [e["resultado"] for e in almacen.obtener().eventos() if e["tipo"] == "ia"]
    assert tipos == ["ok", "cache"]
    # El chat no se guarda en caché: cada turno depende de la conversación
    asyncio.run(cliente.completar("asistente", "s", "u"))
    asyncio.run(cliente.completar("asistente", "s", "u"))
    assert len(falso.llamadas) == 3


def test_costo_por_tokens_con_el_perfil_de_pago_y_sin_retencion(monkeypatch):
    monkeypatch.setattr(settings, "perfil_modelos", "pago")
    falso = _Falso()
    _con_ia(monkeypatch, falso)
    r = asyncio.run(cliente.completar("explicador", "s", "datos del cálculo"))
    assert falso.llamadas[0]["model"] == "anthropic/claude-haiku-4.5"
    assert r.tokens_entrada == 1000 and r.tokens_salida == 200
    assert r.costo_usd == pytest.approx((1000 * 1.0 + 200 * 5.0) / 1_000_000)
    assert falso.llamadas[0]["extra_body"]["provider"] == {"data_collection": "deny"}


def test_modelos_gratis_no_cuestan():
    assert cliente.costo("nvidia/nemotron-3.5-lightning:free", 10_000, 10_000) == 0
    assert cliente.costo("openrouter/free", 10_000, 10_000) == 0


def test_metricas_se_borran_al_cumplir_un_anio(tmp_path):
    a = almacen.reiniciar(almacen._Archivo(tmp_path))
    a.agregar_eventos([
        {"tipo": "http", "sesion": "s1", "creado": "2020-01-01T00:00:00+00:00"},
        {"tipo": "http", "sesion": "s2", "creado": "2099-01-01T00:00:00+00:00"},
    ])
    # La purga automática corre con el primer evento del día: el viejo ya no está, ni en el archivo.
    assert [e["sesion"] for e in a.eventos()] == ["s2"]
    assert [e["sesion"] for e in almacen._Archivo(tmp_path).eventos()] == ["s2"]
