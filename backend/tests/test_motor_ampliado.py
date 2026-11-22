"""HU-39: rentas del exterior, ECE, compensación de pérdidas y renta por comparación patrimonial.

Cada caso revisa la casilla del 210, el cuadre con el resumen y que ninguna casilla con valor
quede sin origen (KPI-02).
"""

from datetime import date

import pytest

from app.orquestador import casillas_sin_origen
from app.tax import reglas as repo_reglas
from app.tax.modelos import DatosDeclaracion, ItemPatrimonio, Liquidacion
from app.tax.motor import liquidar


def _liq(d: DatosDeclaracion) -> tuple[Liquidacion, dict[int, float]]:
    d.control.fecha_presentacion = d.control.fecha_presentacion or date(d.anio_gravable + 1, 7, 1)
    liq = liquidar(d, repo_reglas.cargar(d.anio_gravable))
    c = {x.numero: x.valor for s in liq.formulario.secciones for x in s.casillas} if liq.formulario and liq.formulario.disponible else {}
    if c:
        assert liq.resumen.total_impuesto_cargo == c[129] and liq.resumen.impuesto_neto_renta == c[126]
        assert liq.resumen.saldo_pagar == c[136] and liq.resumen.saldo_favor == c[137]
        assert casillas_sin_origen(liq) == [], casillas_sin_origen(liq)
    return liq, c


def _base(anio: int = 2025) -> DatosDeclaracion:
    d = DatosDeclaracion(anio_gravable=anio)
    d.laboral.salarios_y_pagos_laborales = 72_000_000
    d.laboral.aportes_obligatorios_pension = d.laboral.aportes_obligatorios_salud = 2_880_000
    d.pagos.declaraciones_previas = 2
    return d


def _titulos(liq: Liquidacion) -> list[str]:
    return [a.titulo for a in liq.alertas]


# ---------- Compensación de pérdidas (arts. 147 y 330 ET) ----------


def test_perdida_de_capital_se_compensa_solo_contra_capital():
    d = _base()
    d.capital.arrendamientos = 30_000_000
    d.capital.costos_gastos_procedentes = 5_000_000
    sin, c0 = _liq(d.model_copy(deep=True))
    d.perdidas.capital = 10_000_000
    con, c = _liq(d)
    assert c[72] == 10_000_000 and c[73] == c[70] - 10_000_000
    assert c[97] == c0[97] - 10_000_000
    assert con.resumen.impuesto_neto_renta < sin.resumen.impuesto_neto_renta


def test_perdida_mayor_que_la_renta_se_limita_y_avisa():
    d = _base()
    d.capital.arrendamientos = 12_000_000
    d.perdidas.capital = 100_000_000
    liq, c = _liq(d)
    assert c[72] == c[70] and c[73] == 0
    assert "Pérdidas que quedan para otros años" in _titulos(liq)


def test_perdidas_de_2018_van_en_la_casilla_94():
    d = _base()
    d.perdidas.anios_2018_y_anteriores = 3_000_000
    liq, c = _liq(d)
    assert c[94] == 3_000_000 and c[97] == c[93] - 3_000_000


def test_costos_mayores_que_los_ingresos_dejan_una_perdida_del_ejercicio():
    d = _base()
    d.capital.arrendamientos = 10_000_000
    d.capital.costos_gastos_procedentes = 15_000_000
    liq, c = _liq(d)
    assert c[61] == 0 and c[71] == 5_000_000
    assert "Pérdida en rentas de capital" in _titulos(liq)


# ---------- Renta por comparación patrimonial (arts. 236 a 239 ET) ----------


def _con_patrimonio(anterior: float | None, causas: float = 0) -> DatosDeclaracion:
    d = _base()
    d.patrimonio.bienes = [ItemPatrimonio(concepto="Apartamento", valor=300_000_000)]
    d.comparacion.patrimonio_liquido_anterior = anterior
    d.comparacion.causas_justificativas = causas
    return d


def test_aumento_de_patrimonio_sin_justificar_se_vuelve_renta_gravable():
    liq, c = _liq(_con_patrimonio(100_000_000))
    assert c[96] > 0 and c[97] == c[93] + c[96]
    sec = next(s for s in liq.secciones if s.id == "comparacion_patrimonial")
    lineas = {ln.clave: ln.valor for ln in sec.lineas}
    assert lineas["pl_incremento"] == 200_000_000
    assert lineas["pl_renta"] == c[96] == pytest.approx(lineas["pl_incremento"] - lineas["pl_justificado"], abs=1000)
    assert "Renta por comparación patrimonial" in _titulos(liq)
    sin, _ = _liq(_base())
    assert liq.resumen.impuesto_neto_renta > sin.resumen.impuesto_neto_renta


def test_causas_justificativas_desvirtuan_la_comparacion():
    liq, c = _liq(_con_patrimonio(100_000_000, causas=200_000_000))
    assert c[96] == 0 and "Renta por comparación patrimonial" not in _titulos(liq)


def test_sin_patrimonio_anterior_no_se_compara_y_al_primerizo_se_le_avisa():
    d = _con_patrimonio(None)
    d.pagos.declaraciones_previas = 0
    liq, c = _liq(d)
    assert c[96] == 0
    assert "Primera declaración: tu patrimonio frente a tus rentas" in _titulos(liq)


# ---------- Rentas del exterior ----------


def test_salario_del_exterior_suma_en_trabajo_y_descuenta_lo_pagado_afuera():
    d = _base()
    d.exterior.salarios = 100_000_000
    d.exterior.impuesto_pagado_renta = 5_000_000
    liq, c = _liq(d)
    assert c[32] == 172_000_000
    assert c[122] == 5_000_000 and c[125] >= 5_000_000
    sin_desc = d.model_copy(deep=True)
    sin_desc.exterior.impuesto_pagado_renta = 0
    liq2, c2 = _liq(sin_desc)
    assert c[126] == c2[126] - 5_000_000


def test_descuento_del_exterior_no_pasa_del_impuesto_colombiano_de_esas_rentas():
    d = _base()
    d.exterior.rentas_capital = 20_000_000
    d.exterior.impuesto_pagado_renta = 50_000_000  # más de lo que cobra Colombia por esa renta
    liq, c = _liq(d)
    assert 0 < c[122] < 50_000_000
    assert "Descuento por impuestos del exterior limitado" in _titulos(liq)


def test_dividendos_del_exterior_van_aparte_con_la_tarifa_del_240():
    d = _base()
    d.exterior.dividendos = 50_000_000
    d.exterior.dividendos_exentos = 10_000_000
    liq, c = _liq(d)
    assert c[109] == 50_000_000 and c[110] == 10_000_000
    assert c[120] == 14_000_000  # 35 % de 40 millones
    assert c[121] == c[116] + c[117] + c[118] + c[119] + c[120]


def test_pension_del_exterior_exenta_desde_2023_y_no_antes():
    d = _base(2025)
    d.laboral.salarios_y_pagos_laborales = 0
    d.laboral.aportes_obligatorios_pension = d.laboral.aportes_obligatorios_salud = 0
    d.exterior.pensiones = 60_000_000
    liq, c = _liq(d)
    assert c[99] == 60_000_000 and c[102] == 60_000_000 and c[103] == 0
    d.anio_gravable = 2022
    viejo = liquidar(d, repo_reglas.cargar(2022))
    assert "Pensión del exterior sin exención" in [a.titulo for a in viejo.alertas]


def test_ganancia_ocasional_del_exterior_y_su_descuento():
    d = _base()
    d.exterior.ganancias_ocasionales = 40_000_000
    d.exterior.impuesto_pagado_go = 2_000_000
    liq, c = _liq(d)
    assert c[112] == 40_000_000 and c[127] == 6_000_000  # 15 %
    assert c[128] == 2_000_000 and c[129] == c[126] + c[127] - c[128]


def test_rentas_pasivas_de_una_ece_van_en_las_casillas_62_y_79():
    d = _base()
    d.exterior.ece_rentas_pasivas_capital = 20_000_000
    d.exterior.ece_rentas_pasivas_no_laborales = 5_000_000
    liq, c = _liq(d)
    assert c[62] == 20_000_000 and c[79] == 5_000_000
    assert c[70] == c[61] + c[62] - c[69] and c[87] == c[78] + c[79] - c[86]
