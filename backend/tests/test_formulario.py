"""Formulario 210 casilla por casilla: fórmulas del instructivo, cuadre con el motor y casos de cada cédula."""

import re
from datetime import date

import pytest

from app.tax import reglas as repo_reglas
from app.tax.modelos import DatosDeclaracion, ItemPatrimonio, Liquidacion
from app.tax.motor import liquidar


def _liquidar(d: DatosDeclaracion) -> tuple[Liquidacion, dict[int, float]]:
    d.control.fecha_presentacion = d.control.fecha_presentacion or date(d.anio_gravable + 1, 7, 1)
    liq = liquidar(d, repo_reglas.cargar(d.anio_gravable))
    assert liq.formulario is not None
    c = {x.numero: x.valor for s in liq.formulario.secciones for x in s.casillas}
    return liq, c


def _asalariado(anio: int = 2025) -> DatosDeclaracion:
    d = DatosDeclaracion(anio_gravable=anio)
    d.laboral.salarios_y_pagos_laborales = 96_000_000
    d.laboral.cesantias_e_intereses = 8_000_000
    d.laboral.salario_promedio_mensual_6m = 8_000_000
    d.laboral.aportes_obligatorios_pension = d.laboral.aportes_obligatorios_salud = 3_840_000
    d.capital.rendimientos_financieros = 1_250_000
    d.deducciones.dependientes = 1
    d.deducciones.medicina_prepagada = 4_200_000
    d.deducciones.intereses_vivienda = 7_500_000
    d.deducciones.gmf_pagado = 440_000
    d.deducciones.aportes_voluntarios_afc_fpv = 2_400_000
    d.deducciones.compras_factura_electronica = 22_000_000
    d.pagos.retenciones_renta = 2_400_000
    d.pagos.declaraciones_previas = 1
    d.patrimonio.bienes = [ItemPatrimonio(concepto="Cuentas", valor=204_500_000)]
    d.patrimonio.deudas = [ItemPatrimonio(concepto="Crédito", valor=98_200_000)]
    return d


def _independiente(costos: float) -> DatosDeclaracion:
    d = DatosDeclaracion(anio_gravable=2025)
    d.independiente.honorarios_y_servicios = 150_000_000
    d.independiente.aportes_obligatorios_pension = 9_600_000
    d.independiente.aportes_obligatorios_salud = 7_500_000
    d.independiente.costos_gastos_procedentes = costos
    d.deducciones.dependientes = 2
    d.pagos.retenciones_renta = 11_000_000
    return d


def _rentista() -> DatosDeclaracion:
    d = DatosDeclaracion(anio_gravable=2024)
    d.pensiones.pensiones_nacionales = 120_000_000
    d.pensiones.aportes_salud = 14_400_000
    d.dividendos.no_gravados_subcedula1 = 80_000_000
    d.dividendos.gravados_subcedula2 = 10_000_000
    d.capital.arrendamientos = 36_000_000
    d.capital.costos_gastos_procedentes = 6_000_000
    d.ganancias_ocasionales.utilidad_venta_otros_activos = 50_000_000
    d.descuentos.donaciones = 4_000_000
    d.pagos.anticipo_anio_anterior = 1_000_000
    d.pagos.declaraciones_previas = 3
    d.pagos.impuesto_neto_anio_anterior = 3_000_000
    d.control.ultimos_dos_digitos_nit = "21"
    d.control.fecha_presentacion = date(2025, 12, 15)
    return d


CASOS = [_asalariado(), _asalariado(2023), _independiente(60_000_000), _independiente(5_000_000), _rentista()]


def _evaluar(formula: str, c: dict[int, float]) -> float:
    expr = formula.replace("(o 98)", "")
    total, signo = 0.0, 1
    for token in re.findall(r"\(|\)|[+-]|\d+", expr):
        if token in "()":
            continue
        if token == "+":
            signo = 1
        elif token == "-":
            signo = -1
        else:
            total += signo * c[int(token)]
    return max(total, 0)


@pytest.mark.parametrize("d", CASOS, ids=["asalariado", "asalariado-2023", "independiente-costos", "independiente-25", "rentista"])
def test_cada_casilla_calculada_cumple_su_formula(d):
    liq, c = _liquidar(d.model_copy(deep=True))
    for s in liq.formulario.secciones:
        for x in s.casillas:
            assert x.valor >= 0 and x.valor % 1000 == 0 or x.texto is not None, x.numero  # miles, sin negativos
            if x.tipo == "calculada" and x.formula and re.fullmatch(r"[\d\s+\-()o]+", x.formula):
                assert x.valor == _evaluar(x.formula, c), f"casilla {x.numero}: {x.formula}"


@pytest.mark.parametrize("d", CASOS, ids=["asalariado", "asalariado-2023", "independiente-costos", "independiente-25", "rentista"])
def test_el_resumen_y_el_borrador_cuadran_con_el_formulario(d):
    liq, c = _liquidar(d.model_copy(deep=True))
    r = liq.resumen
    assert (c[29], c[30], c[31]) == (r.patrimonio_bruto, r.deudas, r.patrimonio_liquido)
    assert c[111] == r.renta_liquida_gravable
    assert (c[121], c[125], c[126], c[127], c[129]) == (r.impuesto_renta, r.descuentos, r.impuesto_neto_renta, r.impuesto_ganancias_ocasionales, r.total_impuesto_cargo)
    assert (c[132], c[133], c[135]) == (r.retenciones, r.anticipo_siguiente, r.sancion)
    assert (c[136], c[137]) == (r.saldo_pagar, r.saldo_favor)
    assert liq.formulario.pago_total == c[136]
    lineas = {ln.clave: ln.valor for s in liq.secciones for ln in s.lineas}
    assert lineas["rlg_cg"] == c[97] and lineas["impuesto_neto"] == c[126] and lineas["total_cargo"] == c[129]


def test_asalariado_reparte_exentas_y_deducciones_en_sus_casillas():
    _, c = _liquidar(_asalariado())
    uvt = 49_799
    assert c[32] == 104_000_000 and c[33] == 7_680_000
    assert c[35] == 2_400_000  # AFC / pensión voluntaria
    assert c[36] == 23_900_000  # 25 % exento + cesantías exentas
    assert c[38] == 7_500_000  # intereses de vivienda
    assert c[39] == 14_820_000  # 10 % dependiente (10,4 M) + prepagada (4,2 M) + 50 % del 4x1000 (0,22 M)
    assert c[41] == 38_751_000  # limitada al 40 % del ingreso neto
    assert c[59] == 693_000  # componente inflacionario 55,43 %
    assert c[28] == 220_000 and c[139] == round(72 * uvt, -3) and c[138] == 1
    assert c[92] == c[28] + c[41] + c[139]


def test_independiente_con_costos_usa_la_seccion_43():
    liq, c = _liquidar(_independiente(60_000_000))
    assert liq.opcion_independiente == "costos"
    assert c[32] == 0 and c[43] == 150_000_000 and c[44] == 17_100_000 and c[45] == 60_000_000
    assert c[46] == 72_900_000 and c[51] == 15_000_000 and c[53] == 15_000_000  # el 10 % por dependiente va en su sección


def test_independiente_sin_costos_va_con_las_rentas_de_trabajo_y_el_25():
    liq, c = _liquidar(_independiente(5_000_000))
    assert liq.opcion_independiente == "renta_exenta_25"
    assert c[43] == 0 and c[32] == 150_000_000 and c[36] > 0


def test_pensiones_dividendos_ganancias_y_descuentos():
    _, c = _liquidar(_rentista())
    assert (c[99], c[100], c[101], c[103]) == (120_000_000, 14_400_000, 105_600_000, 0)
    assert (c[107], c[108], c[118]) == (80_000_000, 10_000_000, 3_500_000)
    assert c[111] == c[97] + c[103] + c[107] + c[108] - c[118]
    assert c[60] == 6_000_000 and c[61] == 30_000_000  # gastos del arriendo
    assert c[115] == 50_000_000 and c[127] == 7_500_000  # 15 % en 2024
    assert c[123] == 1_000_000  # 25 % de lo donado (dentro del 25 % del impuesto)
    assert c[124] > 0  # descuento por dividendos del art. 254-1
    assert c[130] == 1_000_000 and c[135] > 0 and c[136] > 0


def test_icetex_va_en_otras_deducciones_con_su_tope():
    d = _asalariado()
    d.deducciones.intereses_icetex = 9_000_000
    _, con = _liquidar(d)
    _, sin = _liquidar(_asalariado())
    assert con[39] - sin[39] == round(100 * 49_799, -3)  # máximo 100 UVT


def test_si_el_salario_no_alcanza_los_intereses_pasan_a_capital():
    d = DatosDeclaracion(anio_gravable=2025)
    d.laboral.salarios_y_pagos_laborales = 12_000_000
    d.capital.arrendamientos = 60_000_000
    d.deducciones.intereses_vivienda = 30_000_000
    _, c = _liquidar(d)
    assert c[38] + c[66] == 30_000_000 and c[66] > 0
    assert c[69] > 0


def test_donaciones_tienen_tope_del_25_por_ciento_del_impuesto():
    d = _asalariado()
    d.deducciones = type(d.deducciones)()  # sin deducciones: más impuesto
    d.descuentos.donaciones = 200_000_000
    _, c = _liquidar(d)
    assert c[123] == round(c[121] * 0.25, -3) or abs(c[123] - c[121] * 0.25) <= 1000


def test_antes_de_2023_no_se_numera():
    d = DatosDeclaracion(anio_gravable=2022)
    d.laboral.salarios_y_pagos_laborales = 80_000_000
    liq = liquidar(d, repo_reglas.cargar(2022))
    assert liq.formulario and not liq.formulario.disponible and "otra numeración" in liq.formulario.motivo
