"""Agente Asistente: la conversación con el usuario.

Responsabilidad única: entender lo que el usuario escribe y decidir qué hacer en ese
turno: responder, anotar o corregir un dato, simular un cambio, calcular, cambiar de
año, abrir la carga de la exógena, o preguntar cuando le falta información.

Cuándo pregunta (lo decide el código, no solo el modelo):
- Una cifra ambigua ("gano 5 millones": ¿al mes o en el año?) o sin concepto.
- Antes de calcular, si falta un dato que cambia el resultado y aún no lo ha preguntado
  (retenciones, dependientes, deducciones, cédula, historial, patrimonio). Pregunta una
  sola vez; con «calcula así» calcula con lo que hay.
- Cuando le preguntan por su caso ("¿tengo que declarar?", "¿cuándo vence?") y no tiene el
  dato. Cuando el usuario responde, retoma lo pendiente: calcula, le dice si está obligado,
  le da su fecha o corre la simulación.

El código valida todo lo que propone la IA antes de aplicarlo:
- Solo se anotan campos de una lista cerrada, con rangos y tipos fijos.
- Una cifra en pesos solo se anota si la escribió el usuario (en este mensaje o en los
  anteriores), o es su valor mensual × 12. La IA no puede inventar montos.
- Si la respuesta de la IA trae una cifra que no está en sus datos de entrada, se descarta.
Sin modelo disponible, todo esto funciona con reglas.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from app.agents import diagnostico, interprete, numeros
from app.agents.base import FilaInterpretada
from app.agents.conocimiento import (
    SeccionKB,
    anios_vigentes,
    base_del_anio,
    buscar,
    fecha_limite,
    fecha_texto,
    norm,
    pesos,
    puntajes,
    valores_anio,
)
from app.llm import cliente
from app.orquestador import Respuestas, SolicitudLiquidacion, construir_declaracion
from app.tax.modelos import ItemPatrimonio, Liquidacion, Obligacion
from app.tax.motor import liquidar

__all__ = ["CAMPOS", "EstadoChat", "RespuestaChat", "SeccionKB", "TurnoChat", "aplicar", "buscar", "responder"]

log = logging.getLogger(__name__)

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

# Cifras que la gente suele decir por mes: si no dice el periodo, el agente pregunta.
_MENSUALES = {"salarios", "pension", "arriendos", "medicina_prepagada", "honorarios", "aportes_voluntarios", "intereses_vivienda"}

# Tema de cada campo (para no volver a preguntar lo mismo)
_TEMA = {
    "salarios": "ingresos", "honorarios": "ingresos", "pension": "ingresos", "arriendos": "ingresos", "otros_ingresos": "ingresos",
    "dividendos": "ingresos", "retenciones": "retenciones", "dependientes": "dependientes", "medicina_prepagada": "deducciones",
    "intereses_vivienda": "deducciones", "aportes_voluntarios": "deducciones", "gmf": "deducciones", "declaraciones_previas": "historial",
    "ultimos_dos_digitos_cedula": "cedula", "bien": "patrimonio", "deuda": "patrimonio",
}

_PREGUNTAS = {
    "ingresos": "¿Cuánto recibiste en {anio}? Por ejemplo, tu salario mensual o lo que te pagaron por honorarios en el año.",
    "retenciones": "¿Te hicieron retención en la fuente en {anio}? Si sí, ¿de cuánto fue en total? Sale en tu certificado de ingresos y retenciones.",
    "dependientes": "¿Alguien depende económicamente de ti, como hijos, pareja o papás?",
    "deducciones": "¿Pagas medicina prepagada, intereses de un crédito de vivienda o aportes voluntarios a pensión o AFC?",
    "cedula": "¿En qué dos números termina tu cédula? Con eso sé tu fecha límite y si hay sanción.",
    "historial": "¿Es la primera vez que declaras renta? Eso cambia el anticipo.",
    "patrimonio": "¿Qué tenías al 31 de diciembre de {anio} (plata en cuentas, casa, carro) y cuánto debías?",
}

WIDGETS = {"subir_exogena", "revisar"}

# ---------- Modelos de la API ----------

Intencion = Literal["calcular", "obligacion", "vencimiento", "simular"]


class MensajeHistorial(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str


class ParteDePregunta(BaseModel):
    """Una de las preguntas de un turno, con respuestas cortas para tocar (como un cuadro de preguntas)."""

    tema: str
    texto: str
    opciones: list[str] = []


class PreguntaPendiente(BaseModel):
    """Lo que el agente preguntó y qué hará cuando le respondan."""

    texto: str = ""
    temas: list[str] = []
    intencion: Intencion | None = None
    campo: str | None = None  # campo de una cifra ambigua (falta el periodo o el concepto)
    valor: float | None = None
    concepto: str | None = None  # bien o deuda cuyo valor falta
    simular: list[dict[str, Any]] = []
    rondas: int = 0  # rondas de preguntas hechas antes de calcular (máximo MAX_RONDAS)
    intro: str = ""  # frase que encabeza el cuadro de preguntas
    partes: list[ParteDePregunta] = []  # una por dato; el front las muestra arriba de la barra del chat


class Simulacion(BaseModel):
    cambios: list[str]
    impuesto_antes: float
    impuesto_despues: float
    total_antes: float
    total_despues: float
    favor_antes: float
    favor_despues: float


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
    pregunta_pendiente: PreguntaPendiente | None = None
    ya_preguntado: list[str] = []


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
    quitadas: list[str] = []
    rechazadas: list[str] = []
    widgets: list[str] = []
    cambiar_anio: int | None = None
    calcular: bool = False
    simulacion: Simulacion | None = None
    pregunta: PreguntaPendiente | None = None
    pregunta_nueva: bool = False  # la pregunta se hizo en este turno (no es una pendiente de antes)
    texto_visible: str = ""  # la respuesta sin la pregunta, que va en su propio cuadro
    ya_preguntado: list[str] = []
    fuentes: list[str] = []
    modelo: str | None = None
    con_ia: bool = False


@dataclass
class _Plan:
    """Lo que el agente decide hacer en un turno, antes de validarlo."""

    respuesta: str = ""
    anotar: list[dict[str, Any]] = field(default_factory=list)
    quitar: list[dict[str, Any]] = field(default_factory=list)
    simular: list[dict[str, Any]] = field(default_factory=list)
    calcular: bool = False
    insiste: bool = False  # "calcula así": no preguntar antes de calcular
    cambiar_anio: int | None = None
    mostrar: list[str] = field(default_factory=list)
    fuentes: list[str] = field(default_factory=list)
    pregunta: PreguntaPendiente | None = None
    caso: Literal["obligacion", "vencimiento"] | None = None  # preguntó por su propio caso
    respondio: bool = False  # contestó lo pendiente con una explicación, sin cifras


# ---------- Aplicar, quitar y leer datos ----------


def _poner(r: Respuestas, ruta: str, valor: Any) -> None:
    if "." in ruta:
        sub, campo = ruta.split(".", 1)
        setattr(getattr(r, sub), campo, valor)
    else:
        setattr(r, ruta, valor)


def _leer(r: Respuestas, ruta: str) -> Any:
    if "." in ruta:
        sub, campo = ruta.split(".", 1)
        return getattr(getattr(r, sub), campo)
    return getattr(r, ruta)


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
    respuestas: Respuestas, anotar: list[dict[str, Any]], texto_usuario: str, verificar_cifras: bool = True
) -> tuple[Respuestas, list[Anotacion], list[str]]:
    """Valida y aplica lo que se quiere anotar. Devuelve (respuestas, anotadas, rechazadas).

    texto_usuario: lo que escribió el usuario (este mensaje y los anteriores); toda cifra
    en pesos debe salir de ahí.
    """
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
            mensual = str(item.get("periodo") or "").lower().startswith("mens")
            if verificar_cifras and v and not item.get("_calculado") and not numeros.aparece(v, texto_usuario):
                rechazadas.append(etiqueta)
                continue
            anual = v * 12 if mensual else v
            if not (minimo <= anual <= maximo):
                rechazadas.append(etiqueta)
                continue
            _poner(r, ruta, anual)
            hechas.append(Anotacion(clave=clave, etiqueta=etiqueta, valor=pesos(anual), detalle=f"{pesos(v)} × 12 meses" if mensual else None))
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
            if verificar_cifras and m.group(1) not in re.sub(r"\D", "", texto_usuario):
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
            if verificar_cifras and not numeros.aparece(v, texto_usuario):
                rechazadas.append(f"{etiqueta}: {concepto}")
                continue
            if not (minimo <= v <= maximo):
                continue
            lista = getattr(r, ruta)
            if any(norm(b.concepto) == norm(concepto) and b.valor == v for b in lista):
                continue  # ya estaba anotado
            lista.append(ItemPatrimonio(concepto=concepto, valor=v, fuente="chat"))
            hechas.append(Anotacion(clave=clave, etiqueta=f"{etiqueta}: {concepto}", valor=pesos(v)))
    return r, hechas, rechazadas


def quitar(respuestas: Respuestas, items: list[dict[str, Any]]) -> tuple[Respuestas, list[str]]:
    """Borra datos que el usuario pidió quitar o corregir. Devuelve (respuestas, etiquetas quitadas)."""
    r = respuestas.model_copy(deep=True)
    quitadas: list[str] = []
    for item in items[:6]:
        clave = str(item.get("campo", ""))
        if clave not in CAMPOS:
            continue
        ruta, tipo, etiqueta, *_ = CAMPOS[clave]
        if tipo == "item":
            concepto = norm(str(item.get("concepto") or ""))
            lista = getattr(r, ruta)
            quedan = [b for b in lista if concepto and concepto not in norm(b.concepto)] if concepto else []
            for b in lista:
                if b not in quedan:
                    quitadas.append(f"{etiqueta}: {b.concepto}")
            setattr(r, ruta, quedan)
        elif tipo == "pesos" and _leer(r, ruta):
            _poner(r, ruta, 0.0)
            quitadas.append(etiqueta)
        elif tipo == "entero" and _leer(r, ruta):
            _poner(r, ruta, None if clave == "declaraciones_previas" else 0)
            quitadas.append(etiqueta)
        elif tipo == "digitos" and _leer(r, ruta):
            _poner(r, ruta, None)
            quitadas.append(etiqueta)
    return r, quitadas


def _hay_ingresos(r: Respuestas) -> bool:
    return any([r.salarios_no_reportados, r.honorarios_no_reportados, r.pensiones_no_reportadas, r.otros_ingresos_no_reportados,
                r.arriendos_no_reportados, r.dividendos_no_reportados])


def _hay_datos(e: EstadoChat, r: Respuestas) -> bool:
    return e.tiene_exogena or bool(e.filas) or _hay_ingresos(r) or bool(r.bienes_adicionales)


def periodo_de(texto: str) -> str | None:
    t = norm(texto)
    if numeros.es_mensual(t) or re.search(r"\b(mensuales?|mes)\b", t):
        return "mensual"
    if re.search(r"\b(al ano|anual\w*|en el ano|todo el ano|por ano|en 20\d\d|del ano|ano completo)\b", t):
        return "anual"
    return None


# ---------- Hechos que calcula el motor (sin IA) ----------


def vista_previa(e: EstadoChat, r: Respuestas | None = None) -> Liquidacion | None:
    """Liquidación con los datos actuales; sirve para saber qué falta y para responder con su caso."""
    r = r or e.respuestas
    if not _hay_datos(e, r):
        return None
    try:
        sol = SolicitudLiquidacion(anio_gravable=e.anio_gravable, filas=e.filas, topes=e.topes, ultimos_dos_digitos_nit=r.ultimos_dos_digitos_nit, respuestas=r)
        return liquidar(construir_declaracion(sol))
    except Exception:  # noqa: BLE001 - sin vista previa el agente sigue respondiendo
        log.exception("No se pudo calcular la vista previa")
        return None


def obligacion_actual(e: EstadoChat, r: Respuestas | None = None) -> Obligacion | None:
    vp = vista_previa(e, r)
    return vp.obligacion if vp else None


def texto_obligacion(e: EstadoChat, ob: Obligacion) -> str:
    anio = e.anio_gravable
    if ob.obligado:
        return f"Con los datos que tengo, sí estás obligado a declarar por el año gravable {anio}: " + "; ".join(ob.razones) + "."
    t = {x.tope: x for x in ob.topes}
    ing = t.get("Ingresos brutos del año")
    pat = t.get("Patrimonio bruto a 31 de diciembre")
    texto = f"Con los datos que tengo, no estás obligado a declarar por el año gravable {anio}"
    if ing and pat:
        texto += f": tus ingresos ({pesos(ing.valor)}) no llegan a {pesos(ing.limite)} y tu patrimonio ({pesos(pat.valor)}) no supera {pesos(pat.limite)}"
    texto += "."
    if not e.tiene_exogena:
        texto += " Ojo: también cuentan los consumos con tarjeta de crédito, las compras y las consignaciones del año, que vienen en tu exógena."
    return texto


def texto_vencimiento(anio: int, digitos: str) -> str | None:
    fecha = fecha_limite(anio, digitos)
    if not fecha:
        return None
    hoy = date.today()
    if fecha < hoy:
        return (f"Para tu cédula terminada en {digitos}, el plazo del año gravable {anio} fue el {fecha_texto(fecha)}. "
                "Ya pasó: todavía puedes declarar, pero con sanción por extemporaneidad.")
    dias = (fecha - hoy).days
    return f"Para tu cédula terminada en {digitos}, el año gravable {anio} vence el {fecha_texto(fecha)}" + (f" (faltan {dias} días)." if dias else " (es hoy).")


def explicar_resultado(res: dict[str, Any]) -> str:
    partes = [
        f"Tus ingresos suman {pesos(res.get('ingresos_brutos_totales', 0))}. Después de restar aportes, rentas exentas y deducciones, "
        f"la parte que paga impuesto (renta líquida gravable) quedó en {pesos(res.get('renta_liquida_gravable', 0))}.",
        f"Con la tabla de tarifas eso da un impuesto a cargo de {pesos(res.get('total_impuesto_cargo', 0))}.",
    ]
    if res.get("retenciones"):
        partes.append(f"A eso se le restan {pesos(res['retenciones'])} que ya te retuvieron durante el año.")
    if res.get("anticipo_siguiente"):
        partes.append(f"Se suma un anticipo de {pesos(res['anticipo_siguiente'])} para el año siguiente.")
    if res.get("sancion"):
        partes.append(f"Como la fecha ya pasó, se suma una sanción estimada de {pesos(res['sancion'])}.")
    total, favor = res.get("total_a_pagar", 0), res.get("saldo_favor", 0)
    partes.append(f"Resultado: total a pagar {pesos(total)}." if total else f"Resultado: saldo a favor de {pesos(favor)}." if favor else "Resultado: no te queda saldo a pagar ni a favor.")
    return " ".join(partes)


@dataclass
class Faltante:
    tema: str
    pregunta: str


_OPCIONES: dict[str, list[str]] = {
    "periodo": ["Al mes", "En todo el año"],
    "dependientes": ["No, nadie", "Sí, 1 persona", "Sí, 2 personas", "Sí, 3 personas"],
    "deducciones": ["No pago nada de eso", "Sí"],
    "retenciones": ["No me retuvieron", "No sé"],
    "costos": ["No tuve costos", "No sé"],
    "bienes": ["No tengo", "Sí"],
    "patrimonio": ["No tenía nada", "Sí"],
    "historial": ["Es la primera vez", "Es la segunda", "Ya llevo más de dos"],
    "otros_ingresos": ["No", "Sí"],
    "ganancias": ["No", "Sí"],
    "sanciones": ["No", "Sí"],
    "anterior": ["No sé"],
    "consignaciones": ["Fue un préstamo", "Pasé plata entre mis cuentas", "Vendí algo"],
    "concepto": ["Salario", "Honorarios", "Arriendo", "Una deuda"],
    "valor": ["No sé"],
}


def _opciones(tema: str, texto: str) -> list[str]:
    if tema == "dependientes" and texto.startswith("¿Cuántas"):
        return ["1", "2", "3", "4"]
    if tema == "historial" and "segunda" in texto:
        return ["Es la segunda", "Ya llevo más de dos"]
    if texto in _SEGUIMIENTO.values():
        return []  # preguntas de seguimiento ("¿De cuánto?"): se responden escribiendo
    return list(_OPCIONES.get(tema, []))


def _parte(tema: str, texto: str) -> ParteDePregunta:
    return ParteDePregunta(tema=tema, texto=texto, opciones=_opciones(tema, texto))


def _completar_partes(p: PreguntaPendiente) -> PreguntaPendiente:
    """Toda pregunta lleva al menos una parte con sus respuestas cortas."""
    if not p.partes:
        tema = "periodo" if "periodo" in p.temas else (p.temas[0] if len(p.temas) == 1 else "dato")
        p.partes = [_parte(tema, p.texto)]
    return p


MAX_RONDAS = 2  # antes de calcular pregunta como máximo dos veces (hasta dos datos cada vez)


def faltantes(e: EstadoChat, r: Respuestas, vp: Liquidacion | None) -> list[Faltante]:
    """Datos que cambian el resultado y que todavía no se han preguntado, en orden de importancia."""
    hecho = set(e.ya_preguntado)
    return [Faltante(v.tema, v.pregunta) for v in diagnostico.vacios(e, r, vp) if v.tema not in hecho]


def _ronda(fs: list[Faltante]) -> list[Faltante]:
    """Lo que se pregunta en un turno: una aclaración larga sola, o hasta dos datos."""
    return fs[:1] if fs[0].tema == "consignaciones" else fs[:2]


def simular(e: EstadoChat, r: Respuestas, cambios: list[dict[str, Any]], texto_usuario: str) -> tuple[Simulacion | None, str]:
    """¿Qué pasaría si…? Compara la liquidación actual con la del escenario. No cambia los datos."""
    base = vista_previa(e, r)
    r2, hechas, _ = aplicar(r, cambios, texto_usuario)
    esc = vista_previa(e, r2) if hechas else None
    if not base or not esc:
        return None, ""
    a, b = base.resumen, esc.resumen
    sim = Simulacion(
        cambios=[f"{h.etiqueta}: {h.valor}" for h in hechas],
        impuesto_antes=a.total_impuesto_cargo, impuesto_despues=b.total_impuesto_cargo,
        total_antes=a.total_a_pagar, total_despues=b.total_a_pagar,
        favor_antes=a.saldo_favor, favor_despues=b.saldo_favor,
    )
    dif = a.total_impuesto_cargo - b.total_impuesto_cargo
    if dif > 0:
        texto = f"Con ese cambio tu impuesto a cargo bajaría de {pesos(a.total_impuesto_cargo)} a {pesos(b.total_impuesto_cargo)}: te ahorrarías {pesos(dif)}."
    elif dif < 0:
        texto = f"Con ese cambio tu impuesto a cargo subiría de {pesos(a.total_impuesto_cargo)} a {pesos(b.total_impuesto_cargo)}."
    elif a.total_impuesto_cargo == 0:
        texto = "Con ese cambio tu impuesto no cambia: con tus datos actuales no pagas impuesto de renta."
    else:
        texto = "Con ese cambio tu impuesto no cambia: ya llegaste al límite de rentas exentas y deducciones, o ese gasto ya está en su tope."
    sin_cambio = (a.total_impuesto_cargo, a.total_a_pagar, a.saldo_favor) == (b.total_impuesto_cargo, b.total_a_pagar, b.saldo_favor)
    return (None if sin_cambio else sim), texto + " Es solo una simulación: no cambié tus datos."


# ---------- Entender el mensaje sin IA ----------

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
_RE_INSISTE = re.compile(r"\b(asi|igual|de una|sin eso|con lo que (tengas|hay|tienes)|no importa|calcula ya|ya calcula|hazlo ya)\b")
_RE_SUBIR = re.compile(r"\b(subir|subo|adjunt\w*|cargar|cargo|enviar|envio|mandar|mando|te paso|aqui esta)\b.{0,25}(exogena|archivo|excel|reporte|documento)|^(ya )?(la|lo) tengo\b")
_RE_SIN_EXOGENA = re.compile(r"no (la |lo )?tengo.{0,20}(exogena|archivo|reporte)|no tengo (la )?exogena|sin (la )?exogena")
_RE_POR_QUE = re.compile(r"por que (me )?(sale|da|toca|queda)|ese valor|de donde sale|explica\w* (el |mi )?resultado|como (se )?(calculo|salio)|por que (tanto|tan poco)")
_RE_OBLIGACION = re.compile(
    r"(tengo|debo|deberia|estoy obligad\w*|me toca|toca|necesito|hay que) (que )?declarar\b(?!.{0,15}\b(el|la|mi|los|las) (carro|casa|moto|apartamento|cesantia|pension|dividend|herencia|cuenta|bien))"
    r"|obligad\w* a declarar|como (se|saber|averiguo|investigo|reviso|verifico|confirmo)\b.{0,30}\bdeclar|quien(es)? (debe|deben|tiene que|tienen que|declara)"
    r"|\bsi (yo )?(declaro|debo declarar)\b|topes? (para|de) declar"
)
_RE_COMO_SE = re.compile(r"\bcomo (se|saber|averiguo|investigo|reviso|verifico|confirmo)\b|donde (veo|reviso|miro)")
_RE_VENCE = re.compile(r"(cuando|hasta cuando|fecha|plazo|limite|vence|vencio|calendario)\b.{0,40}\b(declar\w*|vence|vencio|present\w*|plazo|renta)|cuando me toca")
_RE_SIMULAR = re.compile(
    r"\b(que pasa si|que pasaria si|y si|si (yo )?(pagara|pagaba|aportara|tuviera|tuviese|metiera|agregara|pusiera|ahorrara|declarara))\b"
    r"|cuanto (me )?(ahorr\w*|bajari\w*|pagari\w*|cambiari\w*|me baja)"
)
_RE_QUITAR = re.compile(r"\b(quita\w*|borra\w*|elimina\w*|saca\w*|ya no tengo|me equivoque|no era|no son|no es)\b")
_RE_PREGUNTA = re.compile(r"\?|^(que|como|cual|cuales|cuanto|cuanta|cuantos|por que|porque|donde|quien|quienes|para que|cuando|debo|puedo|tengo que|es obligatorio|me toca|sirve|se puede|hay)\b")
_RE_SALUDO = re.compile(r"(hola|ola|buenas|buenos dias|buenas tardes|buenas noches|hey|holi|que mas|saludos|buen dia)( \w+)?[!. ]*")
_RE_GRACIAS = re.compile(r"(muchas )?gracias|listo gracias|muy amable|perfecto gracias|ok gracias|vale gracias")
_RE_NEGATIVO = re.compile(r"^(no|nop|nada|ninguno|ninguna|nadie|tampoco|no se|ni idea|no tengo|no me|no pago|no aplica|nada mas|eso es todo|cero)\b")
_RE_FALTA = re.compile(r"que (me |te )?falta|que mas (necesitas|te falta|falta|me falta)|que (datos|informacion) (me |te )?(faltan|falta|necesitas)|esta (todo )?completo|ya esta todo|que mas te (digo|cuento)")
_RE_DOCS = re.compile(r"\b(documentos|papeles|certificados|soportes)\b|que (necesito|me piden|debo tener|tengo que (tener|conseguir|pedir|sacar|reunir))\b")
_RE_NO_ES_INGRESO = re.compile(r"prest|entre mis cuentas|mis (propias )?cuentas|traslad|ahorr|vend|devol|me regalaron|regalo|familia|herencia|credito|no era (mio|mia|plata mia)")
_SEGUIMIENTO = {
    "deducciones": "¿Cuál pagas y de cuánto? Por ejemplo «prepagada de 300 mil al mes».",
    "bienes": "¿Cuál y cuánto pagaste por él? Por ejemplo «un carro de 40 millones».",
    "patrimonio": "¿Qué tenías y cuánto valía? Por ejemplo «5 millones en el banco y un carro de 30 millones».",
    "otros_ingresos": "¿Qué fue y de cuánto? Por ejemplo «arriendos de 1 millón al mes».",
    "ganancias": "¿Qué fue? Si vendiste algo, dime en cuánto lo vendiste y en cuánto lo habías comprado.",
    "retenciones": "¿De cuánto fue en total? Sale en tu certificado de ingresos y retenciones.",
    "costos": "¿De cuánto fueron en total en el año?",
    "anterior": "¿De cuánto fue?",
}
_RE_AFIRMATIVO = re.compile(r"^(si|sip|claro|asi es|correcto|exacto|obvio|afirmativo)\b")
_RE_NO_SE = re.compile(r"^(no se|ni idea|no tengo idea|no me acuerdo|no recuerdo|no estoy segur\w*)\b")

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
    return int(_RE_ANIO.findall(m.group(0))[-1]) if m else None


def _concepto_de(clausula: str) -> dict[str, Any] | None:
    """Concepto de una frase sin la cifra: campo (y concepto si es un bien o una deuda)."""
    if re.search(r"\bvend\w*", clausula):
        m = _RE_BIEN.search(clausula)
        return {"campo": "venta", "concepto": _BIENES[m.group(1)] if m else "Bien"}
    if _RE_DEUDA.search(clausula) and not re.search(r"interes", clausula):
        m = _RE_BIEN.search(clausula)
        return {"campo": "deuda", "concepto": f"Crédito del {m.group(1)}" if m and m.group(1) in ("carro", "moto", "casa", "apartamento") else "Deuda"}
    campo = next((cp for patron, cp in _CONCEPTOS if re.search(patron, clausula)), None)
    if campo:
        return {"campo": campo}
    m = _RE_BIEN.search(clausula)
    if m:
        return {"campo": "bien", "concepto": _BIENES[m.group(1)]}
    return None


def _extraer_datos(mensaje: str) -> list[dict[str, Any]]:
    """Datos de la declaración que el usuario escribió, con reglas. El periodo queda vacío si no lo dijo."""
    msg = norm(mensaje)
    anotar: list[dict[str, Any]] = []
    periodo_global = periodo_de(msg)
    clausulas = [c.strip() for c in re.split(r"[,;]|\.\s| y (?!medio\b)(?=[a-z])| ademas | tambien | pero ", msg) if c.strip()]
    con_monto = [c for c in clausulas if any(x >= 1000 for x in numeros.cantidades(c))]
    for c in clausulas:
        montos = [x for x in numeros.cantidades(c) if x >= 1000]
        if not montos:
            continue
        concepto = _concepto_de(c)
        if not concepto:
            continue
        if concepto["campo"] == "venta":
            compra = re.search(r"compr\w*.*", msg)
            precio_compra = [x for x in numeros.cantidades(compra.group(0)) if x >= 1000] if compra else []
            anotar.append({**concepto, "precio_venta": montos[0], **({"precio_compra": precio_compra[0]} if precio_compra and precio_compra[0] != montos[0] else {})})
            continue
        item = {**concepto, "valor": montos[0]}
        if CAMPOS[item["campo"]][1] == "pesos":
            item["periodo"] = periodo_de(c) or (periodo_global if len(con_monto) == 1 else None)
        anotar.append(item)
    if re.search(r"no tengo (hijos|dependientes|personas a cargo)|sin (hijos|dependientes)|nadie depende|ningun dependiente|nadie a cargo", msg):
        anotar.append({"campo": "dependientes", "valor": 0})
    else:
        m = re.search(r"\b(\d+|un|una|dos|tres|cuatro|cinco)\s+(hij[oa]s?|dependientes?|personas? a (mi )?cargo|nin[oa]s?)\b", msg)
        if m:
            n = numeros.cantidades(m.group(1))
            anotar.append({"campo": "dependientes", "valor": n[0] if n else 1})
        elif re.search(r"\b(mama|papa|madre|padre|esposa|esposo|pareja|hermano|hermana|abuel\w*) depende", msg):
            anotar.append({"campo": "dependientes", "valor": 1})
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


def _respuesta_a_pendiente(mensaje: str, p: PreguntaPendiente, ya: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lee respuestas cortas ("2", "al mes", "no", "termina en 21") según lo que el agente preguntó."""
    msg = norm(mensaje)
    campos_ya = {a["campo"] for a in ya}
    salida: list[dict[str, Any]] = []
    montos = [x for x in numeros.cantidades(msg) if x >= 1000]
    if p.valor is not None and p.campo and "periodo" in p.temas:
        per = periodo_de(msg) or ("mensual" if re.search(r"\bmes", msg) else "anual" if re.search(r"\bano\b|\banual|\btotal\b", msg) else None)
        if per:
            salida.append({"campo": p.campo, "valor": p.valor, "periodo": per, **({"concepto": "Bien"} if CAMPOS[p.campo][1] == "item" else {})})
    if p.valor is not None and "concepto" in p.temas and not campos_ya:
        concepto = _concepto_de(msg)
        if concepto:
            item = {**concepto, "valor": p.valor}
            if concepto["campo"] in CAMPOS and CAMPOS[concepto["campo"]][1] == "pesos":
                item["periodo"] = periodo_de(msg)
            salida.append(item)
    if _RE_NO_SE.search(msg):
        return salida
    if "valor" in p.temas and p.campo in CAMPOS and montos and not campos_ya:
        item: dict[str, Any] = {"campo": p.campo, "valor": montos[0]}
        if CAMPOS[p.campo][1] == "item":
            item["concepto"] = p.concepto or CAMPOS[p.campo][2]
        else:
            item["periodo"] = periodo_de(msg)
        salida.append(item)
    if "dependientes" in p.temas and "dependientes" not in campos_ya:
        if _RE_NEGATIVO.search(msg):
            salida.append({"campo": "dependientes", "valor": 0})
        else:
            n = [x for x in numeros.cantidades(msg) if 0 < x <= 10]
            if n:
                salida.append({"campo": "dependientes", "valor": n[0]})
    if "cedula" in p.temas and "ultimos_dos_digitos_cedula" not in campos_ya:
        m = re.search(r"\b(\d{6,11})\b", msg) or re.search(r"\b(\d{2})\b", msg)
        if m:
            salida.append({"campo": "ultimos_dos_digitos_cedula", "valor": m.group(1)})
    if "retenciones" in p.temas and "retenciones" not in campos_ya and montos and not _concepto_de(msg):
        salida.append({"campo": "retenciones", "valor": montos[0], "periodo": "anual"})
    if "sanciones" in p.temas and "sancionado_ultimos_2_anios" not in campos_ya:
        if _RE_NEGATIVO.search(msg) or re.search(r"nunca", msg):
            salida.append({"campo": "sancionado_ultimos_2_anios", "valor": False})
        elif _RE_AFIRMATIVO.search(msg):
            salida.append({"campo": "sancionado_ultimos_2_anios", "valor": True})
    if "anterior" in p.temas and "impuesto_anio_anterior" not in campos_ya and montos and not _concepto_de(msg):
        salida.append({"campo": "impuesto_anio_anterior", "valor": montos[0]})
    if "costos" in p.temas and "costos_independiente" not in campos_ya and montos and (_concepto_de(msg) or {"campo": "costos_independiente"})["campo"] == "costos_independiente":
        salida.append({"campo": "costos_independiente", "valor": montos[0]})
    if "historial" in p.temas and "declaraciones_previas" not in campos_ya and re.search(r"segunda|2da|\buna\b|el ano pasado", msg) and not re.search(r"tercera|mas de", msg):
        salida.append({"campo": "declaraciones_previas", "valor": 1})
    elif "historial" in p.temas and "declaraciones_previas" not in campos_ya and re.search(r"tercera|cuarta|mas de|llevo (varias|muchas|mas)|ya llevo", msg):
        salida.append({"campo": "declaraciones_previas", "valor": 2})
    if "historial" in p.temas and "declaraciones_previas" not in campos_ya and not any(x["campo"] == "declaraciones_previas" for x in salida):
        if re.search(r"primera|nunca", msg) or (_RE_AFIRMATIVO.search(msg) and not re.search(r"\b(ya|antes)\b", msg)):
            salida.append({"campo": "declaraciones_previas", "valor": 0})
        elif re.search(r"varias|muchas|siempre|todos|cada ano|\b[2-9]\b|dos|tres", msg):
            salida.append({"campo": "declaraciones_previas", "valor": 2})
        elif re.search(r"una vez|el ano pasado|^no\b|\bya\b", msg):
            salida.append({"campo": "declaraciones_previas", "valor": 1})
    if "venta" in p.temas and montos and not campos_ya & {"venta"}:
        if p.valor:
            salida.append({"campo": "venta", "concepto": p.concepto or "Bien", "precio_venta": p.valor, "precio_compra": montos[0]})
        else:
            salida.append({"campo": "venta", "concepto": p.concepto or "Bien", "precio_venta": montos[0], **({"precio_compra": montos[1]} if len(montos) > 1 else {})})
    if "ingresos" in p.temas and montos and not (campos_ya & {"salarios", "honorarios", "pension", "arriendos", "otros_ingresos"}) and not salida:
        salida.append({"campo": "salarios", "valor": montos[0], "periodo": periodo_de(msg)})
    return salida


_RE_AFIRMA_TENER = re.compile(r"\b(tengo|tenia|pago|pague|pagamos|recibo|recibi|recibia|gano|ganaba|me pagan|me pagaban|compre|debo|debia|vendi|me gane|cobre)\b")


def _falta_valor(msg: str) -> PreguntaPendiente | None:
    """"Tengo un carro", "pago prepagada": hay un dato pero sin cifra; se pregunta cuánto."""
    if any(x >= 1000 for x in numeros.cantidades(msg)) or not _RE_AFIRMA_TENER.search(msg) or re.match(r"(no|tampoco|ya no)\b", msg):
        return None
    concepto = _concepto_de(msg)
    if not concepto or concepto["campo"] in ("dependientes", "declaraciones_previas"):
        return None
    campo = concepto["campo"]
    if campo == "venta":
        texto = f"¿En cuánto vendiste {concepto['concepto'].lower()} y en cuánto lo habías comprado? La ganancia es la diferencia."
    elif campo == "bien" and concepto["concepto"] in ("Cuentas bancarias", "Ahorros", "CDT", "Inversiones", "Acciones"):
        texto = f"¿Cuánto tenías en {concepto['concepto'].lower()} al 31 de diciembre? Sale en el certificado tributario de tu banco o entidad."
    elif campo == "bien" and concepto["concepto"] in ("Casa", "Apartamento", "Lote", "Finca", "Local"):
        texto = f"¿Cuál es el avalúo catastral de tu {concepto['concepto'].lower()}? Sale en el recibo del impuesto predial. Si lo compraste por más, dime cuánto pagaste."
    elif campo == "bien":
        texto = f"¿Cuánto pagaste por tu {concepto['concepto'].lower()}? Se declara por lo que costó (factura o contrato de compra), no por lo que vale hoy."
    elif campo == "deuda":
        texto = "¿Cuánto debías al 31 de diciembre?"
    elif campo in _MENSUALES:
        texto = f"¿De cuánto es lo de {_CORTA.get(campo, CAMPOS[campo][2].lower())}? Dime si es al mes o en todo el año."
    else:
        texto = f"¿De cuánto fue lo de {CAMPOS[campo][2].lower()} en el año?"
    if campo == "venta":
        return PreguntaPendiente(texto=texto, temas=["venta"], concepto=concepto.get("concepto"))
    return PreguntaPendiente(texto=texto, temas=["valor"], campo=campo, concepto=concepto.get("concepto"))


def _extraer_quitar(msg: str) -> list[dict[str, Any]]:
    if not _RE_QUITAR.search(msg):
        return []
    salida: list[dict[str, Any]] = []
    m = _RE_BIEN.search(msg)
    if m and not _RE_DEUDA.search(msg):
        salida.append({"campo": "bien", "concepto": _BIENES[m.group(1)]})
    elif _RE_DEUDA.search(msg):
        salida.append({"campo": "deuda", "concepto": m.group(1) if m else ""})
    elif re.search(r"hij|dependiente", msg):
        salida.append({"campo": "dependientes"})
    else:
        concepto = _concepto_de(msg)
        if concepto and concepto["campo"] in CAMPOS and CAMPOS[concepto["campo"]][1] == "pesos" and not numeros.cantidades(msg):
            salida.append({"campo": concepto["campo"]})
    return salida


def _sin_ia(t: TurnoChat) -> _Plan:
    e = t.estado
    msg = norm(t.mensaje)
    plan = _Plan()
    p = e.pregunta_pendiente

    if e.resultado and _RE_POR_QUE.search(msg):
        plan.respuesta = explicar_resultado(e.resultado)
        return plan

    plan.cambiar_anio = _anio_pedido(msg)
    anio = plan.cambiar_anio or e.anio_gravable
    plan.quitar = _extraer_quitar(msg)
    datos = [] if plan.quitar and not numeros.cantidades(msg) else _extraer_datos(t.mensaje)
    if p:
        datos = _respuesta_a_pendiente(t.mensaje, p, datos) + datos
    if _RE_SIMULAR.search(msg) and datos and not p:
        plan.simular = datos
    else:
        plan.anotar = datos
    plan.insiste = bool(_RE_INSISTE.search(msg))
    es_pregunta = bool(_RE_PREGUNTA.search(msg))
    partes: list[str] = []
    if plan.cambiar_anio and plan.cambiar_anio != e.anio_gravable:
        partes.append(f"Listo, ahora uso las reglas del año gravable {plan.cambiar_anio}.")
    if p and "consignaciones" in p.temas and _RE_NO_ES_INGRESO.search(msg):
        partes.append("Entonces esa plata no es ingreso y no se suma. Guarda los soportes (contrato del préstamo, escritura de la venta o extractos) por si la DIAN pregunta.")
        plan.respondio = True

    if plan.respondio:
        pass
    elif _RE_SUBIR.search(msg):
        plan.mostrar.append("subir_exogena")
        partes.append("Adjúntala aquí abajo con el clip o arrastrándola.")
    elif _RE_SIN_EXOGENA.search(msg) and not es_pregunta:
        partes.append("No hay problema: trabajo con lo que me cuentes de tus ingresos y bienes del año.")
    elif _RE_FALTA.search(msg):
        vs = diagnostico.vacios(e, e.respuestas, vista_previa(e))
        if vs and vs[0].tema == "ingresos":
            plan.pregunta = PreguntaPendiente(texto=f"Me falta lo principal: tus ingresos. {vs[0].pregunta}", temas=["ingresos"], intencion="calcular")
        elif pend := [v for v in vs if v.tema not in e.ya_preguntado]:
            partes.append("Para un cálculo completo me falta saber " + diagnostico._lista([v.etiqueta for v in pend]) + ".")
            plan.pregunta = PreguntaPendiente(texto="Empecemos por lo primero: " + pend[0].pregunta, temas=[pend[0].tema], intencion="calcular", rondas=1)
        else:
            partes.append("No me falta nada importante: con lo que tengo ya puedo calcular tu borrador.")
    elif _RE_DOCS.search(msg) and _hay_datos(e, e.respuestas):
        partes.append("Para tu caso necesitas:\n" + "\n".join("– " + d for d in diagnostico.documentos(e, e.respuestas)))
    elif _RE_OBLIGACION.search(msg) and not plan.simular:
        if _RE_COMO_SE.search(msg):
            sec = next(s for s in base_del_anio(anio) if s.titulo.startswith("¿Cómo sé si tengo"))
            partes.append(sec.texto)
            plan.fuentes.append(sec.titulo)
        else:
            plan.caso = "obligacion"
    elif _RE_VENCE.search(msg):
        plan.caso = "vencimiento"
    elif _RE_NEGATIVO.search(msg) and not es_pregunta and not datos:
        if not p:
            partes.append("Entendido.")
    elif re.search(r"\b(calcul|recalcul|liquid)", msg) and not plan.simular:
        pass  # pidió calcular: no hace falta explicar nada antes
    elif not (datos or es_pregunta) and (falta := _falta_valor(msg)):
        if p:
            falta.intencion, falta.rondas = p.intencion, p.rondas
        plan.pregunta = falta
    elif (re.search(r"\btengo (unos |unas |varios |varias )?(hij[oa]s|dependientes|personas a (mi )?cargo)\b", msg)
          and not any(a["campo"] == "dependientes" for a in datos) and not es_pregunta):
        plan.pregunta = PreguntaPendiente(texto="¿Cuántas personas dependen económicamente de ti?", temas=["dependientes"], intencion=p.intencion if p else None)
    elif (es_pregunta or not (datos or plan.cambiar_anio or plan.quitar)) and not plan.simular:
        mejores = puntajes(t.mensaje)
        if mejores and mejores[0][0] >= 3.0:
            sec = base_del_anio(anio)[mejores[0][1]]
            partes.append(sec.texto)
            plan.fuentes.append(sec.titulo)

    if _RE_CALCULAR.search(msg) and not plan.simular:
        explicito = bool(re.search(r"\b(calcul|recalcul|liquid)", msg))
        if explicito or not plan.fuentes:
            plan.calcular = True

    if p and "dependientes" in p.temas and _RE_AFIRMATIVO.search(msg) and not any(a["campo"] == "dependientes" for a in plan.anotar):
        plan.pregunta = PreguntaPendiente(texto="¿Cuántas personas dependen de ti?", temas=["dependientes"], intencion=p.intencion, rondas=p.rondas)
    elif p and _RE_AFIRMATIVO.search(msg) and not plan.anotar and not plan.pregunta:
        tema = next((x for x in p.temas if x in _SEGUIMIENTO), None)
        if tema:
            plan.pregunta = PreguntaPendiente(texto=_SEGUIMIENTO[tema], temas=[tema] + (["venta"] if tema == "ganancias" else []), intencion=p.intencion, rondas=p.rondas)
    nada = not (partes or plan.anotar or plan.simular or plan.quitar or plan.calcular or plan.caso or plan.cambiar_anio or plan.pregunta)
    if nada and not (p and (_RE_NEGATIVO.search(msg) or _RE_AFIRMATIVO.search(msg))):
        montos = [x for x in numeros.cantidades(msg) if x >= 1000]
        if _RE_SALUDO.fullmatch(msg):
            partes.append("Hola. ¿En qué te ayudo con tu declaración de renta?")
        elif _RE_GRACIAS.search(msg) and len(msg) < 40:
            partes.append("Con gusto.")
        elif _RE_NEGATIVO.search(msg):
            partes.append("Entendido.")
        elif montos:
            plan.pregunta = PreguntaPendiente(temas=["concepto"], valor=montos[0], texto=f"¿A qué corresponde {pesos(montos[0])}: salario, honorarios, arriendo, un bien o una deuda?")
        else:
            partes.append("No tengo una respuesta segura para eso. Solo te ayudo con la declaración de renta; si es sobre eso, escríbelo con otras palabras.")
    plan.respuesta = " ".join(partes)
    return plan


# ---------- Ruta con IA ----------

SISTEMA = """Eres el agente de DeclaraFácil. Ayudas a personas en Colombia con la declaración de renta de personas naturales residentes (formulario 210): resuelves sus dudas y armas su borrador con lo que te cuentan o con su exógena. Hoy es {hoy}.

CÓMO RESPONDES
- Responde exactamente lo que te preguntaron, desde la primera frase. Sin rodeos, sin introducciones y sin temas que no pidieron.
- Corto: de 1 a 4 frases, máximo 80 palabras. Solo te extiendes si la persona pide detalle o una explicación.
- Español de Colombia, sencillo, tuteando. Si usas un término técnico, explícalo en pocas palabras. Sin markdown, sin listas, sin emojis.
- Ninguna pregunta es tonta: responde lo básico con naturalidad.
- La persona lleva la conversación: nada de preguntas de relleno ni ofrecimientos ("¿Quieres que…?", "Si quieres…", "¿Algo más?").
- PERO pregunta cuando te falte información para hacer bien lo que la persona quiere: una cifra que no sabes si es mensual o anual, una cifra sin concepto, o un dato de su caso que necesitas para contestarle (por ejemplo, pregunta si tiene que declarar y no sabes sus ingresos). Una sola pregunta concreta (máximo dos datos), di para qué la necesitas y descríbela en "pregunta". No repitas lo que está en YA PREGUNTASTE.
- Deduce todo lo que puedas de lo que ya sabes (LO QUE EL SISTEMA DEDUJO, la exógena, la conversación) y nunca preguntes algo que ya está ahí.
- Si pregunta cómo conseguir un dato o un documento, guíalo paso a paso con la BASE DE CONOCIMIENTO y, si aplica, con los nombres de las entidades de su caso (DOCUMENTOS DE SU CASO).
- Si pregunta qué le falta, usa LO QUE FALTA y dile de dónde sale cada dato.
- Si hay una PREGUNTA PENDIENTE y el mensaje la responde (aunque sea corto: "2", "al mes", "no", "termina en 21"), interprétalo en ese contexto y anótalo.
- Si la pregunta es sobre su caso y el ESTADO ya tiene el dato (su obligación, su fecha límite, la vista previa, su resultado), contéstale con su caso concreto.
- Usa solo la BASE DE CONOCIMIENTO, los DATOS DEL AÑO y el ESTADO. No inventes normas, cifras ni fechas, y no hagas cálculos: las cifras las calcula el sistema. Si no lo sabes, dilo en una frase y remite a la DIAN o a un contador.
- Si el mensaje no tiene que ver con impuestos ni con la app, di en una frase que solo ayudas con la declaración de renta.

ACCIONES (las ejecuta el sistema después de validar)
- "anotar": cuando la persona te da un dato suyo. Usa SOLO las claves de CAMPOS. En "valor" copia la cifra como la escribió ("4 millones", "350000"). "periodo": "mensual" o "anual" solo si lo dijo; si no está claro, NO lo anotes: pregunta. Si dice que no tiene algo ("no tengo hijos"), anota 0. Para "bien" y "deuda" agrega "concepto".
- Si vendió un bien, no lo anotes como bien: anota {{"campo": "venta", "concepto": "carro", "precio_venta": "...", "precio_compra": "..."}} con las cifras que dijo; si no dijo en cuánto lo compró, deja "precio_compra" vacío y el sistema lo pregunta. La ganancia la calcula el sistema.
- "quitar": [{{"campo": "...", "concepto": "..."}}] si pide borrar o corregir un dato que ya no aplica. Para corregir una cifra basta con anotar la nueva.
- "simular": igual que anotar, cuando pregunta qué pasaría ("¿y si pago prepagada?", "¿cuánto me ahorro si aporto a AFC?"). No se anota: el sistema calcula la diferencia y la agrega a tu respuesta, así que solo di algo como "Mira la diferencia:".
- "calcular": true si pide calcular, liquidar, ver cuánto paga o ver su borrador. El sistema puede preguntar antes lo que falte.
- "cambiar_anio": el año gravable (2021 a 2025) si pide cambiar de año o quiere declarar otro año.
- "mostrar": ["subir_exogena"] si quiere subir o adjuntar su exógena; ["revisar"] si quiere confirmar los datos dudosos de su exógena.
- "pregunta": si tu respuesta pide un dato, {{"campos": [claves de CAMPOS que esperas], "intencion": "calcular" | "obligacion" | "vencimiento" | null}}. Si no preguntas nada, null.
- "fuente": el título exacto de la sección de la BASE DE CONOCIMIENTO que usaste, o null.

Responde SOLO con un objeto JSON, sin texto antes ni después:
{{"respuesta": "...", "anotar": [], "quitar": [], "simular": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "pregunta": null, "fuente": null}}

EJEMPLOS
Usuario: que es la dian
{{"respuesta": "Es la Dirección de Impuestos y Aduanas Nacionales, la entidad del Gobierno que recibe las declaraciones y cobra los impuestos nacionales. Sus trámites en línea se hacen en el portal MUISCA.", "anotar": [], "quitar": [], "simular": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "pregunta": null, "fuente": "¿Qué es la DIAN?"}}
Usuario: gano 4 millones al mes y tengo un hijo
{{"respuesta": "Listo, lo anoté.", "anotar": [{{"campo": "salarios", "valor": "4 millones", "periodo": "mensual"}}, {{"campo": "dependientes", "valor": 1}}], "quitar": [], "simular": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "pregunta": null, "fuente": null}}
Usuario: me pagan 3 millones
{{"respuesta": "¿Esos 3 millones son tu salario al mes o lo que recibiste en todo el año? Lo necesito para sumar bien tus ingresos.", "anotar": [], "quitar": [], "simular": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "pregunta": {{"campos": ["salarios"], "intencion": null}}, "fuente": null}}
Usuario: y si pago prepagada de 300 mil al mes, cuánto me ahorro?
{{"respuesta": "Mira la diferencia:", "anotar": [], "quitar": [], "simular": [{{"campo": "medicina_prepagada", "valor": "300 mil", "periodo": "mensual"}}], "calcular": false, "cambiar_anio": null, "mostrar": [], "pregunta": null, "fuente": null}}
Usuario: quita el carro, ya lo vendí
{{"respuesta": "Listo, lo quité.", "anotar": [], "quitar": [{{"campo": "bien", "concepto": "carro"}}], "simular": [], "calcular": false, "cambiar_anio": null, "mostrar": [], "pregunta": null, "fuente": null}}
Usuario: calcula
{{"respuesta": "Calculo tu borrador con lo que tengo.", "anotar": [], "quitar": [], "simular": [], "calcular": true, "cambiar_anio": null, "mostrar": [], "pregunta": null, "fuente": null}}"""


def _datos_anio_texto(anio: int) -> str:
    v = valores_anio(anio)
    return (
        f"Año gravable elegido: {anio} (se declara en {v['anio_presenta']}). Años disponibles: {', '.join(map(str, anios_vigentes()))}.\n"
        f"UVT {anio}: {v['uvt']}. UVT para sanciones si declara en {v['anio_hoy']}: {v['uvt_hoy']}.\n"
        f"Topes para estar obligado: patrimonio bruto mayor a {v['tope_patrimonio']}; ingresos, consumos con tarjeta, compras o consignaciones de {v['tope_ingresos']} o más; o ser responsable de IVA.\n"
        f"Plazos para declarar: del {v['venc_desde']} al {v['venc_hasta']}, según los dos últimos dígitos de la cédula.\n"
        f"Límite de rentas exentas y deducciones: 40 % y {v['limite_uvt']} UVT ({v['limite_pesos']}). Renta exenta laboral del 25 % hasta {v['exenta_tope_uvt']} UVT. Ganancias ocasionales: {v['go_tarifa']}."
    )


_USO = {"suma": "se suma", "informativo": "solo informativo", "revisar": "por confirmar"}


def _celda(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("|", "/")).strip()


def _tabla_exogena(e: EstadoChat) -> str:
    """La exógena ya procesada, en una tabla markdown: los modelos la leen mejor que una lista de campos."""
    if not e.filas:
        return "EXÓGENA (totales por campo):\n" + "\n".join(f"- {k}: {pesos(v)}" for k, v in list(e.resumen_exogena.items())[:20])
    lineas = ["EXÓGENA (cada dato reportado, ya procesado por el sistema; las cifras son exactas):",
              "| Entidad | Concepto | Valor | Va en | Uso |", "|---|---|---|---|---|"]
    for f in e.filas[:45]:
        concepto = re.sub(r"\((concepto|titular|formato)[^)]*\)", "", f.detalle, flags=re.I)
        destino = interprete.CAMPOS.get(f.campo or "", "—")
        lineas.append(f"| {_celda(f.informante or '—')[:45]} | {_celda(concepto)[:70]} | {pesos(f.valor)} | {destino} | {_USO.get(f.tratamiento, f.tratamiento)} |")
    if e.topes:
        lineas.append("Topes que reporta la DIAN: " + "; ".join(f"{k}: {pesos(v)}" for k, v in e.topes.items()))
    return "\n".join(lineas)


def _datos_chat(notados: dict[str, Any]) -> str:
    if not notados:
        return "DATOS QUE CONTÓ EN EL CHAT: ninguno."
    etiquetas = {v[0]: v[2] for v in CAMPOS.values()}
    def valor(v: Any) -> str:
        return pesos(v) if isinstance(v, float) and v >= 1000 else str(v)
    return "DATOS QUE CONTÓ EN EL CHAT:\n" + "\n".join(f"- {etiquetas.get(k, k)}: {valor(v)}" for k, v in notados.items())


def _estado_texto(e: EstadoChat, vp: Liquidacion | None) -> str:
    r = e.respuestas
    notados = {k: v for k, v in r.model_dump(exclude={"ganancias_ocasionales", "bienes_adicionales", "deudas_adicionales"}).items() if v not in (0, None, False, "", [])}
    notados.pop("sin_sanciones_ultimos_2_anios", None)
    go = {k: v for k, v in r.ganancias_ocasionales.model_dump().items() if v and not isinstance(v, bool)}
    partes = [f"Pantalla: {e.pantalla}.", f"Exógena: {'sí, del año ' + str(e.anio_exogena) if e.tiene_exogena else 'no ha subido'}."]
    if e.resumen_exogena:
        partes.append(_tabla_exogena(e))
    if e.por_revisar:
        partes.append(f"Datos de la exógena por confirmar ({len(e.por_revisar)}): " + "; ".join(e.por_revisar[:5]))
    partes.append(_datos_chat(notados))
    if go:
        partes.append("Ganancias ocasionales que contó: " + json.dumps(go, ensure_ascii=False))
    if r.bienes_adicionales or r.deudas_adicionales:
        partes.append("Bienes y deudas que contó: " + "; ".join(f"{b.concepto} {pesos(b.valor)}" for b in r.bienes_adicionales + r.deudas_adicionales))
    if vp:
        s = vp.resumen
        partes.append(
            "VISTA PREVIA con los datos actuales (calculada por el sistema; es un estimado, no el resultado final): "
            f"ingresos {pesos(s.ingresos_brutos_totales)}; renta líquida gravable {pesos(s.renta_liquida_gravable)}; impuesto a cargo {pesos(s.total_impuesto_cargo)}; "
            f"retenciones {pesos(s.retenciones)}; sanción {pesos(s.sancion)}; "
            + (f"total a pagar {pesos(s.total_a_pagar)}." if s.total_a_pagar else f"saldo a favor {pesos(s.saldo_favor)}.")
        )
        partes.append("Obligación (calculada por el sistema): " + texto_obligacion(e, vp.obligacion))
    else:
        partes.append("Vista previa: no hay datos todavía (ni ingresos ni exógena).")
    if r.ultimos_dos_digitos_nit:
        partes.append("Fecha límite (calculada por el sistema): " + (texto_vencimiento(e.anio_gravable, r.ultimos_dos_digitos_nit) or "sin dato"))
    if e.tiene_exogena:
        dx = diagnostico.diagnostico(e, r, vp)
        if dx:
            partes.append("LO QUE EL SISTEMA DEDUJO DE LA EXÓGENA: " + dx)
    vs = diagnostico.vacios(e, r, vp)
    if vs:
        partes.append("LO QUE FALTA PARA UN CÁLCULO COMPLETO (con dónde se consigue): " + "; ".join(
            f"{v.etiqueta}" + (f" [{v.fuente}]" if v.fuente else "") + (" (ya lo preguntaste)" if v.tema in e.ya_preguntado else "") for v in vs))
    else:
        partes.append("LO QUE FALTA: nada importante.")
    if _hay_datos(e, r):
        partes.append("DOCUMENTOS DE SU CASO: " + " | ".join(diagnostico.documentos(e, r)))
    if e.ya_preguntado:
        partes.append("YA PREGUNTASTE (no lo repitas): " + ", ".join(e.ya_preguntado))
    if e.pregunta_pendiente and e.pregunta_pendiente.texto:
        partes.append(f"PREGUNTA PENDIENTE (lo último que preguntaste): {e.pregunta_pendiente.texto}")
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


def _ordenar_texto(texto: str) -> str:
    """Espacios simples, conserva los saltos de línea y quita puntos dobles ("S.A..")."""
    t = re.sub(r"[ \t]+", " ", texto)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\.\.(?=\s|$)", ".", t)
    return t.strip()


def _cifras_validas(respuesta: str, permitidas: list[float]) -> bool:
    """Toda cifra de la respuesta debe venir de lo que recibió el modelo (o ser un ×12 de lo que dijo el usuario)."""
    for c in numeros.cantidades(respuesta):
        if c < 1000:
            continue
        if not any(abs(c - p) <= max(1000, 0.015 * p) for p in permitidas):
            return False
    return True


def _texto_usuario(t: TurnoChat) -> str:
    """Lo que escribió el usuario en esta conversación (las cifras solo pueden salir de aquí)."""
    previos = [m.texto for m in t.historial[-10:] if m.rol == "usuario"]
    return "\n".join([*previos, t.mensaje])


def _lista_dict(v: Any) -> list[dict[str, Any]]:
    # Las claves internas ("_calculado") solo las pone el código, nunca el modelo
    return [{k: y for k, y in x.items() if not str(k).startswith("_")} for x in (v or []) if isinstance(x, dict)] if isinstance(v, list) else []


async def _con_ia(t: TurnoChat, vp: Liquidacion | None) -> tuple[_Plan, str]:
    e = t.estado
    base = base_del_anio(e.anio_gravable)
    sistema = (
        SISTEMA.format(hoy=fecha_texto(date.today()))
        + "\n\nCAMPOS (claves para anotar, quitar o simular):\n" + "\n".join(f"- {k}: {v[2]}" for k, v in CAMPOS.items())
        + "\n\nDATOS DEL AÑO:\n" + _datos_anio_texto(e.anio_gravable)
        + "\n\nBASE DE CONOCIMIENTO:\n" + "\n".join(f"### {s.titulo}\n{s.texto}" for s in base)
    )
    historial = "\n".join(f"{'Usuario' if m.rol == 'usuario' else 'Tú'}: {m.texto[:500]}" for m in t.historial[-10:])
    usuario = f"ESTADO:\n{_estado_texto(e, vp)}\n\nCONVERSACIÓN RECIENTE:\n{historial or '(es el primer mensaje)'}\n\nMENSAJE DEL USUARIO: {t.mensaje}"

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
    permitidas = numeros.cantidades(sistema + "\n" + usuario) + [c * 12 for c in numeros.cantidades(_texto_usuario(t))]
    if not _cifras_validas(respuesta, permitidas):
        raise ValueError("la respuesta trae cifras que no están en los datos")
    titulos = {s.titulo for s in base}
    fuente = j.get("fuente")
    cambiar = j.get("cambiar_anio")
    try:
        cambiar = int(cambiar) if cambiar not in (None, "", False) else None
    except (TypeError, ValueError):
        cambiar = None
    pregunta = None
    jp = j.get("pregunta")
    if isinstance(jp, dict) and respuesta.rstrip().endswith("?"):
        campos = [c for c in (jp.get("campos") or []) if isinstance(c, str) and c in CAMPOS]
        intencion = jp.get("intencion") if jp.get("intencion") in ("calcular", "obligacion", "vencimiento", "simular") else None
        temas = sorted({_TEMA.get(c, c) for c in campos})
        pregunta = PreguntaPendiente(texto=respuesta, temas=temas, intencion=intencion)
        montos = [x for x in numeros.cantidades(t.mensaje) if x >= 1000]
        if len(campos) == 1 and CAMPOS[campos[0]][1] == "pesos" and len(montos) == 1:
            pregunta.campo, pregunta.valor = campos[0], montos[0]
            pregunta.temas = sorted({*temas, "periodo"})
    plan = _Plan(
        respuesta=respuesta,
        anotar=_lista_dict(j.get("anotar")),
        quitar=_lista_dict(j.get("quitar")),
        simular=_lista_dict(j.get("simular")),
        calcular=j.get("calcular") is True or str(j.get("calcular")).lower() == "true",
        insiste=bool(_RE_INSISTE.search(norm(t.mensaje))),
        cambiar_anio=cambiar,
        mostrar=[str(x) for x in (j.get("mostrar") or []) if isinstance(x, str)],
        fuentes=[fuente] if isinstance(fuente, str) and fuente in titulos else [],
        pregunta=pregunta,
    )
    # Respuestas cortas a la pregunta pendiente que el modelo no anotó
    if e.pregunta_pendiente:
        extra = _respuesta_a_pendiente(t.mensaje, e.pregunta_pendiente, plan.anotar)
        if e.pregunta_pendiente.intencion == "simular":
            plan.simular = plan.simular or extra
        else:
            plan.anotar += [x for x in extra if x["campo"] not in {a.get("campo") for a in plan.anotar}]
    return plan, r.modelo


# ---------- Turno completo ----------


_FEMENINOS = {"moto", "casa", "finca", "camioneta"}


def _con_articulo(concepto: str) -> str:
    c = concepto.lower()
    if c in ("bien", ""):
        return "ese bien"
    return ("la " if c in _FEMENINOS else "el ") + c


_CORTA = {"salarios": "salario", "pension": "pensión", "arriendos": "arriendo", "medicina_prepagada": "medicina prepagada",
          "honorarios": "honorarios", "aportes_voluntarios": "aportes voluntarios", "intereses_vivienda": "intereses de vivienda"}


def _pregunta_periodo(item: dict[str, Any], intencion: Intencion | None) -> PreguntaPendiente:
    v = _a_float(item.get("valor")) or 0
    etiqueta = _CORTA.get(item["campo"], CAMPOS[item["campo"]][2].lower())
    return PreguntaPendiente(
        texto=f"¿Los {pesos(v)} de {etiqueta} son al mes o en todo el año? Lo necesito para sumarlo bien.",
        temas=["periodo"], campo=item["campo"], valor=v, intencion=intencion,
        simular=[item] if intencion == "simular" else [],
    )


def diagnosticar(e: EstadoChat) -> RespuestaChat:
    """Lo primero que dice el agente al leer la exógena: qué deduce y lo que la exógena no muestra.

    Es con reglas (no gasta cupo de IA). Si falta algo que cambia el resultado, lo pregunta;
    cuando el usuario responde, sigue preguntando lo importante y luego calcula.
    """
    r = e.respuestas
    vp = vista_previa(e, r)
    partes = [diagnostico.diagnostico(e, r, vp)]
    if e.por_revisar:
        n = len(e.por_revisar)
        partes.append("Hay un dato de tu exógena que no sé cómo tratar; te lo pregunto abajo." if n == 1
                      else f"Hay {n} datos de tu exógena que no sé cómo tratar; te los pregunto abajo, uno por uno.")
    fs = faltantes(e, r, vp)
    pregunta = None
    ya = list(e.ya_preguntado)
    if fs:
        top = _ronda(fs)
        intro = "Algo no me cuadra." if top[0].tema == "consignaciones" else "Lo que la exógena no me dice:"
        preguntas = " ".join(re.sub(r" Lo de .* ya viene en tu exógena\.", "", f.pregunta) for f in top)
        pregunta = PreguntaPendiente(texto=f"{intro} {preguntas}", temas=[f.tema for f in top], intencion="calcular", rondas=1,
                                     intro=intro, partes=[_parte(f.tema, re.sub(r" Lo de .* ya viene en tu exógena\.", "", f.pregunta)) for f in top])
        partes.append(pregunta.texto)
        ya = list(dict.fromkeys([*ya, *pregunta.temas]))
    elif vp:
        partes.append("Con esto ya puedo calcular tu borrador cuando me digas.")
    texto = _ordenar_texto("\n".join(x for x in partes if x)) or "Leí tu exógena."
    return RespuestaChat(
        respuesta=texto,
        texto_visible=_ordenar_texto(texto.replace(pregunta.texto, "")) if pregunta else texto,
        respuestas=r,
        widgets=["revisar"] if e.por_revisar else [],
        pregunta=pregunta,
        pregunta_nueva=bool(pregunta),
        ya_preguntado=ya,
    )


async def responder(t: TurnoChat) -> RespuestaChat:
    e = t.estado
    p = e.pregunta_pendiente
    vp_inicial = vista_previa(e)
    plan: _Plan | None = None
    modelo, con_ia = None, False
    if cliente.disponible():
        try:
            plan, modelo = await _con_ia(t, vp_inicial)
            con_ia = True
        except Exception as ex:  # noqa: BLE001 - si el modelo falla, responde la ruta sin IA
            log.warning("Asistente sin IA en este turno: %s", ex)
    if plan is None:
        plan = _sin_ia(t)

    msg = norm(t.mensaje)
    texto_usuario = _texto_usuario(t)
    if p and p.intencion == "simular" and p.simular and not plan.simular:
        # Se respondió el periodo de una simulación pendiente
        plan.simular = [x for x in plan.anotar if x.get("campo") == p.campo]
        plan.anotar = [x for x in plan.anotar if x.get("campo") != p.campo]

    # 1. Cifras ambiguas: no se anotan, se pregunta
    pregunta_codigo: PreguntaPendiente | None = None
    for lista, intencion in ((plan.simular, "simular"), (plan.anotar, None)):
        for item in list(lista):
            if item.get("campo") in _MENSUALES and str(item.get("periodo") or "") not in ("mensual", "anual"):
                per = periodo_de(t.mensaje)
                if per and len([x for x in numeros.cantidades(msg) if x >= 1000]) <= 1:
                    item["periodo"] = per
                elif pregunta_codigo is None:
                    pregunta_codigo = _pregunta_periodo(item, intencion or (p.intencion if p else None))  # type: ignore[arg-type]
                    lista.remove(item)
                else:
                    lista.remove(item)

    # 2. Ventas: la ganancia (precio de venta - precio de compra) la calcula el código
    pregunta_venta, notas_venta = None, []
    ventas = [x for x in plan.anotar if x.get("campo") == "venta"]
    plan.anotar = [x for x in plan.anotar if x.get("campo") != "venta"]
    for v in ventas[:1]:
        concepto = str(v.get("concepto") or "Bien")
        venta, compra = _a_float(v.get("precio_venta") or v.get("valor")), _a_float(v.get("precio_compra"))
        if venta is None or not numeros.aparece(venta, texto_usuario) or (compra is not None and not numeros.aparece(compra, texto_usuario)):
            continue
        if compra is None:
            pregunta_venta = PreguntaPendiente(
                texto=f"¿En cuánto habías comprado {_con_articulo(concepto)}? La ganancia es la diferencia con los {pesos(venta)} de la venta.",
                temas=["venta"], valor=venta, concepto=concepto, intencion=p.intencion if p else None, rondas=p.rondas if p else 0,
            )
        elif venta > compra:
            casa = norm(concepto) in ("casa", "apartamento")
            plan.anotar.append({"campo": "venta_casa_utilidad" if casa else "venta_otros_activos", "valor": venta - compra, "_calculado": True})
            notas_venta.append(f"La ganancia de la venta es {pesos(venta - compra)} ({pesos(venta)} menos {pesos(compra)}). Si lo tenías hace más de dos años, paga como ganancia ocasional; si lo vendiste antes de fin de año, ya no va en tu patrimonio.")
        else:
            notas_venta.append(f"Vendiste {_con_articulo(concepto)} por menos de lo que te costó, así que no hay ganancia que declarar. Si ya no lo tenías al 31 de diciembre, no va en tu patrimonio.")

    # 3. Quitar y anotar
    r = e.respuestas
    r, quitadas = quitar(r, plan.quitar)
    r, hechas, rechazadas = aplicar(r, plan.anotar, texto_usuario)
    partes: list[str] = []
    respuesta = plan.respuesta
    if not con_ia:
        if quitadas:
            partes.append("Listo, quité " + ", ".join(quitadas) + ".")
        elif plan.quitar:
            partes.append("No tenía eso anotado.")
        if hechas and not respuesta.startswith("Listo"):
            partes.append("Listo, lo anoté.")
    if pregunta_codigo and con_ia:
        respuesta = ("Anoté lo demás." if hechas else "")  # la pregunta del código reemplaza lo que dijo el modelo
    partes.append(respuesta)
    partes.extend(notas_venta)
    if rechazadas:
        partes.append(f"No anoté {', '.join(rechazadas)} porque no encontré esa cifra en lo que escribiste; escríbela con números.")

    # 4. Año
    cambiar = plan.cambiar_anio if plan.cambiar_anio in anios_vigentes() and plan.cambiar_anio != e.anio_gravable else None
    anio = cambiar or e.anio_gravable
    if cambiar and e.tiene_exogena and e.anio_exogena and e.anio_exogena != cambiar:
        partes.append(f"Ojo: tu exógena es del {e.anio_exogena}; para {cambiar} necesitas la de ese año.")
    e2 = e.model_copy(update={"anio_gravable": anio, "respuestas": r})
    vp = vista_previa(e2, r)

    ya = list(dict.fromkeys(e.ya_preguntado))
    pregunta: PreguntaPendiente | None = pregunta_codigo or pregunta_venta or plan.pregunta
    calcular = plan.calcular and not pregunta
    insiste = plan.insiste
    simulacion: Simulacion | None = None

    # 4. Retomar lo que quedó pendiente cuando el usuario respondió
    respondio = bool(hechas or quitadas or notas_venta or plan.respondio or _RE_NEGATIVO.search(msg) or _RE_AFIRMATIVO.search(msg) or _RE_NO_SE.search(msg) or insiste)
    if p and p.intencion and respondio and not pregunta:
        if p.intencion == "calcular":
            calcular = True
            insiste = insiste or p.rondas >= MAX_RONDAS  # ya preguntó lo suficiente: calcula con lo que hay
        elif p.intencion == "obligacion" and vp and "obligad" not in norm(" ".join(partes)):
            partes.append(texto_obligacion(e2, vp.obligacion))
        elif p.intencion == "vencimiento" and r.ultimos_dos_digitos_nit and "terminada en" not in " ".join(partes):
            partes.append(texto_vencimiento(anio, r.ultimos_dos_digitos_nit) or "")

    # 5. Preguntas sobre su propio caso (ruta sin IA)
    if plan.caso == "obligacion":
        if vp:
            partes.append(texto_obligacion(e2, vp.obligacion))
        else:
            sec = base_del_anio(anio)[0]
            partes.append(sec.texto)
            plan.fuentes.append(sec.titulo)
            if not pregunta and "ingresos" not in ya:
                pregunta = PreguntaPendiente(texto=f"¿Cuánto recibiste en {anio} y qué tenías al 31 de diciembre (cuentas, casa, carro)? Con eso te digo si te toca.",
                                             temas=["ingresos", "patrimonio"], intencion="obligacion")
    elif plan.caso == "vencimiento":
        if r.ultimos_dos_digitos_nit:
            partes.append(texto_vencimiento(anio, r.ultimos_dos_digitos_nit) or "")
        else:
            sec = next(s for s in base_del_anio(anio) if s.titulo.startswith("¿Cuándo vence"))
            partes.append(sec.texto)
            plan.fuentes.append(sec.titulo)
            if not pregunta and "cedula" not in ya:
                pregunta = PreguntaPendiente(texto="¿En qué dos números termina tu cédula? Te digo tu fecha exacta.", temas=["cedula"], intencion="vencimiento")

    # 6. Simular
    if plan.simular and not pregunta:
        if not _hay_datos(e2, r):
            pregunta = PreguntaPendiente(texto=f"Para simularlo necesito tus ingresos. {_PREGUNTAS['ingresos'].format(anio=anio)}", temas=["ingresos"], intencion="simular", simular=plan.simular)
        else:
            simulacion, texto = simular(e2, r, plan.simular, texto_usuario)
            partes.append(texto or "No pude simular ese cambio con los datos que tengo.")
    elif p and p.intencion == "simular" and p.simular and respondio and _hay_datos(e2, r) and not pregunta:
        simulacion, texto = simular(e2, r, p.simular, texto_usuario)
        if texto:
            partes.append(texto)

    # 7. Antes de calcular: preguntar lo que cambia el resultado (una sola vez)
    if calcular and not pregunta:
        fs = faltantes(e2.model_copy(update={"ya_preguntado": ya}), r, vp)
        if fs and fs[0].tema == "ingresos":
            calcular = False
            pregunta = PreguntaPendiente(texto=f"Para calcular necesito tus ingresos. {fs[0].pregunta}", temas=["ingresos"], intencion="calcular")
            partes = [x for x in partes if "calcul" not in norm(x)]
        elif fs and not insiste:
            calcular = False
            rondas = (p.rondas if p and p.intencion == "calcular" else 0) + 1
            top = _ronda(fs)
            if top[0].tema == "consignaciones":
                intro = "Antes de calcular, algo no me cuadra."
            elif rondas > 1:
                intro = "Una última cosa antes de calcular." if len(top) == 1 else "Dos últimas cosas antes de calcular."
            else:
                intro = "Antes de calcular necesito un dato que cambia el resultado." if len(top) == 1 else "Antes de calcular necesito dos datos que cambian el resultado."
            pregunta = PreguntaPendiente(
                texto=f"{intro} {' '.join(f.pregunta for f in top)} Si no lo sabes, escribe «calcula así».",
                temas=[f.tema for f in top], intencion="calcular", rondas=rondas,
                intro=intro, partes=[_parte(f.tema, f.pregunta) for f in top],
            )
            partes = [x for x in partes if "calcul" not in norm(x)]
        elif calcular and not any("calcul" in norm(x) for x in partes):
            partes.append("Con eso calculo tu borrador.")
        if calcular and e.por_revisar:
            partes.append(f"Dejé por fuera {len(e.por_revisar)} dato(s) de tu exógena que aún no confirmas.")
            plan.mostrar.append("revisar")

    # 8. La pregunta va al final de la respuesta y no se vuelve a hacer
    nueva = bool(pregunta)
    if pregunta:
        _completar_partes(pregunta)
        if pregunta.texto and pregunta.texto not in " ".join(partes):
            partes.append(pregunta.texto)
        ya = list(dict.fromkeys([*ya, *pregunta.temas]))
    elif p and not respondio and not (calcular or simulacion or hechas):
        pregunta = _completar_partes(p)  # siguió preguntando otra cosa: lo pendiente se conserva

    mostrar = [w for w in dict.fromkeys(plan.mostrar) if w in WIDGETS]
    if "revisar" in mostrar and not e.por_revisar:
        mostrar.remove("revisar")

    texto_final = _ordenar_texto(" ".join(x for x in partes if x)) or "Entendido."
    visible = _ordenar_texto(texto_final.replace(pregunta.texto, "")) if (pregunta and nueva and pregunta.texto) else texto_final
    return RespuestaChat(
        respuesta=texto_final,
        texto_visible=visible,
        pregunta_nueva=nueva,
        respuestas=r,
        anotaciones=hechas,
        quitadas=quitadas,
        rechazadas=rechazadas,
        widgets=mostrar,
        cambiar_anio=cambiar,
        calcular=calcular,
        simulacion=simulacion,
        pregunta=pregunta,
        ya_preguntado=ya,
        fuentes=plan.fuentes[:2],
        modelo=modelo,
        con_ia=con_ia,
    )
