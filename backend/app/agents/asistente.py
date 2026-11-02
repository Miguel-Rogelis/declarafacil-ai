"""Agente Asistente: la conversación con el usuario.

Responsabilidad única: entender lo que el usuario escribe, contestarle y decidir qué
acción pide (anotar un dato, calcular, cambiar de año, abrir la carga de la exógena).
No guía la conversación: responde a lo que el usuario dice, de inicio a fin.

El código valida todo lo que propone la IA antes de aplicarlo:
- Solo se anotan campos de una lista cerrada, con rangos y tipos fijos.
- Una cifra en pesos solo se anota si aparece en el mensaje del usuario (o es su
  valor mensual × 12). Así la IA no puede inventar montos.
- Si la respuesta de la IA trae una cifra que no está en sus datos de entrada, se
  descarta y se responde con reglas.
Sin modelo disponible, responde con reglas y la base de conocimiento.
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel

from app.agents import numeros
from app.agents.base import FilaInterpretada
from app.config import settings
from app.llm import cliente
from app.orquestador import Respuestas, SolicitudLiquidacion, construir_declaracion
from app.tax import reglas as repo_reglas
from app.tax.modelos import ItemPatrimonio, Obligacion
from app.tax.motor import liquidar

log = logging.getLogger(__name__)

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _pesos(v: float) -> str:
    return "$" + f"{v:,.0f}".replace(",", ".")


def _miles(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _fecha(d: date) -> str:
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


def _norm(texto: str) -> str:
    """Minúsculas sin tildes y con las abreviaturas del chat expandidas (q → que)."""
    s = numeros.normalizar(texto)
    reemplazos = {r"\bq\b": "que", r"\b(xq|pq|xk)\b": "porque", r"\b(tb|tmb)\b": "tambien", r"\bdnd\b": "donde", r"\bk\b(?<!\d k)": "que", r"\bpa\b": "para"}
    for patron, nuevo in reemplazos.items():
        s = re.sub(patron, nuevo, s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- Datos del año gravable ----------


def _vencimientos(r: dict[str, Any]) -> list[date]:
    return sorted(date.fromisoformat(v) for v in (r.get("vencimientos") or {}).values())


def _fecha_limite(anio: int, digitos: str) -> date | None:
    calendario = repo_reglas.cargar(anio).get("vencimientos") or {}
    n = int(digitos) or 100
    for clave, fecha in calendario.items():
        desde, hasta = int(clave[:2]), int(clave[3:]) or 100
        if desde <= n <= hasta:
            return date.fromisoformat(fecha)
    return None


def _valores_anio(anio: int) -> dict[str, str]:
    """Valores que llenan la base de conocimiento para el año gravable elegido."""
    r = repo_reglas.cargar(anio)
    uvt = float(r["uvt"])
    cg, t, go, div = r["cedula_general"], r["topes_obligacion_uvt"], r["ganancias_ocasionales"], r["dividendos"]
    hoy = date.today().year
    uvt_hoy = repo_reglas.uvt_del_anio(hoy) or float(r.get("uvt_anio_presentacion") or uvt)
    venc = _vencimientos(r)
    if cg.get("dependiente_adicional_uvt"):
        dependientes = (
            f"Por el primero puedes restar el 10 % de tus ingresos de trabajo (máximo {_miles(cg['dependiente_art387_tope_uvt'])} UVT al año) "
            f"y además {_miles(cg['dependiente_adicional_uvt'])} UVT por cada dependiente, hasta {cg.get('dependiente_adicional_max', 4)}."
        )
    else:
        dependientes = (
            f"Puedes restar el 10 % de tus ingresos de trabajo (máximo {_miles(cg['dependiente_art387_tope_uvt'])} UVT al año). "
            f"La deducción adicional de 72 UVT por dependiente empezó en el año gravable 2023, así que en {anio} no aplica."
        )
    if cg.get("factura_electronica_pct"):
        factura = (
            f"Puedes restar el 1 % de tus compras de bienes y servicios con factura electrónica a tu nombre, pagadas con tarjeta o transferencia, "
            f"hasta {_miles(cg['factura_electronica_tope_uvt'])} UVT al año ({_pesos(cg['factura_electronica_tope_uvt'] * uvt)} en {anio}). "
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
        "uvt": _pesos(uvt),
        "uvt_hoy": _pesos(uvt_hoy),
        "tope_patrimonio": _pesos(t["patrimonio_bruto"] * uvt),
        "tope_ingresos": _pesos(t["ingresos_brutos"] * uvt),
        "venc_desde": _fecha(venc[0]) if venc else "agosto",
        "venc_hasta": _fecha(venc[-1]) if venc else "octubre",
        "sancion_minima": _pesos(round(10 * uvt_hoy, -3)),
        "tramo0": _pesos(1090 * uvt),
        "exenta_tope_uvt": _miles(cg["renta_exenta_laboral_tope_uvt"]),
        "limite_uvt": _miles(cg["limite_rentas_exentas_deducciones_uvt"]),
        "limite_pesos": _pesos(cg["limite_rentas_exentas_deducciones_uvt"] * uvt),
        "dependientes_texto": dependientes,
        "factura_texto": factura,
        "dividendos_texto": dividendos,
        "go_tarifa": f"{go['tarifa_general'] * 100:.0f} %",
        "go_casa_uvt": _miles(go["exencion_venta_casa_habitacion_uvt"]),
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


def _raices(texto: str) -> set[str]:
    return {_raiz(t) for t in re.findall(r"[a-z0-9]+", _norm(texto)) if t not in _VACIAS and len(t) >= 3}


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
        cabeza = _raices(s.titulo + " " + " ".join(s.alias))
        cuerpo = _raices(s.texto)
        for t in cabeza | cuerpo:
            df[t] = df.get(t, 0) + 1
        docs.append((cabeza, cuerpo, tuple(_norm(a) for a in (s.titulo.strip("¿?"), *s.alias))))
    n = len(docs)
    idf = {t: math.log(1 + n / c) for t, c in df.items()}
    return idf, docs


def _rellenar(texto: str, valores: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: valores.get(m.group(1), m.group(0)), texto)


def base_del_anio(anio: int) -> list[SeccionKB]:
    v = _valores_anio(anio)
    return [SeccionKB(titulo=_rellenar(s.titulo, v), texto=_rellenar(s.texto, v)) for s in _crudas()]


def _puntajes(pregunta: str) -> list[tuple[float, int]]:
    idf, docs = _indice()
    q = _raices(pregunta)
    frase = _norm(pregunta)
    salida = []
    for i, (cabeza, cuerpo, frases) in enumerate(docs):
        p = sum(idf.get(t, 0) * (2.5 if t in cabeza else 1.0 if t in cuerpo else 0) for t in q)
        if any(f and re.search(r"\b" + re.escape(f) + r"\b", frase) for f in frases):
            p += 6
        elif not (q & cabeza):
            p *= 0.5  # solo coincide con palabras sueltas del texto: coincidencia débil
        if p:
            salida.append((p, i))
    return sorted(salida, reverse=True)


def buscar(pregunta: str, anio: int = 2025, k: int = 3, minimo: float = 0.0) -> list[SeccionKB]:
    base = base_del_anio(anio)
    return [base[i] for p, i in _puntajes(pregunta)[:k] if p >= minimo]


# ---------- Campos que el chat puede anotar ----------

Tipo = Literal["pesos", "entero", "digitos", "booleano", "item"]

# clave → (campo en Respuestas, tipo, etiqueta, mínimo, máximo)
CAMPOS: dict[str, tuple[str, Tipo, str, float, float]] = {
    "salarios": ("salarios_no_reportados", "pesos", "Salarios del año", 0, 5e10),
    "honorarios": ("honorarios_no_reportados", "pesos", "Honorarios o servicios", 0, 5e10),
    "costos_independiente": ("costos_independiente", "pesos", "Costos del trabajo independiente", 0, 5e10),
    "arriendos": ("arriendos_no_reportados", "pesos", "Arriendos recibidos", 0, 5e10),
    "pension": ("pensiones_no_reportadas", "pesos", "Pensión recibida", 0, 5e10),
    "otros_ingresos": ("otros_ingresos_no_reportados", "pesos", "Otros ingresos", 0, 5e10),
    "dividendos": ("dividendos_no_reportados", "pesos", "Dividendos recibidos", 0, 5e10),
    "dividendos_gravados": ("dividendos_gravados", "pesos", "Dividendos gravados", 0, 5e10),
    "retenciones": ("retenciones_no_reportadas", "pesos", "Retenciones que te hicieron", 0, 5e10),
    "dependientes": ("dependientes", "entero", "Personas a cargo", 0, 10),
    "medicina_prepagada": ("medicina_prepagada", "pesos", "Medicina prepagada", 0, 1e9),
    "intereses_vivienda": ("intereses_vivienda", "pesos", "Intereses de crédito de vivienda", 0, 5e9),
    "aportes_voluntarios": ("aportes_voluntarios_afc_fpv", "pesos", "Aportes voluntarios y AFC", 0, 5e9),
    "gmf": ("gmf_pagado", "pesos", "4x1000 pagado", 0, 1e9),
    "venta_casa_utilidad": ("ganancias_ocasionales.utilidad_venta_casa_habitacion", "pesos", "Utilidad en la venta de tu casa", 0, 5e10),
    "venta_otros_activos": ("ganancias_ocasionales.utilidad_venta_otros_activos", "pesos", "Utilidad en la venta de otros bienes", 0, 5e10),
    "herencia_vivienda": ("ganancias_ocasionales.herencia_vivienda_causante", "pesos", "Herencia: vivienda", 0, 5e10),
    "herencia_otros_inmuebles": ("ganancias_ocasionales.herencia_otros_inmuebles", "pesos", "Herencia: otros inmuebles", 0, 5e10),
    "herencia": ("ganancias_ocasionales.herencia_porcion_heredero", "pesos", "Herencia o legado", 0, 5e10),
    "donaciones": ("ganancias_ocasionales.donaciones_recibidas", "pesos", "Donaciones recibidas", 0, 5e10),
    "seguros_vida": ("ganancias_ocasionales.seguros_vida", "pesos", "Seguro de vida cobrado", 0, 5e10),
    "loterias": ("ganancias_ocasionales.loterias_premios", "pesos", "Loterías o premios", 0, 5e10),
    "declaraciones_previas": ("declaraciones_previas", "entero", "Veces que has declarado antes", 0, 3),
    "impuesto_anio_anterior": ("impuesto_neto_anio_anterior", "pesos", "Impuesto neto del año anterior", 0, 5e10),
    "anticipo_anio_anterior": ("anticipo_anio_anterior", "pesos", "Anticipo pagado el año anterior", 0, 5e10),
    "ultimos_dos_digitos_cedula": ("ultimos_dos_digitos_nit", "digitos", "Dos últimos dígitos de tu cédula", 0, 99),
    "responsable_iva": ("responsable_iva", "booleano", "Responsable de IVA", 0, 1),
    "sancionado_ultimos_2_anios": ("sin_sanciones_ultimos_2_anios", "booleano", "Sancionado por declarar tarde en los últimos 2 años", 0, 1),
    "bien": ("bienes_adicionales", "item", "Bien", 1, 5e10),
    "deuda": ("deudas_adicionales", "item", "Deuda", 1, 5e10),
}

WIDGETS = {"subir_exogena", "revisar"}


# ---------- Modelos de la API ----------


class MensajeHistorial(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str


class EstadoChat(BaseModel):
    pantalla: Literal["inicio", "declarar", "resultado", "configuracion"] = "declarar"
    anio_gravable: int = 2025
    tiene_exogena: bool = False
    anio_exogena: int | None = None
    perfil: dict[str, bool] = {}
    resumen_exogena: dict[str, float] = {}
    por_revisar: list[str] = []
    filas: list[FilaInterpretada] = []
    topes: dict[str, float] = {}
    respuestas: Respuestas = Respuestas()
    resultado: dict[str, Any] | None = None


class TurnoChat(BaseModel):
    mensaje: str
    historial: list[MensajeHistorial] = []
    estado: EstadoChat = EstadoChat()


class Anotacion(BaseModel):
    clave: str
    etiqueta: str
    valor: str
    detalle: str | None = None


class RespuestaChat(BaseModel):
    respuesta: str
    respuestas: Respuestas
    anotaciones: list[Anotacion] = []
    rechazadas: list[str] = []
    widgets: list[str] = []
    cambiar_anio: int | None = None
    calcular: bool = False
    fuentes: list[str] = []
    modelo: str | None = None
    con_ia: bool = False


@dataclass
class _Plan:
    """Lo que el agente decide hacer en un turno (antes de validar)."""

    respuesta: str = ""
    anotar: list[dict[str, Any]] = field(default_factory=list)
    calcular: bool = False
    cambiar_anio: int | None = None
    mostrar: list[str] = field(default_factory=list)
    fuentes: list[str] = field(default_factory=list)


# ---------- Aplicar anotaciones con validación ----------


def _poner(r: Respuestas, ruta: str, valor: Any) -> None:
    if "." in ruta:
        sub, campo = ruta.split(".", 1)
        setattr(getattr(r, sub), campo, valor)
    else:
        setattr(r, ruta, valor)


def _a_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        c = numeros.cantidades(v)
        return c[0] if c else None
    return None


def aplicar(
    respuestas: Respuestas, anotar: list[dict[str, Any]], mensaje_usuario: str, verificar_cifras: bool = True
) -> tuple[Respuestas, list[Anotacion], list[str]]:
    """Valida y aplica lo que se quiere anotar. Devuelve (respuestas, anotadas, rechazadas)."""
    r = respuestas.model_copy(deep=True)
    hechas: list[Anotacion] = []
    rechazadas: list[str] = []
    for item in anotar[:8]:
        clave = str(item.get("campo", ""))
        if clave not in CAMPOS:
            continue
        ruta, tipo, etiqueta, minimo, maximo = CAMPOS[clave]
        if tipo == "pesos":
            v = _a_float(item.get("valor"))
            if v is None:
                continue
            mensual = str(item.get("periodo", "")).lower().startswith("mens")
            if verificar_cifras and v and not numeros.aparece(v, mensaje_usuario):
                rechazadas.append(etiqueta)
                continue
            anual = v * 12 if mensual else v
            if not (minimo <= anual <= maximo):
                rechazadas.append(etiqueta)
                continue
            _poner(r, ruta, anual)
            hechas.append(Anotacion(clave=clave, etiqueta=etiqueta, valor=_pesos(anual), detalle=f"{_pesos(v)} × 12 meses" if mensual else None))
        elif tipo == "entero":
            v = _a_float(item.get("valor"))
            if v is None or not (minimo <= v <= maximo):
                continue
            _poner(r, ruta, int(v))
            texto = {0: "Ninguna", 1: "Una", 2: "Dos o más", 3: "Tres o más"}.get(int(v), str(int(v))) if clave == "declaraciones_previas" else str(int(v))
            hechas.append(Anotacion(clave=clave, etiqueta=etiqueta, valor=texto))
        elif tipo == "digitos":
            m = re.search(r"(\d{2})\D*$", str(item.get("valor", "")))
            if not m:
                continue
            if verificar_cifras and m.group(1) not in re.sub(r"\D", "", mensaje_usuario):
                rechazadas.append(etiqueta)
                continue
            _poner(r, ruta, m.group(1))
            hechas.append(Anotacion(clave=clave, etiqueta=etiqueta, valor=m.group(1)))
        elif tipo == "booleano":
            v = item.get("valor")
            b = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "si", "sí", "1")
            _poner(r, ruta, (not b) if clave == "sancionado_ultimos_2_anios" else b)
            hechas.append(Anotacion(clave=clave, etiqueta=etiqueta, valor="Sí" if b else "No"))
        elif tipo == "item":
            concepto = str(item.get("concepto") or "").strip()[:80]
            v = _a_float(item.get("valor"))
            if not concepto or v is None:
                continue
            if verificar_cifras and not numeros.aparece(v, mensaje_usuario):
                rechazadas.append(f"{etiqueta}: {concepto}")
                continue
            if not (minimo <= v <= maximo):
                continue
            getattr(r, ruta).append(ItemPatrimonio(concepto=concepto, valor=v, fuente="chat"))
            hechas.append(Anotacion(clave=clave, etiqueta=f"{etiqueta}: {concepto}", valor=_pesos(v)))
    return r, hechas, rechazadas


# ---------- Hechos que se calculan con reglas (sin IA) ----------


def _hay_ingresos(r: Respuestas) -> bool:
    return any([r.salarios_no_reportados, r.honorarios_no_reportados, r.pensiones_no_reportadas, r.otros_ingresos_no_reportados,
                r.arriendos_no_reportados, r.dividendos_no_reportados])


def _hay_datos(e: EstadoChat, r: Respuestas) -> bool:
    return e.tiene_exogena or bool(e.filas) or _hay_ingresos(r) or bool(r.bienes_adicionales)


def obligacion_actual(e: EstadoChat, r: Respuestas | None = None) -> Obligacion | None:
    """Con los datos que hay (exógena + chat), ¿está obligado? Lo decide el motor, no la IA."""
    r = r or e.respuestas
    if not _hay_datos(e, r):
        return None
    try:
        sol = SolicitudLiquidacion(anio_gravable=e.anio_gravable, filas=e.filas, topes=e.topes, ultimos_dos_digitos_nit=r.ultimos_dos_digitos_nit, respuestas=r)
        return liquidar(construir_declaracion(sol)).obligacion
    except Exception:  # noqa: BLE001 - si algo falla, se responde con la base de conocimiento
        log.exception("No se pudo evaluar la obligación")
        return None


def texto_obligacion(e: EstadoChat, ob: Obligacion) -> str:
    anio = e.anio_gravable
    if ob.obligado:
        return f"Con los datos que tengo, sí estás obligado a declarar por el año gravable {anio}: " + "; ".join(ob.razones) + "."
    t = {x.tope: x for x in ob.topes}
    ing = t.get("Ingresos brutos del año")
    pat = t.get("Patrimonio bruto a 31 de diciembre")
    texto = f"Con los datos que tengo, no estás obligado a declarar por el año gravable {anio}"
    if ing and pat:
        texto += f": tus ingresos ({_pesos(ing.valor)}) no llegan a {_pesos(ing.limite)} y tu patrimonio ({_pesos(pat.valor)}) no supera {_pesos(pat.limite)}"
    texto += "."
    if not e.tiene_exogena:
        texto += " Ojo: también cuentan los consumos con tarjeta de crédito, las compras y las consignaciones del año, que vienen en tu exógena."
    return texto


def texto_vencimiento(anio: int, digitos: str) -> str | None:
    fecha = _fecha_limite(anio, digitos)
    if not fecha:
        return None
    hoy = date.today()
    if fecha < hoy:
        return (f"Para tu cédula terminada en {digitos}, el plazo del año gravable {anio} fue el {_fecha(fecha)}. "
                "Ya pasó: todavía puedes declarar, pero con sanción por extemporaneidad.")
    dias = (fecha - hoy).days
    return f"Para tu cédula terminada en {digitos}, el año gravable {anio} vence el {_fecha(fecha)}" + (f" (faltan {dias} días)." if dias else " (es hoy).")


def explicar_resultado(res: dict[str, Any]) -> str:
    partes = [
        f"Tus ingresos suman {_pesos(res.get('ingresos_brutos_totales', 0))}. Después de restar aportes, rentas exentas y deducciones, "
        f"la parte que paga impuesto (renta líquida gravable) quedó en {_pesos(res.get('renta_liquida_gravable', 0))}.",
        f"Con la tabla de tarifas eso da un impuesto a cargo de {_pesos(res.get('total_impuesto_cargo', 0))}.",
    ]
    if res.get("retenciones"):
        partes.append(f"A eso se le restan {_pesos(res['retenciones'])} que ya te retuvieron durante el año.")
    if res.get("anticipo_siguiente"):
        partes.append(f"Se suma un anticipo de {_pesos(res['anticipo_siguiente'])} para el año siguiente.")
    if res.get("sancion"):
        partes.append(f"Como la fecha ya pasó, se suma una sanción estimada de {_pesos(res['sancion'])}.")
    total, favor = res.get("total_a_pagar", 0), res.get("saldo_favor", 0)
    partes.append(f"Resultado: total a pagar {_pesos(total)}." if total else f"Resultado: saldo a favor de {_pesos(favor)}." if favor else "Resultado: no te queda saldo a pagar ni a favor.")
    return " ".join(partes)


# ---------- Ruta sin IA ----------

_RE_ANIO = re.compile(r"\b(20(?:2[0-9]))\b")
_RE_PIDE_ANIO = re.compile(
    r"(cambi\w*|pasa\w*|usa\w*|pon\w*|quiero|hazlo|calcul\w*|hacer|ver|mira\w*)\b.{0,30}\b20(2[0-9])\b"
    r"|\b(declara\w*|renta|reglas|ano gravable|ano)\s+(del?|para el|el)?\s*(ano\s+)?20(2[0-9])\b"
    r"|^(y\s+)?(el|del|para el|en el|ano|ano gravable)?\s*20(2[0-9])\s*\??$"
)
_RE_CALCULAR = re.compile(
    r"\b(calcul\w*|liquid\w*|recalcul\w*)\b|haz(me)? (la|mi) (declaracion|liquidacion)|cuanto (me toca|tengo que|debo|voy a) pagar|cuanto pago\b"
    r"|(mi|el) borrador|(ver|muestrame) (el|mi) resultado|cuanto me (sale|da|queda)"
)
_RE_SUBIR = re.compile(r"\b(subir|subo|adjunt\w*|cargar|cargo|enviar|envio|mandar|mando|te paso|aqui esta)\b.{0,25}(exogena|archivo|excel|reporte|documento)|^(ya )?(la|lo) tengo\b")
_RE_SIN_EXOGENA = re.compile(r"no (la |lo )?tengo.{0,20}(exogena|archivo|reporte)|no tengo (la )?exogena|sin (la )?exogena")
_RE_POR_QUE = re.compile(r"por que (me )?(sale|da|toca|queda)|ese valor|de donde sale|explica\w* (el |mi )?resultado|como (se )?(calculo|salio)|por que (tanto|tan poco)")
_RE_OBLIGACION = re.compile(
    r"(tengo|debo|deberia|estoy obligad\w*|me toca|toca|necesito|hay que) (que )?declarar\b(?!.{0,15}\b(el|la|mi|los|las) (carro|casa|moto|apartamento|cesantia|pension|dividend|herencia|cuenta|bien))"
    r"|obligad\w* a declarar|como (se|saber|averiguo|investigo|reviso|verifico|confirmo)\b.{0,30}\bdeclar|quien(es)? (debe|deben|tiene que|tienen que|declara)"
    r"|\bsi (yo )?(declaro|debo declarar)\b|topes? (para|de) declar"
)
_RE_VENCE = re.compile(r"(cuando|hasta cuando|fecha|plazo|limite|vence|vencio|calendario)\b.{0,40}\b(declar\w*|vence|vencio|present\w*|plazo|renta)|cuando me toca")
_RE_PREGUNTA = re.compile(r"\?|^(que|como|cual|cuales|cuanto|cuanta|cuantos|por que|porque|donde|quien|quienes|para que|cuando|debo|puedo|tengo que|es obligatorio|me toca|sirve|se puede|hay)\b")
_RE_SALUDO = re.compile(r"(hola|ola|buenas|buenos dias|buenas tardes|buenas noches|hey|holi|que mas|saludos|buen dia)( \w+)?[!. ]*")
_RE_GRACIAS = re.compile(r"(muchas )?gracias|listo gracias|muy amable|perfecto gracias|ok gracias|vale gracias")
_RE_NEGATIVO = re.compile(r"(no|nop|nada|ninguno|ninguna|nadie|tampoco|no tengo|no aplica|nada mas|eso es todo)[!. ]*")

_CONCEPTOS: list[tuple[str, str]] = [
    (r"voluntari|\bafc\b|\bavc\b", "aportes_voluntarios"),
    (r"prepagad|medicina|poliza de salud|plan complementario", "medicina_prepagada"),
    (r"interes\w*.{0,30}(vivienda|hipotec|apartamento|casa)|hipotec|leasing habitacional", "intereses_vivienda"),
    (r"4\s*x\s*1\.?000|4 por mil|cuatro por mil|\bgmf\b", "gmf"),
    (r"retenc|retuvieron|retefuente", "retenciones"),
    (r"dividend", "dividendos"),
    (r"arriend|arrendamiento|alquiler", "arriendos"),
    (r"honorari|independiente|freelance|prestacion de servicios|por servicios|contratista", "honorarios"),
    (r"\bcostos?\b|gastos? (del|de mi) (negocio|trabajo|actividad)", "costos_independiente"),
    (r"pension", "pension"),
    (r"loteria|premio|chance|rifa|baloto", "loterias"),
    (r"herencia|herede|legado", "herencia"),
    (r"donacion|me regalaron|me donaron", "donaciones"),
    (r"seguro de vida", "seguros_vida"),
    (r"salario|sueldo|\bgano\b|ganaba|me pagan|me pagaban|devengo|devengaba|nomina|soy empleado|trabajo en|ingresos?", "salarios"),
]
_RE_DEUDA = re.compile(r"\b(debo|deuda|deudas|prestamo|credito|le debo)\b")
_BIENES = {"carro": "Carro", "moto": "Moto", "vehiculo": "Vehículo", "camioneta": "Camioneta", "casa": "Casa", "apartamento": "Apartamento",
           "apto": "Apartamento", "lote": "Lote", "finca": "Finca", "local": "Local", "cdt": "CDT", "acciones": "Acciones", "ahorros": "Ahorros",
           "banco": "Cuentas bancarias", "cuenta": "Cuentas bancarias", "inversion": "Inversiones"}
_RE_BIEN = re.compile(r"\b(" + "|".join(_BIENES) + r")\b")


def _anio_pedido(msg: str) -> int | None:
    if "reforma" in msg or "uvt" in msg:
        return None
    m = _RE_PIDE_ANIO.search(msg)
    if not m:
        return None
    anio = int(_RE_ANIO.findall(m.group(0))[-1])
    return anio


def _extraer_datos(mensaje: str) -> list[dict[str, Any]]:
    """Datos de la declaración que el usuario escribió, con reglas (modo sin IA)."""
    msg = _norm(mensaje)
    anotar: list[dict[str, Any]] = []
    mensual_global = numeros.es_mensual(msg)
    clausulas = [c.strip() for c in re.split(r"[,;]|\.\s| y (?=[a-z])| ademas | tambien | pero ", msg) if c.strip()]
    con_monto = [c for c in clausulas if any(x >= 1000 for x in numeros.cantidades(c))]
    for c in clausulas:
        montos = [x for x in numeros.cantidades(c) if x >= 1000]
        if not montos:
            continue
        monto = montos[0]
        periodo = "mensual" if numeros.es_mensual(c) or (mensual_global and len(con_monto) == 1) else "anual"
        if _RE_DEUDA.search(c) and not re.search(r"interes", c):
            m = _RE_BIEN.search(c)
            anotar.append({"campo": "deuda", "concepto": f"Crédito del {m.group(1)}" if m and m.group(1) in ("carro", "moto", "casa", "apartamento") else "Deuda", "valor": monto})
            continue
        campo = next((cp for patron, cp in _CONCEPTOS if re.search(patron, c)), None)
        if campo:
            anotar.append({"campo": campo, "valor": monto, "periodo": periodo})
            continue
        m = _RE_BIEN.search(c)
        if m:
            anotar.append({"campo": "bien", "concepto": _BIENES[m.group(1)], "valor": monto})
    # Personas a cargo
    if re.search(r"no tengo (hijos|dependientes|personas a cargo)|sin (hijos|dependientes)|nadie depende|ningun dependiente|nadie a cargo", msg):
        anotar.append({"campo": "dependientes", "valor": 0})
    else:
        m = re.search(r"\b(\d+|un|una|dos|tres|cuatro|cinco)\s+(hij[oa]s?|dependientes?|personas? a (mi )?cargo|nin[oa]s?)\b", msg)
        if m:
            anotar.append({"campo": "dependientes", "valor": numeros.cantidades(m.group(1))[0] if numeros.cantidades(m.group(1)) else 1})
        elif re.search(r"\b(mama|papa|madre|padre|esposa|esposo|pareja|hermano|hermana|abuel\w*) depende", msg):
            anotar.append({"campo": "dependientes", "valor": 1})
    # Historial con la DIAN
    if re.search(r"primera vez|nunca (he|habia) declarado|nunca declare", msg):
        anotar.append({"campo": "declaraciones_previas", "valor": 0})
    elif re.search(r"(he declarado|declare|declaro)\b.{0,20}(una vez|el ano pasado)", msg):
        anotar.append({"campo": "declaraciones_previas", "valor": 1})
    elif re.search(r"(he declarado|declare|declaro)\b.{0,20}(antes|varias|siempre|todos los anos|cada ano|muchas)", msg):
        anotar.append({"campo": "declaraciones_previas", "valor": 2})
    m = re.search(r"termina\w*\s+en\s+(\d{2})\b", msg) or re.search(r"\b(cedula|cc|documento)\D{0,20}(\d{6,11})\b", msg)
    if m:
        anotar.append({"campo": "ultimos_dos_digitos_cedula", "valor": m.group(m.lastindex or 1)})
    if re.search(r"no (soy|es) responsable de iva", msg):
        anotar.append({"campo": "responsable_iva", "valor": False})
    elif re.search(r"soy responsable de iva", msg):
        anotar.append({"campo": "responsable_iva", "valor": True})
    return anotar


def _sin_ia(t: TurnoChat) -> _Plan:
    e = t.estado
    msg = _norm(t.mensaje)
    plan = _Plan()
    anio = e.anio_gravable

    if e.resultado and _RE_POR_QUE.search(msg):
        plan.respuesta = explicar_resultado(e.resultado)
        return plan

    plan.cambiar_anio = _anio_pedido(msg)
    if plan.cambiar_anio:
        anio = plan.cambiar_anio
    plan.anotar = _extraer_datos(t.mensaje)
    partes: list[str] = []
    if plan.cambiar_anio and plan.cambiar_anio != e.anio_gravable:
        partes.append(f"Listo, ahora uso las reglas del año gravable {plan.cambiar_anio}.")
    if plan.anotar:
        partes.append("Listo, lo anoté.")

    es_pregunta = bool(_RE_PREGUNTA.search(msg))
    e_anio = e.model_copy(update={"anio_gravable": anio})
    if _RE_SUBIR.search(msg):
        plan.mostrar.append("subir_exogena")
        partes.append("Adjúntala aquí abajo con el clip o arrastrándola.")
    elif _RE_SIN_EXOGENA.search(msg) and not _RE_PREGUNTA.search(msg):
        partes.append("No hay problema: trabajo con lo que me cuentes de tus ingresos y bienes del año.")
    elif _RE_OBLIGACION.search(msg):
        nuevas = aplicar(e.respuestas, plan.anotar, t.mensaje)[0]
        ob = obligacion_actual(e_anio, nuevas)
        if ob:
            partes.append(texto_obligacion(e_anio, ob))
        else:
            como = bool(re.search(r"\bcomo (se|saber|averiguo|investigo|reviso|verifico|confirmo)\b|donde (veo|reviso|miro)", msg))
            sec = base_del_anio(anio)[1 if como else 0]
            partes.append(sec.texto)
            plan.fuentes.append(sec.titulo)
    elif _RE_VENCE.search(msg) and (e.respuestas.ultimos_dos_digitos_nit or any(a["campo"] == "ultimos_dos_digitos_cedula" for a in plan.anotar)):
        dig = next((str(a["valor"])[-2:] for a in plan.anotar if a["campo"] == "ultimos_dos_digitos_cedula"), e.respuestas.ultimos_dos_digitos_nit)
        partes.append(texto_vencimiento(anio, dig or "") or "")
    elif es_pregunta or not (plan.anotar or plan.cambiar_anio):
        mejores = _puntajes(t.mensaje)
        if mejores and mejores[0][0] >= 3.0 and not (plan.anotar and not es_pregunta):
            sec = base_del_anio(anio)[mejores[0][1]]
            partes.append(sec.texto)
            plan.fuentes.append(sec.titulo)

    if _RE_CALCULAR.search(msg):
        explicito = bool(re.search(r"\b(calcul|recalcul|liquid)", msg))
        hay = _hay_datos(e, aplicar(e.respuestas, plan.anotar, t.mensaje)[0])
        if hay and (explicito or not plan.fuentes):
            plan.calcular = True
            partes.append("Calculo tu borrador con lo que tengo.")
        elif explicito and not hay:
            partes.append(f"Para calcular necesito al menos tus ingresos de {anio}: cuéntamelos o adjunta tu exógena.")
    if not partes:
        if _RE_SALUDO.fullmatch(msg):
            partes.append("Hola. ¿En qué te ayudo con tu declaración de renta?")
        elif _RE_GRACIAS.search(msg) and len(msg) < 40:
            partes.append("Con gusto.")
        elif _RE_NEGATIVO.fullmatch(msg):
            partes.append("Entendido.")
        elif any(x >= 1000 for x in numeros.cantidades(msg)):
            partes.append("¿A qué corresponde ese valor: salario, honorarios, arriendo, un bien o una deuda?")
        else:
            partes.append("No tengo una respuesta segura para eso. Solo te ayudo con la declaración de renta; si es sobre eso, escríbelo con otras palabras.")
    plan.respuesta = " ".join(p for p in partes if p)
    return plan


# ---------- Ruta con IA ----------

SISTEMA = """Eres el agente de DeclaraFácil. Ayudas a personas en Colombia con la declaración de renta de personas naturales residentes (formulario 210): resuelves sus dudas y, cuando ellas quieran, armas su borrador con lo que te cuentan o con su exógena. Hoy es {hoy}.

CÓMO RESPONDES
- Responde exactamente lo que te preguntaron, desde la primera frase. Sin rodeos, sin introducciones y sin temas que no pidieron.
- Corto: de 1 a 4 frases, máximo 80 palabras. Solo te extiendes si la persona pide detalle o una explicación.
- Español de Colombia, sencillo, tuteando. Si usas un término técnico, explícalo en pocas palabras. Sin markdown, sin listas, sin emojis.
- Ninguna pregunta es tonta: responde lo básico con naturalidad, sin decir que es buena pregunta.
- La persona lleva la conversación. NO le pidas datos por tu cuenta, NO le preguntes qué quiere hacer después, NO termines con ofrecimientos ("¿Quieres que…?", "Si quieres…", "¿Algo más?"). Solo pregunta algo cuando sea indispensable para hacer lo que pidió.
- Si la pregunta es sobre su caso y el ESTADO ya tiene el dato (sus ingresos, su obligación, su fecha límite, su resultado), contéstale con su caso concreto.
- Usa solo la BASE DE CONOCIMIENTO, los DATOS DEL AÑO y el ESTADO. No inventes normas, cifras ni fechas, y no hagas cálculos tú: las cifras las calcula el sistema. Si no lo sabes, dilo en una frase y remite a la DIAN o a un contador.
- Si el mensaje no tiene que ver con impuestos ni con la app, di en una frase que solo ayudas con la declaración de renta.

ACCIONES (las ejecuta el sistema después de validar)
- "anotar": cuando la persona te cuenta un dato suyo para la declaración. Usa SOLO las claves de CAMPOS. En "valor" copia la cifra tal como la escribió ("4 millones", "350000"); pon "periodo": "mensual" si dijo que es por mes. No sumes ni conviertas. Si dice que no tiene algo ("no tengo hijos"), anota 0. Para "bien" y "deuda" agrega "concepto".
- "calcular": true si pide calcular, liquidar, ver cuánto paga o ver su borrador, y en ESTADO dice que se puede calcular.
- "cambiar_anio": el año gravable (2021 a 2025) si pide cambiar de año o quiere declarar otro año.
- "mostrar": ["subir_exogena"] si quiere subir o adjuntar su exógena; ["revisar"] si quiere confirmar los datos dudosos de su exógena.
- "fuente": el título exacto de la sección de la BASE DE CONOCIMIENTO que usaste, o null.
Cuando anotes algo, basta con decir "Listo, lo anoté." (el sistema le muestra qué quedó anotado).

Responde SOLO con un objeto JSON, sin texto antes ni después:
{{"respuesta": "...", "anotar": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "fuente": null}}

EJEMPLOS
Usuario: que es la dian
{{"respuesta": "Es la Dirección de Impuestos y Aduanas Nacionales, la entidad del Gobierno que recibe las declaraciones y cobra los impuestos nacionales. Sus trámites en línea se hacen en el portal MUISCA.", "anotar": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "fuente": "¿Qué es la DIAN?"}}
Usuario: gano 4 millones al mes y tengo un hijo
{{"respuesta": "Listo, lo anoté.", "anotar": [{{"campo": "salarios", "valor": "4 millones", "periodo": "mensual"}}, {{"campo": "dependientes", "valor": 1}}], "calcular": false, "cambiar_anio": null, "mostrar": [], "fuente": null}}
Usuario: calcula cuánto me toca pagar
{{"respuesta": "Calculo tu borrador con lo que tengo.", "anotar": [], "calcular": true, "cambiar_anio": null, "mostrar": [], "fuente": null}}
Usuario: hazlo con las reglas del 2023
{{"respuesta": "Listo, ahora uso las reglas del año gravable 2023.", "anotar": [], "calcular": false, "cambiar_anio": 2023, "mostrar": [], "fuente": null}}"""


def _datos_anio_texto(anio: int) -> str:
    v = _valores_anio(anio)
    return (
        f"Año gravable elegido: {anio} (se declara en {v['anio_presenta']}). Años disponibles: {', '.join(map(str, anios_vigentes()))}.\n"
        f"UVT {anio}: {v['uvt']}. UVT para sanciones si declara en {v['anio_hoy']}: {v['uvt_hoy']}.\n"
        f"Topes para estar obligado: patrimonio bruto mayor a {v['tope_patrimonio']}; ingresos, consumos con tarjeta, compras o consignaciones de {v['tope_ingresos']} o más; o ser responsable de IVA.\n"
        f"Plazos para declarar: del {v['venc_desde']} al {v['venc_hasta']}, según los dos últimos dígitos de la cédula.\n"
        f"Límite de rentas exentas y deducciones: 40 % y {v['limite_uvt']} UVT ({v['limite_pesos']}). Renta exenta laboral del 25 % hasta {v['exenta_tope_uvt']} UVT. Ganancias ocasionales: {v['go_tarifa']}."
    )


def _estado_texto(e: EstadoChat) -> str:
    r = e.respuestas
    notados = {k: v for k, v in r.model_dump(exclude={"ganancias_ocasionales", "bienes_adicionales", "deudas_adicionales"}).items() if v not in (0, None, False, "", [])}
    notados.pop("sin_sanciones_ultimos_2_anios", None)
    go = {k: v for k, v in r.ganancias_ocasionales.model_dump().items() if v and not isinstance(v, bool)}
    partes = [f"Pantalla: {e.pantalla}.", f"Exógena: {'sí, del año ' + str(e.anio_exogena) if e.tiene_exogena else 'no ha subido'}."]
    if e.resumen_exogena:
        partes.append("Datos de la exógena: " + "; ".join(f"{k}: {_pesos(v)}" for k, v in list(e.resumen_exogena.items())[:14]))
    if e.por_revisar:
        partes.append(f"Datos de la exógena por confirmar ({len(e.por_revisar)}): " + "; ".join(e.por_revisar[:5]))
    partes.append("Datos que contó en el chat: " + (json.dumps(notados, ensure_ascii=False) if notados else "ninguno"))
    if go:
        partes.append("Ganancias ocasionales que contó: " + json.dumps(go, ensure_ascii=False))
    if r.bienes_adicionales or r.deudas_adicionales:
        partes.append("Bienes y deudas que contó: " + "; ".join(f"{b.concepto} {_pesos(b.valor)}" for b in r.bienes_adicionales + r.deudas_adicionales))
    partes.append("Se puede calcular: " + ("sí" if _hay_datos(e, r) else "no, faltan sus ingresos o su exógena"))
    ob = obligacion_actual(e)
    if ob:
        partes.append("Obligación con los datos actuales (calculada por el sistema): " + texto_obligacion(e, ob))
    if r.ultimos_dos_digitos_nit:
        partes.append("Fecha límite de esta persona (calculada por el sistema): " + (texto_vencimiento(e.anio_gravable, r.ultimos_dos_digitos_nit) or "sin dato"))
    if e.resultado:
        partes.append("Resultado ya calculado: " + json.dumps(e.resultado, ensure_ascii=False)[:900])
    return "\n".join(partes)


_RE_OFRECIMIENTO = re.compile(
    r"^(¿\s*)?(quieres|te gustaria|deseas|prefieres|necesitas algo|hay algo mas|en que mas|algo mas|si quieres|si gustas|si deseas|si lo deseas|"
    r"puedo ayudarte|te ayudo|avisame|dime si|no dudes|cuentame si|me cuentas si|estoy aqui|aqui estoy|con gusto te)",
)


def _limpiar(texto: str) -> str:
    """Quita markdown y los ofrecimientos del final ("¿Quieres que…?")."""
    t = re.sub(r"\*\*|__|^#+\s*|^[-*]\s+", "", texto.strip(), flags=re.MULTILINE)
    t = re.sub(r"\s*\n\s*", " ", t).strip()
    frases = re.split(r"(?<=[.!?])\s+(?=[¿A-ZÁÉÍÓÚÑ])", t)
    while len(frases) > 1 and _RE_OFRECIMIENTO.search(numeros.normalizar(frases[-1]).lstrip("¿ ")):
        frases.pop()
    return " ".join(frases).strip()


def _cifras_validas(respuesta: str, permitidas: list[float]) -> bool:
    """Toda cifra de la respuesta debe venir de lo que recibió el modelo (o ser un ×12 de lo que dijo el usuario)."""
    for c in numeros.cantidades(respuesta):
        if c < 1000:
            continue
        if not any(abs(c - p) <= max(1000, 0.015 * p) for p in permitidas):
            return False
    return True


async def _con_ia(t: TurnoChat) -> tuple[_Plan, str]:
    e = t.estado
    base = base_del_anio(e.anio_gravable)
    sistema = (
        SISTEMA.format(hoy=_fecha(date.today()))
        + "\n\nCAMPOS (claves para anotar):\n" + "\n".join(f"- {k}: {v[2]}" for k, v in CAMPOS.items())
        + "\n\nDATOS DEL AÑO:\n" + _datos_anio_texto(e.anio_gravable)
        + "\n\nBASE DE CONOCIMIENTO:\n" + "\n".join(f"### {s.titulo}\n{s.texto}" for s in base)
    )
    estado = _estado_texto(e)
    historial = "\n".join(f"{'Usuario' if m.rol == 'usuario' else 'Tú'}: {m.texto[:500]}" for m in t.historial[-10:])
    usuario = f"ESTADO:\n{estado}\n\nCONVERSACIÓN RECIENTE:\n{historial or '(es el primer mensaje)'}\n\nMENSAJE DEL USUARIO: {t.mensaje}"

    r = await cliente.completar("asistente", sistema, usuario, json_mode=True, max_tokens=1800)
    try:
        j = cliente.extraer_json(r.texto)
        if not isinstance(j, dict):
            raise ValueError("no es un objeto")
    except ValueError:
        if "{" in r.texto:
            raise
        j = {"respuesta": r.texto}  # respondió en texto plano: se usa como respuesta, sin acciones
    respuesta = _limpiar(str(j.get("respuesta") or ""))
    if not respuesta:
        raise ValueError("respuesta vacía")
    permitidas = numeros.cantidades(sistema + "\n" + usuario)
    permitidas += [c * 12 for c in numeros.cantidades(t.mensaje)]
    if not _cifras_validas(respuesta, permitidas):
        raise ValueError("la respuesta trae cifras que no están en los datos")
    titulos = {s.titulo for s in base}
    fuente = j.get("fuente")
    cambiar = j.get("cambiar_anio")
    try:
        cambiar = int(cambiar) if cambiar not in (None, "", False) else None
    except (TypeError, ValueError):
        cambiar = None
    plan = _Plan(
        respuesta=respuesta,
        anotar=[x for x in (j.get("anotar") or []) if isinstance(x, dict)],
        calcular=j.get("calcular") is True or str(j.get("calcular")).lower() == "true",
        cambiar_anio=cambiar,
        mostrar=[str(x) for x in (j.get("mostrar") or []) if isinstance(x, str)],
        fuentes=[fuente] if isinstance(fuente, str) and fuente in titulos else [],
    )
    return plan, r.modelo


# ---------- Turno completo ----------


async def responder(t: TurnoChat) -> RespuestaChat:
    e = t.estado
    plan: _Plan | None = None
    modelo, con_ia = None, False
    if cliente.disponible():
        try:
            plan, modelo = await _con_ia(t)
            con_ia = True
        except Exception as ex:  # noqa: BLE001 - si el modelo falla, responde la ruta sin IA
            log.warning("Asistente sin IA en este turno: %s", ex)
    if plan is None:
        plan = _sin_ia(t)

    nuevas, hechas, rechazadas = aplicar(e.respuestas, plan.anotar, t.mensaje)
    respuesta = plan.respuesta
    if rechazadas:
        respuesta += f" No anoté {', '.join(rechazadas)} porque no encontré esa cifra en tu mensaje; escríbela con números."

    cambiar = plan.cambiar_anio if plan.cambiar_anio in anios_vigentes() and plan.cambiar_anio != e.anio_gravable else None
    anio = cambiar or e.anio_gravable
    if cambiar and e.tiene_exogena and e.anio_exogena and e.anio_exogena != cambiar:
        respuesta += f" Ojo: tu exógena es del {e.anio_exogena}; para {cambiar} necesitas la de ese año."

    mostrar = [w for w in dict.fromkeys(plan.mostrar) if w in WIDGETS]
    calcular = plan.calcular
    if calcular and not _hay_datos(e, nuevas):
        calcular = False
        if "ingres" not in numeros.normalizar(respuesta):
            respuesta += f" Para calcular necesito al menos tus ingresos de {anio}: cuéntamelos o adjunta tu exógena."
    elif calcular and e.por_revisar:
        respuesta += f" Dejé por fuera {len(e.por_revisar)} dato(s) de tu exógena que aún no confirmas."
        mostrar.append("revisar")
    if "revisar" in mostrar and not e.por_revisar:
        mostrar.remove("revisar")

    return RespuestaChat(
        respuesta=respuesta.strip(),
        respuestas=nuevas,
        anotaciones=hechas,
        rechazadas=rechazadas,
        widgets=mostrar,
        cambiar_anio=cambiar,
        calcular=calcular,
        fuentes=plan.fuentes[:2],
        modelo=modelo,
        con_ia=con_ia,
    )
