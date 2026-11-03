"""Base de conocimiento del Asistente y valores de cada año gravable.

Las respuestas de la base (data/conocimiento/*.md) tienen marcadores como {tope_ingresos}
que se llenan con las reglas del año elegido: la misma pregunta responde con las cifras
de 2021, 2023 o 2025 según el año. La búsqueda sin IA usa raíces de palabras, peso por
rareza (IDF) y las frases de la línea "También:" de cada sección.
"""

import math
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from app.agents import numeros
from app.config import settings
from app.tax import reglas as repo_reglas

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def pesos(v: float) -> str:
    return "$" + f"{v:,.0f}".replace(",", ".")


def miles(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def fecha_texto(d: date) -> str:
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


def norm(texto: str) -> str:
    """Minúsculas sin tildes y con las abreviaturas del chat expandidas (q → que)."""
    s = numeros.normalizar(texto)
    reemplazos = {r"\bq\b": "que", r"\b(xq|pq|xk)\b": "porque", r"\b(tb|tmb)\b": "tambien", r"\bdnd\b": "donde", r"\bk\b(?<!\d k)": "que", r"\bpa\b": "para"}
    for patron, nuevo in reemplazos.items():
        s = re.sub(patron, nuevo, s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- Datos del año gravable ----------


def _vencimientos(r: dict[str, Any]) -> list[date]:
    return sorted(date.fromisoformat(v) for v in (r.get("vencimientos") or {}).values())


def fecha_limite(anio: int, digitos: str) -> date | None:
    calendario = repo_reglas.cargar(anio).get("vencimientos") or {}
    n = int(digitos) or 100
    for clave, fecha in calendario.items():
        desde, hasta = int(clave[:2]), int(clave[3:]) or 100
        if desde <= n <= hasta:
            return date.fromisoformat(fecha)
    return None


def valores_anio(anio: int) -> dict[str, str]:
    """Valores que llenan la base de conocimiento para el año gravable elegido."""
    r = repo_reglas.cargar(anio)
    uvt = float(r["uvt"])
    cg, t, go, div = r["cedula_general"], r["topes_obligacion_uvt"], r["ganancias_ocasionales"], r["dividendos"]
    hoy = date.today().year
    uvt_hoy = repo_reglas.uvt_del_anio(hoy) or float(r.get("uvt_anio_presentacion") or uvt)
    venc = _vencimientos(r)
    if cg.get("dependiente_adicional_uvt"):
        dependientes = (
            f"Por el primero puedes restar el 10 % de tus ingresos de trabajo (máximo {miles(cg['dependiente_art387_tope_uvt'])} UVT al año) "
            f"y además {miles(cg['dependiente_adicional_uvt'])} UVT por cada dependiente, hasta {cg.get('dependiente_adicional_max', 4)}."
        )
    else:
        dependientes = (
            f"Puedes restar el 10 % de tus ingresos de trabajo (máximo {miles(cg['dependiente_art387_tope_uvt'])} UVT al año). "
            f"La deducción adicional de 72 UVT por dependiente empezó en el año gravable 2023, así que en {anio} no aplica."
        )
    if cg.get("factura_electronica_pct"):
        factura = (
            f"Puedes restar el 1 % de tus compras de bienes y servicios con factura electrónica a tu nombre, pagadas con tarjeta o transferencia, "
            f"hasta {miles(cg['factura_electronica_tope_uvt'])} UVT al año ({pesos(cg['factura_electronica_tope_uvt'] * uvt)} en {anio}). "
            "No entra en el límite del 40 %. La exógena trae el monto que la DIAN considera para este beneficio."
        )
    else:
        factura = f"Es un beneficio que existe desde el año gravable 2023 (Ley 2277 de 2022). Para el año gravable {anio} todavía no aplicaba."
    if div.get("regimen") == "tabla_propia":
        dividendos = (
            f"En {anio} tenían su propia tabla: los no gravados hasta 300 UVT no pagaban y lo que pasara de ahí pagaba el 10 %. "
            f"Los gravados pagaban primero el {div['tarifa_subcedula_gravada'] * 100:.0f} %."
        )
    else:
        dividendos = (
            "Los no gravados se suman a la tabla de tarifas del art. 241 junto con tus otras rentas, y tienes un descuento del 19 % "
            f"sobre lo que pase de 1.090 UVT. Los gravados pagan primero el {div['tarifa_subcedula_gravada'] * 100:.0f} % y el resto se suma a la tabla."
        )
    return {
        "anio": str(anio),
        "anio_presenta": str(anio + 1),
        "anio_hoy": str(hoy),
        "uvt": pesos(uvt),
        "uvt_hoy": pesos(uvt_hoy),
        "tope_patrimonio": pesos(t["patrimonio_bruto"] * uvt),
        "tope_ingresos": pesos(t["ingresos_brutos"] * uvt),
        "venc_desde": fecha_texto(venc[0]) if venc else "agosto",
        "venc_hasta": fecha_texto(venc[-1]) if venc else "octubre",
        "sancion_minima": pesos(round(10 * uvt_hoy, -3)),
        "tramo0": pesos(1090 * uvt),
        "exenta_tope_uvt": miles(cg["renta_exenta_laboral_tope_uvt"]),
        "limite_uvt": miles(cg["limite_rentas_exentas_deducciones_uvt"]),
        "limite_pesos": pesos(cg["limite_rentas_exentas_deducciones_uvt"] * uvt),
        "dependientes_texto": dependientes,
        "factura_texto": factura,
        "dividendos_texto": dividendos,
        "go_tarifa": f"{go['tarifa_general'] * 100:.0f} %",
        "go_casa_uvt": miles(go["exencion_venta_casa_habitacion_uvt"]),
    }


def anios_vigentes() -> list[int]:
    return sorted(a["anio_gravable"] for a in repo_reglas.anios_disponibles() if a["estado"] == "vigente")


# ---------- Base de conocimiento ----------

_VACIAS = set(
    "de la el los las un una y o a en que por para con del al se mi mis tu tus es como cual cuanto cuando donde si no lo le me te su sus hay "
    "eso esto esa este hola buenas pues porfa favor quiero saber necesito ayuda oye bueno entonces mas muy ya estoy esta son ser fue era "
    "algo alguien cosa cosas tipo osea cuentame dime explicame puedes puedo puede ayudar ayudame ayuda hago hacer hace digame sabes".split()
)


@dataclass(frozen=True)
class _Seccion:
    titulo: str
    alias: tuple[str, ...]
    texto: str


class SeccionKB(BaseModel):
    titulo: str
    texto: str


def _raiz(t: str) -> str:
    if t.isdigit():
        return t
    for suf in ("aciones", "acion", "iones", "ion", "iendo", "ando", "aron", "ieron", "amos", "emos", "imos", "ados", "adas", "idos", "idas", "ado", "ada", "ido", "ida", "ar", "er", "ir", "as", "es", "os", "a", "e", "o", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            t = t[: -len(suf)]
            break
    return t[:6]


def raices(texto: str) -> set[str]:
    return {_raiz(t) for t in re.findall(r"[a-z0-9]+", norm(texto)) if t not in _VACIAS and len(t) >= 3}


@lru_cache(maxsize=1)
def _crudas() -> tuple[_Seccion, ...]:
    secciones: list[_Seccion] = []
    for archivo in sorted((settings.data_dir / "conocimiento").glob("*.md")):
        titulo, alias, texto = None, (), ""
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.startswith("## "):
                if titulo:
                    secciones.append(_Seccion(titulo, alias, texto.strip()))
                titulo, alias, texto = linea[3:].strip(), (), ""
            elif titulo and linea.startswith("También:"):
                alias = tuple(a.strip() for a in linea[8:].split("|") if a.strip())
            elif titulo and linea.strip() and not linea.startswith("#"):
                texto += linea.strip() + " "
        if titulo:
            secciones.append(_Seccion(titulo, alias, texto.strip()))
    return tuple(secciones)


@lru_cache(maxsize=1)
def _indice() -> tuple[dict[str, float], list[tuple[set[str], set[str], tuple[str, ...]]]]:
    docs = []
    df: dict[str, int] = {}
    for s in _crudas():
        cabeza = raices(s.titulo + " " + " ".join(s.alias))
        cuerpo = raices(s.texto)
        for t in cabeza | cuerpo:
            df[t] = df.get(t, 0) + 1
        docs.append((cabeza, cuerpo, tuple(norm(a) for a in (s.titulo.strip("¿?"), *s.alias))))
    n = len(docs)
    idf = {t: math.log(1 + n / c) for t, c in df.items()}
    return idf, docs


def _rellenar(texto: str, valores: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: valores.get(m.group(1), m.group(0)), texto)


def base_del_anio(anio: int) -> list[SeccionKB]:
    v = valores_anio(anio)
    return [SeccionKB(titulo=_rellenar(s.titulo, v), texto=_rellenar(s.texto, v)) for s in _crudas()]


def puntajes(pregunta: str) -> list[tuple[float, int]]:
    idf, docs = _indice()
    q = raices(pregunta)
    frase = norm(pregunta)
    definicion = bool(re.search(r"\bque (es|son|significa|quiere decir)\b", frase))
    salida = []
    for i, (cabeza, cuerpo, frases) in enumerate(docs):
        p = sum(idf.get(t, 0) * (2.5 if t in cabeza else 1.0 if t in cuerpo else 0) for t in q)
        if any(f and re.search(r"\b" + re.escape(f) + r"\b", frase) for f in frases):
            p += 6
        if p and definicion and re.match(r"que (es|son)\b", frases[0]):
            p += 2.5  # "¿qué es…?" prefiere las secciones que definen algo
        elif not (q & cabeza):
            p *= 0.5  # solo coincide con palabras sueltas del texto: coincidencia débil
        if p:
            salida.append((p, i))
    return sorted(salida, reverse=True)


def buscar(pregunta: str, anio: int = 2025, k: int = 3, minimo: float = 0.0) -> list[SeccionKB]:
    base = base_del_anio(anio)
    return [base[i] for p, i in puntajes(pregunta)[:k] if p >= minimo]
