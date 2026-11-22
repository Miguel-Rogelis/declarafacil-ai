"""HU-38: certificados escaneados o en foto se leen con OCR y ninguna cifra entra sin confirmación."""

import asyncio
import io

import pytest

from app import orquestador
from app.agents import lector
from app.config import settings

pytestmark = pytest.mark.skipif(not lector.ocr_disponible(), reason="Tesseract no está instalado")

DEMO = settings.data_dir / "demo"


def _png_de(pdf: str) -> bytes:
    import pypdfium2 as pdfium

    pagina = pdfium.PdfDocument((DEMO / pdf).read_bytes())[0]
    img = pagina.render(scale=200 / 72).to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pdf_escaneado(pdf: str) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(_png_de(pdf))).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PDF")  # un PDF hecho solo de imagen, como el de un escáner
    return buf.getvalue()


def _correr(archivos):
    async def correr():
        return [x async for x in orquestador.procesar_documentos(archivos, 2025)]

    return asyncio.run(correr())


def test_lector_saca_texto_de_una_foto():
    doc = lector.leer(_png_de("certificado_banco_demo_2025.pdf"), "certificado.png")
    assert doc.ocr and doc.formato == "imagen"
    texto = " ".join(doc.lineas).lower()
    assert "certificado" in texto and len(doc.lineas) > 5


def test_foto_de_certificado_queda_toda_por_confirmar():
    salida = _correr([(_png_de("certificado_banco_demo_2025.pdf"), "foto_banco.png")])
    r = salida[-1]
    assert isinstance(r, orquestador.ResultadoDocumento), r
    doc = r.nuevos[0]
    assert doc.ocr and doc.tipo == "certificado_bancario"
    filas = [f for f in r.extraccion.filas if f.documento == doc.id and f.tratamiento != "informativo"]
    assert filas and all(f.tratamiento == "revisar" and f.pregunta for f in filas)
    # Nada de lo leído con OCR entra al cálculo hasta que la persona lo confirme
    assert not r.extraccion.datos.get("pagos", {}).get("retenciones_renta")


def test_pdf_escaneado_se_lee_con_ocr():
    salida = _correr([(_pdf_escaneado("certificado_220_demo_2025.pdf"), "220_escaneado.pdf")])
    r = salida[-1]
    assert isinstance(r, orquestador.ResultadoDocumento), r
    assert r.nuevos[0].ocr and r.nuevos[0].tipo == "certificado_220"
    assert all(f.tratamiento == "revisar" for f in r.extraccion.filas if f.documento == r.nuevos[0].id and f.tratamiento != "informativo")


def test_la_exogena_no_se_acepta_por_foto():
    from openpyxl import load_workbook  # noqa: F401 - solo para asegurar que el entorno lee Excel

    # Una foto con apariencia de exógena: el sistema pide el Excel en vez de leer cifras de una imagen
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1400, 500), "white")
    d = ImageDraw.Draw(img)
    for i, linea in enumerate(["REPORTE DE INFORMACION EXOGENA", "Uso declaracion sugerida", "Ano al que se refiere 2025"]):
        d.text((40, 40 + 60 * i), linea, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    salida = _correr([(buf.getvalue(), "exogena.png")])
    assert isinstance(salida[-1], orquestador.ErrorFlujo)
