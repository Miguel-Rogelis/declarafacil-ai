"""Reglas confirmadas con una declaración real presentada (AG 2025): asalariada con dos dependientes,
crédito de vivienda, rendimientos y compras con factura electrónica. Su exógena pasó por todo el flujo
(lector → intérprete → chat → motor) y el formulario 210 quedó igual al PDF presentado en las 115 casillas.

Los datos reales no están en el repo. Aquí van cifras ficticias que pasan por los mismos caminos:
- el 10 % del art. 387 sale de los ingresos BRUTOS de trabajo, y la asalariada toma además 72 UVT por cada dependiente;
- el 25 % exento se calcula después de las deducciones, sin restar las 72 UVT ni el 1 % de facturas;
- la casilla 92 suma 28 + 41 + 53 + 69 + 86 + 139;
- la casilla 41 sale de las casillas ya aproximadas (37 + 40), como en MUISCA, no de aproximar la suma sin redondear;
- restar el componente inflacionario (casilla 59) es opcional: la declaración presentada lo dejó en cero.
"""

import math
import os
import random

import pytest

os.environ["LLM_MODE"] = "simulado"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.orquestador import Respuestas, SolicitudLiquidacion, construir_declaracion  # noqa: E402
from app.tax import reglas  # noqa: E402
from app.tax.motor import liquidar  # noqa: E402
from tests.test_invariantes import REGLAS, a_datos, perfil  # noqa: E402

UVT = 49_799


def r(v: float) -> float:
    return math.floor(max(v, 0) / 1000 + 0.5) * 1000


def casillas(liq):
    return {x.numero: x.valor for s in liq.formulario.secciones for x in s.casillas}


def _asalariada(**extra):
    d = construir_declaracion(SolicitudLiquidacion(anio_gravable=2025, respuestas=Respuestas(dependientes=2, intereses_vivienda=3_007_420, **extra)))
    d.laboral.salarios_y_pagos_laborales = 60_000_000
    d.laboral.aportes_obligatorios_pension = 2_700_000
    d.laboral.aportes_obligatorios_salud = 2_400_000
    return d


def test_asalariada_con_dependientes_y_vivienda_como_muisca():
    c = casillas(liquidar(_asalariada(), reglas.cargar(2025)))
    assert (c[32], c[33], c[34]) == (60_000_000, 5_100_000, 54_900_000)
    assert c[39] == r(0.10 * 60_000_000)  # 10 % de los ingresos brutos, no de la renta líquida
    assert c[38] == 3_007_000 and c[40] == c[38] + c[39]
    assert c[36] == r(0.25 * (54_900_000 - 6_000_000 - 3_007_420)) == 11_473_000  # después de deducciones
    # Sin redondear, exentas + deducciones = 20.480.565 → 20.481.000; MUISCA suma las casillas: 11.473.000 + 9.007.000
    assert c[41] == c[37] + c[40] == 20_480_000
    assert c[42] == c[34] - c[41]
    assert c[139] == r(2 * 72 * UVT) == 7_171_000  # 72 UVT por cada uno, también por el que da el 10 %
    assert c[92] == c[28] + c[41] + c[53] + c[69] + c[86] + c[139]
    assert c[93] == c[91] - c[92] and c[111] == c[97] == c[93]


def test_el_1_por_ciento_de_facturas_va_en_la_92_y_no_baja_el_25():
    sin = casillas(liquidar(_asalariada(), reglas.cargar(2025)))
    con = casillas(liquidar(_asalariada(compras_factura_electronica=15_114_022), reglas.cargar(2025)))
    assert con[28] == r(0.01 * 15_114_022) == 151_000
    assert con[36] == sin[36] and con[41] == sin[41]  # el 1 % no reduce la base del 25 % ni entra al límite del 40 %
    assert con[92] == sin[92] + 151_000


def test_componente_inflacionario_es_opcional():
    reg = reglas.cargar(2025)
    restando = liquidar(_asalariada(rendimientos_financieros=129_000), reg)
    sin_restar = liquidar(_asalariada(rendimientos_financieros=129_000, restar_componente_inflacionario=False), reg)
    a, b = casillas(restando), casillas(sin_restar)
    assert a[58] == b[58] == 129_000
    assert a[59] == r(129_000 * 0.5543) == 72_000 and b[59] == 0
    assert b[61] == b[70] == b[73] == 129_000 and b[91] == a[91] + 72_000
    nota = next(x.nota for s in sin_restar.formulario.secciones for x in s.casillas if x.numero == 59)
    assert "Podrías restar $72.000" in nota and "55,43 %" in nota
    nota_a = next(x.nota for s in restando.formulario.secciones for x in s.casillas if x.numero == 59)
    assert nota_a.endswith("2025).")  # antes quedaba «2025),» por reemplazar todos los puntos


@pytest.mark.parametrize(
    ("mensaje", "esperado"),
    [("no restes el componente inflacionario, déjalo como la sugerida", False),
     ("no quiero restar el componente inflacionario", False),
     ("deja el componente inflacionario en cero", False),
     ("mejor sí réstalo, el componente inflacionario", True),
     ("no sé si restar el componente inflacionario, qué me conviene?", True)],  # duda: no cambia lo que había (restar)
)
def test_el_chat_entiende_si_restar_el_componente(mensaje, esperado):
    c = TestClient(app)
    estado = {"anio_gravable": 2025, "respuestas": {"rendimientos_financieros": 129_000}}
    j = c.post("/api/chat", json={"mensaje": mensaje, "historial": [], "estado": estado}).json()
    assert j["respuestas"]["restar_componente_inflacionario"] is esperado


def test_limitadas_salen_de_las_casillas_aproximadas():
    """En perfiles al azar, 41, 53, 69 y 86 son lo que calcula MUISCA con las casillas ya aproximadas:
    exentas + deducciones de la subcédula, sin pasar del cupo del 40 % (o 1.340 UVT) ni de su renta líquida."""
    rng = random.Random(210)
    for _ in range(600):
        anio = rng.choice([2023, 2024, 2025, 2026])
        d = a_datos(perfil(rng, rng.choice(["empleado", "empleado_honorarios", "independiente_25", "independiente_costos"])), anio)
        d.capital.rendimientos_financieros = rng.choice([0, rng.uniform(0, 30e6)])
        d.capital.restar_componente_inflacionario = rng.random() < 0.7
        d.no_laborales.ingresos = rng.choice([0, rng.uniform(0, 20e6)])
        d.deducciones.intereses_vivienda = rng.choice([0, rng.uniform(0, 40e6)])
        c = casillas(liquidar(d, REGLAS[anio]))
        cg = REGLAS[anio]["cedula_general"]
        base = (c[32] - c[33]) + (c[43] - c[44]) + (c[58] - c[59]) + (c[74] - c[75] - c[76])
        cupo = r(min(base * cg["limite_rentas_exentas_deducciones_pct"], cg["limite_rentas_exentas_deducciones_uvt"] * REGLAS[anio]["uvt"]))
        for exe, ded, lim, rl in ((37, 40, 41, c[34]), (49, 52, 53, c[46]), (65, 68, 69, c[61] + c[62]), (82, 85, 86, c[78] + c[79])):
            esperado = min(c[exe] + c[ded], cupo, max(rl, 0))
            cupo -= esperado
            assert c[lim] == esperado, (anio, lim, c[lim], esperado)
