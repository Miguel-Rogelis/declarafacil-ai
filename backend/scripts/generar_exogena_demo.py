"""Genera una exógena FICTICIA con el mismo formato del reporte de la DIAN.

Sirve para pruebas automáticas y para que cualquiera pruebe la app sin usar datos
reales. Ninguna persona, cédula ni cuenta de este archivo existe.

Uso: python scripts/generar_exogena_demo.py
"""

from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

BASE = Path(__file__).resolve().parent.parent
CEDULA = "1012345678"
NOMBRE = "PEREZ GOMEZ LAURA MARCELA"

# (NIT informante, informante, detalle, valor, uso sugerido, info adicional)
FILAS = [
    (900111222, "COMERCIALIZADORA ANDINA S.A.S.", "Pagos por salarios (Concepto: 2276)", 96_000_000, "Tope 1: Ingresos brutos | R32 Ingresos brutos por rentas de trabajo (art. 103 E.T.)", None),
    (900111222, "COMERCIALIZADORA ANDINA S.A.S.", "Aporte obligatorio fondos pensiones y solidaridad a cargo del trabajador (Concepto: 2276)", 3_840_000, "Ingresos no constitutivos de renta | Asignación según el tipo de renta: R33 (Trabajo)", None),
    (900111222, "COMERCIALIZADORA ANDINA S.A.S.", "Aportes obligatorios a salud a cargo Trabajador (Concepto: 2276)", 3_840_000, "Ingresos no constitutivos de renta | Asignación según el tipo de renta: R33 (Trabajo)", None),
    (900111222, "COMERCIALIZADORA ANDINA S.A.S.", "Retención por pagos rentas de trabajo o pensiones (Concepto: 2276)", 2_100_000, "R132 Retenciones año gravable a declarar", None),
    (900111222, "COMERCIALIZADORA ANDINA S.A.S.", "Valor de los bonos de alimentación entregados (Concepto: 2276)", 1_800_000, None, None),
    (900111222, "COMERCIALIZADORA ANDINA S.A.S.", "Activos aportes parafiscales, salud, pensión y cesantías (Concepto: 2214)", 18_400_000, "Tope 2: Patrimonio | R29 Patrimonio Bruto", None),
    (800227940, "FONDO DE CESANTIAS EJEMPLO S.A.", "Valor total de las cesantías abonadas en el periodo.  (Formato del fondo de cesantías)", 8_000_000, "Tope 1: Ingresos brutos | R29 Patrimonio Bruto | R32 Ingresos brutos por rentas de trabajo (art. 103 E.T.)", None),
    (860000001, "BANCO EJEMPLO S.A.", "Saldo cuentas bancarias (Titular Principal)", 4_500_000, "Tope 2: Patrimonio | R29 Patrimonio Bruto (si el saldo es positivo)| R30 Deudas  (si el saldo es negativo)", "Número de Cuenta / Documento: 00012345678901 | Concepto Códigos Tributaria: *1* Cuenta de ahorro"),
    (860000001, "BANCO EJEMPLO S.A.", "Valor total de los movimientos en cuentas corrientes y de ahorros  (Titular Principal)", 110_000_000, "Tope 4: Consignaciones e inversiones", "Número de Cuenta / Documento: 00012345678901"),
    (860000001, "BANCO EJEMPLO S.A.", "Valor de los intereses o rendimientos financieros pagados (Concepto: 1311)", 1_200_000, "Tope 1: Ingresos brutos | R58 Ingresos brutos por rentas de capital", None),
    (860000001, "BANCO EJEMPLO S.A.", "Saldo CDT a 31 de diciembre (Titular Principal) (Concepto: 1020)", 20_000_000, "Tope 2: Patrimonio | R29 Patrimonio Bruto", "Número de Cuenta / Documento: 000099887766"),
    (860000002, "BANCO HIPOTECARIO DEMO S.A.", "Cuentas por pagar de clientes (Concepto: 1315)", 95_000_000, "R30 Deudas", None),
    (860000002, "BANCO HIPOTECARIO DEMO S.A.", "Intereses pagados en créditos de vivienda (Concepto: 1315)", 7_500_000, "Deducción por intereses de vivienda", None),
    (860000003, "TARJETAS DEMO S.A.", "Cuentas por pagar de clientes (Concepto: 1315)", 3_200_000, "R30 Deudas", None),
    (860000003, "TARJETAS DEMO S.A.", "Total consumos o gastos con tarjeta Crédito o Débito (Concepto: 1023)", 18_000_000, "Tope 3: Consumos TC", "Número de Cuenta / Documento: 4111111111114321 | Clase de Tarjeta: *1* Tarjeta de Credito Principal"),
    (830000004, "MEDICINA PREPAGADA DEMO S.A.", "Pagos por medicina prepagada (Concepto: 1361)", 4_200_000, "Deducción medicina prepagada", None),
    (899999061, "BOGOTA DISTRITO CAPITAL", "Valor avalúo catastral (Concepto: 1476)", 180_000_000, "Tope 2: Patrimonio | R29 Patrimonio Bruto | Se toma el mayor valor informado entre el avalúo y la base del impuesto predial", "Porcentaje de Participación: 100.00 | Matricula: 050C12345678 | Número Propietarios: 1"),
    (800197268, "U.A.E. DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES", "Suma valor total facturas tras ajustes por notas", 26_000_000, "Tope 5: Compras registradas en Factura Electrónica", None),
    (800197268, "U.A.E. DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES", "Monto total de facturación electrónica susceptible de beneficio", 22_000_000, None, None),
    (int(CEDULA), NOMBRE, "Total patrimonio bruto declarado en el año anterior", 205_000_000, "El Tope 2 - Patrimonio, toma el mayor valor entre la suma de variables del año gravable reportadas en la exógena y el valor de patrimonio bruto declarado en el año anterior", None),
]


def generar(destino: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte"
    ws.append([None, None, "Consulta de Información reportada por terceros"])
    ws.append(["ADVERTENCIA: Esta información corresponde a la fecha de corte del proceso y puede estar sujeta a cambios.", None, None, None, None, None, "Fecha   Reporte:", datetime(2026, 11, 1, 10, 0)])
    ws.append(["Fecha corte del proceso: ", None, datetime(2026, 10, 31)])
    ws.append(["Año al que se refiere la consulta:", None, "2025"])
    ws.append(["Identificación del consultante"])
    ws.append(["Tipo de documento:", None, "C. C."])
    ws.append(["Identificación:", None, CEDULA])
    ws.append(["Nombres / Razón social:", None, NOMBRE])
    ws.append(["IMPORTANTE: Para cumplir con su obligación de declarar, la Información Exógena Tributaria NO ES INDISPENSABLE y NO REEMPLAZA la información de su realidad económica."])
    ws.append(["Persona que reporta", None, "Información reportada"])
    ws.append(["NIT", "Nombre / Razón Social", "NIT", "Nombre/Razón Social reportada por el tercero", "Detalle", "Valor", "Uso declaración Sugerida", "Información  Adicional "])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    ingresos = 96_000_000 + 8_000_000 + 1_200_000 + 1_800_000
    patrimonio = max(4_500_000 + 20_000_000 + 180_000_000 + 18_400_000 + 8_000_000, 205_000_000)
    for nombre, valor in [("Tope 1 - Ingresos", ingresos), ("Tope 2 - Patrimonio", patrimonio), ("Tope 3 - Consumo TC", 18_000_000), ("Tope 4 - Movimiento", 110_000_000), ("Tope 5 - Compras", 26_000_000)]:
        ws.append([None, None, None, None, nombre, valor, None, None])
    for nit, inf, det, valor, uso, info in FILAS:
        ws.append([nit, inf, CEDULA, NOMBRE, det, valor, uso, info])
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


if __name__ == "__main__":
    for ruta in (BASE / "data" / "demo" / "exogena_demo_2025.xlsx", BASE / "tests" / "fixtures" / "exogena_ficticia.xlsx"):
        print("Generado:", generar(ruta))
