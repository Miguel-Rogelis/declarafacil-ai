"""Lee cantidades escritas como las escribe la gente en Colombia.

"300 mil", "1,5 millones", "2 palos", "500 lucas", "$3.600.000", "dos hijos"...
Se usa para verificar que una cifra que anotó la IA de verdad está en el mensaje
del usuario, y para el modo sin IA.
"""

import re
import unicodedata

_PALABRAS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "medio": 0.5,
}
_MULT = {
    "mil": 1_000, "lucas": 1_000, "luca": 1_000, "k": 1_000,
    "millon": 1_000_000, "millones": 1_000_000, "palo": 1_000_000, "palos": 1_000_000, "m": 1_000_000, "mm": 1_000_000,
    "millardo": 1_000_000_000, "millardos": 1_000_000_000,
}
_TOKEN = re.compile(r"(\d[\d.,]*|[a-z]+)")


def normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return s.replace("$", " ")


def _numero(token: str) -> float | None:
    t = token.strip(".,")
    if not t:
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):  # 3.600.000
        return float(t.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(,\d{3})+", t):  # 3,600,000
        return float(t.replace(",", ""))
    if re.fullmatch(r"\d+[.,]\d{1,2}", t):  # 1,5 / 2.5
        return float(t.replace(",", "."))
    if re.fullmatch(r"\d+", t):
        return float(t)
    return None


_GMF = re.compile(r"\b(4\s*x\s*1\.?000|4\s*por\s*mil|cuatro\s*por\s*mil)\b")


def cantidades(texto: str) -> list[float]:
    """Todas las cantidades del texto, aplicando 'mil', 'millones', etc."""
    tokens = _TOKEN.findall(_GMF.sub(" gmf ", normalizar(texto)))
    salida: list[float] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        valor = _numero(tok) if tok[0].isdigit() else _PALABRAS.get(tok)
        if valor is None:
            i += 1
            continue
        j = i + 1
        sin_multiplicador = j >= len(tokens) or tokens[j] not in _MULT
        if sin_multiplicador and re.fullmatch(r"(19[9]\d|20[0-3]\d)", tok):
            i = j  # es un año (2025), no una cantidad
            continue
        # "1 millon 500 mil" → suma de partes
        while j < len(tokens) and tokens[j] in _MULT:
            valor *= _MULT[tokens[j]]
            j += 1
            if j + 1 < len(tokens) and _numero(tokens[j] or "") is not None and tokens[j + 1] in ("mil", "lucas"):
                valor += _numero(tokens[j]) * 1_000  # type: ignore[operator]
                j += 2
        salida.append(valor)
        i = j
    return salida


def es_mensual(texto: str) -> bool:
    return bool(re.search(r"\b(al mes|mensual(es)?|cada mes|por mes|mensualmente)\b", normalizar(texto)))


def aparece(valor: float, texto: str, tolerancia: float = 0.01) -> bool:
    """¿La cifra (o su versión mensual ×12) sale del texto del usuario?"""
    for c in cantidades(texto):
        for candidato in (c, c * 12):
            if candidato and abs(candidato - valor) <= max(1.0, abs(valor) * tolerancia):
                return True
    return False
