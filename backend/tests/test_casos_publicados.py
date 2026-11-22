"""Casos resueltos publicados por terceros (portales tributarios y guías), pasados por el motor.

Cada caso trae la fuente y lo que la fuente calculó. Cuando la fuente se equivoca o no termina el
cálculo, el comentario dice qué se comprobó y por qué.
"""

from datetime import date

import pytest

from app.tax import reglas
from app.tax.modelos import DatosDeclaracion
from app.tax.motor import impuesto_tabla_241, liquidar

R24, R25 = reglas.cargar(2024), reglas.cargar(2025)


def casilla(liq, numero):
    for s in liq.formulario.secciones:
        for c in s.casillas:
            if c.numero == numero:
                return c.valor
    raise KeyError(numero)


def linea(liq, clave, defecto=None):
    for s in liq.secciones:
        for ln in s.lineas:
            if ln.clave == clave:
                return ln.valor
    if defecto is not None:  # las líneas en cero no se muestran
        return defecto
    raise KeyError(clave)


# ---------- Asalariados ----------

def test_siemprealdia_asalariado_ag2025_limite_40_y_72_uvt():
    """Siempre al Día, 'Rentas líquidas gravables en el formulario 210 AG 2025', ejemplo 1:
    ingresos 80 M, INCR 5,5 M, exentas y deducciones que pasan del 40 % (29,8 M) y un dependiente.
    Resultado publicado: casilla 97 = 41.114.000."""
    d = DatosDeclaracion(anio_gravable=2025,
                         laboral={"salarios_y_pagos_laborales": 80_000_000, "aportes_obligatorios_salud": 2_500_000, "aportes_obligatorios_pension": 3_000_000},
                         deducciones={"dependientes": 1, "aportes_voluntarios_afc_fpv": 15_000_000})
    liq = liquidar(d, R25)
    assert casilla(liq, 34) == 74_500_000
    assert linea(liq, "limite_40") == 29_800_000
    assert casilla(liq, 97) == 41_114_000


def test_actualicese_salario_120m_un_hijo_ag2024():
    """Actualícese (conferencia de dependientes): salario 120 M y un hijo → 10 % = 12 M (art. 387) y
    72 UVT = 3.388.680 (art. 336) por el mismo dependiente."""
    d = DatosDeclaracion(anio_gravable=2024, laboral={"salarios_y_pagos_laborales": 120_000_000}, deducciones={"dependientes": 1})
    liq = liquidar(d, R24)
    assert linea(liq, "dep_387") == 12_000_000
    assert linea(liq, "dep_72") == pytest.approx(72 * 47065, abs=1000)


def test_gerencie_paso_a_paso_ag2024_caso_1():
    """Gerencie / ofiscol, 'Paso a paso para elaborar declaraciones de renta AG 2024', caso práctico 1.
    La fuente tiene cálculos inconsistentes (no resta las 72 UVT y liquida la tabla sobre otra base),
    así que aquí se comprueba lo que sí es verificable: el tope de 1.340 UVT, las 72 UVT fuera del
    límite, las cesantías exentas al 100 % y el 25 % calculado después de todas las demás exentas y
    deducciones de trabajo (Oficio DIAN 15492 de 2025)."""
    d = DatosDeclaracion(anio_gravable=2024,
        laboral={"salarios_y_pagos_laborales": 169_000_000, "cesantias_e_intereses": 9_600_000, "salario_promedio_mensual_6m": 12_000_000,
                     "aportes_obligatorios_salud": 6_180_000, "aportes_obligatorios_pension": 7_725_000},
        independiente={"honorarios_y_servicios": 4_500_000, "opcion": "renta_exenta_25"},
        capital={"arrendamientos": 17_000_000, "costos_gastos_procedentes": 2_870_000},
        deducciones={"dependientes": 1, "medicina_prepagada": 1_850_000, "intereses_vivienda": 6_560_000, "gmf_pagado": 685_000, "aportes_voluntarios_afc_fpv": 21_850_000},
        pagos={"retenciones_renta": 13_900_000, "saldo_favor_anterior": 560_000, "impuesto_neto_anio_anterior": 11_560_000, "declaraciones_previas": 3})
    liq = liquidar(d, R24)
    uvt = 47065
    assert linea(liq, "cesantias_exentas") == 9_600_000
    # 25 % de: renta líquida de trabajo − cesantías − AFC/FVP − dependiente − prepagada − vivienda − GMF
    base = 169_195_000 - 9_600_000 - 21_850_000 - 384 * uvt - 1_850_000 - 6_560_000 - 342_500
    assert linea(liq, "exenta_25") == pytest.approx(base * 0.25, abs=1000)
    assert linea(liq, "limite_40") == pytest.approx(1340 * uvt, abs=1000)  # 63.067.100: el 40 % (74,5 M) es mayor
    assert casilla(liq, 92) == pytest.approx(1340 * uvt + 72 * uvt, abs=1000)
    assert casilla(liq, 97) == 116_869_000
    assert casilla(liq, 126) == 15_780_000
    assert casilla(liq, 136) == 1_320_000


# ---------- Independientes ----------

@pytest.mark.parametrize(("honorarios", "incr", "costos", "rl_25", "rl_costos", "elegida"), [
    # Siempre al Día, 'Honorarios profesionales en la declaración de renta AG 2025'
    (120_000_000, 18_000_000, 0, 76_500_000, None, "renta_exenta_25"),           # contador: 25 % = 25,5 M
    (180_000_000, 27_000_000, 90_000_000, 114_750_000, 63_000_000, "costos"),     # arquitecto
    (250_000_000, 37_500_000, 165_000_000, None, 47_500_000, "costos"),           # médico especialista
    # Contadía, 'Costos o renta exenta del 25 %: cómo elegir con criterio' (AG 2025)
    (120_000_000, 10_000_000, 40_000_000, 82_500_000, 70_000_000, "costos"),
])
def test_independientes_publicados_ag2025(honorarios, incr, costos, rl_25, rl_costos, elegida):
    base = {"honorarios_y_servicios": honorarios, "aportes_obligatorios_salud": incr * 0.4, "aportes_obligatorios_pension": incr * 0.6,
            "costos_gastos_procedentes": costos}
    if rl_25 is not None:
        liq = liquidar(DatosDeclaracion(anio_gravable=2025, independiente={**base, "opcion": "renta_exenta_25"}), R25)
        assert casilla(liq, 97) == rl_25
    if rl_costos is not None:
        liq = liquidar(DatosDeclaracion(anio_gravable=2025, independiente={**base, "opcion": "costos"}), R25)
        assert casilla(liq, 97) == rl_costos
    liq = liquidar(DatosDeclaracion(anio_gravable=2025, independiente={**base, "opcion": "auto"}), R25)
    assert liq.opcion_independiente == elegida


def test_independiente_con_un_dependiente_elige_72_uvt_si_el_40_por_ciento_ya_esta_lleno():
    """Sin salarios, un dependiente da derecho al 10 % del art. 387 o a 72 UVT, no a ambos (num. 1.1.2
    art. 1.2.1.20.3 DUR; Gerencie, '¿Si tengo un solo dependiente puedo optar…?'). Si el 25 % ya llena
    el límite del 40 %, el 10 % no sirve y conviene tomar las 72 UVT fuera del límite."""
    d = DatosDeclaracion(anio_gravable=2025, independiente={"honorarios_y_servicios": 100_000_000, "opcion": "renta_exenta_25"},
                         deducciones={"dependientes": 1, "aportes_voluntarios_afc_fpv": 30_000_000})
    liq = liquidar(d, R25)
    assert linea(liq, "dep_387", 0) == 0
    assert linea(liq, "dep_72") == pytest.approx(72 * 49799, abs=1000)
    assert any(a.titulo.startswith("Elegimos cómo tomar la deducción por dependientes") for a in liq.alertas)
    # Con cinco dependientes sigue conviniendo el 10 % por uno y 72 UVT por cada uno de los otros cuatro
    d5 = d.model_copy(update={"deducciones": d.deducciones.model_copy(update={"dependientes": 5})})
    liq5 = liquidar(d5, R25)
    assert linea(liq5, "dep_72") == pytest.approx(4 * 72 * 49799, abs=1000)


# ---------- Pensiones, dividendos y tabla ----------

def test_siemprealdia_pensionado_ag2025():
    """Pensión nacional 180 M y salud 21,6 M: todo exento (tope 1.000 UVT al mes). Casillas 99-103."""
    liq = liquidar(DatosDeclaracion(anio_gravable=2025, pensiones={"pensiones_nacionales": 180_000_000, "aportes_salud": 21_600_000}), R25)
    assert (casilla(liq, 99), casilla(liq, 100), casilla(liq, 101), casilla(liq, 102), casilla(liq, 103)) == (
        180_000_000, 21_600_000, 158_400_000, 158_400_000, 0)


def test_siemprealdia_dividendos_ag2025():
    """Dividendos 2017+: 20 M (subcédula 1) y 50 M (subcédula 2). 35 % sobre 50 M = 17,5 M (casilla 118)
    y a la tabla van 20 M + 32,5 M = 52,5 M, que no pasan de 1.090 UVT: impuesto de tabla cero."""
    liq = liquidar(DatosDeclaracion(anio_gravable=2025, dividendos={"no_gravados_subcedula1": 20_000_000, "gravados_subcedula2": 50_000_000}), R25)
    assert linea(liq, "imp_sub2") == 17_500_000
    assert linea(liq, "div_base") == 52_500_000
    assert linea(liq, "impuesto_241") == 0
    assert casilla(liq, 126) == 17_500_000


def test_contadia_tabla_241_sobre_90_990_000():
    """Contadía, 'Impuesto sobre las rentas líquidas gravables': 90.990.000 = 1.827,15 UVT →
    (1.827,15 − 1.700) × 28 % + 116 UVT = 151,60 UVT ≈ 7.550.000."""
    assert round(impuesto_tabla_241(90_990_000, 49799, R25["tabla_renta_art241"]), -3) == 7_550_000


# ---------- Ganancias ocasionales ----------

@pytest.mark.parametrize(("utilidad", "cumple", "impuesto"), [
    (217_500_000, False, 32_625_000),   # apartamento sin exención (método art. 73)
    (282_570_000, False, 42_386_000),   # mismo apartamento con el reajuste del art. 70 (42.385.500)
    (417_500_000, True, 25_276_000),    # vivienda con exención de 5.000 UVT: (417,5 M − 248.995.000) × 15 % = 25.275.750
])
def test_siemprealdia_venta_de_inmueble_ag2025(utilidad, cumple, impuesto):
    """Siempre al Día, 'Ganancia ocasional por venta de inmuebles en AG 2025'."""
    d = DatosDeclaracion(anio_gravable=2025, ganancias_ocasionales={"utilidad_venta_casa_habitacion": utilidad, "cumple_requisitos_exencion_casa": cumple})
    liq = liquidar(d, R25)
    assert linea(liq, "go_impuesto") == pytest.approx(impuesto, abs=1000)


# ---------- Anticipo y sanciones ----------

def test_gerencie_anticipo_promedio_de_dos_anios():
    """Gerencie, 'Anticipo del impuesto de renta': impuesto neto 12 M (2025) y 10 M (2024), retenciones
    4 M, 75 %. Procedimiento 1 = 5 M; procedimiento 2 = 11 M × 75 % − 4 M = 4,25 M → se toma el menor."""
    d = DatosDeclaracion(anio_gravable=2025, pagos={"retenciones_renta": 4_000_000, "declaraciones_previas": 4, "impuesto_neto_anio_anterior": 10_000_000})
    liq = liquidar(d, R25)
    # El impuesto lo da el motor; el anticipo se comprueba con la fórmula publicada sobre ese impuesto
    imp = casilla(liq, 126)
    esperado = max(min(imp * 0.75 - 4_000_000, (imp + 10_000_000) / 2 * 0.75 - 4_000_000), 0)
    assert casilla(liq, 133) == pytest.approx(esperado, abs=1000)


def test_actualicese_anticipo_segundo_anio():
    """Actualícese: segundo año, impuesto 1.350.000 × 50 % = 675.000 − retenciones 250.000 = 425.000."""
    d = DatosDeclaracion(anio_gravable=2025, laboral={"salarios_y_pagos_laborales": 70_000_000}, pagos={"retenciones_renta": 250_000, "declaraciones_previas": 1})
    liq = liquidar(d, R25)
    imp = casilla(liq, 126)
    assert casilla(liq, 133) == pytest.approx(max(imp * 0.5 - 250_000, 0), abs=1000)


def test_rcn_sancion_minima_2026():
    """Noticias RCN: impuesto 2 M y un mes de retraso → 5 % = 100.000, pero la mínima es 10 UVT de 2026
    (523.740 ≈ 524.000), aun con la reducción del art. 640."""
    d = DatosDeclaracion(anio_gravable=2025, laboral={"salarios_y_pagos_laborales": 75_000_000},
                         control={"ultimos_dos_digitos_nit": "01", "fecha_presentacion": date(2026, 9, 1)})
    liq = liquidar(d, R25)
    assert casilla(liq, 135) == 524_000
