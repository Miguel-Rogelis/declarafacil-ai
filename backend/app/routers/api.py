"""Endpoints HTTP. Los flujos largos responden con Server-Sent Events para mostrar
en vivo qué agente está trabajando."""

from collections.abc import AsyncIterable
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app import orquestador
from app.agents import asistente, configuracion
from app.agents.base import EventoAgente
from app.config import settings
from app.llm import cliente
from app.tax import reglas as repo_reglas

router = APIRouter(prefix="/api")


def _admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Necesitas la clave de administrador para cambiar la configuración")


AdminDep = Annotated[None, Depends(_admin)]


def _evento(item: orquestador.Salida) -> ServerSentEvent:
    if isinstance(item, EventoAgente):
        return ServerSentEvent(data=item, event="agente")
    if isinstance(item, orquestador.ErrorFlujo):
        return ServerSentEvent(data=item, event="error")
    return ServerSentEvent(data=item, event="resultado")


class Estado(BaseModel):
    modo_llm: str
    anios: list[dict[str, Any]]
    admin_protegido: bool


@router.get("/estado")
def estado() -> Estado:
    return Estado(modo_llm=settings.modo_llm, anios=repo_reglas.anios_disponibles(), admin_protegido=bool(settings.admin_token))


@router.post("/documentos/analizar", response_class=EventSourceResponse)
async def analizar_documento(
    archivo: Annotated[UploadFile, File(description="Reporte de exógena en .xlsx o .pdf")],
    anio_gravable: Annotated[int, Form()] = 2025,
) -> AsyncIterable[ServerSentEvent]:
    contenido = await archivo.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(contenido) > settings.max_upload_mb * 1024 * 1024:
        yield ServerSentEvent(data={"mensaje": f"El archivo supera {settings.max_upload_mb} MB", "agente": "lector"}, event="error")
        return
    async for item in orquestador.procesar_documento(contenido, archivo.filename or "archivo", anio_gravable):
        yield _evento(item)
    del contenido


@router.post("/declaracion/liquidar", response_class=EventSourceResponse)
async def liquidar(solicitud: orquestador.SolicitudLiquidacion) -> AsyncIterable[ServerSentEvent]:
    async for item in orquestador.procesar_liquidacion(solicitud):
        yield _evento(item)


class MensajeChat(BaseModel):
    mensaje: str
    historial: list[dict[str, str]] = []
    contexto: str | None = None


@router.post("/asistente")
async def chat(m: MensajeChat) -> asistente.RespuestaAsistente:
    if not m.mensaje.strip():
        raise HTTPException(status_code=422, detail="Escribe una pregunta")
    return await asistente.responder(m.mensaje[:800], m.historial, m.contexto)


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
def guardar_reglas(anio: int, datos: Annotated[dict[str, Any], Body()], _: AdminDep) -> dict[str, Any]:
    try:
        repo_reglas.guardar(anio, datos)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return repo_reglas.cargar(anio)


class Clonar(BaseModel):
    destino: int
    uvt: float | None = None


@router.post("/reglas/{anio}/clonar")
def clonar_reglas(anio: int, c: Clonar, _: AdminDep) -> dict[str, Any]:
    try:
        return repo_reglas.clonar(anio, c.destino, c.uvt)
    except (ValueError, repo_reglas.ReglasNoEncontradas) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ---------- Agentes ----------


@router.get("/agentes")
def listar_agentes() -> dict[str, dict[str, Any]]:
    return configuracion.todos()


@router.put("/agentes/{agente}")
def actualizar_agente(agente: str, cambios: Annotated[dict[str, Any], Body()], _: AdminDep) -> dict[str, Any]:
    try:
        return configuracion.actualizar(agente, cambios)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Agente no encontrado") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/agentes/modelos-gratis")
async def modelos_gratis() -> list[dict[str, Any]]:
    """Lista los modelos gratuitos que OpenRouter ofrece hoy (rotan casi cada semana)."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{settings.openrouter_base_url}/models")
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"No pude consultar OpenRouter: {e}") from e
    salida = []
    for m in r.json().get("data", []):
        precio = m.get("pricing", {})
        if m["id"].endswith(":free") or (precio.get("prompt") == "0" and precio.get("completion") == "0"):
            salida.append({"id": m["id"], "nombre": m.get("name"), "contexto": m.get("context_length")})
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
