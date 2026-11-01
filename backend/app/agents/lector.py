"""Agente Lector: convierte el reporte de exógena (Excel o PDF) en filas estructuradas.

Responsabilidad única: leer. No interpreta conceptos ni toca montos.
"""

import io
import re
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


def _leer_xlsx(contenido: bytes) -> DocumentoLeido:
    import openpyxl

    # read_only=False: la DIAN genera archivos con la dimensión de la hoja mal declarada
    wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=False)
    doc = DocumentoLeido(formato="xlsx")
    for ws in wb.worksheets:
        filas = [list(r) for r in ws.iter_rows(values_only=True)]
        _filas_tabulares(doc, filas)
        if doc.filas:
            break
    wb.close()
    return doc


def _leer_pdf(contenido: bytes) -> DocumentoLeido:
    import pdfplumber

    doc = DocumentoLeido(formato="pdf")
    filas: list[list[Any]] = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for pagina in pdf.pages[:40]:
            texto = pagina.extract_text() or ""
            for linea in texto.splitlines()[:15]:
                filas.append([linea.split(":")[0] + ":" if ":" in linea else linea, linea.split(":", 1)[1].strip() if ":" in linea else None])
            for tabla in pagina.extract_tables():
                filas.extend([list(f) for f in tabla])
    _filas_tabulares(doc, filas)
    return doc


def leer(contenido: bytes, nombre_archivo: str) -> DocumentoLeido:
    nombre = nombre_archivo.lower()
    if nombre.endswith(".xlsx") or contenido[:2] == b"PK":
        try:
            return _leer_xlsx(contenido)
        except Exception as e:  # noqa: BLE001
            raise ArchivoNoSoportado(f"No pude abrir el Excel: {e}") from e
    if nombre.endswith(".pdf") or contenido[:4] == b"%PDF":
        try:
            return _leer_pdf(contenido)
        except Exception as e:  # noqa: BLE001
            raise ArchivoNoSoportado(f"No pude abrir el PDF: {e}") from e
    raise ArchivoNoSoportado("Sube el reporte de exógena en Excel (.xlsx) o PDF")
