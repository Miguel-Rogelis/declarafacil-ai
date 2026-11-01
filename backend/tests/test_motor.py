"""Casos verificados a mano contra el Estatuto Tributario (AG 2025, UVT $49.799)."""

from datetime import date

import pytest

from app.tax import reglas
from app.tax.modelos import DatosDeclaracion, ItemPatrimonio
from app.tax.motor import impuesto_tabla_241, liquidar

UVT = 49799
R = reglas.cargar(2025)


def linea(liq, clave):
    for s in liq.secciones:
        for ln in s.lineas:
            if ln.clave == clave:
                return ln.valor
    raise KeyError(clave)


@pytest.mark.parametrize(
    ("uvts", "esperado_uvt"),
    [(0, 0), (1090, 0), (1700, 115.9), (4100, 787.9), (8670, 2296.0), (18970, 5901.0), (31000, 10352.1)],
)
def test_tabla_241_es_continua_en_los_limites(uvts, esperado_uvt):
    impuesto = impuesto_tabla_241(uvts * UVT, UVT, R["tabla_renta_art241"])
    assert impuesto / UVT == pytest.approx(esperado_uvt, abs=0.2)


def test_empleado_con_un_dependiente():
    d = DatosDeclaracion(
        laboral={"salarios_y_pagos_laborales": 120_000_000, "aportes_obligatorios_pension": 4_800_000, "aportes_obligatorios_salud": 4_800_000},
        deducciones={"dependientes": 1},
    )
    liq = liquidar(d, R)
    assert linea(liq, "dep_387") == 12_000_000
    assert linea(liq, "exenta_25") == 24_600_000  # 25 % de (110,4 M - 12 M)
    assert linea(liq, "dep_72") == 3_586_000  # 72 UVT, fuera del límite
    rlg = 110_400_000 - 12_000_000 - 24_600_000 - 72 * UVT
    assert liq.resumen.renta_liquida_gravable == pytest.approx(rlg, abs=500)
    esperado = (rlg - 1090 * UVT) * 0.19
    assert liq.resumen.impuesto_neto_renta == pytest.approx(esperado, abs=500)
    assert liq.obligacion.obligado


def test_limite_del_40_por_ciento_recorta_beneficios():
    d = DatosDeclaracion(
        laboral={"salarios_y_pagos_laborales": 50_000_000},
        deducciones={"intereses_vivienda": 30_000_000},
    )
    liq = liquidar(d, R)
    assert linea(liq, "aceptadas") == 20_000_000  # 40 % de 50 M
    assert any("límite" in a.titulo for a in liq.alertas)


def test_no_obligado_por_debajo_de_los_topes():
    d = DatosDeclaracion(laboral={"salarios_y_pagos_laborales": 30_000_000})
    liq = liquidar(d, R)
    assert not liq.obligacion.obligado
    assert liq.resumen.impuesto_neto_renta == 0


def test_obligado_por_patrimonio():
    d = DatosDeclaracion(patrimonio={"bienes": [ItemPatrimonio(concepto="Apartamento", valor=230_000_000)]})
    liq = liquidar(d, R)
    assert liq.obligacion.obligado


def test_dividendos_no_gravados_con_descuento_254_1():
    d = DatosDeclaracion(dividendos={"no_gravados_subcedula1": 100_000_000})
    liq = liquidar(d, R)
    base_uvt = 100_000_000 / UVT
    impuesto = ((base_uvt - 1700) * 0.28 + 116) * UVT
    descuento = (base_uvt - 1090) * 0.19 * UVT
    assert liq.resumen.impuesto_neto_renta == pytest.approx(impuesto - descuento, abs=1000)


def test_dividendos_gravados_pagan_35_y_el_resto_va_a_la_tabla():
    d = DatosDeclaracion(dividendos={"gravados_subcedula2": 100_000_000})
    liq = liquidar(d, R)
    assert linea(liq, "imp_sub2") == 35_000_000
    assert linea(liq, "div_base") == 65_000_000


def test_pensiones_exentas_hasta_12000_uvt_anuales():
    d = DatosDeclaracion(pensiones={"pensiones_nacionales": 80_000_000, "aportes_salud": 9_600_000})
    liq = liquidar(d, R)
    assert linea(liq, "rlg_pen") == 0


def test_ganancia_ocasional_venta_casa():
    d = DatosDeclaracion(ganancias_ocasionales={"utilidad_venta_casa_habitacion": 300_000_000})
    liq = liquidar(d, R)
    assert liq.resumen.impuesto_ganancias_ocasionales == pytest.approx((300_000_000 - 5000 * UVT) * 0.15, abs=1000)


def test_loterias_al_20_por_ciento():
    d = DatosDeclaracion(ganancias_ocasionales={"loterias_premios": 10_000_000})
    assert liquidar(d, R).resumen.impuesto_ganancias_ocasionales == 2_000_000


def test_independiente_elige_la_opcion_mas_favorable():
    con_costos = DatosDeclaracion(independiente={"honorarios_y_servicios": 100_000_000, "costos_gastos_procedentes": 60_000_000})
    assert liquidar(con_costos, R).opcion_independiente == "costos"
    sin_costos = DatosDeclaracion(independiente={"honorarios_y_servicios": 100_000_000, "costos_gastos_procedentes": 1_000_000})
    assert liquidar(sin_costos, R).opcion_independiente == "renta_exenta_25"


def test_componente_inflacionario_de_rendimientos():
    d = DatosDeclaracion(capital={"rendimientos_financieros": 10_000_000})
    assert linea(liquidar(d, R), "incr_cap") == 5_543_000


def test_anticipo_primera_declaracion_25():
    d = DatosDeclaracion(laboral={"salarios_y_pagos_laborales": 150_000_000})
    liq = liquidar(d, R)
    assert liq.resumen.anticipo_siguiente == pytest.approx(liq.resumen.impuesto_neto_renta * 0.25, abs=1000)


def test_sancion_extemporaneidad_minima():
    d = DatosDeclaracion(
        laboral={"salarios_y_pagos_laborales": 120_000_000},
        pagos={"declaraciones_previas": 3, "retenciones_renta": 10_000_000},
        control={"ultimos_dos_digitos_nit": "21", "fecha_presentacion": date(2026, 11, 1)},
    )
    liq = liquidar(d, R)
    assert liq.vencimiento.fecha == date(2026, 8, 27)
    assert liq.vencimiento.meses_retraso == 3
    assert liq.resumen.sancion >= 524_000


def test_digitos_00_corresponden_al_ultimo_vencimiento():
    d = DatosDeclaracion(control={"ultimos_dos_digitos_nit": "00", "fecha_presentacion": date(2026, 10, 1)})
    liq = liquidar(d, R)
    assert liq.vencimiento.fecha == date(2026, 10, 26)
    assert not liq.vencimiento.extemporanea


def test_reglas_validan_tabla_con_huecos():
    malo = reglas.cargar(2025)
    malo["tabla_renta_art241"][2]["desde_uvt"] = 1800
    assert reglas.validar(malo)


def test_sancion_se_descuenta_del_saldo_a_favor():
    d = DatosDeclaracion(
        laboral={"salarios_y_pagos_laborales": 80_000_000},
        pagos={"declaraciones_previas": 3, "retenciones_renta": 5_000_000},
        control={"ultimos_dos_digitos_nit": "21", "fecha_presentacion": date(2026, 9, 10)},
    )
    liq = liquidar(d, R)
    favor_sin_sancion = 5_000_000 - liq.resumen.total_impuesto_cargo
    assert liq.resumen.sancion == 524_000
    assert liq.resumen.saldo_favor == pytest.approx(favor_sin_sancion - 524_000, abs=1000)
    assert liq.resumen.total_a_pagar == 0
