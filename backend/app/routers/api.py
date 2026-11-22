"""Endpoints HTTP. Los flujos largos responden con Server-Sent Events para mostrar
en vivo qué agente está trabajando."""

import asyncio
import time
from collections.abc import AsyncIterable
from typing import Annotated, Any

import httpx
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.responses import Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app import almacen, cuentas, kpis, metricas, orquestador
from app.agents import asistente, configuracion
from app.agents.base import EventoAgente
from app.config import settings
from app.llm import cliente, cupo
from app.tax import reglas as repo_reglas

router = APIRouter(prefix="/api")


async def _admin(x_admin_token: Annotated[str | None, Header()] = None, authorization: Annotated[str | None, Header()] = None) -> str:
    """Quién administra: la clave ADMIN_TOKEN o una cuenta cuyo correo está en ADMIN_EMAILS. Devuelve el autor para el historial."""
    if settings.admin_token and x_admin_token == settings.admin_token:
        return "clave de administrador"
    if settings.admin_emails:
        correo = await cuentas.correo_de(authorization)
        if correo and correo in settings.admin_emails:
            return correo
    if not settings.admin_token and not settings.admin_emails:
        return "sin clave (modo local)"
    raise HTTPException(status_code=401, detail="Necesitas la clave de administrador o una cuenta de administrador para esto")


AdminDep = Annotated[str, Depends(_admin)]


def _evento(item: orquestador.Salida) -> ServerSentEvent:
    if isinstance(item, EventoAgente):
        return ServerSentEvent(data=item, event="agente")
    if isinstance(item, orquestador.ErrorFlujo):
        return ServerSentEvent(data=item, event="error")
    return ServerSentEvent(data=item, event="resultado")


class Supabase(BaseModel):
    url: str
    anon_key: str
    google_client_id: str | None = None


class Estado(BaseModel):
    modo_llm: str
    anios: list[dict[str, Any]]
    admin_protegido: bool
    ia_restante_hoy: int
    supabase: Supabase | None = None  # cuentas activas: el navegador inicia sesión con esto
    perfil_modelos: str = "gratis"
    almacen: str = "memoria"  # dónde se guardan reglas, agentes y métricas
    version_consentimiento: str = "2026-11"


@router.get("/estado")
def estado() -> Estado:
    return Estado(modo_llm=settings.modo_llm, anios=repo_reglas.anios_disponibles(), admin_protegido=bool(settings.admin_token or settings.admin_emails),
                  ia_restante_hoy=cupo.restante_hoy(), perfil_modelos=configuracion.perfil(), almacen=almacen.obtener().nombre,
                  supabase=Supabase(url=settings.supabase_url, anon_key=settings.supabase_anon_key, google_client_id=settings.google_client_id or None) if cuentas.activas() else None)


@router.post("/documentos/analizar", response_class=EventSourceResponse)
async def analizar_documentos(
    archivos: Annotated[list[UploadFile] | None, File(description="Exógena y certificados en .xlsx o .pdf (uno o varios)")] = None,
    archivo: Annotated[UploadFile | None, File(description="Un solo archivo (forma anterior)")] = None,
    anio_gravable: Annotated[int, Form()] = 2025,
    previas: Annotated[str | None, Form(description="JSON con lo que ya se había leído: filas, topes y documentos")] = None,
) -> AsyncIterable[ServerSentEvent]:
    subidos = [*(archivos or []), *([archivo] if archivo else [])]
    if not subidos:
        yield ServerSentEvent(data={"mensaje": "No llegó ningún archivo", "agente": "lector"}, event="error")
        return
    if len(subidos) > orquestador.MAX_ARCHIVOS:
        yield ServerSentEvent(data={"mensaje": f"Sube máximo {orquestador.MAX_ARCHIVOS} archivos a la vez", "agente": "lector"}, event="error")
        return
    limite = settings.max_upload_mb * 1024 * 1024
    contenidos: list[tuple[bytes, str]] = []
    for a in subidos:
        contenido = await a.read(limite + 1)
        if len(contenido) > limite:
            yield ServerSentEvent(data={"mensaje": f"{a.filename} supera {settings.max_upload_mb} MB", "agente": "lector"}, event="error")
            return
        contenidos.append((contenido, a.filename or "archivo"))
    try:
        antes = orquestador.Previas.model_validate_json(previas) if previas else None
    except ValueError:
        antes = None
    async for item in orquestador.procesar_documentos(contenidos, anio_gravable, antes):
        yield _evento(item)
    del contenidos


@router.post("/declaracion/liquidar", response_class=EventSourceResponse)
async def liquidar(solicitud: orquestador.SolicitudLiquidacion) -> AsyncIterable[ServerSentEvent]:
    async for item in orquestador.procesar_liquidacion(solicitud):
        yield _evento(item)


@router.post("/chat/diagnostico")
def chat_diagnostico(estado: asistente.EstadoChat) -> asistente.RespuestaChat:
    """Lo que el agente dice apenas lee la exógena: qué deduce y qué le falta (sin IA)."""
    return asistente.diagnosticar(estado)


def _registrar_chat(r: asistente.RespuestaChat, t0: float) -> None:
    m = metricas.marcas()
    metricas.registrar("chat", ms=(time.perf_counter() - t0) * 1000, ia_intento=cliente.disponible(), con_ia=r.con_ia,
                       descartada=bool(m.get("descartada")), sin_cupo=r.limite_ia or bool(m.get("sin_cupo")), error_ia=bool(m.get("error_ia")),
                       tokens_entrada=m.get("tokens_entrada"), calcular=r.calcular, pregunta=r.pregunta is not None)


@router.post("/chat")
async def chat(turno: asistente.TurnoChat) -> asistente.RespuestaChat:
    if not turno.mensaje.strip():
        raise HTTPException(status_code=422, detail="Escribe un mensaje")
    turno.mensaje = turno.mensaje[:1000]
    t0 = time.perf_counter()
    r = await asistente.responder(turno)
    _registrar_chat(r, t0)
    return r


@router.post("/chat/en-vivo", response_class=EventSourceResponse)
async def chat_en_vivo(turno: asistente.TurnoChat) -> AsyncIterable[ServerSentEvent]:
    """Igual que /chat, pero el texto del modelo llega por partes («texto») y al final la respuesta validada («final»)."""
    if not turno.mensaje.strip():
        yield ServerSentEvent(data={"mensaje": "Escribe un mensaje"}, event="error")
        return
    turno.mensaje = turno.mensaje[:1000]
    cola: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def al_texto(parte: str) -> None:
        await cola.put(("texto", parte))

    t0 = time.perf_counter()

    async def trabajar() -> None:
        try:
            r = await asistente.responder(turno, al_texto)
            _registrar_chat(r, t0)
            await cola.put(("final", r))
        except Exception as ex:  # noqa: BLE001 - el front muestra el error en el chat
            await cola.put(("error", {"mensaje": f"No pude responder: {ex}"}))

    tarea = asyncio.create_task(trabajar())
    try:
        while True:
            tipo, dato = await cola.get()
            yield ServerSentEvent(data={"texto": dato} if tipo == "texto" else dato, event=tipo)
            if tipo != "texto":
                break
    finally:
        tarea.cancel()


# ---------- Reglas por año ----------


@router.get("/reglas")
def listar_reglas() -> list[dict[str, Any]]:
    return repo_reglas.anios_disponibles()


@router.get("/reglas/{anio}")
def ver_reglas(anio: int) -> dict[str, Any]:
    try:
        return repo_reglas.cargar(anio)
    except repo_reglas.ReglasNoEncontradas as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/reglas/{anio}")
def guardar_reglas(anio: int, datos: Annotated[dict[str, Any], Body()], autor: AdminDep) -> dict[str, Any]:
    try:
        repo_reglas.guardar(anio, datos, autor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 - el almacén no respondió
        raise HTTPException(status_code=503, detail=f"No pude guardar el cambio: {e}") from e
    return repo_reglas.cargar(anio)


class Clonar(BaseModel):
    destino: int
    uvt: float | None = None


@router.post("/reglas/{anio}/clonar")
def clonar_reglas(anio: int, c: Clonar, autor: AdminDep) -> dict[str, Any]:
    try:
        return repo_reglas.clonar(anio, c.destino, c.uvt, autor)
    except (ValueError, repo_reglas.ReglasNoEncontradas) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


class Revertir(BaseModel):
    version: int | None = Field(default=None, description="Versión del historial; vacío = volver al archivo del repositorio")


@router.get("/reglas/{anio}/historial")
def historial_reglas(anio: int, _: AdminDep) -> list[dict[str, Any]]:
    return repo_reglas.historial(anio)


@router.post("/reglas/{anio}/revertir")
def revertir_reglas(anio: int, r: Revertir, autor: AdminDep) -> dict[str, Any]:
    try:
        return repo_reglas.revertir(anio, r.version, autor)
    except repo_reglas.ReglasNoEncontradas as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ---------- Agentes ----------


@router.get("/agentes")
def listar_agentes() -> dict[str, dict[str, Any]]:
    return configuracion.todos()


@router.get("/agentes/historial")
def historial_agentes(_: AdminDep) -> list[dict[str, Any]]:
    return configuracion.historial()


@router.post("/agentes/revertir")
def revertir_agentes(r: Revertir, autor: AdminDep) -> dict[str, dict[str, Any]]:
    try:
        return configuracion.revertir(r.version, autor)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="No existe esa versión de los agentes") from e


@router.put("/agentes/{agente}")
def actualizar_agente(agente: str, cambios: Annotated[dict[str, Any], Body()], autor: AdminDep) -> dict[str, Any]:
    try:
        return configuracion.actualizar(agente, cambios, autor)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Agente no encontrado") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/agentes/modelos-gratis")
async def modelos_gratis(todos: bool = False) -> list[dict[str, Any]]:
    """Lista los modelos gratuitos que OpenRouter ofrece hoy (rotan casi cada semana). Con todos=true, también los de pago y su precio."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{settings.openrouter_base_url}/models")
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"No pude consultar OpenRouter: {e}") from e
    salida = []
    for m in r.json().get("data", []):
        precio = m.get("pricing", {})
        gratis = m["id"].endswith(":free") or (precio.get("prompt") == "0" and precio.get("completion") == "0")
        if gratis or todos:
            item: dict[str, Any] = {"id": m["id"], "nombre": m.get("name"), "contexto": m.get("context_length")}
            if not gratis:
                try:  # OpenRouter da el precio por token; aquí va por millón de tokens
                    item["usd_millon_entrada"] = round(float(precio.get("prompt", 0)) * 1e6, 4)
                    item["usd_millon_salida"] = round(float(precio.get("completion", 0)) * 1e6, 4)
                except (TypeError, ValueError):
                    pass
            salida.append(item)
    return sorted(salida, key=lambda x: x["id"])


@router.post("/agentes/{agente}/probar")
async def probar_agente(agente: str) -> dict[str, Any]:
    if not cliente.disponible():
        return {"ok": False, "detalle": "Sin OPENROUTER_API_KEY: la app está en modo simulado"}
    try:
        r = await cliente.completar(agente, "Responde solo: OK", "Prueba de conexión", max_tokens=5)
        return {"ok": True, "modelo": r.modelo, "respuesta": r.texto[:40]}
    except cliente.LLMNoDisponible as e:
        return {"ok": False, "detalle": str(e)}


# ---------- Métricas y KPI (sin datos personales) ----------


@router.get("/metricas")
def ver_metricas(_: AdminDep, dias: int = 30) -> dict[str, Any]:
    return kpis.resumen(max(1, min(dias, 365)))


@router.get("/metricas/eventos.csv")
def exportar_metricas(_: AdminDep, dias: int = 30) -> Response:
    from datetime import datetime, timedelta, timezone

    desde = (datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 365)))).isoformat(timespec="seconds")
    return Response(content=kpis.a_csv(almacen.obtener().eventos(desde)), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="declarafacil-metricas.csv"'})


class KpiManual(BaseModel):
    valor: float
    n: int = Field(ge=0, le=100000)
    nota: str = ""


@router.put("/metricas/manuales/{kpi}")
def guardar_kpi_manual(kpi: str, m: KpiManual, autor: AdminDep) -> dict[str, Any]:
    try:
        return kpis.guardar_manual(kpi, m.valor, m.n, m.nota, autor)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Ese KPI no se registra a mano") from e


_DEMOS = {
    "exogena_demo_2025.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "certificado_220_demo_2025.pdf": "application/pdf",
    "certificado_banco_demo_2025.pdf": "application/pdf",
}


@router.get("/demo/archivos")
def demos() -> list[str]:
    """Documentos ficticios para probar sin datos reales."""
    return [n for n in _DEMOS if (settings.data_dir / "demo" / n).exists()]


@router.get("/demo/archivo/{nombre}")
def demo(nombre: str) -> Response:
    ruta = settings.data_dir / "demo" / nombre
    if nombre not in _DEMOS or not ruta.exists():
        raise HTTPException(status_code=404, detail="No hay archivo de demostración con ese nombre")
    return Response(content=ruta.read_bytes(), media_type=_DEMOS[nombre], headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/demo/exogena")
def exogena_demo() -> Response:
    """Exógena ficticia para probar sin usar datos reales."""
    ruta = settings.data_dir / "demo" / "exogena_demo_2025.xlsx"
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="No hay archivo de demostración")
    return Response(
        content=ruta.read_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="exogena_demo_2025.xlsx"'},
    )
