"""Agente Asistente: la conversación con el usuario.

Responsabilidad única: entender lo que el usuario escribe y contestarle. Puede
proponer acciones (anotar un dato, mostrar el botón de subir la exógena, calcular),
pero el código las valida antes de aplicarlas:
- Solo se anotan campos de una lista cerrada, con rangos y tipos fijos.
- Una cifra en pesos solo se anota si aparece en el mensaje del usuario (o es su
  valor mensual × 12). Así la IA no puede inventar montos.
Sin modelo disponible, responde con reglas y la base de conocimiento.
"""

import json
import re
import unicodedata
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel

from app.agents import numeros
from app.config import settings
from app.llm import cliente
from app.orquestador import Respuestas
from app.tax import reglas as repo_reglas

# ---------- Base de conocimiento ----------

_VACIAS = set(
    "de la el los las un una y o a en que por para con del al se mi mis tu tus es como cual cuanto cuando donde si no lo le me te su sus hay eso esto esa este".split()
)


class SeccionKB(BaseModel):
    titulo: str
    texto: str


def _tokens(texto: str) -> set[str]:
    s = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return {t for t in re.findall(r"[a-z0-9]+", s) if t not in _VACIAS and len(t) > 2}


@lru_cache(maxsize=1)
def _base() -> tuple[SeccionKB, ...]:
    secciones: list[SeccionKB] = []
    for archivo in sorted((settings.data_dir / "conocimiento").glob("*.md")):
        actual: SeccionKB | None = None
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.startswith("## "):
                if actual:
                    secciones.append(actual)
                actual = SeccionKB(titulo=linea[3:].strip(), texto="")
            elif actual and linea.strip():
                actual.texto += linea.strip() + " "
        if actual:
            secciones.append(actual)
    return tuple(secciones)


def buscar(pregunta: str, k: int = 3) -> list[SeccionKB]:
    q = _tokens(pregunta)
    puntajes = []
    definicion = bool(re.search(r"\b(que es|que son|que significa|que quiere decir)\b", numeros.normalizar(pregunta)))
    for s in _base():
        puntaje = 3 * len(q & _tokens(s.titulo)) + len(q & _tokens(s.texto))
        if puntaje and definicion and re.match(r"¿?qu[eé] (es|son)", s.titulo.lower()):
            puntaje += 2
        if puntaje:
            puntajes.append((puntaje, s))
    puntajes.sort(key=lambda x: -x[0])
    return [s for _, s in puntajes[:k]]


# ---------- Campos que el chat puede anotar ----------

Tipo = Literal["pesos", "entero", "digitos", "booleano", "item"]

# clave → (campo en Respuestas, tipo, etiqueta, tema, mínimo, máximo)
CAMPOS: dict[str, tuple[str, Tipo, str, str, float, float]] = {
    "salarios": ("salarios_no_reportados", "pesos", "Salarios del año", "ingresos", 0, 5e10),
    "honorarios": ("honorarios_no_reportados", "pesos", "Honorarios o servicios", "ingresos", 0, 5e10),
    "costos_independiente": ("costos_independiente", "pesos", "Costos del trabajo independiente", "otros", 0, 5e10),
    "arriendos": ("arriendos_no_reportados", "pesos", "Arriendos recibidos", "otros", 0, 5e10),
    "pension": ("pensiones_no_reportadas", "pesos", "Pensión recibida", "ingresos", 0, 5e10),
    "otros_ingresos": ("otros_ingresos_no_reportados", "pesos", "Otros ingresos", "otros", 0, 5e10),
    "dividendos": ("dividendos_no_reportados", "pesos", "Dividendos recibidos", "otros", 0, 5e10),
    "dividendos_gravados": ("dividendos_gravados", "pesos", "Dividendos gravados", "otros", 0, 5e10),
    "retenciones": ("retenciones_no_reportadas", "pesos", "Retenciones que te hicieron", "ingresos", 0, 5e10),
    "dependientes": ("dependientes", "entero", "Personas a cargo", "dependientes", 0, 10),
    "medicina_prepagada": ("medicina_prepagada", "pesos", "Medicina prepagada", "gastos", 0, 1e9),
    "intereses_vivienda": ("intereses_vivienda", "pesos", "Intereses de crédito de vivienda", "gastos", 0, 5e9),
    "aportes_voluntarios": ("aportes_voluntarios_afc_fpv", "pesos", "Aportes voluntarios y AFC", "gastos", 0, 5e9),
    "gmf": ("gmf_pagado", "pesos", "4x1000 pagado", "gastos", 0, 1e9),
    "venta_casa_utilidad": ("ganancias_ocasionales.utilidad_venta_casa_habitacion", "pesos", "Utilidad en la venta de tu casa", "otros", 0, 5e10),
    "venta_otros_activos": ("ganancias_ocasionales.utilidad_venta_otros_activos", "pesos", "Utilidad en la venta de otros bienes", "otros", 0, 5e10),
    "herencia_vivienda": ("ganancias_ocasionales.herencia_vivienda_causante", "pesos", "Herencia: vivienda", "otros", 0, 5e10),
    "herencia_otros_inmuebles": ("ganancias_ocasionales.herencia_otros_inmuebles", "pesos", "Herencia: otros inmuebles", "otros", 0, 5e10),
    "herencia": ("ganancias_ocasionales.herencia_porcion_heredero", "pesos", "Herencia o legado", "otros", 0, 5e10),
    "donaciones": ("ganancias_ocasionales.donaciones_recibidas", "pesos", "Donaciones recibidas", "otros", 0, 5e10),
    "seguros_vida": ("ganancias_ocasionales.seguros_vida", "pesos", "Seguro de vida cobrado", "otros", 0, 5e10),
    "loterias": ("ganancias_ocasionales.loterias_premios", "pesos", "Loterías o premios", "otros", 0, 5e10),
    "declaraciones_previas": ("declaraciones_previas", "entero", "Veces que has declarado antes", "historial", 0, 3),
    "impuesto_anio_anterior": ("impuesto_neto_anio_anterior", "pesos", "Impuesto neto del año anterior", "historial", 0, 5e10),
    "anticipo_anio_anterior": ("anticipo_anio_anterior", "pesos", "Anticipo pagado el año anterior", "historial", 0, 5e10),
    "ultimos_dos_digitos_cedula": ("ultimos_dos_digitos_nit", "digitos", "Dos últimos dígitos de tu cédula", "historial", 0, 99),
    "responsable_iva": ("responsable_iva", "booleano", "Responsable de IVA", "otros", 0, 1),
    "sancionado_ultimos_2_anios": ("sin_sanciones_ultimos_2_anios", "booleano", "Sancionado por declarar tarde en los últimos 2 años", "historial", 0, 1),
    "bien": ("bienes_adicionales", "item", "Bien", "otros", 1, 5e10),
    "deuda": ("deudas_adicionales", "item", "Deuda", "otros", 1, 5e10),
}

TEMAS = ["exogena", "ingresos", "revisar", "dependientes", "gastos", "otros", "historial"]
WIDGETS = {"subir_exogena", "como_descargar", "revisar", "calcular"}


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
    respuestas: Respuestas = Respuestas()
    temas_cubiertos: list[str] = []
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


class Siguiente(BaseModel):
    tema: str | None
    texto: str
    widgets: list[str]
    sugerencias: list[str]


class RespuestaChat(BaseModel):
    respuesta: str
    respuestas: Respuestas
    temas_cubiertos: list[str]
    anotaciones: list[Anotacion] = []
    rechazadas: list[str] = []
    widgets: list[str] = []
    cambiar_anio: int | None = None
    sugerencias: list[str] = []
    fuentes: list[str] = []
    modelo: str | None = None
    con_ia: bool = False


# ---------- Temas pendientes y pregunta siguiente ----------


def _hay_ingresos(r: Respuestas) -> bool:
    return any([r.salarios_no_reportados, r.honorarios_no_reportados, r.pensiones_no_reportadas, r.otros_ingresos_no_reportados, r.arriendos_no_reportados, r.dividendos_no_reportados])


def pendientes(e: EstadoChat) -> list[str]:
    hecho = set(e.temas_cubiertos)
    salida = []
    if not e.tiene_exogena and "exogena" not in hecho:
        salida.append("exogena")
    if not e.tiene_exogena and "exogena" in hecho and not _hay_ingresos(e.respuestas) and "ingresos" not in hecho:
        salida.append("ingresos")
    if e.por_revisar:
        salida.append("revisar")
    for t in ("dependientes", "gastos", "otros", "historial"):
        if t not in hecho:
            salida.append(t)
    return salida


def siguiente(e: EstadoChat) -> Siguiente:
    p = pendientes(e)
    anio = e.anio_gravable
    if not p:
        return Siguiente(
            tema=None,
            texto="Ya tengo lo necesario para armar tu borrador. ¿Lo calculo?",
            widgets=["calcular"],
            sugerencias=["Sí, calcula", "Quiero cambiar algo", "¿Qué es el anticipo?"],
        )
    tema = p[0]
    textos = {
        "exogena": (
            f"Para empezar, ¿tienes tu reporte de información exógena del año {anio}? Es un Excel que se descarga en la página de la DIAN. Si no lo tienes, también podemos empezar con lo que sepas de tus ingresos.",
            ["subir_exogena"],
            ["Ya lo tengo", "¿Qué es la exógena?", "No lo tengo"],
        ),
        "ingresos": (
            f"Cuéntame cuánto recibiste en {anio}. Por ejemplo: «salario de 4 millones al mes» o «honorarios de 60 millones en el año».",
            [],
            ["Salario de 4 millones al mes", "Soy independiente", "¿Qué cuenta como ingreso?"],
        ),
        "revisar": (
            f"Hay {len(e.por_revisar)} dato(s) de tu exógena que necesito que confirmes antes de sumarlos.",
            ["revisar"],
            ["¿Por qué hay que confirmarlos?"],
        ),
        "dependientes": (
            "¿Alguien depende económicamente de ti? Por ejemplo hijos, tu pareja o tus papás.",
            [],
            ["No, nadie", "Tengo 2 hijos", "¿Quién cuenta como dependiente?"],
        ),
        "gastos": (
            "¿Pagas medicina prepagada, intereses de un crédito de vivienda o ahorras en pensión voluntaria o AFC? Esos gastos pueden bajar tu impuesto.",
            [],
            ["No pago nada de eso", "Prepagada de 350 mil al mes", "¿Para qué sirve eso?"],
        ),
        "otros": (
            "¿Tuviste algo más que la exógena no muestre? Por ejemplo arriendos, trabajos como independiente, la venta de algo o un carro.",
            [],
            ["No, nada más", "Tengo un carro de 40 millones", "Recibí arriendos"],
        ),
        "historial": (
            "Por último: ¿cuántas veces has declarado renta antes, y en qué dos números termina tu cédula?",
            [],
            ["Es la primera vez", "Ya he declarado varias veces", "Mi cédula termina en 21"],
        ),
    }
    if tema == "historial":
        r = e.respuestas
        if r.declaraciones_previas is not None and not r.ultimos_dos_digitos_nit:
            textos["historial"] = ("¿En qué dos números termina tu cédula? Con eso reviso tu fecha límite.", [], ["Termina en 21", "¿Por qué lo necesitas?"])
        elif r.declaraciones_previas is None and r.ultimos_dos_digitos_nit:
            textos["historial"] = ("Por último: ¿cuántas veces has declarado renta antes de esta?", [], ["Es la primera vez", "Una vez", "Varias veces"])
    texto, widgets, sug = textos[tema]
    return Siguiente(tema=tema, texto=texto, widgets=widgets, sugerencias=sug)


# ---------- Aplicar anotaciones con validación ----------


def _pesos(v: float) -> str:
    return "$" + f"{v:,.0f}".replace(",", ".")


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
) -> tuple[Respuestas, list[Anotacion], list[str], set[str]]:
    """Valida y aplica lo que se quiere anotar. Devuelve (respuestas, anotadas, rechazadas, temas tocados)."""
    r = respuestas.model_copy(deep=True)
    hechas: list[Anotacion] = []
    rechazadas: list[str] = []
    temas: set[str] = set()
    for item in anotar[:8]:
        clave = str(item.get("campo", ""))
        if clave not in CAMPOS:
            continue
        ruta, tipo, etiqueta, tema, minimo, maximo = CAMPOS[clave]
        if tipo == "pesos":
            v = _a_float(item.get("valor"))
            if v is None:
                continue
            mensual = str(item.get("periodo", "")).lower().startswith("mens")
            if verificar_cifras and not numeros.aparece(v, mensaje_usuario):
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
            if clave == "sancionado_ultimos_2_anios":
                _poner(r, ruta, not b)
            else:
                _poner(r, ruta, b)
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
            from app.tax.modelos import ItemPatrimonio

            getattr(r, ruta).append(ItemPatrimonio(concepto=concepto, valor=v, fuente="chat"))
            hechas.append(Anotacion(clave=clave, etiqueta=f"{etiqueta}: {concepto}", valor=_pesos(v)))
        temas.add(tema)
    return r, hechas, rechazadas, temas


# ---------- Ruta sin IA ----------

_PREGUNTA = re.compile(r"\?|^(que|como|cual|cuales|cuanto|cuanta|cuantos|por que|porque|donde|quien|quienes|para que|cuando|debo|puedo|tengo que|es obligatorio|me toca|sirve)\b")
_NEGATIVO = re.compile(r"^(no|nop|nada|ninguno|ninguna|nadie|tampoco|no tengo|no pago|no aplica)\b|\b(nada de eso|no tengo|ninguno|nadie)\b")


def _sin_ia(t: TurnoChat) -> tuple[str, list[dict[str, Any]], list[str], list[str], list[str]]:
    """Devuelve (respuesta, anotar, cubrir, mostrar, fuentes) usando solo reglas."""
    msg = numeros.normalizar(t.mensaje).strip()
    e = t.estado
    tema = (pendientes(e) or [None])[0]
    anotar: list[dict[str, Any]] = []
    cubrir: list[str] = []
    mostrar: list[str] = []
    cifras = numeros.cantidades(msg)
    mensual = numeros.es_mensual(msg)
    monto = next((c for c in cifras if c >= 1000), None)

    if _PREGUNTA.search(msg):
        kb = buscar(t.mensaje)
        texto = kb[0].texto.strip() if kb else "Esa no la tengo en mi base. Te sugiero consultar el micrositio de renta de la DIAN o a un contador."
        if e.resultado and re.search(r"pag|debo|saldo|favor|cuanto", msg):
            res = e.resultado
            texto = f"Según el cálculo, tu impuesto a cargo es {_pesos(res.get('total_impuesto_cargo', 0))} y el total a pagar {_pesos(res.get('total_a_pagar', 0))}. " + texto
        return texto, [], [], [], [kb[0].titulo] if kb else []

    if re.search(r"\b(calcula|calcular|calculalo|listo|dale)\b", msg) and not pendientes(e):
        return "Perfecto, calculo tu borrador.", [], [], ["calcular"], []

    if re.fullmatch(r"(hola|buenas|buenos dias|buenas tardes|buenas noches|hey|holi|que mas|saludos)[!. ]*", msg):
        return "¡Hola! Pregúntame lo que quieras sobre la declaración de renta, por básico que parezca, o armemos la tuya paso a paso.", [], [], [], []
    if re.search(r"\b(gracias|listo gracias|muy amable)\b", msg) and len(msg) < 30:
        return "Con gusto.", [], [], [], []
    if tema == "exogena":
        if _NEGATIVO.search(msg):
            cubrir.append("exogena")
            return "Listo, empecemos sin ella.", [], cubrir, [], []
        if re.search(r"\b(si|ya|la tengo|lo tengo|tengo|aqui|subir|subo|claro)\b", msg):
            mostrar.append("subir_exogena")
            return "Súbela aquí abajo y la leo por ti.", [], [], mostrar, []
    if tema == "ingresos" and monto:
        campo = "honorarios" if re.search(r"honorario|independiente|servicio", msg) else "pension" if "pension" in msg else "salarios"
        anotar.append({"campo": campo, "valor": monto, "periodo": "mensual" if mensual else "anual"})
        return "Anotado.", anotar, ["ingresos"], [], []
    if tema == "dependientes":
        if _NEGATIVO.search(msg):
            anotar.append({"campo": "dependientes", "valor": 0})
            return "Anotado: nadie a cargo.", anotar, ["dependientes"], [], []
        if cifras:
            anotar.append({"campo": "dependientes", "valor": cifras[0]})
            return "Anotado.", anotar, ["dependientes"], [], []
    if tema == "gastos":
        if _NEGATIVO.search(msg):
            return "Entendido, sin gastos de esos.", [], ["gastos"], [], []
        for patron, campo in (("prepagada|medicina|poliza", "medicina_prepagada"), ("vivienda|hipotec|intereses", "intereses_vivienda"), ("voluntari|afc|avc", "aportes_voluntarios"), ("4x1000|4 x 1000|gmf|cuatro por mil", "gmf")):
            if re.search(patron, msg) and monto:
                anotar.append({"campo": campo, "valor": monto, "periodo": "mensual" if mensual else "anual"})
        if anotar:
            return "Anotado. Si tienes otro gasto de esos, dímelo; si no, escribe «nada más».", anotar, [], [], []
        if re.search(r"nada mas|eso es todo|solo eso", msg):
            return "Listo.", [], ["gastos"], [], []
    if tema == "otros":
        if _NEGATIVO.search(msg) or re.search(r"nada mas|eso es todo", msg):
            return "Listo.", [], ["otros"], [], []
        if monto:
            if re.search(r"carro|moto|vehiculo|casa|apartamento|apto|lote|finca|bien", msg):
                concepto = next(p for p in ("carro", "moto", "vehiculo", "casa", "apartamento", "apto", "lote", "finca", "bien") if p in msg)
                anotar.append({"campo": "bien", "concepto": concepto.capitalize(), "valor": monto})
            elif re.search(r"debo|deuda|prestamo|credito", msg):
                anotar.append({"campo": "deuda", "concepto": "Deuda", "valor": monto})
            elif "arriend" in msg:
                anotar.append({"campo": "arriendos", "valor": monto, "periodo": "mensual" if mensual else "anual"})
            elif re.search(r"honorario|independiente", msg):
                anotar.append({"campo": "honorarios", "valor": monto, "periodo": "mensual" if mensual else "anual"})
            elif re.search(r"vend", msg):
                anotar.append({"campo": "venta_otros_activos", "valor": monto})
            if anotar:
                return "Anotado. ¿Algo más? Si no, escribe «nada más».", anotar, [], [], []
    if tema == "historial":
        if re.search(r"primera|nunca", msg):
            anotar.append({"campo": "declaraciones_previas", "valor": 0})
        elif re.search(r"varias|muchas|siempre|dos|tres|\b[2-9]\b", msg) and not re.search(r"termina", msg):
            anotar.append({"campo": "declaraciones_previas", "valor": 2})
        elif re.search(r"una vez|el ano pasado|\b1\b", msg):
            anotar.append({"campo": "declaraciones_previas", "valor": 1})
        m = re.search(r"termina\w* en (\d{2})|\b(\d{2})\b", msg)
        if m:
            anotar.append({"campo": "ultimos_dos_digitos_cedula", "valor": m.group(1) or m.group(2)})
        if anotar:
            return "Anotado.", anotar, [], [], []

    kb = buscar(t.mensaje)
    if kb:
        return kb[0].texto.strip(), [], [], [], [kb[0].titulo]
    return "No te entendí del todo. Puedes escribirlo con otras palabras o tocar una de las opciones.", [], [], [], []


# ---------- Ruta con IA ----------

SISTEMA = """Eres DeclaraFácil, un asistente que conversa con personas en Colombia sobre su declaración de renta de personas naturales y les ayuda a armar un borrador.

Cómo hablas:
- Español colombiano sencillo y cálido, frases cortas, tuteo. Si usas un término técnico, lo explicas con un ejemplo cotidiano.
- Ninguna pregunta es tonta: responde lo básico con paciencia (qué es la DIAN, qué es renta, si da miedo, etc.).
- Adáptate a la persona: si dice que no sabe nada, explica desde cero; si sabe, ve al grano.

Qué haces en cada turno:
1. Primero responde lo que la persona dijo o preguntó, usando la BASE DE CONOCIMIENTO y el ESTADO (lo que tiene en pantalla, sus datos y su resultado si ya existe).
2. Si tiene sentido, termina con UNA sola pregunta para avanzar con el PRÓXIMO TEMA PENDIENTE. Nunca hagas dos preguntas.
3. Si la persona te da un dato de su declaración, anótalo en "anotar" usando SOLO las claves de CAMPOS. Copia el número tal como lo dijo (por ejemplo 350000) y pon "periodo": "mensual" si es por mes. No conviertas ni sumes cifras: eso lo hace el sistema.
4. Si dice que algo no le aplica (por ejemplo "no tengo hijos", "no pago prepagada"), anota el valor 0 si existe el campo o marca el tema en "cubrir".
5. Si quiere subir la exógena o calcular, usa "mostrar" con "subir_exogena", "como_descargar", "revisar" o "calcular".
6. Si pide cambiar de año gravable (2021 a 2025), usa "cambiar_anio".

Límites:
- No calcules impuestos ni inventes cifras. Las cifras del resultado solo las puedes citar si están en ESTADO.
- No pidas la cédula completa, contraseñas ni números de cuenta. Solo los dos últimos dígitos de la cédula.
- Si el tema no tiene que ver con impuestos ni con la app, responde amable en una frase y vuelve al tema.
- Si no sabes algo, dilo y sugiere a la DIAN o a un contador.
- "respuesta": máximo 110 palabras.

Responde SOLO con este JSON:
{"respuesta": "...", "anotar": [{"campo": "...", "valor": 0, "periodo": "anual", "concepto": "solo para bien o deuda"}], "cubrir": [], "mostrar": [], "cambiar_anio": null, "sugerencias": ["hasta 3 respuestas cortas que la persona podría escribir"]}"""


def _estado_texto(e: EstadoChat) -> str:
    r = e.respuestas
    notados = {k: v for k, v in r.model_dump(exclude={"ganancias_ocasionales", "bienes_adicionales", "deudas_adicionales"}).items() if v not in (0, None, False, "", [])}
    notados.pop("sin_sanciones_ultimos_2_anios", None)
    go = {k: v for k, v in r.ganancias_ocasionales.model_dump().items() if v and not isinstance(v, bool)}
    partes = [
        f"Pantalla actual: {e.pantalla}. Año gravable elegido: {e.anio_gravable}.",
        f"Exógena subida: {'sí, del año ' + str(e.anio_exogena) if e.tiene_exogena else 'no'}.",
    ]
    if e.resumen_exogena:
        partes.append("Datos de la exógena: " + "; ".join(f"{k}: {_pesos(v)}" for k, v in list(e.resumen_exogena.items())[:14]))
    if e.por_revisar:
        partes.append("Datos por confirmar: " + "; ".join(e.por_revisar[:5]))
    partes.append("Lo que ya anotó: " + (json.dumps(notados, ensure_ascii=False) if notados else "nada"))
    if go:
        partes.append("Ganancias ocasionales anotadas: " + json.dumps(go, ensure_ascii=False))
    if r.bienes_adicionales or r.deudas_adicionales:
        partes.append("Bienes/deudas agregados: " + "; ".join(f"{b.concepto} {_pesos(b.valor)}" for b in r.bienes_adicionales + r.deudas_adicionales))
    if e.resultado:
        partes.append("Resultado ya calculado: " + json.dumps(e.resultado, ensure_ascii=False)[:900])
    return "\n".join(partes)


async def responder(t: TurnoChat) -> RespuestaChat:
    e = t.estado
    kb = buscar(t.mensaje)
    sig = siguiente(e)
    respuesta, anotar, cubrir, mostrar, fuentes = "", [], [], [], [s.titulo for s in kb]
    cambiar_anio: int | None = None
    sugerencias: list[str] = []
    modelo, con_ia = None, False

    if cliente.disponible():
        usuario = (
            "CAMPOS:\n" + "\n".join(f"- {k}: {v[2]}" for k, v in CAMPOS.items())
            + "\n\nESTADO:\n" + _estado_texto(e)
            + f"\n\nPRÓXIMO TEMA PENDIENTE: {sig.tema or 'ninguno, ya se puede calcular'}. Pregunta sugerida: {sig.texto}"
            + "\n\nBASE DE CONOCIMIENTO:\n" + ("\n".join(f"### {s.titulo}\n{s.texto}" for s in kb) or "(sin coincidencias)")
            + "\n\nCONVERSACIÓN RECIENTE:\n" + "\n".join(f"{m.rol}: {m.texto[:400]}" for m in t.historial[-8:])
            + f"\n\nMENSAJE DEL USUARIO: {t.mensaje}"
        )
        try:
            r = await cliente.completar("asistente", SISTEMA, usuario, json_mode=True, max_tokens=700)
            j = cliente.extraer_json(r.texto)
            respuesta = str(j.get("respuesta", "")).strip()
            anotar = [x for x in j.get("anotar") or [] if isinstance(x, dict)]
            cubrir = [str(x) for x in j.get("cubrir") or []]
            mostrar = [str(x) for x in j.get("mostrar") or []]
            cambiar_anio = j.get("cambiar_anio")
            sugerencias = [str(s)[:48] for s in (j.get("sugerencias") or [])][:3]
            modelo, con_ia = r.modelo, bool(respuesta)
        except Exception:  # noqa: BLE001 - si el modelo falla, sigue la ruta sin IA
            respuesta = ""

    if not respuesta:
        respuesta, anotar, cubrir, mostrar, fuentes_reglas = _sin_ia(t)
        fuentes = fuentes_reglas

    nuevas, hechas, rechazadas, temas = aplicar(e.respuestas, anotar, t.mensaje)
    cubiertos = set(e.temas_cubiertos) | {c for c in cubrir if c in TEMAS}
    # Un dato anotado cierra su tema, salvo los que suelen tener varias respuestas
    for tema in temas:
        if tema in ("dependientes", "ingresos"):
            cubiertos.add(tema)
    if nuevas.declaraciones_previas is not None and nuevas.ultimos_dos_digitos_nit:
        cubiertos.add("historial")

    if rechazadas:
        respuesta += f" (No anoté {', '.join(rechazadas)} porque no encontré esa cifra en tu mensaje. ¿Me la escribes con números?)"

    estado_nuevo = e.model_copy(update={"respuestas": nuevas, "temas_cubiertos": sorted(cubiertos)})
    sig_nuevo = siguiente(estado_nuevo)
    if not con_ia:
        # Sin IA, la conversación avanza sola: nueva pregunta si cambió el tema,
        # o se repite la actual si el mensaje fue una duda o no se entendió.
        if sig_nuevo.tema != sig.tema or (not hechas and not cubrir and not mostrar):
            respuesta = (respuesta + " " + sig_nuevo.texto).strip()
            mostrar = list(dict.fromkeys(mostrar + sig_nuevo.widgets))
        sugerencias = sig_nuevo.sugerencias
    elif not sugerencias:
        sugerencias = sig_nuevo.sugerencias
    if not pendientes(estado_nuevo) and not e.resultado:
        mostrar = list(dict.fromkeys(mostrar + ["calcular"]))

    if cambiar_anio is not None:
        vigentes = {a["anio_gravable"] for a in repo_reglas.anios_disponibles() if a["estado"] == "vigente"}
        try:
            cambiar_anio = int(cambiar_anio)
        except (TypeError, ValueError):
            cambiar_anio = None
        if cambiar_anio not in vigentes:
            cambiar_anio = None

    return RespuestaChat(
        respuesta=respuesta,
        respuestas=nuevas,
        temas_cubiertos=sorted(cubiertos),
        anotaciones=hechas,
        rechazadas=rechazadas,
        widgets=[w for w in dict.fromkeys(mostrar) if w in WIDGETS],
        cambiar_anio=cambiar_anio,
        sugerencias=sugerencias,
        fuentes=fuentes[:3],
        modelo=modelo,
        con_ia=con_ia,
    )
