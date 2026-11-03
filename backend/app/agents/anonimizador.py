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
    # El texto completo repite lo mismo que el encabezado y las filas: se limpia sin contarlo otra vez
    antes = contador
    copia.lineas = [limpiar(x) or "" for x in copia.lineas]
    copia.tablas = [[[limpiar(c) or "" for c in fila] for fila in t] for t in copia.tablas]
    contador = antes
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


# ---------- Certificados ----------

_ETIQUETA_ID = re.compile(
    r"^(c\.?c\.?|cc|t\.?i\.?|c\.?e\.?|cedula|identificacion:?|documento:?|no\.?|n[°º]|numero|#|cuenta:?|producto:?|tarjeta:?|nit:?|celular:?|telefono:?)$",
    re.IGNORECASE,
)
_LINEA_PERSONAL = re.compile(
    r"nombres?\b|apellidos?|senor(a|es)?\b|\btitular\s*:|\bcliente\s*:|afiliado\s*:|beneficiario\s*:|direccion|correo|e-?mail|telefono|celular",
)
_DIGITOS = re.compile(r"\d")


def _sin_tildes(t: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _enmascarar_linea(linea: str) -> tuple[str, int]:
    """Deja solo los últimos 4 dígitos de cédulas, cuentas y teléfonos. Las cifras en pesos no cambian."""
    tokens = linea.split(" ")
    salida, n, tras_etiqueta = [], 0, False
    for t in tokens:
        limpio = t.strip("$():;,")
        digitos = re.sub(r"\D", "", limpio)
        es_numero = bool(digitos) and bool(re.fullmatch(r"[\d.,\-*xX]+", limpio))
        if es_numero and len(digitos) >= 4:
            empresa = len(digitos) in (9, 10) and digitos[0] in "89" and not re.fullmatch(r"\d{1,3}([.,]\d{3}){2,}([.,]\d{1,2})?", limpio)
            sin_formato_largo = len(digitos) >= 10 and not re.fullmatch(r"\d{1,3}([.,]\d{3})+([.,]\d{1,2})?", limpio)
            if (tras_etiqueta and not empresa) or sin_formato_largo and not empresa:
                salida.append(t.replace(limpio, "****" + digitos[-4:]))
                n += 1
                tras_etiqueta = False
                continue
        if es_numero:
            tras_etiqueta = False
        elif _ETIQUETA_ID.match(_sin_tildes(limpio)):
            tras_etiqueta = True
        salida.append(t)
    return " ".join(salida), n


_TITULO_TRIBUTARIO = re.compile(r"cuenta|cdt|saldo|credito|tarjeta|producto|interes|retencion|certific|pagos?\b|aportes?|concepto|periodo|valor")
_PARENTESCO = re.compile(r"\b(hij[oa]s?|conyuge|esposa|esposo|companer[oa] permanente|padre|madre|herman[oa])\b")


def _marca(n: str) -> str:
    """Línea con datos personales: se borra, pero se deja el parentesco (dice si hay un dependiente, no quién es)."""
    m = _PARENTESCO.search(n)
    return f"[DATOS PERSONALES] ({m.group(1)})" if m else "[DATOS PERSONALES]"


def anonimizar_certificado(doc: DocumentoLeido) -> tuple[DocumentoLeido, int]:
    """Quita datos personales del texto de un certificado antes de seguir.

    - Las líneas con nombre, dirección o teléfono de la persona (y la línea de valores que
      viene después de esos títulos) se reemplazan por "[DATOS PERSONALES]".
    - Cédulas, cuentas y teléfonos quedan con sus últimos 4 dígitos.
    Las cifras en pesos y el NIT de la entidad se conservan: los necesita el Extractor.
    """
    copia = doc.model_copy(deep=True)
    contador = 0
    nuevas: list[str] = []
    saltar_siguiente = False
    for linea in copia.lineas:
        n = _sin_tildes(linea)
        if _LINEA_PERSONAL.search(n) and not re.search(r"retenedor|pagador|entidad|razon social|producto", n):
            nuevas.append(_marca(n))
            contador += 1
            # En los formularios el valor va en la línea siguiente, sin títulos
            saltar_siguiente = True
            continue
        if saltar_siguiente:
            saltar_siguiente = False
            if not re.search(r"\$|\d{1,3}[.,]\d{3}[.,]\d{3}", linea) and not _TITULO_TRIBUTARIO.search(n):
                nuevas.append(_marca(n))
                contador += 1
                continue
        limpia, k = _enmascarar_linea(linea)
        contador += k
        nuevas.append(limpia)
    copia.lineas = nuevas
    tablas = []
    for tabla in copia.tablas:
        filas = []
        for fila in tabla:
            celdas = []
            for c in fila:
                if _LINEA_PERSONAL.search(_sin_tildes(c)) and not re.search(r"retenedor|pagador|entidad|razon social|producto", _sin_tildes(c)):
                    celdas.append("[DATOS PERSONALES]")
                    contador += 1
                    continue
                limpia, k = _enmascarar_linea(c)
                contador += k
                celdas.append(limpia)
            filas.append(celdas)
        tablas.append(filas)
    copia.tablas = tablas
    copia.identificacion = None
    copia.nombre = None
    return copia, contador
