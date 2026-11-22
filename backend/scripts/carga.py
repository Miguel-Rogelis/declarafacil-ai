"""Prueba de carga y de costo del pico de temporada (HU-40, RNF-07, RNF-08, KPI-08 a KPI-12).

Simula N declaraciones completas contra la app real (en el mismo proceso, sin red): cada una sube la
exógena y dos certificados, liquida, conversa 12 turnos con el agente (incluye responder lo que pregunta antes de calcular), vuelve a liquidar con lo que
contó y pregunta por el resultado. Lo único falso es OpenRouter: un doble que responde con la
latencia típica de Claude Haiku 4.5 y cuenta los tokens de entrada reales de cada llamada
(≈ 4 caracteres por token, lo mismo que usa la app cuando el proveedor no informa el uso).

    cd backend
    python scripts/carga.py                         # 95 declaraciones, 95 a la vez, perfil de pago
    python scripts/carga.py --declaraciones 20 --concurrencia 5 --escala 0.2
    python scripts/carga.py --conservador            # costo con salidas casi al máximo
    python scripts/carga.py --salida ../docs/carga.json

Supuestos (se imprimen con el resultado):
- Todas las declaraciones del día llegan a la vez: es el peor caso, el pico real es mucho más suave.
- Sin caché de IA: cada persona trae documentos distintos, así que no se aprovecha la de la app.
- Tokens de salida por agente: «típico» (lo que piden los prompts: chat 150, explicador 250,
  intérprete 400) o, con --conservador, casi el máximo (chat 300, explicador 400, intérprete 900).
  El costo se juzga con el conservador; la latencia con el típico.
- Latencia de Haiku 4.5: 0,6 s hasta el primer token + 110 tokens/s, multiplicada por --escala.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

# La configuración se lee al importar la app: primero el entorno de la prueba.
os.environ.setdefault("PERFIL_MODELOS", "pago")
os.environ["LLM_MODE"] = "openrouter"
os.environ["OPENROUTER_API_KEY"] = "sk-carga-falsa"
os.environ["ALMACEN"] = "memoria"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging  # noqa: E402

import httpx  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)  # una línea por solicitud tapa el resultado

from app import almacen, kpis  # noqa: E402
from app.agents import clasificador, explicador, interprete  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import cliente, cupo  # noqa: E402
from app.main import app  # noqa: E402

DEMO = settings.data_dir / "demo"
# Tokens de salida por agente. «tipico»: lo que piden los prompts (el chat responde en máximo 80
# palabras y omite las claves vacías; el explicador, un párrafo). «conservador»: casi el máximo permitido.
SALIDAS = {
    "tipico": {"clasificador": 40, "interprete": 400, "explicador": 250, "asistente": 150},
    "conservador": {"clasificador": 60, "interprete": 900, "explicador": 400, "asistente": 300},
}
SALIDA = dict(SALIDAS["tipico"])
MENSAJES = [
    "hola, quiero hacer mi declaración",
    "tengo 2 hijos menores que dependen de mí",
    "pago medicina prepagada, 4.800.000 al año",
    "intereses de crédito de vivienda 9.500.000 en el año",
    "aportes voluntarios a pensión 6.000.000 en el año",
    "¿qué es la renta exenta del 25 %?",
    "compras con factura electrónica por 30.000.000 en el año",
    "¿cuándo vence mi declaración? mi cédula termina en 21",
    "calcula",
    "no tengo carro ni moto ni otros bienes, y no tengo deudas",
    "no recibí plata por fuera de bancos, calcula con lo que tienes",
    "¿por qué me sale ese saldo?",
]


class OpenRouterFalso:
    """Responde como Haiku 4.5 sin salir a internet y anota qué se le pidió."""

    def __init__(self, escala: float) -> None:
        self.escala = escala
        self.llamadas: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    @staticmethod
    def _agente(sistema: str) -> str:
        for nombre, mod in (("clasificador", clasificador), ("interprete", interprete), ("explicador", explicador)):
            if sistema.startswith(mod.SISTEMA[:60]):
                return nombre
        return "asistente"

    async def _create(self, model, messages, max_tokens=1200, **kw):
        if kw.get("stream"):
            raise RuntimeError("la prueba de carga no usa streaming")
        agente = self._agente(messages[0]["content"])
        entrada = cliente.estimar_tokens("".join(m["content"] for m in messages))
        salida = min(SALIDA[agente], max_tokens)
        self.llamadas.append({"agente": agente, "modelo": model, "entrada": entrada, "salida": salida,
                              "sin_retencion": (kw.get("extra_body") or {}).get("provider") == {"data_collection": "deny"}})
        await asyncio.sleep(self.escala * (0.6 + salida / 110 + entrada / 20_000) * random.uniform(0.8, 1.3))
        texto = {
            "clasificador": '{"tipo": "desconocido", "confianza": 0.3, "motivo": "prueba de carga"}',
            "interprete": '{"conceptos": []}',
            "explicador": "Tu borrador sale de sumar tus ingresos y restar lo que la ley permite. Revisa cada casilla antes de presentar.",
            "asistente": '{"respuesta": "Listo, lo tengo en cuenta. ¿Quieres contarme algo más?"}',
        }[agente]
        if agente == "asistente" and re.search(r"MENSAJE DEL USUARIO: .*calcula", messages[-1]["content"]):
            texto = '{"respuesta": "Listo, calculo tu borrador con todo lo que me contaste.", "calcular": true}'
        return SimpleNamespace(model=model, usage=SimpleNamespace(prompt_tokens=entrada, completion_tokens=salida),
                               choices=[SimpleNamespace(message=SimpleNamespace(content=texto))])


def _sse(texto: str) -> list[tuple[str | None, dict]]:
    evs, ev = [], None
    for linea in texto.splitlines():
        if linea.startswith("event:"):
            ev = linea[6:].strip()
        elif linea.startswith("data:"):
            evs.append((ev, json.loads(linea[5:].strip())))
    return evs


async def declaracion(c: httpx.AsyncClient, i: int, tiempos: dict[str, list[float]], fallas: list[str]) -> bool:
    h = {"x-sesion": str(uuid.uuid4()), "x-forwarded-for": f"10.0.{i // 250}.{i % 250 + 1}"}

    async def medir(nombre: str, coro):
        t0 = time.perf_counter()
        r = await coro
        tiempos.setdefault(nombre, []).append((time.perf_counter() - t0) * 1000)
        if r.status_code >= 500:
            fallas.append(f"{nombre}: HTTP {r.status_code}")
        return r

    archivos = [("archivos", (n, (DEMO / n).read_bytes())) for n in ("exogena_demo_2025.xlsx", "certificado_220_demo_2025.pdf", "certificado_banco_demo_2025.pdf")]
    r = await medir("documentos", c.post("/api/documentos/analizar", files=archivos, data={"anio_gravable": "2025"}, headers=h))
    fin = _sse(r.text)[-1]
    if fin[0] != "resultado":
        fallas.append(f"documentos: {fin}")
        return False
    ext = fin[1]["extraccion"]
    base = {"anio_gravable": 2025, "filas": ext["filas"], "topes": ext["topes"], "ultimos_dos_digitos_nit": ext["ultimos_dos_digitos_nit"]}
    r = await medir("liquidar", c.post("/api/declaracion/liquidar", json=base, headers=h))
    resultado = _sse(r.text)[-1][1]
    estado = {"anio_gravable": 2025, "tiene_exogena": True, "anio_exogena": 2025, "filas": ext["filas"], "topes": ext["topes"],
              "resultado": resultado.get("liquidacion") if isinstance(resultado, dict) else None}
    historial: list[dict] = []
    for m in MENSAJES:
        r = await medir("chat", c.post("/api/chat", json={"mensaje": m, "historial": historial[-10:], "estado": estado}, headers=h))
        if r.status_code != 200:
            fallas.append(f"chat: HTTP {r.status_code}")
            continue
        j = r.json()
        if j.get("limite_ia"):
            fallas.append("chat: respondió sin IA por cupo")
        estado["respuestas"] = j["respuestas"]
        estado["pregunta_pendiente"] = j.get("pregunta")
        historial += [{"rol": "usuario", "texto": m}, {"rol": "asistente", "texto": j["respuesta"]}]
        if j.get("calcular"):
            r = await medir("liquidar", c.post("/api/declaracion/liquidar", json={**base, "respuestas": j["respuestas"]}, headers=h))
            fin = _sse(r.text)[-1]
            if fin[0] == "resultado":
                estado["resultado"] = fin[1].get("liquidacion")
    return True


def p95(xs: list[float]) -> float:
    return statistics.quantiles(xs, n=20)[-1] if len(xs) >= 2 else (xs[0] if xs else 0.0)


async def correr(n: int, concurrencia: int, escala: float) -> dict:
    falso = OpenRouterFalso(escala)
    cliente._get_cliente = lambda: falso  # type: ignore[assignment]
    cliente.CACHEABLES = set()  # sin caché: cada persona trae documentos distintos
    almacen.reiniciar()
    cupo.reiniciar()
    tiempos: dict[str, list[float]] = {}
    fallas: list[str] = []
    sem = asyncio.Semaphore(concurrencia)

    async def una(i: int, c: httpx.AsyncClient) -> bool:
        async with sem:
            try:
                return await declaracion(c, i, tiempos, fallas)
            except Exception as e:  # noqa: BLE001
                fallas.append(f"declaración {i}: {type(e).__name__}: {e}")
                return False

    t0 = time.perf_counter()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://carga", timeout=300) as c:
        ok = sum(await asyncio.gather(*(una(i, c) for i in range(n))))
    duracion = time.perf_counter() - t0
    await asyncio.sleep(0.1)

    eventos = almacen.obtener().eventos()
    ia = [e for e in eventos if e["tipo"] == "ia"]
    por_agente: dict[str, dict] = {}
    for x in falso.llamadas:
        a = por_agente.setdefault(x["agente"], {"llamadas": 0, "entrada": [], "salida": 0})
        a["llamadas"] += 1
        a["entrada"].append(x["entrada"])
        a["salida"] += x["salida"]
    costo = sum(e.get("costo_usd") or 0 for e in ia)
    k = {x["id"]: x for x in kpis.calcular(eventos)["kpis"]}
    return {
        "supuestos": {
            "declaraciones": n, "concurrencia": concurrencia, "escala_latencia": escala, "perfil": settings.perfil_modelos,
            "modelos_asistente": cliente.configuracion.obtener("asistente").get("modelos"),
            "tokens_salida_por_agente": dict(SALIDA), "cache": False,
            "cupo": {"por_hora_por_persona": cupo.POR_HORA, "tope_diario": cupo.TOPE_DIARIO},
        },
        "duracion_s": round(duracion, 1),
        "declaraciones_ok": ok,
        "rechazos_por_cupo": sum(1 for e in ia if e.get("resultado") == "sin_cupo"),
        "errores_5xx": sum(1 for f in fallas if "HTTP 5" in f),
        "fallas": fallas[:10],
        "llamadas_ia": len(falso.llamadas),
        "llamadas_por_declaracion": round(len(falso.llamadas) / max(n, 1), 1),
        "todas_sin_retencion": all(x["sin_retencion"] for x in falso.llamadas),
        "por_agente": {a: {"llamadas": d["llamadas"], "entrada_mediana": int(statistics.median(d["entrada"])),
                           "entrada_max": max(d["entrada"]), "salida_total": d["salida"]} for a, d in por_agente.items()},
        "costo_total_usd": round(costo, 4),
        "costo_por_declaracion_usd": round(costo / max(ok, 1), 4),
        "latencia_ms": {k2: {"p50": round(statistics.median(v)), "p95": round(p95(v)), "n": len(v)} for k2, v in tiempos.items()},
        "kpi": {i: {"valor": k[i]["valor"], "meta": f'{k[i]["comparacion"]} {k[i]["meta"]} {k[i]["unidad"]}', "estado": k[i]["estado"]}
                for i in ("KPI-03", "KPI-05", "KPI-07", "KPI-08", "KPI-09", "KPI-10", "KPI-11", "KPI-12")},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--declaraciones", type=int, default=95)
    ap.add_argument("--concurrencia", type=int, default=95)
    ap.add_argument("--escala", type=float, default=1.0, help="multiplica la latencia simulada del modelo (1 = real)")
    ap.add_argument("--salida", type=Path, help="guarda el resultado en JSON")
    ap.add_argument("--conservador", action="store_true", help="tokens de salida casi al máximo (para acotar el costo)")
    a = ap.parse_args()
    random.seed(7)
    SALIDA.update(SALIDAS["conservador" if a.conservador else "tipico"])
    res = asyncio.run(correr(a.declaraciones, a.concurrencia, a.escala))
    texto = json.dumps(res, ensure_ascii=False, indent=2)
    print(texto)
    if a.salida:
        a.salida.parent.mkdir(parents=True, exist_ok=True)
        a.salida.write_text(texto + "\n", encoding="utf-8")
    cumple = res["rechazos_por_cupo"] == 0 and res["errores_5xx"] == 0 and res["costo_por_declaracion_usd"] <= 0.30
    print(f"\nHU-40: {'CUMPLE' if cumple else 'NO CUMPLE'} · {res['declaraciones_ok']}/{a.declaraciones} declaraciones, "
          f"{res['rechazos_por_cupo']} rechazos por cupo, USD {res['costo_por_declaracion_usd']:.3f} por declaración")
    sys.exit(0 if cumple else 1)


if __name__ == "__main__":
    main()
