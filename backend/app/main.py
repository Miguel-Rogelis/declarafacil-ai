"""DeclaraFácil AI — API y sitio web en un solo servicio."""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import cuentas, metricas
from app.config import settings
from app.llm import cupo
from app.routers import api

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="DeclaraFácil AI",
    description="Asistente agéntico para preparar la declaración de renta de personas naturales en Colombia.",
    version="1.0.0",
)
# La demo en GitHub Pages llama esta API desde otro dominio
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(api.router)


@app.middleware("http")
async def identificar(request: Request, call_next):  # noqa: ANN001, ANN201
    """Quién llama (para el cupo de IA) y si pide respuestas sin IA (modo demo)."""
    reenviada = request.headers.get("x-forwarded-for", "")
    ip = reenviada.split(",")[0].strip() or (request.client.host if request.client else "anonimo")
    # Con sesión iniciada cada persona tiene su cupo; sin sesión se cuenta por IP (un salón entero comparte la suya)
    usuario = await cuentas.usuario_de(request.headers.get("authorization")) if request.url.path.startswith("/api/") else None
    cupo.quien.set(f"usuario:{usuario}" if usuario else ip)
    cupo.sin_ia.set(request.headers.get("x-sin-ia") == "1")
    cupo.limitado.set(False)
    metricas.fijar_sesion(request.headers.get("x-sesion"))
    t0 = time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception:  # noqa: BLE001 - se cuenta como error 5xx y se responde sin detalles internos
        logging.getLogger(__name__).exception("Error no controlado en %s", request.url.path)
        respuesta = JSONResponse({"detail": "Error interno"}, status_code=500)
    ruta = getattr(request.scope.get("route"), "path", None)
    if request.url.path.startswith("/api/") and request.url.path != "/api/salud" and ruta:
        metricas.registrar("http", ruta=ruta, estado=respuesta.status_code, ms=(time.perf_counter() - t0) * 1000)
    return respuesta


@app.get("/api/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok", "modo_llm": settings.modo_llm}


if settings.frontend_dir.exists():
    app.frontend("/", directory=str(settings.frontend_dir))
