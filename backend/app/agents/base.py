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


# ---------- Documentos: exógena y certificados ----------

TipoDocumento = Literal[
    "exogena",
    "certificado_220",
    "certificado_bancario",
    "certificado_vivienda",
    "certificado_prepagada",
    "certificado_voluntarios",
    "certificado_cesantias",
    "certificado_retencion",
    "declaracion_anterior",
    "predial",
    "desconocido",
]

NOMBRE_TIPO: dict[str, str] = {
    "exogena": "Reporte de información exógena",
    "certificado_220": "Certificado de ingresos y retenciones (220)",
    "certificado_bancario": "Certificado tributario del banco",
    "certificado_vivienda": "Certificado de intereses de vivienda",
    "certificado_prepagada": "Certificado de medicina prepagada",
    "certificado_voluntarios": "Certificado de aportes voluntarios o AFC",
    "certificado_cesantias": "Certificado del fondo de cesantías",
    "certificado_retencion": "Certificado de retención en la fuente",
    "declaracion_anterior": "Declaración de renta del año anterior",
    "predial": "Recibo del impuesto predial",
    "desconocido": "Documento",
}


class FilaExogena(BaseModel):
    id: str
    nit_informante: str | None = None
    informante: str | None = None
    detalle: str
    valor: float
    uso_sugerido: str | None = None
    info_adicional: str | None = None
    # De qué documento salió la cifra (huella del archivo) y de qué tipo es
    documento: str | None = None
    fuente: str = "exogena"


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
    # Texto completo y tablas, para los certificados (que no traen el formato de la exógena)
    lineas: list[str] = []
    tablas: list[list[list[str]]] = []


class DocumentoCargado(BaseModel):
    """Un archivo que ya se leyó en esta sesión."""

    id: str  # huella del contenido: el mismo archivo no se lee dos veces
    nombre: str
    tipo: str
    etiqueta: str  # "Certificado tributario de BANCO EJEMPLO S.A."
    entidad: str | None = None
    nit: str | None = None
    anio: int | None = None
    cifras: int = 0
    resumen: str = ""
    pistas: list[str] = []  # lo que el documento deja ver sin ser una cifra (p. ej. "dependiente")


Tratamiento = Literal["suma", "informativo", "revisar"]


class OpcionRevision(BaseModel):
    """Una respuesta posible a la pregunta de confirmación de una fila."""

    texto: str
    incluir: bool
    campo: str | None = None
    recomendada: bool = False


class FilaInterpretada(FilaExogena):
    campo: str | None = None
    tratamiento: Tratamiento = "revisar"
    explicacion: str = ""
    origen_mapeo: Literal["reglas", "ia", "sin_mapeo"] = "sin_mapeo"
    # Si hay que confirmarla: pregunta en lenguaje sencillo y respuestas cortas
    pregunta: str = ""
    ayuda: str = ""
    opciones: list[OpcionRevision] = []
    # Documento cuya cifra reemplazó a esta (un certificado reemplaza lo que dice la exógena)
    reemplazada_por: str | None = None


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
    documentos: list[DocumentoCargado] = []
