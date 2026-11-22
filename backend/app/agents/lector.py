"""Agente Lector: convierte un archivo (Excel, PDF o foto) en filas y texto estructurados.

- Si es el reporte de exógena, saca sus filas (informante, concepto, valor, uso sugerido).
- Para cualquier documento guarda además el texto línea por línea y las tablas, que es lo
  que usa el Extractor con los certificados (banco, 220, vivienda, prepagada…).
- Si el PDF no tiene texto (escaneo) o es una foto, lo lee con OCR (Tesseract, en español) y
  marca el documento: cada cifra que salga de ahí se le confirma a la persona antes de usarla.
Responsabilidad única: leer. No interpreta conceptos ni toca montos.
"""

import io
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from typing import Any

from app.agents.base import DocumentoLeido, FilaExogena


class ArchivoNoSoportado(Exception):
    pass


def _norm(texto: Any) -> str:
    s = "" if texto is None else str(texto)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _a_numero(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    negativo = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    # Formato colombiano: 1.234.567,89 ; también 1,234,567.89
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if negativo else n


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, datetime):
        return v.date().isoformat()
    s = str(v).strip()
    return s or None


_ETIQUETAS = {
    "ano al que se refiere": "anio",
    "identificacion:": "identificacion",
    "nombres / razon social": "nombre",
    "fecha corte del proceso": "fecha_corte",
}


def _metadatos(doc: DocumentoLeido, fila: list[Any]) -> None:
    for i, celda in enumerate(fila):
        n = _norm(celda)
        for etiqueta, campo in _ETIQUETAS.items():
            if n.startswith(etiqueta):
                valor = next((fila[j] for j in range(i + 1, len(fila)) if fila[j] not in (None, "")), None)
                if valor is None:
                    continue
                if campo == "anio":
                    m = re.search(r"(20\d{2})", str(valor))
                    doc.anio = int(m.group(1)) if m else None
                elif campo == "fecha_corte":
                    doc.fecha_corte = _texto(valor)
                else:
                    setattr(doc, campo, _texto(valor))


def _indices_encabezado(fila: list[Any]) -> dict[str, int] | None:
    nombres = [_norm(c) for c in fila]
    if "detalle" not in nombres or "valor" not in nombres:
        return None
    idx: dict[str, int] = {"detalle": nombres.index("detalle"), "valor": nombres.index("valor")}
    nits = [i for i, n in enumerate(nombres) if n == "nit"]
    if nits:
        idx["nit_informante"] = nits[0]
        idx["informante"] = nits[0] + 1
    for i, n in enumerate(nombres):
        if n.startswith("uso declaracion"):
            idx["uso_sugerido"] = i
        elif n.startswith("informacion adicional"):
            idx["info_adicional"] = i
    return idx


def _filas_tabulares(doc: DocumentoLeido, filas: list[list[Any]]) -> None:
    idx: dict[str, int] | None = None
    contador = 0
    for fila in filas:
        if not any(c not in (None, "") for c in fila):
            continue
        if idx is None:
            _metadatos(doc, fila)
            idx = _indices_encabezado(fila)
            if idx is None:
                primera = next((c for c in fila if c not in (None, "")), None)
                if primera is not None and not doc.titulo and "informacion" in _norm(primera):
                    doc.titulo = str(primera).strip()
                if primera is not None:
                    doc.lineas_encabezado.append(str(primera).strip()[:200])
            continue

        def celda(nombre: str) -> Any:
            i = idx.get(nombre)
            return fila[i] if i is not None and i < len(fila) else None

        detalle = _texto(celda("detalle"))
        valor = _a_numero(celda("valor"))
        if not detalle or valor is None:
            continue
        nit = _texto(celda("nit_informante"))
        if not nit and _norm(detalle).startswith("tope"):
            doc.topes[detalle] = valor
            continue
        contador += 1
        doc.filas.append(
            FilaExogena(
                id=f"F{contador:03d}",
                nit_informante=nit,
                informante=_texto(celda("informante")),
                detalle=detalle,
                valor=valor,
                uso_sugerido=_texto(celda("uso_sugerido")),
                info_adicional=_texto(celda("info_adicional")),
            )
        )


_MAX_LINEAS = 1500


def _celda_texto(c: Any) -> str:
    if c is None:
        return ""
    if isinstance(c, float) and c.is_integer():
        c = int(c)
    if isinstance(c, datetime):
        return c.date().isoformat()
    return re.sub(r"\s+", " ", str(c)).strip()


def _leer_xlsx(contenido: bytes) -> DocumentoLeido:
    import openpyxl

    # read_only=False: la DIAN genera archivos con la dimensión de la hoja mal declarada
    wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=False)
    doc = DocumentoLeido(formato="xlsx")
    for ws in wb.worksheets:
        filas = [list(r) for r in ws.iter_rows(values_only=True)]
        if not doc.filas:
            _filas_tabulares(doc, filas)
        tabla = [[_celda_texto(c) for c in f] for f in filas if any(c not in (None, "") for c in f)]
        if len(doc.lineas) < _MAX_LINEAS:
            doc.lineas.extend(" ".join(c for c in f if c) for f in tabla[:_MAX_LINEAS])
            doc.tablas.append(tabla[:400])
    wb.close()
    return doc


def _leer_pdf(contenido: bytes) -> DocumentoLeido:
    import pdfplumber

    doc = DocumentoLeido(formato="pdf")
    filas: list[list[Any]] = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for pagina in pdf.pages[:40]:
            texto = pagina.extract_text() or ""
            lineas = [x.strip() for x in texto.splitlines() if x.strip()]
            for linea in lineas[:15]:
                filas.append([linea.split(":")[0] + ":" if ":" in linea else linea, linea.split(":", 1)[1].strip() if ":" in linea else None])
            if len(doc.lineas) < _MAX_LINEAS:
                doc.lineas.extend(lineas)
            for tabla in pagina.extract_tables():
                filas.extend([list(f) for f in tabla])
                doc.tablas.append([[_celda_texto(c) for c in f] for f in tabla])
    _filas_tabulares(doc, filas)
    doc.lineas = doc.lineas[:_MAX_LINEAS]
    return doc


MAX_PAGINAS_OCR = 4
_IMAGEN = re.compile(r"\.(jpe?g|png|webp|tiff?|bmp)$")


def ocr_disponible() -> bool:
    return shutil.which("tesseract") is not None


def _ocr(imagen) -> str:  # noqa: ANN001 - imagen de Pillow
    """Texto de una imagen con Tesseract (español). La imagen se pasa en gris y agrandada si es pequeña."""
    from PIL import ImageOps

    img = ImageOps.exif_transpose(imagen).convert("L")
    if img.width < 1600:
        factor = 1600 / img.width
        img = img.resize((int(img.width * factor), int(img.height * factor)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "spa", "--psm", "6"], input=buf.getvalue(),
                       capture_output=True, timeout=60, check=False)
    return r.stdout.decode("utf-8", "ignore")


_COLUMNAS = re.compile(r"saldo|intereses|rendimientos|retenci[oó]n|gmf|4x1000|gravamen|valor|pagos|aportes")
_NUMERO = re.compile(r"(?<![\w*\"'+])\d{1,3}(?:[.,]\d{3})+(?:,\d{1,2})?(?!\d)|(?<![\w*\"'+.,])\d{1,9}(?![\d.,])")


def _tabla_de_lineas(lineas: list[str]) -> list[list[str]]:
    """Rearma la tabla de un certificado a partir del texto del OCR (que no trae celdas).

    Busca el encabezado (saldo, intereses, retención, 4x1000…) y toma de cada fila siguiente sus
    últimos números, uno por columna. La primera celda es el producto o concepto de la fila.
    """
    for i, linea in enumerate(lineas):
        n = "".join(((_norm(ch) or ch)[:1]).lower() if ch.strip() else " " for ch in linea)  # misma longitud que la línea
        marcas = [m.start() for m in _COLUMNAS.finditer(n)]
        inicios = [x for j, x in enumerate(marcas) if j == 0 or x - marcas[j - 1] > 6]
        if len(inicios) < 2 or len(re.findall(r"\d{1,3}(?:[.,]\d{3})+", linea)) >= 2:
            continue  # un encabezado nombra columnas; no trae cifras
        columnas = [linea[a:b].strip() for a, b in zip(inicios, inicios[1:] + [len(linea)])]
        tabla = [[linea[: inicios[0]].strip() or "Concepto", *columnas]]
        for fila in lineas[i + 1 :]:
            numeros = list(_NUMERO.finditer(fila))
            if len(numeros) < len(columnas):
                break
            ultimos = numeros[-len(columnas):]
            etiqueta = re.sub(r"[*+\"'#]+\d+", "", fila[: ultimos[0].start()]).strip(" :-")
            tabla.append([etiqueta, *[m.group(0) for m in ultimos]])
        if len(tabla) > 1:
            return tabla
    return []


def _doc_de_texto(textos: list[str], formato: str) -> DocumentoLeido:
    doc = DocumentoLeido(formato=formato, ocr=True)  # type: ignore[arg-type]
    filas: list[list[Any]] = []
    for texto in textos:
        lineas = [re.sub(r"[|]", " ", x).strip() for x in texto.splitlines() if x.strip()]
        for linea in lineas[:15]:
            filas.append([linea.split(":")[0] + ":" if ":" in linea else linea, linea.split(":", 1)[1].strip() if ":" in linea else None])
        doc.lineas.extend(lineas)
    _filas_tabulares(doc, filas)
    doc.filas = []  # una exógena nunca se toma de una foto: se descarga en Excel
    doc.lineas = doc.lineas[:_MAX_LINEAS]
    if tabla := _tabla_de_lineas(doc.lineas):
        doc.tablas.append(tabla)
    return doc


def _ocr_pdf(contenido: bytes) -> DocumentoLeido:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(contenido)
    textos = []
    for i in range(min(len(pdf), MAX_PAGINAS_OCR)):
        textos.append(_ocr(pdf[i].render(scale=300 / 72).to_pil()))
    return _doc_de_texto(textos, "pdf")


def _ocr_imagen(contenido: bytes) -> DocumentoLeido:
    from PIL import Image

    return _doc_de_texto([_ocr(Image.open(io.BytesIO(contenido)))], "imagen")


def leer(contenido: bytes, nombre_archivo: str) -> DocumentoLeido:
    nombre = nombre_archivo.lower()
    if nombre.endswith(".xlsx") or contenido[:2] == b"PK":
        try:
            return _leer_xlsx(contenido)
        except Exception as e:  # noqa: BLE001
            raise ArchivoNoSoportado(f"No pude abrir el Excel: {e}") from e
    if nombre.endswith(".pdf") or contenido[:4] == b"%PDF":
        try:
            doc = _leer_pdf(contenido)
        except Exception as e:  # noqa: BLE001
            raise ArchivoNoSoportado(f"No pude abrir el PDF: {e}") from e
        if doc.filas or any(len(x) > 3 for x in doc.lineas) or not ocr_disponible():
            return doc
        try:
            return _ocr_pdf(contenido)  # PDF escaneado: sin texto, se lee con OCR
        except Exception as e:  # noqa: BLE001
            raise ArchivoNoSoportado(f"El PDF parece escaneado y no pude leerlo con OCR: {e}") from e
    if re.search(r"\.(heic|heif)$", nombre):
        raise ArchivoNoSoportado("Las fotos HEIC del iPhone no se pueden leer: tómala en JPG (Ajustes › Cámara › Formatos › Más compatible) o descarga el PDF de la entidad")
    if _IMAGEN.search(nombre) or contenido[:3] == b"\xff\xd8\xff" or contenido[:8] == b"\x89PNG\r\n\x1a\n":
        if not ocr_disponible():
            raise ArchivoNoSoportado("Este servidor no tiene OCR para leer fotos. Descarga el certificado en PDF desde el portal de la entidad")
        try:
            return _ocr_imagen(contenido)
        except Exception as e:  # noqa: BLE001
            raise ArchivoNoSoportado(f"No pude leer la foto: {e}") from e
    raise ArchivoNoSoportado("Sube tus documentos en Excel (.xlsx), PDF o una foto (JPG o PNG)")
