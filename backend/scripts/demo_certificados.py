"""Genera los certificados FICTICIOS de demostración (data/demo/*.pdf).

Coinciden con la exógena de ejemplo (exogena_demo_2025.xlsx) para mostrar cómo se cruzan:
- Certificado de ingresos y retenciones (220) de COMERCIALIZADORA ANDINA S.A.S.
- Certificado tributario de BANCO EJEMPLO S.A.

Solo para desarrollo; requiere reportlab, que no es dependencia de la app:
    pip install reportlab && python scripts/demo_certificados.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo"
estilos = getSampleStyleSheet()
normal = estilos["Normal"]
normal.fontSize = 8.5
normal.leading = 11


def p(texto: str) -> Paragraph:
    return Paragraph(texto, normal)


def certificado_220() -> None:
    doc = SimpleDocTemplate(str(DEMO / "certificado_220_demo_2025.pdf"), pagesize=letter, title="Certificado 220 (ficticio)")
    filas = [
        ("Pagos por salarios", "36", "84.000.000"),
        ("Pagos realizados con bonos electrónicos o de papel de servicio, cheques, tarjetas, vales, etc.", "37", "0"),
        ("Valor del exceso de los pagos por alimentación mayores a 41 UVT, art. 387-1 E.T.", "38", "0"),
        ("Pagos por honorarios", "39", "0"),
        ("Pagos por servicios", "40", "0"),
        ("Pagos por comisiones", "41", "0"),
        ("Pagos por prestaciones sociales", "42", "12.000.000"),
        ("Pagos por viáticos", "43", "0"),
        ("Pagos por gastos de representación", "44", "0"),
        ("Pagos por compensaciones por el trabajo asociado cooperativo", "45", "0"),
        ("Otros pagos", "46", "0"),
        ("Auxilio de cesantía o intereses efectivamente pagados al empleado", "47", "0"),
        ("Auxilio de cesantía reconocido a trabajadores del régimen tradicional del CST", "48", "0"),
        ("Auxilio de cesantía consignado al fondo de cesantías", "49", "8.000.000"),
        ("Pensiones de jubilación, vejez o invalidez", "50", "0"),
        ("Apoyos económicos educativos financiados con recursos públicos, no reembolsables o condonados", "51", "0"),
        ("Total ingresos brutos (Sume 36 a 51)", "52", "104.000.000"),
    ]
    aportes = [
        ("Aportes obligatorios por salud a cargo del trabajador", "53", "3.840.000"),
        ("Aportes obligatorios a fondos de pensiones y solidaridad pensional a cargo del trabajador", "54", "3.840.000"),
        ("Cotizaciones voluntarias al régimen de ahorro individual con solidaridad - RAIS", "55", "0"),
        ("Aportes voluntarios a fondos de pensiones", "56", "2.400.000"),
        ("Aportes a cuentas AFC", "57", "0"),
        ("Aportes a cuentas AVC", "58", "0"),
        ("Ingreso laboral promedio de los últimos seis meses anteriores (numeral 4 art. 206 E.T.)", "59", "8.000.000"),
        ("Valor de la retención en la fuente por ingresos laborales y de pensiones", "60", "2.350.000"),
    ]

    def tabla(datos, titulo):
        t = Table([[titulo, "", "Valor"]] + [[p(a), b, c] for a, b, c in datos], colWidths=[380, 30, 90])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (2, -1), "RIGHT")]))
        return t

    contenido = [
        p("<b>DOCUMENTO FICTICIO DE DEMOSTRACIÓN — DeclaraFácil</b>"),
        p("<b>Certificado de Ingresos y Retenciones por Rentas de Trabajo y de Pensiones</b> — Año gravable 2025 — Formulario 220"),
        Spacer(1, 6),
        p("Retenedor: 5. Número de Identificación Tributaria (NIT) 6. DV. 7. Primer apellido 8. Segundo apellido 9. Primer nombre 10. Otros nombres"),
        p("900.111.222 3"),
        p("11. Razón social: COMERCIALIZADORA ANDINA S.A.S."),
        p("Trabajador: 24. Tipo de documento 25. Número de identificación 26. Primer apellido 27. Segundo apellido 28. Primer nombre 29. Otros nombres"),
        p("13 1012345678 PEREZ GOMEZ LAURA MARCELA"),
        p("Período de la certificación 30. DE: 01/01/2025 31. A: 31/12/2025 32. Fecha de expedición: 15/02/2026 33. Lugar donde se practicó la retención: Bogotá D.C."),
        Spacer(1, 6),
        tabla(filas, "Concepto de los ingresos"),
        Spacer(1, 6),
        tabla(aportes, "Concepto de los aportes"),
        Spacer(1, 6),
        p("Nombre del pagador o agente retenedor: COMERCIALIZADORA ANDINA S.A.S."),
        p("Datos a cargo del trabajador o pensionado — Concepto de otros ingresos: Arrendamientos 61 68 · Honorarios, comisiones y servicios 62 69 · Totales 67 74"),
        p("Total retenciones año gravable (Sume 60 + 74) 75 2.350.000"),
        Spacer(1, 6),
        p("Identificación del dependiente económico de acuerdo al parágrafo 2 del artículo 387 del Estatuto Tributario"),
        p("79. Tipo documento 80. No. Documento 81. Apellidos y Nombres 82. Parentesco"),
        p("12 1098765432 PEREZ RUIZ SOFIA Hija"),
    ]
    doc.build(contenido)


def certificado_banco() -> None:
    doc = SimpleDocTemplate(str(DEMO / "certificado_banco_demo_2025.pdf"), pagesize=letter, title="Certificado tributario (ficticio)")
    tabla = Table(
        [
            ["Producto", "Número", "Saldo a 31 de diciembre", "Intereses pagados", "Retención en la fuente", "GMF (4x1000)"],
            ["Cuenta de ahorros", "****8901", "4.500.000", "50.000", "2.000", "440.000"],
            ["CDT", "****7766", "20.000.000", "1.200.000", "48.000", "0"],
            ["Totales", "", "24.500.000", "1.250.000", "50.000", "440.000"],
        ],
        colWidths=[90, 60, 100, 85, 95, 70],
    )
    tabla.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (2, 1), (-1, -1), "RIGHT")]))
    contenido = [
        p("<b>DOCUMENTO FICTICIO DE DEMOSTRACIÓN — DeclaraFácil</b>"),
        p("<b>BANCO EJEMPLO S.A.</b> NIT 860.000.001-5"),
        p("<b>CERTIFICADO TRIBUTARIO AÑO GRAVABLE 2025</b>"),
        p("Bogotá D.C., 20 de febrero de 2026"),
        p("Señor(a): LAURA MARCELA PEREZ GOMEZ"),
        p("C.C. 1.012.345.678"),
        Spacer(1, 6),
        p("Certificamos que a 31 de diciembre de 2025 el cliente tenía los siguientes productos con el banco:"),
        Spacer(1, 6),
        tabla,
        Spacer(1, 8),
        p("Este certificado se expide para efectos de la declaración de renta del año gravable 2025. Vigilado Superintendencia Financiera de Colombia."),
    ]
    doc.build(contenido)


if __name__ == "__main__":
    certificado_220()
    certificado_banco()
    print("Listo:", ", ".join(x.name for x in DEMO.glob("*.pdf")))
