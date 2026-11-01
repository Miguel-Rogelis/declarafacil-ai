"""Piezas comunes de los agentes: eventos de traza y modelos de documento."""

import time
from contextlib import contextmanager
from typing import Any, Literal

from pydantic import BaseModel

from app.agents import configuracion

EstadoEvento = Literal["inicio", "ok", "advertencia", "error"]


class EventoAgente(BaseModel):
    agente: str
    nombre: str
    estado: EstadoEvento
    mensaje: str
    duracion_ms: int | None = None
    modelo: str | None = None
    usa_ia: bool = False


class Traza:
    """Registra qué hizo cada agente, cuánto tardó y con qué modelo (si usó uno)."""

    def __init__(self) -> None:
        self.eventos: list[EventoAgente] = []

    def inicio(self, agente: str, mensaje: str) -> EventoAgente:
        cfg = configuracion.obtener(agente)
        ev = EventoAgente(agente=agente, nombre=cfg.get("nombre", agente), estado="inicio", mensaje=mensaje, usa_ia=cfg.get("usa_ia", False))
        self.eventos.append(ev)
        return ev

    def fin(self, agente: str, mensaje: str, t0: float, estado: EstadoEvento = "ok", modelo: str | None = None) -> EventoAgente:
        cfg = configuracion.obtener(agente)
        ev = EventoAgente(
            agente=agente,
            nombre=cfg.get("nombre", agente),
            estado=estado,
            mensaje=mensaje,
            duracion_ms=int((time.perf_counter() - t0) * 1000),
            modelo=modelo,
            usa_ia=cfg.get("usa_ia", False),
        )
        self.eventos.append(ev)
        return ev


@contextmanager
def cronometro():
    t0 = time.perf_counter()
    yield t0


# ---------- Documento de exógena ----------


class FilaExogena(BaseModel):
    id: str
    nit_informante: str | None = None
    informante: str | None = None
    detalle: str
    valor: float
    uso_sugerido: str | None = None
    info_adicional: str | None = None


class DocumentoLeido(BaseModel):
    formato: Literal["xlsx", "pdf"]
    titulo: str = ""
    anio: int | None = None
    identificacion: str | None = None
    nombre: str | None = None
    fecha_corte: str | None = None
    topes: dict[str, float] = {}
    filas: list[FilaExogena] = []
    lineas_encabezado: list[str] = []


Tratamiento = Literal["suma", "informativo", "revisar"]


class FilaInterpretada(FilaExogena):
    campo: str | None = None
    tratamiento: Tratamiento = "revisar"
    explicacion: str = ""
    origen_mapeo: Literal["reglas", "ia", "sin_mapeo"] = "sin_mapeo"


class Perfil(BaseModel):
    empleado: bool = False
    independiente: bool = False
    pensionado: bool = False
    rentas_capital: bool = False
    dividendos: bool = False
    ganancias_ocasionales: bool = False
    declaro_antes: bool = False


class Extraccion(BaseModel):
    anio: int | None
    ultimos_dos_digitos_nit: str | None
    filas: list[FilaInterpretada]
    datos: dict[str, Any]
    perfil: Perfil
    resumen_campos: dict[str, float]
    datos_enmascarados: int = 0
    topes: dict[str, float] = {}
