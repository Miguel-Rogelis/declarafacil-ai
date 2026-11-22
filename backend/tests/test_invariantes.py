"""Batería de propiedades sobre miles de perfiles al azar (semilla fija, así que es reproducible).

1. Oráculo independiente: un cálculo escrito aparte, directo desde los artículos 206, 241, 336 y 387
   del ET, para perfiles comunes (empleado, empleado con honorarios, independiente). El motor y el
   oráculo deben dar la misma renta líquida gravable y el mismo impuesto.
2. Propiedades que toda declaración debe cumplir: nada negativo, valores redondeados al mil, topes
   en UVT respetados, más ingresos nunca bajan el impuesto, más deducciones nunca lo suben, la opción
   automática nunca es peor que las fijas y el resumen coincide con el formulario 210.
"""

import random

import pytest

from app.tax import reglas
from app.tax.modelos import DatosDeclaracion
from app.tax.motor import liquidar

ANIOS_2277 = [2023, 2024, 2025, 2026]  # con la Ley 2277 (40 % / 1.340 UVT, 25 % hasta 790 UVT)
TODOS = [2021, 2022, 2023, 2024, 2025, 2026]
REGLAS = {a: reglas.cargar(a) for a in TODOS}
UVT = {a: float(REGLAS[a]["uvt"]) for a in TODOS}

# Tabla del art. 241 tal como la escribe la ley (en UVT): desde, tarifa marginal, impuesto fijo
TABLA_LEY = [(0, 0.0, 0), (1090, 0.19, 0), (1700, 0.28, 116), (4100, 0.33, 788), (8670, 0.35, 2296), (18970, 0.37, 5901), (31000, 0.39, 10352)]


def tabla_ley(renta, uvt):
    x = max(renta, 0) / uvt
    desde, tarifa, fijo = max((t for t in TABLA_LEY if x >= t[0]), key=lambda t: t[0])
    return ((x - desde) * tarifa + fijo) * uvt


def pct_cesantias(promedio, uvt):
    tramos = [(350, 1.0), (410, 0.9), (470, 0.8), (530, 0.6), (590, 0.4), (650, 0.2)]
    m = promedio / uvt
    return next((p for h, p in tramos if m <= h), 0.0)


def oraculo(p, anio, dep_solo_72=False):
    """Cédula general + pensiones + dividendos para los perfiles que genera `perfil()`. Devuelve la
    renta líquida gravable total y el impuesto (antes de descuentos, sin redondeo)."""
    u = UVT[anio]
    ley_2277 = anio >= 2023
    tope_40, tope_25 = (1340, 790) if ley_2277 else (5040, 2880)
    sal, ces, prom = p["salario"], p["cesantias"], p["promedio"]
    ap_lab = p["ap_lab"]
    hon, ap_ind, costos, op = p["honorarios"], p["ap_ind"], p["costos"], p["opcion"]
    arr, costos_arr = p["arriendos"], p["costos_arriendos"]
    ing_lab = sal + ces
    neto_lab = ing_lab - ap_lab
    neto_ind = hon - ap_ind
    ingresos = ing_lab + hon + arr
    base_40 = ingresos - ap_lab - ap_ind  # num. 2 art. 336: ingresos menos no constitutivos
    rl_trab = neto_lab + (neto_ind if op == "renta_exenta_25" else 0)
    rl_43 = max(neto_ind - costos, 0) if op == "costos" else 0
    rl_cap = max(arr - costos_arr, 0)
    renta_liquida = rl_trab + rl_43 + rl_cap

    deps = p["dependientes"]
    con_relacion_laboral = ing_lab > 0
    trabajo = ing_lab + hon
    usa_387 = deps >= 1 and trabajo > 0 and not (dep_solo_72 and not con_relacion_laboral)
    dep_387 = min(0.10 * trabajo, 384 * u) if usa_387 else 0
    prepagada = min(p["prepagada"], 192 * u)
    vivienda = min(p["vivienda"], 1200 * u)
    gmf = 0.5 * p["gmf"]
    afc = min(p["afc"], 0.30 * ingresos, 3800 * u)
    ces_ex = ces * pct_cesantias(prom, u)
    # Num. 10 art. 206 (Oficio DIAN 15492 de 2025): el 25 % se calcula después de restar INCR,
    # deducciones y demás rentas exentas de las rentas de trabajo
    resto = rl_trab - ces_ex - dep_387 - prepagada - afc - vivienda - gmf
    exenta_25 = min(0.25 * max(resto, 0), tope_25 * u) if rl_trab > 0 else 0
    sujetas = ces_ex + dep_387 + prepagada + afc + vivienda + gmf + exenta_25
    limitadas = min(sujetas, 0.40 * base_40, tope_40 * u)

    if con_relacion_laboral or dep_solo_72:
        n_72 = min(deps, 4)
    else:
        n_72 = min(max(deps - 1, 0), 4)
    fuera = n_72 * 72 * u if trabajo > 0 and ley_2277 else 0  # num. 3 y 5 art. 336, desde la Ley 2277
    fuera += min(0.01 * p["compras_fe"], 240 * u) if ley_2277 else 0
    fuera = min(fuera, max(renta_liquida - limitadas, 0))
    rlg_cg = renta_liquida - limitadas - fuera

    pen_neto = max(p["pension"] - p["salud_pension"], 0)
    rlg_pen = pen_neto - min(pen_neto, 12000 * u)
    sub2 = p["div_sub2"]
    base_div = p["div_sub1"] + sub2 * 0.65
    rlg = rlg_cg + rlg_pen + base_div
    impuesto = tabla_ley(rlg, u) + 0.35 * sub2
    return rlg, impuesto


def perfil(rng, tipo):
    """Perfiles en los que la renta de trabajo alcanza para absorber todas las deducciones (así el
    oráculo no necesita repartirlas entre subcédulas)."""
    p = {"salario": 0, "cesantias": 0, "promedio": 0, "ap_lab": 0, "honorarios": 0, "ap_ind": 0, "costos": 0, "opcion": "renta_exenta_25",
             "arriendos": 0, "costos_arriendos": 0, "dependientes": 0, "prepagada": 0, "vivienda": 0, "gmf": 0, "afc": 0, "compras_fe": 0,
             "pension": 0, "salud_pension": 0, "div_sub1": 0, "div_sub2": 0}
    m = lambda a, b: rng.randrange(a, b) * 100_000
    if tipo in ("empleado", "mixto"):
        p["salario"] = m(300, 12_000)            # 30 M a 1.200 M
        p["cesantias"] = rng.choice([0, p["salario"] // 13])
        p["promedio"] = p["salario"] / 13
        p["ap_lab"] = round(p["salario"] * rng.choice([0.08, 0.09, 0.1]))
    if tipo in ("mixto", "independiente"):
        p["honorarios"] = m(200, 8_000)
        p["ap_ind"] = round(p["honorarios"] * 0.4 * 0.285)
    if tipo == "independiente_costos":
        p["honorarios"] = m(500, 8_000)
        p["ap_ind"] = round(p["honorarios"] * 0.4 * 0.285)
        p["costos"] = round(p["honorarios"] * rng.uniform(0.1, 0.5))
        p["opcion"] = "costos"
        p["salario"] = m(300, 3_000)  # con salario, para que las deducciones vayan a rentas de trabajo
        p["ap_lab"] = round(p["salario"] * 0.08)
    if rng.random() < 0.4:
        p["arriendos"] = m(50, 1_500)
        p["costos_arriendos"] = round(p["arriendos"] * rng.uniform(0, 0.3))
    p["dependientes"] = rng.choice([0, 0, 1, 1, 2, 3, 4, 5, 6])
    base = p["salario"] + p["honorarios"]
    if rng.random() < 0.5:
        p["prepagada"] = m(0, 150)
    if rng.random() < 0.4:
        p["vivienda"] = m(0, 700)
    if rng.random() < 0.6:
        p["gmf"] = m(0, 40)
    if rng.random() < 0.4:
        p["afc"] = round(base * rng.uniform(0, 0.35))
    if rng.random() < 0.4:
        p["compras_fe"] = m(0, 4_000)
    if rng.random() < 0.15:
        p["pension"] = m(200, 9_000)
        p["salud_pension"] = round(p["pension"] * 0.12)
    if rng.random() < 0.2:
        p["div_sub1"] = m(0, 2_000)
        p["div_sub2"] = m(0, 500)
    return p


def a_datos(p, anio):
    return DatosDeclaracion(
        anio_gravable=anio,
        laboral={"salarios_y_pagos_laborales": p["salario"], "cesantias_e_intereses": p["cesantias"], "salario_promedio_mensual_6m": p["promedio"],
                 "aportes_obligatorios_salud": p["ap_lab"] * 0.5, "aportes_obligatorios_pension": p["ap_lab"] * 0.5},
        independiente={"honorarios_y_servicios": p["honorarios"], "aportes_obligatorios_salud": p["ap_ind"] * 0.44, "aportes_obligatorios_pension": p["ap_ind"] * 0.56,
                       "costos_gastos_procedentes": p["costos"], "opcion": p["opcion"]},
        capital={"arrendamientos": p["arriendos"], "costos_gastos_procedentes": p["costos_arriendos"]},
        deducciones={"dependientes": p["dependientes"], "medicina_prepagada": p["prepagada"], "intereses_vivienda": p["vivienda"], "gmf_pagado": p["gmf"],
                     "aportes_voluntarios_afc_fpv": p["afc"], "compras_factura_electronica": p["compras_fe"]},
        pensiones={"pensiones_nacionales": p["pension"], "aportes_salud": p["salud_pension"]},
        dividendos={"no_gravados_subcedula1": p["div_sub1"], "gravados_subcedula2": p["div_sub2"]},
    )


class _Casillas(dict):
    def __missing__(self, numero):  # las secciones vacías no traen casillas: valen cero
        return 0.0


def casillas(liq):
    return _Casillas({c.numero: c.valor for s in liq.formulario.secciones for c in s.casillas})


def linea(liq, clave):
    return next((ln.valor for s in liq.secciones for ln in s.lineas if ln.clave == clave), 0.0)


TIPOS = ["empleado", "mixto", "independiente", "independiente_costos"]


@pytest.mark.parametrize("anio", TODOS)
@pytest.mark.parametrize("tipo", TIPOS)
def test_motor_coincide_con_el_oraculo(anio, tipo):
    rng = random.Random(f"{anio}-{tipo}")
    fallas = []
    for i in range(150):
        p = perfil(rng, tipo)
        if anio < 2023:  # antes de la Ley 2277 los dividendos tenían tabla propia: se prueban en test_motor
            p["div_sub1"] = p["div_sub2"] = 0
        liq = liquidar(a_datos(p, anio), REGLAS[anio])
        rlg_motor = linea(liq, "rlg_total")  # general + pensiones + dividendos, como la casilla 111
        # Sin salarios el motor elige la variante de dependientes más favorable; el oráculo también
        variantes = [False, True] if (p["salario"] + p["cesantias"] == 0 and p["dependientes"] >= 1) else [False]
        rlg_o, imp_o = min((oraculo(p, anio, v) for v in variantes), key=lambda x: x[1])
        imp_motor = linea(liq, "impuesto_renta")
        # Tolerancia por el redondeo al mil de cada casilla (unas 10 casillas en el camino)
        if abs(rlg_motor - rlg_o) > 10_000 or abs(imp_motor - imp_o) > 5_000:
            fallas.append((i, round(rlg_motor), round(rlg_o), round(imp_motor), round(imp_o), p))
    assert not fallas, f"{len(fallas)} perfiles no cuadran; primero: {fallas[0]}"


def _perfiles(n=120, anios=TODOS):
    rng = random.Random("propiedades")
    for i in range(n):
        anio = rng.choice(anios)
        tipo = rng.choice(TIPOS)
        yield anio, perfil(rng, tipo)


def test_nada_negativo_y_todo_redondeado_al_mil():
    # La vista casilla por casilla existe desde el AG 2023 (antes la DIAN usó otra numeración)
    for anio, p in _perfiles(anios=ANIOS_2277):
        c = casillas(liquidar(a_datos(p, anio), REGLAS[anio]))
        negativas = {k: v for k, v in c.items() if v < 0}
        sin_redondear = {k: v for k, v in c.items() if k not in (138,) and abs(v - round(v, -3)) > 0.5}
        assert not negativas, (anio, negativas)
        assert not sin_redondear, (anio, sin_redondear)


def test_topes_en_uvt_se_respetan():
    for anio, p in _perfiles():
        liq = liquidar(a_datos(p, anio), REGLAS[anio])
        cg, u = REGLAS[anio]["cedula_general"], UVT[anio]
        tol = 1000
        assert linea(liq, "exenta_25") <= cg["renta_exenta_laboral_tope_uvt"] * u + tol
        assert linea(liq, "dep_387") <= 384 * u + tol
        assert linea(liq, "dep_72") <= 4 * 72 * u + tol
        tope = min(cg["limite_rentas_exentas_deducciones_uvt"] * u, cg["limite_rentas_exentas_deducciones_pct"] * liq.resumen.ingresos_brutos_totales)
        assert linea(liq, "limite_40") <= tope + tol
        if anio >= 2023:  # casilla 92 = limitadas + adición por dependientes (139) + 1 % de factura electrónica
            c = casillas(liq)
            factura = min(p["compras_fe"] * 0.01, 240 * u)
            assert c[92] - c[139] - factura <= tope + 3 * tol, (anio, c[92], c[139], factura, tope)


def test_mas_ingresos_nunca_bajan_el_impuesto():
    for anio, p in _perfiles(80):
        antes = liquidar(a_datos(p, anio), REGLAS[anio]).resumen.impuesto_neto_renta
        q = dict(p)
        if q["salario"]:
            q["salario"] += 5_000_000
        else:
            q["honorarios"] += 5_000_000
        despues = liquidar(a_datos(q, anio), REGLAS[anio]).resumen.impuesto_neto_renta
        assert despues >= antes - 1000, (anio, antes, despues, p)


@pytest.mark.parametrize("campo", ["prepagada", "vivienda", "gmf", "afc", "compras_fe", "dependientes"])
def test_mas_deducciones_nunca_suben_el_impuesto(campo):
    for anio, p in _perfiles(60):
        antes = liquidar(a_datos(p, anio), REGLAS[anio]).resumen.impuesto_neto_renta
        q = dict(p)
        q[campo] += 1 if campo == "dependientes" else 3_000_000
        despues = liquidar(a_datos(q, anio), REGLAS[anio]).resumen.impuesto_neto_renta
        assert despues <= antes + 1000, (campo, anio, antes, despues, p)


def test_la_opcion_automatica_nunca_es_peor_que_las_fijas():
    rng = random.Random("auto")
    for _ in range(80):
        anio = rng.choice(TODOS)
        p = perfil(rng, rng.choice(["independiente", "independiente_costos"]))
        p["costos"] = round(p["honorarios"] * rng.uniform(0, 0.7))
        imp = {}
        for op in ("auto", "costos", "renta_exenta_25"):
            p["opcion"] = op
            imp[op] = liquidar(a_datos(p, anio), REGLAS[anio]).resumen.impuesto_neto_renta
        assert imp["auto"] <= min(imp["costos"], imp["renta_exenta_25"]) + 1000, (anio, imp)


def test_resumen_coincide_con_el_formulario():
    for anio, p in _perfiles(anios=ANIOS_2277):
        liq = liquidar(a_datos(p, anio), REGLAS[anio])
        c, r = casillas(liq), liq.resumen
        assert c[126] == pytest.approx(r.impuesto_neto_renta, abs=1000)
        assert c[129] == pytest.approx(r.total_impuesto_cargo, abs=1000)
        assert c[136] == pytest.approx(r.total_a_pagar, abs=1000)
        assert c[137] == pytest.approx(r.saldo_favor, abs=1000)
        assert not (c[136] > 0 and c[137] > 0)
