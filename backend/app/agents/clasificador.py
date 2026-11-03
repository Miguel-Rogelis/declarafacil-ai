"""Agente Clasificador: ¿qué documento es? ¿de qué año?

Distingue el reporte de información exógena de los certificados que la complementan
(ingresos y retenciones 220, banco, crédito de vivienda, medicina prepagada, aportes
voluntarios, cesantías, retenciones de independientes, predial y la declaración del año
anterior). Primero usa reglas (rápido y gratis). Solo si no reconoce el documento consulta
un modelo, y le envía únicamente títulos sin cifras ni datos personales.
"""

import re
import unicodedata
from collections import Counter

from pydantic import BaseModel

from app.agents.base import NOMBRE_TIPO, DocumentoLeido
from app.llm import cliente

SISTEMA = (
    "Eres un clasificador de documentos tributarios colombianos. Responde SOLO un JSON con las llaves "
    '"tipo" (una de: ' + ", ".join(NOMBRE_TIPO) + '), "anio" (entero o null), "confianza" (0 a 1) y "motivo" (máx. 20 palabras). '
    "exogena = reporte de información exógena de la DIAN (lo que bancos, empleadores y fondos reportaron). "
    "certificado_220 = certificado de ingresos y retenciones por rentas de trabajo y de pensiones. "
    "certificado_bancario = certificado tributario de un banco con saldos, intereses, retenciones o 4x1000. "
    "declaracion_anterior = formulario 210 de un año anterior."
)


class Clasificacion(BaseModel):
    es_exogena: bool
    anio: int | None
    confianza: float
    motivo: str
    modelo: str | None = None
    tipo: str = "exogena"


def _n(t: str) -> str:
    s = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).lower()


def _por_reglas(doc: DocumentoLeido) -> Clasificacion:
    puntos = 0.0
    encabezado = " ".join(doc.lineas_encabezado + [doc.titulo]).lower()
    if "reportada por terceros" in encabezado or "exógena" in encabezado or "exogena" in encabezado:
        puntos += 0.45
    if doc.topes:
        puntos += 0.25
    if doc.filas:
        puntos += 0.15
    if any(f.uso_sugerido for f in doc.filas):
        puntos += 0.15
    return Clasificacion(
        es_exogena=puntos >= 0.5,
        anio=doc.anio,
        confianza=round(min(puntos, 1.0), 2),
        motivo="Encabezado, topes y columnas coinciden con el formato DIAN" if puntos >= 0.7 else "Formato parcialmente reconocido",
    )


# (tipo, patrones que lo identifican, puntos de cada uno). Se busca en el texto del documento.
_SENALES: list[tuple[str, list[tuple[str, float]]]] = [
    ("certificado_220", [(r"certificado de ingresos y retenciones", 0.6), (r"rentas de trabajo y de pensiones", 0.3), (r"\b220\b", 0.15),
                         (r"pagos? por salarios", 0.2), (r"agente retenedor|pagador", 0.1)]),
    ("declaracion_anterior", [(r"declaracion de renta y complementario", 0.6), (r"personas naturales y asimiladas", 0.2), (r"\b210\b", 0.15),
                              (r"impuesto neto de renta", 0.2), (r"renta liquida gravable", 0.1)]),
    ("certificado_vivienda", [(r"credito (de )?vivienda|credito hipotecario|leasing habitacional|prestamo de vivienda", 0.5),
                              (r"intereses (pagados|cancelados)", 0.2), (r"art(iculo|\.)? 119", 0.2), (r"correccion monetaria", 0.1)]),
    ("certificado_prepagada", [(r"medicina prepagada|plan(es)? complementario|poliza de salud|plan de salud", 0.6), (r"\b387\b", 0.15),
                               (r"valor (total )?pagado|pagos realizados", 0.15)]),
    ("certificado_voluntarios", [(r"pensiones voluntarias|fondo voluntario de pensiones|aportes voluntarios", 0.5),
                                 (r"\bafc\b|ahorro para el fomento de la construccion|\bavc\b", 0.5), (r"126-1|126-4", 0.2)]),
    ("certificado_cesantias", [(r"fondo de cesantias|certificado de cesantias|saldo de cesantias", 0.6), (r"cesantias", 0.2)]),
    ("certificado_retencion", [(r"certificado de retencion en la fuente", 0.6), (r"base (sometida a retencion|de retencion|gravable)", 0.2),
                               (r"art(iculo|\.)? 381", 0.15), (r"valor retenido", 0.15)]),
    ("predial", [(r"impuesto predial", 0.6), (r"avaluo catastral", 0.3), (r"\bchip\b|matricula inmobiliaria", 0.1)]),
    ("certificado_bancario", [(r"certificado tributario|certificacion tributaria|informacion tributaria", 0.5), (r"\bbanco\b|bancolombia|davivienda|bbva|nequi|daviplata", 0.2),
                              (r"icetex|credito educativo", 0.45),
                              (r"cuenta de ahorros?|cuenta corriente|\bcdt\b|certificado de deposito", 0.2),
                              (r"saldo (a|al) 31|saldo a diciembre|saldo final", 0.2), (r"gravamen a los movimientos financieros|\bgmf\b|4 ?x ?1000", 0.15),
                              (r"rendimientos financieros|intereses (abonados|pagados|recibidos)", 0.1)]),
]

_ANIO = [
    re.compile(r"a[nñ]o gravable:?\s*(20\d{2})"),
    re.compile(r"a[nñ]o:?\s*(20\d{2})\b"),
    re.compile(r"31 de diciembre de(l)?\s*(?:a[nñ]o\s*)?(20\d{2})"),
    re.compile(r"(?:31|dic(?:iembre)?)[/\-. ](?:12|dic(?:iembre)?)[/\-. ](20\d{2})"),
    re.compile(r"(?:vigencia|periodo|corte)[^0-9]{0,30}(20\d{2})"),
]


def anio_de(lineas: list[str]) -> int | None:
    """El año al que se refiere un certificado (el que más se repite en frases de fecha de corte)."""
    vistos: Counter[int] = Counter()
    for linea in lineas[:400]:
        n = _n(linea)
        for patron in _ANIO:
            for m in patron.finditer(n):
                vistos[int(m.group(m.lastindex or 1))] += 1
    return vistos.most_common(1)[0][0] if vistos else None


def tipo_por_reglas(doc: DocumentoLeido, nombre_archivo: str = "") -> tuple[str, float]:
    texto = _n(" ".join(doc.lineas[:250]) + " " + nombre_archivo.replace("_", " "))
    puntajes = {tipo: sum(p for patron, p in senales if re.search(patron, texto)) for tipo, senales in _SENALES}
    tipo, puntos = max(puntajes.items(), key=lambda x: x[1])
    # Un certificado de ingresos y retenciones dice "retenciones" y puede nombrar cesantías: gana por su título
    if puntajes["certificado_220"] >= 0.6:
        tipo, puntos = "certificado_220", puntajes["certificado_220"]
    return (tipo, min(puntos, 1.0)) if puntos >= 0.45 else ("desconocido", puntos)


def _muestra_para_ia(doc: DocumentoLeido) -> str:
    """Solo títulos: sin cifras, sin líneas con datos personales."""
    salida = []
    for linea in doc.lineas[:60]:
        if "[DATOS PERSONALES]" in linea:
            continue
        t = re.sub(r"\d", "#", linea)
        if re.search(r"[a-záéíóúñ]{4,}", t, re.IGNORECASE) and not re.fullmatch(r"[A-ZÁÉÍÓÚÑ ]{6,}", t.strip()):
            salida.append(t[:120])
        if len(salida) >= 15:
            break
    return "\n".join(salida)


async def clasificar(doc: DocumentoLeido, nombre_archivo: str = "") -> Clasificacion:
    base = _por_reglas(doc)
    if base.es_exogena and base.confianza >= 0.7:
        return base
    if doc.filas and base.es_exogena and not doc.lineas:
        return base
    tipo, confianza = tipo_por_reglas(doc, nombre_archivo)
    if base.es_exogena and confianza < 0.6:
        return base
    if tipo != "desconocido" or not cliente.disponible():
        return Clasificacion(es_exogena=False, anio=anio_de(doc.lineas), confianza=round(confianza, 2), tipo=tipo,
                             motivo=f"{NOMBRE_TIPO[tipo]}, reconocido con reglas" if tipo != "desconocido" else "No reconocí el tipo de documento")
    muestra = _muestra_para_ia(doc)
    if not muestra:
        return Clasificacion(es_exogena=False, anio=anio_de(doc.lineas), confianza=0.2, tipo="desconocido", motivo="El documento casi no tiene texto")
    try:
        r = await cliente.completar("clasificador", SISTEMA, muestra, json_mode=True, max_tokens=200)
        j = cliente.extraer_json(r.texto)
        tipo_ia = str(j.get("tipo", "desconocido"))
        if tipo_ia not in NOMBRE_TIPO:
            tipo_ia = "desconocido"
        return Clasificacion(
            es_exogena=tipo_ia == "exogena",
            anio=int(j["anio"]) if j.get("anio") else anio_de(doc.lineas),
            confianza=float(j.get("confianza", 0.5)),
            motivo=str(j.get("motivo", ""))[:160],
            modelo=r.modelo,
            tipo=tipo_ia,
        )
    except Exception:  # noqa: BLE001 - si el modelo falla, se queda la decisión por reglas
        return Clasificacion(es_exogena=False, anio=anio_de(doc.lineas), confianza=0.2, tipo="desconocido", motivo="No reconocí el tipo de documento")
