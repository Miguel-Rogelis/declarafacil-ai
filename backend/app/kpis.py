"""KPI de DeclaraFácil con su meta y su criterio de aceptación, calculados desde los eventos.

Cada KPI dice cómo se calcula, contra qué meta se compara y si hoy cumple. Los que no se pueden
medir dentro del sistema (exactitud frente a un contador y SUS) se registran a mano desde la
pantalla de administración con el resultado del piloto.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app import almacen

PERFILES = ("asalariado", "independiente", "pensionado", "capital", "primerizo", "exterior")
MIN_MUESTRA = 5  # por debajo de esto el KPI se muestra, pero sin veredicto


@dataclass(frozen=True)
class KPI:
    id: str
    nombre: str
    formula: str
    meta: float
    comparacion: str  # "<=", ">=" o "=="
    unidad: str
    fuente: str = "sistema"
    criterio: str = ""


CATALOGO: list[KPI] = [
    KPI("KPI-01", "Respuestas de IA descartadas por cifras no verificadas", "descartadas ÷ respuestas de IA (chat y resumen)", 10, "<=", "%",
        criterio="Dado un periodo con al menos 5 respuestas de IA, cuando se calcula, entonces a lo sumo el 10 % se descartó por traer cifras que no estaban en los datos."),
    KPI("KPI-02", "Casillas con valor y sin origen", "casillas del 210 con valor y sin documento ni dato de origen", 0, "==", "casillas",
        criterio="Dado cualquier borrador, cuando se arma el 210, entonces ninguna casilla con valor queda sin documento o dato de origen."),
    KPI("KPI-03", "Tiempo de respuesta del chat con IA (p95)", "percentil 95 de los turnos respondidos por la IA", 3000, "<=", "ms",
        criterio="Dado al menos 5 turnos con IA, cuando se mide el percentil 95, entonces es de 3 segundos o menos."),
    KPI("KPI-04", "Tiempo de respuesta del chat sin IA (p95)", "percentil 95 de los turnos respondidos con reglas", 100, "<=", "ms",
        criterio="Dado al menos 5 turnos sin IA, cuando se mide el percentil 95, entonces es de 0,1 segundos o menos."),
    KPI("KPI-05", "Tiempo de análisis de documentos (p95)", "percentil 95 del análisis de cada envío de documentos", 10000, "<=", "ms",
        criterio="Dado al menos 5 envíos de documentos, cuando se mide el percentil 95, entonces es de 10 segundos o menos (incluye IA y OCR)."),
    KPI("KPI-06", "Tiempo hasta el primer borrador (mediana)", "desde el primer evento de la sesión hasta su primera liquidación", 15, "<=", "min",
        criterio="Dado al menos 5 sesiones que llegan al borrador, cuando se calcula la mediana, entonces es de 15 minutos o menos."),
    KPI("KPI-07", "Sesiones con documentos que llegan al borrador", "sesiones con liquidación ÷ sesiones que subieron documentos", 70, ">=", "%",
        criterio="Dado al menos 5 sesiones que subieron documentos, cuando se calcula, entonces al menos el 70 % llegó al borrador."),
    KPI("KPI-08", "Llamadas de IA por declaración", "llamadas a modelos (sin caché) ÷ sesiones con borrador", 20, "<=", "llamadas",
        criterio="Dado al menos 5 sesiones con borrador, cuando se calcula, entonces el promedio es de 20 llamadas o menos."),
    KPI("KPI-09", "Costo de IA por declaración", "costo de las llamadas ÷ sesiones con borrador", 0.30, "<=", "USD",
        criterio="Dado al menos 5 sesiones con borrador, cuando se calcula con los precios del modelo, entonces el costo promedio es de USD 0,30 o menos."),
    KPI("KPI-10", "Turnos del chat sin IA por falta de cupo o falla", "turnos sin cupo o con error de IA ÷ turnos del chat", 10, "<=", "%",
        criterio="Dado al menos 5 turnos del chat, cuando se calcula, entonces a lo sumo el 10 % se quedó sin IA por cupo o falla."),
    KPI("KPI-11", "Errores del servidor", "respuestas 5xx ÷ solicitudes a la API", 1, "<=", "%",
        criterio="Dado al menos 5 solicitudes a la API, cuando se calcula, entonces a lo sumo el 1 % termina en error 5xx."),
    KPI("KPI-12", "Tokens de entrada por turno del chat (mediana)", "mediana de los tokens enviados al modelo por turno", 5000, "<=", "tokens",
        criterio="Dado al menos 5 turnos con IA, cuando se calcula la mediana, entonces es de 5.000 tokens o menos."),
    KPI("KPI-13", "Brecha de finalización entre perfiles", "máximo menos mínimo de KPI-07 entre perfiles con 5 sesiones o más", 15, "<=", "puntos",
        criterio="Dado al menos dos perfiles con 5 sesiones, cuando se compara la finalización, entonces la diferencia es de 15 puntos o menos."),
    KPI("KPI-14", "Casillas iguales a las del contador", "casillas iguales ÷ casillas comparadas en el piloto", 95, ">=", "%", fuente="piloto",
        criterio="Dado el piloto A con al menos 20 casos, cuando se comparan casilla por casilla, entonces al menos el 95 % coincide."),
    KPI("KPI-15", "Errores críticos sin alerta", "diferencias > $1.000 en obligación, RLG, impuesto neto o saldo sin alerta", 0, "==", "casos", fuente="piloto",
        criterio="Dado el piloto A, cuando se comparan los resultados clave, entonces no hay ningún error crítico sin alerta."),
    KPI("KPI-16", "Usabilidad (SUS)", "puntaje promedio del cuestionario SUS", 68, ">=", "puntos", fuente="piloto",
        criterio="Dado el piloto B con al menos 8 participantes, cuando responden el SUS, entonces el promedio es de 68 o más."),
]

MANUALES = {k.id for k in CATALOGO if k.fuente == "piloto"}


def _p(valores: list[float], q: float) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * q
    i, f = int(k), k - int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * f


def _pct(a: float, b: float) -> float | None:
    return 100 * a / b if b else None


def _estado(k: KPI, valor: float | None, n: int) -> str:
    if valor is None:
        return "sin_datos"
    if k.fuente == "sistema" and n < MIN_MUESTRA:
        return "muestra_pequena"
    ok = {"<=": valor <= k.meta, ">=": valor >= k.meta, "==": abs(valor - k.meta) < 1e-9}[k.comparacion]
    return "cumple" if ok else "no_cumple"


def _ts(e: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(e["creado"])


def calcular(eventos: list[dict[str, Any]], manuales: dict[str, Any] | None = None) -> dict[str, Any]:
    por_tipo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sesiones: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in eventos:
        por_tipo[e["tipo"]].append(e)
        if e.get("sesion") and e["sesion"] != "sin-sesion":
            sesiones[e["sesion"]].append(e)

    chat = por_tipo["chat"]
    liq = por_tipo["liquidacion"]
    ia = por_tipo["ia"]
    http = por_tipo["http"]
    docs = por_tipo["documentos"]

    con_doc = {s for s, ev in sesiones.items() if any(x["tipo"] == "documentos" and x.get("n_ok", 0) > 0 for x in ev)}
    con_borrador = {s for s, ev in sesiones.items() if any(x["tipo"] == "liquidacion" for x in ev)}

    def perfil_de(s: str) -> set[str]:
        """Perfiles de la sesión: los que se vieron al leer sus documentos o al calcular."""
        return {p for x in sesiones[s] if x["tipo"] in ("documentos", "liquidacion") for p in PERFILES if x.get(p)}

    tiempos_borrador = []
    for s in con_borrador:
        ev = sorted(sesiones[s], key=_ts)
        primera = next(x for x in ev if x["tipo"] == "liquidacion")
        tiempos_borrador.append((_ts(primera) - _ts(ev[0])).total_seconds() / 60)

    ia_reales = [x for x in ia if x.get("resultado") == "ok"]
    en_borrador = [x for x in ia_reales if x.get("sesion") in con_borrador]
    respuestas_ia = [x for x in chat if x.get("ia_intento")] + [x for x in liq if x.get("explicacion_ia") or x.get("explicacion_descartada")]
    descartadas = sum(1 for x in chat if x.get("descartada")) + sum(1 for x in liq if x.get("explicacion_descartada"))
    chat_ia = [x["ms"] for x in chat if x.get("con_ia") and "ms" in x]
    chat_sin = [x["ms"] for x in chat if not x.get("con_ia") and "ms" in x]
    sin_ia_falla = sum(1 for x in chat if x.get("sin_cupo") or x.get("error_ia"))
    tokens = [x["tokens_entrada"] for x in chat if x.get("tokens_entrada")]

    finalizacion: dict[str, dict[str, Any]] = {}
    for p in PERFILES:
        base = {s for s in con_doc if p in perfil_de(s)}
        hechas = {s for s in base if s in con_borrador}
        finalizacion[p] = {"sesiones": len(base), "borradores": len(hechas), "pct": _pct(len(hechas), len(base))}
    comparables = [v["pct"] for v in finalizacion.values() if v["sesiones"] >= MIN_MUESTRA and v["pct"] is not None]

    calculos: dict[str, tuple[float | None, int]] = {
        "KPI-01": (_pct(descartadas, len(respuestas_ia)), len(respuestas_ia)),
        "KPI-02": (float(sum(x.get("casillas_sin_origen", 0) for x in liq)) if liq else None, len(liq) or MIN_MUESTRA),
        "KPI-03": (_p(chat_ia, 0.95), len(chat_ia)),
        "KPI-04": (_p(chat_sin, 0.95), len(chat_sin)),
        "KPI-05": (_p([x["ms"] for x in docs if "ms" in x], 0.95), len(docs)),
        "KPI-06": (statistics.median(tiempos_borrador) if tiempos_borrador else None, len(tiempos_borrador)),
        "KPI-07": (_pct(len(con_doc & con_borrador), len(con_doc)), len(con_doc)),
        "KPI-08": (len(en_borrador) / len(con_borrador) if con_borrador else None, len(con_borrador)),
        "KPI-09": (sum(x.get("costo_usd", 0) for x in en_borrador) / len(con_borrador) if con_borrador else None, len(con_borrador)),
        "KPI-10": (_pct(sin_ia_falla, len(chat)), len(chat)),
        "KPI-11": (_pct(sum(1 for x in http if x.get("estado", 0) >= 500), len(http)), len(http)),
        "KPI-12": (statistics.median(tokens) if tokens else None, len(tokens)),
        "KPI-13": ((max(comparables) - min(comparables)) if len(comparables) >= 2 else None, len(comparables) * MIN_MUESTRA),
    }
    manuales = manuales or {}
    salida = []
    for k in CATALOGO:
        if k.fuente == "piloto":
            m = manuales.get(k.id) or {}
            valor, n = m.get("valor"), int(m.get("n") or 0)
        else:
            valor, n = calculos[k.id]
        salida.append({
            "id": k.id, "nombre": k.nombre, "formula": k.formula, "meta": k.meta, "comparacion": k.comparacion, "unidad": k.unidad,
            "fuente": k.fuente, "criterio": k.criterio, "valor": None if valor is None else round(valor, 4), "n": n,
            "estado": _estado(k, valor, n), "nota": (manuales.get(k.id) or {}).get("nota") if k.fuente == "piloto" else None,
        })
    return {
        "eventos": len(eventos),
        "sesiones": len(sesiones),
        "sesiones_con_documentos": len(con_doc),
        "sesiones_con_borrador": len(con_borrador),
        "kpis": salida,
        "por_perfil": finalizacion,
        "llamadas_ia": {"total": len(ia), "ok": len(ia_reales), "cache": sum(1 for x in ia if x.get("resultado") == "cache"),
                        "error": sum(1 for x in ia if x.get("resultado") == "error"), "sin_cupo": sum(1 for x in ia if x.get("resultado") == "sin_cupo")},
    }


def resumen(dias: int = 30) -> dict[str, Any]:
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
    a = almacen.obtener()
    datos = calcular(a.eventos(desde), a.leer("kpis:manuales") or {})
    datos["dias"] = dias
    datos["desde"] = desde
    return datos


def guardar_manual(kpi: str, valor: float, n: int, nota: str, autor: str) -> dict[str, Any]:
    if kpi not in MANUALES:
        raise KeyError(kpi)
    a = almacen.obtener()
    actuales = a.leer("kpis:manuales") or {}
    actuales[kpi] = {"valor": float(valor), "n": int(n), "nota": nota[:300], "fecha": datetime.now(timezone.utc).date().isoformat()}
    a.escribir("kpis:manuales", actuales, autor)
    return actuales[kpi]


Csv = Callable[[list[dict[str, Any]]], str]


def a_csv(eventos: list[dict[str, Any]]) -> str:
    columnas = ["creado", "sesion", "tipo"] + sorted({k for e in eventos for k in e} - {"creado", "sesion", "tipo"})
    filas = [",".join(columnas)]
    for e in eventos:
        celdas = []
        for c in columnas:
            v = e.get(c, "")
            if isinstance(v, list):
                v = "|".join(map(str, v))
            celdas.append(str(v).replace(",", ";"))
        filas.append(",".join(celdas))
    return "\n".join(filas) + "\n"
