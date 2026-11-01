"""Orquestador: decide el orden de los agentes y emite la traza en tiempo real.

Flujo fijo y trazable (no es un agente que decide solo):
  Fase 1 · documento:  Lector → Anonimizador → Clasificador → Intérprete
  Fase 2 · cálculo:    Motor tributario → Auditor → Explicador
El Asistente atiende el chat en paralelo, fuera de este flujo.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from pydantic import BaseModel

from app.agents import anonimizador, auditor, clasificador, explicador, interprete, lector
from app.agents.base import EventoAgente, Extraccion, FilaInterpretada, Traza
from app.tax import reglas as repo_reglas
from app.tax.modelos import DatosDeclaracion, GananciasOcasionales, ItemPatrimonio, Liquidacion
from app.tax.motor import liquidar


class Respuestas(BaseModel):
    """Lo que el usuario responde en el chat guiado (lo que la exógena no trae)."""

    dependientes: int = 0
    medicina_prepagada: float = 0
    intereses_vivienda: float = 0
    aportes_voluntarios_afc_fpv: float = 0
    gmf_pagado: float = 0
    honorarios_no_reportados: float = 0
    costos_independiente: float = 0
    arriendos_no_reportados: float = 0
    otros_ingresos_no_reportados: float = 0
    pensiones_no_reportadas: float = 0
    dividendos_gravados: float = 0
    ganancias_ocasionales: GananciasOcasionales = GananciasOcasionales()
    bienes_adicionales: list[ItemPatrimonio] = []
    deudas_adicionales: list[ItemPatrimonio] = []
    declaraciones_previas: int | None = None
    impuesto_neto_anio_anterior: float = 0
    anticipo_anio_anterior: float = 0
    ultimos_dos_digitos_nit: str | None = None
    fecha_presentacion: date | None = None
    sin_sanciones_ultimos_2_anios: bool = True
    responsable_iva: bool = False


class SolicitudLiquidacion(BaseModel):
    anio_gravable: int = 2025
    filas: list[FilaInterpretada] = []
    topes: dict[str, float] = {}
    ultimos_dos_digitos_nit: str | None = None
    respuestas: Respuestas = Respuestas()


class ResultadoDocumento(BaseModel):
    extraccion: Extraccion
    clasificacion: dict[str, Any]
    traza: list[EventoAgente]


class ResultadoLiquidacion(BaseModel):
    datos: DatosDeclaracion
    liquidacion: Liquidacion
    explicacion: str
    explicacion_con_ia: bool
    traza: list[EventoAgente]


class ErrorFlujo(BaseModel):
    mensaje: str
    agente: str


Salida = EventoAgente | ResultadoDocumento | ResultadoLiquidacion | ErrorFlujo


async def procesar_documento(contenido: bytes, nombre: str, anio_esperado: int) -> AsyncIterator[Salida]:
    traza = Traza()

    yield traza.inicio("lector", "Leyendo el archivo…")
    t0 = time.perf_counter()
    try:
        doc = await asyncio.to_thread(lector.leer, contenido, nombre)
    except lector.ArchivoNoSoportado as e:
        yield traza.fin("lector", str(e), t0, "error")
        yield ErrorFlujo(mensaje=str(e), agente="lector")
        return
    if not doc.filas:
        msg = "No encontré filas con conceptos y valores. ¿Es el reporte de información exógena de la DIAN?"
        yield traza.fin("lector", msg, t0, "error")
        yield ErrorFlujo(mensaje=msg, agente="lector")
        return
    yield traza.fin("lector", f"{len(doc.filas)} filas y {len(doc.topes)} topes leídos ({doc.formato.upper()})", t0)

    yield traza.inicio("anonimizador", "Quitando datos personales…")
    t0 = time.perf_counter()
    anon, ultimos, enmascarados = anonimizador.anonimizar(doc)
    del doc  # el original con datos personales no sigue en el flujo
    yield traza.fin("anonimizador", f"{enmascarados} datos personales enmascarados antes de usar IA", t0)

    yield traza.inicio("clasificador", "Verificando que sea una exógena…")
    t0 = time.perf_counter()
    clas = await clasificador.clasificar(anon)
    if not clas.es_exogena:
        msg = f"El archivo no parece un reporte de exógena ({clas.motivo})."
        yield traza.fin("clasificador", msg, t0, "error", clas.modelo)
        yield ErrorFlujo(mensaje=msg, agente="clasificador")
        return
    estado = "ok"
    msg = f"Exógena del año {clas.anio or '¿?'} · confianza {clas.confianza:.0%}" + (" (por reglas)" if not clas.modelo else "")
    if clas.anio and clas.anio != anio_esperado:
        estado = "advertencia"
        msg += f" · ojo: elegiste el año {anio_esperado}"
    yield traza.fin("clasificador", msg, t0, estado, clas.modelo)  # type: ignore[arg-type]

    yield traza.inicio("interprete", "Ubicando cada concepto en la declaración…")
    t0 = time.perf_counter()
    extraccion, modelo, enviados = await interprete.interpretar(anon, ultimos, enmascarados)
    sumadas = sum(1 for f in extraccion.filas if f.tratamiento == "suma")
    revisar = sum(1 for f in extraccion.filas if f.tratamiento == "revisar")
    msg = f"{sumadas} conceptos ubicados, {revisar} para revisar"
    msg += f" · {enviados} consultados a la IA (sin montos)" if modelo else " · todo con reglas"
    yield traza.fin("interprete", msg, t0, "advertencia" if revisar else "ok", modelo)

    yield ResultadoDocumento(extraccion=extraccion, clasificacion=clas.model_dump(), traza=traza.eventos)


def construir_declaracion(sol: SolicitudLiquidacion) -> DatosDeclaracion:
    datos, _, _ = interprete.construir_datos(sol.filas, sol.topes, sol.anio_gravable, sol.ultimos_dos_digitos_nit)
    d = DatosDeclaracion(**datos)
    d.anio_gravable = sol.anio_gravable
    r = sol.respuestas
    d.deducciones.dependientes = r.dependientes
    d.deducciones.medicina_prepagada += r.medicina_prepagada
    d.deducciones.intereses_vivienda += r.intereses_vivienda
    d.deducciones.aportes_voluntarios_afc_fpv += r.aportes_voluntarios_afc_fpv
    d.deducciones.gmf_pagado += r.gmf_pagado
    d.independiente.honorarios_y_servicios += r.honorarios_no_reportados
    d.independiente.costos_gastos_procedentes += r.costos_independiente
    d.capital.arrendamientos += r.arriendos_no_reportados
    d.no_laborales.ingresos += r.otros_ingresos_no_reportados
    d.pensiones.pensiones_nacionales += r.pensiones_no_reportadas
    if r.dividendos_gravados:
        mover = min(r.dividendos_gravados, d.dividendos.no_gravados_subcedula1)
        d.dividendos.no_gravados_subcedula1 -= mover
        d.dividendos.gravados_subcedula2 += r.dividendos_gravados
    go = r.ganancias_ocasionales.model_dump()
    for k, v in go.items():
        actual = getattr(d.ganancias_ocasionales, k)
        setattr(d.ganancias_ocasionales, k, v if isinstance(v, bool) else actual + v)
    d.patrimonio.bienes += r.bienes_adicionales
    d.patrimonio.deudas += r.deudas_adicionales
    for item in r.bienes_adicionales + r.deudas_adicionales:
        d.fuentes.setdefault("usuario", []).append(item.concepto)
    if r.declaraciones_previas is not None:
        d.pagos.declaraciones_previas = r.declaraciones_previas
    d.pagos.impuesto_neto_anio_anterior = r.impuesto_neto_anio_anterior
    d.pagos.anticipo_anio_anterior += r.anticipo_anio_anterior
    if r.ultimos_dos_digitos_nit:
        d.control.ultimos_dos_digitos_nit = r.ultimos_dos_digitos_nit
    d.control.fecha_presentacion = r.fecha_presentacion or date.today()
    d.control.sin_sanciones_ultimos_2_anios = r.sin_sanciones_ultimos_2_anios
    d.indicadores.responsable_iva = r.responsable_iva
    return d


async def procesar_liquidacion(sol: SolicitudLiquidacion) -> AsyncIterator[Salida]:
    traza = Traza()

    yield traza.inicio("motor", "Aplicando las reglas del año gravable…")
    t0 = time.perf_counter()
    try:
        datos = construir_declaracion(sol)
        reglas = repo_reglas.cargar(sol.anio_gravable)
        liq = liquidar(datos, reglas)
    except repo_reglas.ReglasNoEncontradas as e:
        yield traza.fin("motor", str(e), t0, "error")
        yield ErrorFlujo(mensaje=str(e), agente="motor")
        return
    estado = "advertencia" if reglas.get("estado") == "borrador" else "ok"
    yield traza.fin("motor", f"Reglas AG {sol.anio_gravable} (UVT ${reglas['uvt']:,.0f}) · {sum(len(s.lineas) for s in liq.secciones)} cálculos".replace(",", "."), t0, estado)  # type: ignore[arg-type]

    yield traza.inicio("auditor", "Buscando inconsistencias y riesgos…")
    t0 = time.perf_counter()
    extra = auditor.auditar(datos, liq, sol.filas)
    liq.alertas = liq.alertas + extra
    criticas = sum(1 for a in liq.alertas if a.nivel == "critica")
    yield traza.fin("auditor", f"{len(liq.alertas)} observaciones · {criticas} críticas", t0, "advertencia" if criticas else "ok")

    yield traza.inicio("explicador", "Redactando el resumen en lenguaje simple…")
    t0 = time.perf_counter()
    texto, modelo, con_ia = await explicador.explicar(liq, liq.alertas)
    msg = "Resumen escrito por IA y verificado cifra por cifra" if con_ia else "Resumen con plantilla" + (" (la IA citó cifras que no existen y se descartó)" if modelo else "")
    yield traza.fin("explicador", msg, t0, "ok", modelo)

    yield ResultadoLiquidacion(datos=datos, liquidacion=liq, explicacion=texto, explicacion_con_ia=con_ia, traza=traza.eventos)
