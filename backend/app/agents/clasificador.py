"""Agente Clasificador: ¿el archivo es un reporte de información exógena? ¿de qué año?

Primero usa reglas (rápido y gratis). Solo si la confianza es baja consulta un
modelo, y le envía únicamente el encabezado ya anonimizado.
"""

from pydantic import BaseModel

from app.agents.base import DocumentoLeido
from app.llm import cliente

SISTEMA = (
    "Eres un clasificador de documentos tributarios colombianos. Responde SOLO un JSON con las llaves "
    '"es_exogena" (bool), "anio" (entero o null), "confianza" (0 a 1) y "motivo" (máx. 20 palabras). '
    "Un reporte de información exógena de la DIAN lista lo que terceros (bancos, empleadores, fondos) "
    "reportaron sobre una persona: conceptos como salarios, saldos, retenciones y topes."
)


class Clasificacion(BaseModel):
    es_exogena: bool
    anio: int | None
    confianza: float
    motivo: str
    modelo: str | None = None


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


async def clasificar(doc: DocumentoLeido) -> Clasificacion:
    base = _por_reglas(doc)
    if base.confianza >= 0.7 or not cliente.disponible():
        return base
    muestra = "\n".join(doc.lineas_encabezado[:15])
    muestra += "\nConceptos: " + "; ".join(f.detalle for f in doc.filas[:15])
    try:
        r = await cliente.completar("clasificador", SISTEMA, muestra, json_mode=True, max_tokens=200)
        j = cliente.extraer_json(r.texto)
        return Clasificacion(
            es_exogena=bool(j.get("es_exogena")),
            anio=int(j["anio"]) if j.get("anio") else base.anio,
            confianza=float(j.get("confianza", 0.5)),
            motivo=str(j.get("motivo", ""))[:160],
            modelo=r.modelo,
        )
    except Exception:  # noqa: BLE001 - si el modelo falla, se queda la decisión por reglas
        return base
