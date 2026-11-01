"""Agente Asistente: responde dudas usando la base de conocimiento del proyecto.

Recupera las secciones más parecidas a la pregunta (búsqueda por palabras) y le
pide al modelo una respuesta corta apoyada en ellas. Sin modelo, devuelve la
sección más relevante tal cual.
"""

import re
import unicodedata
from functools import lru_cache

from pydantic import BaseModel

from app.config import settings
from app.llm import cliente

SISTEMA = """Eres el Asistente de DeclaraFácil: ayudas a personas sin formación contable con su declaración de renta en Colombia (año gravable 2025).
- Responde en español sencillo, máximo 110 palabras, tono cercano.
- Básate en la BASE DE CONOCIMIENTO y en el CONTEXTO del usuario. Si no está ahí, dilo y sugiere consultar a un contador o a la DIAN.
- No inventes cifras ni normas. No pidas datos personales como cédula o contraseñas.
- Si la pregunta no es sobre impuestos o sobre cómo usar DeclaraFácil, redirígela con amabilidad."""

_VACIAS = set("de la el los las un una y o a en que por para con del al se mi mis tu tus es como cual cuanto cuando donde si no lo le me te su sus".split())


class Seccion(BaseModel):
    titulo: str
    texto: str


class RespuestaAsistente(BaseModel):
    respuesta: str
    fuentes: list[str]
    modelo: str | None = None


def _tokens(texto: str) -> set[str]:
    s = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return {t for t in re.findall(r"[a-z0-9]+", s) if t not in _VACIAS and len(t) > 2}


@lru_cache(maxsize=1)
def _base() -> tuple[Seccion, ...]:
    secciones: list[Seccion] = []
    for archivo in sorted((settings.data_dir / "conocimiento").glob("*.md")):
        actual: Seccion | None = None
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.startswith("## "):
                if actual:
                    secciones.append(actual)
                actual = Seccion(titulo=linea[3:].strip(), texto="")
            elif actual and linea.strip():
                actual.texto += linea.strip() + " "
        if actual:
            secciones.append(actual)
    return tuple(secciones)


def buscar(pregunta: str, k: int = 3) -> list[Seccion]:
    q = _tokens(pregunta)
    puntajes = []
    for s in _base():
        titulo, cuerpo = _tokens(s.titulo), _tokens(s.texto)
        puntaje = 3 * len(q & titulo) + len(q & cuerpo)
        if puntaje:
            puntajes.append((puntaje, s))
    puntajes.sort(key=lambda x: -x[0])
    return [s for _, s in puntajes[:k]]


async def responder(mensaje: str, historial: list[dict[str, str]], contexto: str | None) -> RespuestaAsistente:
    relevantes = buscar(mensaje)
    if not cliente.disponible():
        if relevantes:
            s = relevantes[0]
            return RespuestaAsistente(respuesta=s.texto.strip(), fuentes=[s.titulo])
        return RespuestaAsistente(
            respuesta="No tengo esa respuesta en mi base. Te sugiero revisar el micrositio de renta de la DIAN o consultar a un contador.",
            fuentes=[],
        )
    base = "\n\n".join(f"### {s.titulo}\n{s.texto}" for s in relevantes) or "(sin coincidencias)"
    previo = "\n".join(f"{m.get('rol', 'usuario')}: {m.get('texto', '')[:300]}" for m in historial[-6:])
    usuario = f"BASE DE CONOCIMIENTO:\n{base}\n\nCONTEXTO DEL USUARIO:\n{contexto or '(sin cálculo todavía)'}\n\nCONVERSACIÓN:\n{previo}\n\nPREGUNTA: {mensaje}"
    try:
        r = await cliente.completar("asistente", SISTEMA, usuario, max_tokens=400)
        return RespuestaAsistente(respuesta=r.texto, fuentes=[s.titulo for s in relevantes], modelo=r.modelo)
    except Exception:  # noqa: BLE001
        if relevantes:
            return RespuestaAsistente(respuesta=relevantes[0].texto.strip(), fuentes=[relevantes[0].titulo])
        return RespuestaAsistente(respuesta="Ahora mismo no puedo consultar el modelo. Intenta de nuevo en un momento.", fuentes=[])
