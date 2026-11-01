"""DeclaraFácil AI — API y sitio web en un solo servicio."""

import logging

from fastapi import FastAPI

from app.config import settings
from app.routers import api

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="DeclaraFácil AI",
    description="Asistente agéntico para preparar la declaración de renta de personas naturales en Colombia.",
    version="1.0.0",
)
app.include_router(api.router)


@app.get("/api/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok", "modo_llm": settings.modo_llm}


if settings.frontend_dir.exists():
    app.frontend("/", directory=str(settings.frontend_dir))
