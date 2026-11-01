"""Agente Anonimizador: quita datos personales antes de que algo salga del servidor.

- Cédula y nombre del contribuyente → "[CONTRIBUYENTE]" / "[ID]".
- Números de cuenta y tarjetas → solo los últimos 4 dígitos.
- Informantes que son personas naturales → "[PERSONA NATURAL]".
Guarda aparte los dos últimos dígitos de la cédula (los necesita el Auditor para
el vencimiento) y no conserva el resto.
"""

import re

from app.agents.base import DocumentoLeido

_CUENTA = re.compile(r"(?<!\d)(\d{4,})(\d{4})(?!\d)")
_NUMEROS_LARGOS = re.compile(r"\b\d{6,}\b")


def _parece_empresa(nit: str | None) -> bool:
    digitos = re.sub(r"\D", "", nit or "")
    return len(digitos) == 9 and digitos[0] in "89"


def _palabras_nombre(nombre: str | None) -> list[str]:
    return [p for p in re.split(r"\s+", (nombre or "").strip()) if len(p) >= 3]


def anonimizar(doc: DocumentoLeido) -> tuple[DocumentoLeido, str | None, int]:
    """Devuelve (documento anonimizado, últimos dos dígitos del NIT, cantidad de datos enmascarados)."""
    ident = re.sub(r"\D", "", doc.identificacion or "")
    ultimos = ident[-2:] if len(ident) >= 2 else None
    palabras = _palabras_nombre(doc.nombre)
    contador = 0

    def limpiar(texto: str | None) -> str | None:
        nonlocal contador
        if texto is None:
            return None
        nuevo = texto
        if ident:
            nuevo, n = re.subn(re.escape(ident), "[ID]", nuevo)
            contador += n
        for p in palabras:
            nuevo, n = re.subn(rf"\b{re.escape(p)}\b", "[NOMBRE]", nuevo, flags=re.IGNORECASE)
            contador += n
        nuevo, n = _CUENTA.subn(lambda m: "****" + m.group(2), nuevo)
        contador += n
        return nuevo

    copia = doc.model_copy(deep=True)
    if copia.identificacion:
        copia.identificacion = "[ID]"
        contador += 1
    if copia.nombre:
        copia.nombre = "[CONTRIBUYENTE]"
        contador += 1
    copia.lineas_encabezado = [limpiar(x) or "" for x in copia.lineas_encabezado]
    for fila in copia.filas:
        nit_limpio = re.sub(r"\D", "", fila.nit_informante or "")
        if nit_limpio and (nit_limpio == ident or not _parece_empresa(nit_limpio)):
            fila.nit_informante = "[ID]" if nit_limpio == ident else "[NIT PERSONA]"
            fila.informante = "[CONTRIBUYENTE]" if nit_limpio == ident else "[PERSONA NATURAL]"
            contador += 2
        fila.informante = limpiar(fila.informante)
        fila.detalle = limpiar(fila.detalle) or fila.detalle
        fila.info_adicional = limpiar(fila.info_adicional)
        if fila.info_adicional:
            fila.info_adicional, n = _NUMEROS_LARGOS.subn(lambda m: "****" + m.group(0)[-4:], fila.info_adicional)
            contador += n
    return copia, ultimos, contador
