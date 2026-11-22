"""Flujo completo con un juego de documentos variados de una misma persona (AG 2025, modo simulado):
certificado 220 con la numeración oficial, crédito hipotecario, prepagada, ICETEX y banco con cuenta
y CDT. Se comprueba lo que se lee de cada uno, lo que llega al motor y el resultado final."""

import os

os.environ["LLM_MODE"] = "simulado"

import pytest

from app import orquestador
from app.agents import clasificador, extractor
from app.agents.base import DocumentoLeido
from app.tax import reglas
from app.tax.motor import liquidar

DOCS = {
"c220_oficial.pdf": [
 "CERTIFICADO DE INGRESOS Y RETENCIONES POR RENTAS DE TRABAJO Y DE PENSIONES",
 "Año gravable 2025", "Formulario 220",
 "Retenedor: INDUSTRIAS DEL VALLE S.A.S. NIT 901.234.567-1",
 "Período de la certificación: 01/01/2025 a 31/12/2025",
 "Concepto de los ingresos Valor",
 "36 Pagos por salarios o emolumentos eclesiásticos $ 54.000.000",
 "37 Pagos realizados con bonos electrónicos o de papel de servicio, cheques, tarjetas, vales, etc. $ 0",
 "38 Valor del exceso de los pagos por alimentación mayores a 41 UVT $ 0",
 "39 Pagos por honorarios $ 0",
 "40 Pagos por servicios $ 0",
 "41 Pagos por comisiones $ 0",
 "42 Pagos por prestaciones sociales $ 9.000.000",
 "43 Pagos por viáticos $ 0",
 "44 Pagos por gastos de representación $ 0",
 "45 Pagos por compensaciones por el trabajo asociado cooperativo $ 0",
 "46 Otros pagos $ 0",
 "47 Cesantías e intereses de cesantías efectivamente pagadas al empleado $ 1.200.000",
 "48 Cesantías consignadas al fondo de cesantías $ 4.500.000",
 "49 Pensiones de jubilación, vejez o invalidez $ 0",
 "50 Total de ingresos brutos $ 68.700.000",
 "51 Aportes obligatorios por salud a cargo del trabajador $ 2.160.000",
 "52 Aportes obligatorios a fondos de pensiones y solidaridad pensional a cargo del trabajador $ 2.700.000",
 "53 Cotizaciones voluntarias al régimen de ahorro individual con solidaridad - RAIS $ 0",
 "54 Aportes voluntarios a fondos de pensiones $ 1.800.000",
 "55 Aportes a cuentas AFC $ 3.000.000",
 "56 Aportes a cuentas AVC $ 0",
 "57 Ingreso laboral promedio de los últimos seis meses $ 4.500.000",
 "58 Valor de la retención en la fuente por ingresos laborales y de pensiones $ 640.000",
 "Datos del dependiente: Hijo",
],
"hipotecario.pdf": [
 "BANCO DAVIVIENDA S.A. NIT 860.034.313-7",
 "CERTIFICADO TRIBUTARIO AÑO GRAVABLE 2025",
 "Crédito hipotecario No. 05700123456",
 "Intereses pagados en el año: $ 7.850.000",
 "Saldo de capital a 31 de diciembre de 2025: $ 96.400.000",
],
"prepagada.pdf": [
 "SURA EPS MEDICINA PREPAGADA S.A. NIT 800.088.702-2",
 "Certificado de pagos por contratos de medicina prepagada año 2025",
 "Valor total pagado en el año 2025: $ 3.960.000",
],
"icetex.pdf": [
 "INSTITUTO COLOMBIANO DE CRÉDITO EDUCATIVO Y ESTUDIOS TÉCNICOS EN EL EXTERIOR - ICETEX NIT 899.999.035-7",
 "Certificado de intereses pagados año gravable 2025",
 "Crédito educativo No. 123456",
 "Intereses pagados: $ 2.300.000",
 "Saldo a 31 de diciembre de 2025: $ 11.000.000",
],
"banco.pdf": [
 "BANCO DE BOGOTÁ S.A. NIT 860.002.964-4",
 "Certificación tributaria año 2025",
 "Cuenta de ahorros No. ****4421",
 "Saldo a 31-12-2025 $ 8.750.000",
 "Rendimientos financieros $ 210.000",
 "Retención en la fuente $ 8.400",
 "Gravamen a los movimientos financieros (4x1000) $ 368.000",
 "CDT No. 778899",
 "Valor del CDT a 31 de diciembre $ 20.000.000",
 "Intereses $ 1.640.000",
 "Retención en la fuente $ 65.600",
],
}


def _leer():
    filas, docs = [], {}
    for i, (nombre, lineas) in enumerate(DOCS.items()):
        doc = DocumentoLeido(formato="pdf", lineas=lineas)
        tipo, _ = clasificador.tipo_por_reglas(doc)
        f, d = extractor.extraer(doc, tipo, f"{i:02d}".ljust(12, "0"), nombre, 2025)
        filas += f
        docs[nombre] = (tipo, d)
    return filas, docs


def test_cada_documento_se_reconoce_con_su_entidad():
    _, docs = _leer()
    assert {n: t for n, (t, _) in docs.items()} == {
        "c220_oficial.pdf": "certificado_220", "hipotecario.pdf": "certificado_bancario", "prepagada.pdf": "certificado_prepagada",
        "icetex.pdf": "certificado_bancario", "banco.pdf": "certificado_bancario"}
    assert docs["c220_oficial.pdf"][1].entidad == "INDUSTRIAS DEL VALLE S.A.S."  # sin el rótulo "Retenedor:"
    assert docs["c220_oficial.pdf"][1].pistas == ["dependiente:hijo"]
    assert {n: d.nit for n, (_, d) in docs.items()} == {
        "c220_oficial.pdf": "901234567", "hipotecario.pdf": "860034313", "prepagada.pdf": "800088702", "icetex.pdf": "899999035", "banco.pdf": "860002964"}


def test_lo_que_llega_al_motor():
    filas, _ = _leer()
    d = orquestador.construir_declaracion(orquestador.SolicitudLiquidacion(anio_gravable=2025, filas=filas))
    assert d.laboral.salarios_y_pagos_laborales == 63_000_000      # salarios + prestaciones; el total (casilla 50) no se suma otra vez
    assert d.laboral.cesantias_e_intereses == 5_700_000
    assert d.laboral.salario_promedio_mensual_6m == 4_500_000
    assert d.laboral.aportes_obligatorios_salud + d.laboral.aportes_obligatorios_pension == 4_860_000
    assert d.deducciones.aportes_voluntarios_afc_fpv == 4_800_000
    assert d.deducciones.intereses_vivienda == 7_850_000
    assert d.deducciones.medicina_prepagada == 3_960_000
    assert d.deducciones.intereses_icetex == 2_300_000
    assert d.deducciones.gmf_pagado == 368_000
    assert d.capital.rendimientos_financieros == 1_850_000
    assert d.pagos.retenciones_renta == 714_000
    assert sum(b.valor for b in d.patrimonio.bienes) == 28_750_000
    assert sum(x.valor for x in d.patrimonio.deudas) == 107_400_000
    assert d.deducciones.dependientes == 0  # el hijo del 220 es una pista: el asistente lo confirma antes de usarlo


@pytest.mark.parametrize(("dependientes", "rlg"), [(0, 38_799_000), (1, 35_213_000)])
def test_resultado_final_hecho_a_mano(dependientes, rlg):
    """Ingresos 70,55 M; INCR 4,86 M + componente inflacionario 1.025.455. Exentas y deducciones
    (cesantías 5,7 M, prepagada, AFC, vivienda, GMF 50 %, ICETEX y 25 %) pasan del 40 % de
    64.664.545 = 25.865.818, así que se limitan. Con el hijo: 10 % entra al mismo límite (no cambia
    nada) y 72 UVT (3.585.528) se restan por fuera. El impuesto da cero (menos de 1.090 UVT) y las
    retenciones quedan como saldo a favor."""
    filas, _ = _leer()
    sol = orquestador.SolicitudLiquidacion(anio_gravable=2025, filas=filas, respuestas={"dependientes": dependientes})
    liq = liquidar(orquestador.construir_declaracion(sol), reglas.cargar(2025))
    c = {x.numero: x.valor for s in liq.formulario.secciones for x in s.casillas}
    assert c[97] == pytest.approx(rlg, abs=1000)
    assert c[126] == 0
    assert c[137] == 714_000
    assert liq.obligacion.obligado  # ingresos > 1.400 UVT
