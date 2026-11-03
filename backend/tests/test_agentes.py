"""Pruebas de los agentes con la exógena ficticia (modo simulado, sin red)."""

import asyncio
import json
import os
from pathlib import Path

os.environ["LLM_MODE"] = "simulado"

from fastapi.testclient import TestClient  # noqa: E402

from app.agents import anonimizador, explicador, interprete, lector  # noqa: E402
from app.main import app  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "exogena_ficticia.xlsx"
CEDULA, NOMBRE = "1012345678", "PEREZ GOMEZ LAURA MARCELA"


def _doc():
    return lector.leer(FIXTURE.read_bytes(), FIXTURE.name)


def test_lector_lee_filas_topes_y_metadatos():
    doc = _doc()
    assert doc.anio == 2025
    assert len(doc.topes) == 5
    assert len(doc.filas) == 20
    assert doc.identificacion == CEDULA


def test_anonimizador_no_deja_datos_personales():
    anon, ultimos, n = anonimizador.anonimizar(_doc())
    texto = anon.model_dump_json()
    assert CEDULA not in texto
    for palabra in NOMBRE.split():
        assert palabra not in texto.upper()
    assert "4111111111114321" not in texto and "****4321" in texto
    assert ultimos == "78" and n > 0


def test_interprete_ubica_conceptos_y_copia_cifras_exactas():
    anon, ultimos, n = anonimizador.anonimizar(_doc())
    ext, modelo, _ = asyncio.run(interprete.interpretar(anon, ultimos, n))
    por_detalle = {f.detalle: f for f in ext.filas}
    assert por_detalle["Pagos por salarios (Concepto: 2276)"].campo == "laboral.salarios_y_pagos_laborales"
    assert por_detalle["Intereses pagados en créditos de vivienda (Concepto: 1315)"].campo == "deducciones.intereses_vivienda"
    assert por_detalle["Activos aportes parafiscales, salud, pensión y cesantías (Concepto: 2214)"].tratamiento == "revisar"
    bonos = por_detalle["Valor de los bonos de alimentación entregados (Concepto: 2276)"]
    assert bonos.tratamiento == "informativo" and "387-1" in bonos.explicacion  # salario < 310 UVT y bonos < 41 UVT al mes: no son ingreso
    parafiscales = por_detalle["Activos aportes parafiscales, salud, pensión y cesantías (Concepto: 2214)"]
    assert "¿La dejo por fuera?" in parafiscales.pregunta and [o.recomendada for o in parafiscales.opciones] == [True, False]
    # Cada cifra del resultado es la suma exacta de sus filas de origen
    assert ext.resumen_campos["laboral.salarios_y_pagos_laborales"] == 96_000_000
    assert ext.resumen_campos["patrimonio.deudas"] == 98_200_000
    assert ext.perfil.empleado and ext.perfil.declaro_antes
    assert modelo is None  # modo simulado: no se llamó a ningún modelo


def test_explicador_detecta_cifras_inventadas():
    permitidas = {1_000_000, 250_000}
    assert explicador.verificar_cifras("Pagas $1.000.000 y te retuvieron $250.000.", permitidas) == []
    assert explicador.verificar_cifras("Pagas $1.234.567 en total.", permitidas) == ["$1.234.567"]


def _sse(texto: str) -> list[tuple[str, dict]]:
    eventos, tipo = [], None
    for linea in texto.splitlines():
        if linea.startswith("event:"):
            tipo = linea.split(":", 1)[1].strip()
        elif linea.startswith("data:"):
            eventos.append((tipo, json.loads(linea.split(":", 1)[1])))
    return eventos


def test_flujo_completo_por_api():
    cliente = TestClient(app)
    with FIXTURE.open("rb") as f:
        r = cliente.post("/api/documentos/analizar", files={"archivo": ("exogena.xlsx", f)}, data={"anio_gravable": "2025"})
    assert r.status_code == 200
    eventos = _sse(r.text)
    agentes = [d["agente"] for t, d in eventos if t == "agente" and d["estado"] != "inicio"]
    assert agentes == ["lector", "anonimizador", "clasificador", "interprete"]
    extraccion = next(d for t, d in eventos if t == "resultado")["extraccion"]
    assert CEDULA not in json.dumps(extraccion)

    solicitud = {
        "anio_gravable": 2025,
        "filas": extraccion["filas"],
        "topes": extraccion["topes"],
        "ultimos_dos_digitos_nit": extraccion["ultimos_dos_digitos_nit"],
        "respuestas": {"dependientes": 1, "declaraciones_previas": 2, "fecha_presentacion": "2026-10-01"},
    }
    r = cliente.post("/api/declaracion/liquidar", json=solicitud)
    eventos = _sse(r.text)
    agentes = [d["agente"] for t, d in eventos if t == "agente" and d["estado"] != "inicio"]
    assert agentes == ["motor", "auditor", "explicador"]
    res = next(d for t, d in eventos if t == "resultado")
    liq = res["liquidacion"]
    assert liq["obligacion"]["obligado"] is True
    assert liq["vencimiento"]["fecha"] == "2026-10-08"
    assert liq["resumen"]["sancion"] == 0
    assert res["explicacion"]


def test_archivo_que_no_es_exogena():
    r = TestClient(app).post("/api/documentos/analizar", files={"archivo": ("nota.txt", b"hola")})
    assert any(t == "error" for t, _ in _sse(r.text))


def test_asistente_responde_desde_la_base():
    r = TestClient(app).post("/api/chat", json={"mensaje": "¿Cómo descargo mi exógena?"})
    assert r.status_code == 200
    assert "MUISCA" in r.json()["respuesta"]


def test_reglas_y_agentes_se_pueden_consultar():
    c = TestClient(app)
    assert {a["anio_gravable"] for a in c.get("/api/reglas").json()} >= {2025, 2026}
    assert c.get("/api/reglas/2025").json()["uvt"] == 49799
    assert "interprete" in c.get("/api/agentes").json()
