from app.agents import consejos
from app.orquestador import Respuestas, SolicitudLiquidacion, construir_declaracion
from app.tax import reglas
from app.tax.motor import liquidar


def _caso(**r):
    d = construir_declaracion(SolicitudLiquidacion(anio_gravable=2025, respuestas=Respuestas(**r)))
    reg = reglas.cargar(2025)
    return d, liquidar(d, reg), reg


def test_salario_alto_recibe_consejo_de_afc_con_ahorro_real():
    d, liq, reg = _caso(salarios_no_reportados=180e6)
    cs = consejos.consejos(d, liq, reg)
    afc = next(c for c in cs if c.clave == "afc")
    assert afc.ahorro > 0 and afc.monto > 0
    d.deducciones.aportes_voluntarios_afc_fpv += afc.monto
    assert round(liq.resumen.total_impuesto_cargo - liquidar(d, reg).resumen.total_impuesto_cargo) == round(afc.ahorro)
    assert any(c.clave == "factura" for c in cs)


def test_sin_impuesto_no_hay_consejos():
    d, liq, reg = _caso(salarios_no_reportados=30e6)
    assert consejos.consejos(d, liq, reg) == []
