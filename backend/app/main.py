"""DeclaraFácil AI — API y sitio web en un solo servicio."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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
    cupo.quien.set(getattr(request.state, "usuario", None) or ip)
    cupo.sin_ia.set(request.headers.get("x-sin-ia") == "1")
    cupo.limitado.set(False)
    return await call_next(request)


@app.get("/api/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok", "modo_llm": settings.modo_llm}


if settings.frontend_dir.exists():
    app.frontend("/", directory=str(settings.frontend_dir))
