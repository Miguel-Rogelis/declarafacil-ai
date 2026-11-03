"""Orquestador: decide el orden de los agentes y emite la traza en tiempo real.

Flujo fijo y trazable (no es un agente que decide solo):
  Fase 1 · documentos (uno o varios a la vez):
           Lector → Anonimizador → Clasificador → Intérprete (exógena) o Extractor (certificados)
           y al final el Conciliador, que cruza todo para no contar nada dos veces
  Fase 2 · cálculo:    Motor tributario → Auditor → Explicador
El Asistente atiende el chat en paralelo, fuera de este flujo.
"""

import asyncio
import hashlib
import time
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from pydantic import BaseModel

from app.agents import (
    anonimizador,
    auditor,
    clasificador,
    conciliador,
    explicador,
    extractor,
    interprete,
    lector,
)
from app.agents.base import (
    NOMBRE_TIPO,
    DocumentoCargado,
    EventoAgente,
    Extraccion,
    FilaInterpretada,
    Traza,
)
from app.tax import reglas as repo_reglas
from app.tax.modelos import (
    DatosDeclaracion,
    GananciasOcasionales,
    ItemPatrimonio,
    Liquidacion,
)
from app.tax.motor import liquidar


class Respuestas(BaseModel):
    """Lo que el usuario responde en el chat guiado (lo que la exógena no trae)."""

    dependientes: int = 0
    salarios_no_reportados: float = 0
    retenciones_no_reportadas: float = 0
    dividendos_no_reportados: float = 0
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


class Previas(BaseModel):
    """Lo que ya se había leído en la sesión: los documentos nuevos se cruzan con esto."""

    filas: list[FilaInterpretada] = []
    topes: dict[str, float] = {}
    documentos: list[DocumentoCargado] = []
    ultimos_dos_digitos_nit: str | None = None
    anio: int | None = None
    datos_enmascarados: int = 0


class ErrorArchivo(BaseModel):
    nombre: str
    mensaje: str


class ResultadoDocumento(BaseModel):
    extraccion: Extraccion  # todo lo que hay, ya cruzado
    nuevos: list[DocumentoCargado] = []
    cruces: list[str] = []
    errores: list[ErrorArchivo] = []
    mensaje: str = ""
    clasificacion: dict[str, Any] = {}
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


MAX_ARCHIVOS = 12


def _corto(nombre: str) -> str:
    return nombre if len(nombre) <= 34 else nombre[:22] + "…" + nombre[-10:]


async def procesar_documentos(archivos: list[tuple[bytes, str]], anio_esperado: int, previas: Previas | None = None) -> AsyncIterator[Salida]:
    """Lee uno o varios documentos (exógena y certificados), los cruza con lo que ya había y devuelve todo unido."""
    previas = previas or Previas()
    traza = Traza()
    vistos = {d.id for d in previas.documentos}
    nuevas: list[FilaInterpretada] = []
    nuevos: list[DocumentoCargado] = []
    errores: list[ErrorArchivo] = []
    topes, ultimos, anio_exogena = dict(previas.topes), previas.ultimos_dos_digitos_nit, previas.anio
    enmascarados = previas.datos_enmascarados
    clasificacion_exogena: dict[str, Any] = {}
    modelos: list[str] = []

    for contenido, nombre in archivos[:MAX_ARCHIVOS]:
        corto = _corto(nombre)
        huella = hashlib.sha256(contenido).hexdigest()[:12]
        yield traza.inicio("lector", f"Leyendo {corto}…")
        t0 = time.perf_counter()
        if huella in vistos:
            yield traza.fin("lector", f"{corto}: ya lo había leído", t0, "advertencia")
            continue
        vistos.add(huella)
        try:
            doc = await asyncio.to_thread(lector.leer, contenido, nombre)
        except lector.ArchivoNoSoportado as e:
            yield traza.fin("lector", f"{corto}: {e}", t0, "error")
            errores.append(ErrorArchivo(nombre=nombre, mensaje=str(e)))
            continue
        if not doc.filas and not any(len(x) > 3 for x in doc.lineas):
            msg = "no tiene texto que pueda leer (parece escaneado). Descárgalo en PDF desde el portal de la entidad"
            yield traza.fin("lector", f"{corto}: {msg}", t0, "error")
            errores.append(ErrorArchivo(nombre=nombre, mensaje=msg[:1].upper() + msg[1:]))
            continue
        yield traza.fin("lector", f"{corto}: " + (f"{len(doc.filas)} filas y {len(doc.topes)} topes" if doc.filas else f"{len(doc.lineas)} líneas de texto") + f" ({doc.formato.upper()})", t0)

        yield traza.inicio("anonimizador", f"Quitando datos personales de {corto}…")
        t0 = time.perf_counter()
        anon, ult, n_exo = anonimizador.anonimizar(doc)
        n_cert = 0
        if not doc.filas:  # un certificado: su texto se limpia aparte
            anon, n_cert = anonimizador.anonimizar_certificado(anon)
        del doc  # el original con datos personales no sigue en el flujo
        enmascarados += n_exo + n_cert
        yield traza.fin("anonimizador", f"{corto}: {n_exo + n_cert} datos personales enmascarados", t0)

        yield traza.inicio("clasificador", f"Identificando {corto}…")
        t0 = time.perf_counter()
        clas = await clasificador.clasificar(anon, nombre)
        if clas.modelo:
            modelos.append(clas.modelo)
        tipo = "exogena" if clas.es_exogena else clas.tipo
        msg = f"{corto}: {NOMBRE_TIPO.get(tipo, 'documento').lower() if tipo != 'desconocido' else 'no reconocí el tipo de documento'}"
        msg += f" del año {clas.anio}" if clas.anio else ""
        estado = "ok" if tipo != "desconocido" else "advertencia"
        if clas.anio and clas.anio != anio_esperado and tipo != "declaracion_anterior":
            estado, msg = "advertencia", msg + f". Ojo: elegiste el año {anio_esperado}"
        yield traza.fin("clasificador", msg, t0, estado, clas.modelo)  # type: ignore[arg-type]

        if tipo == "exogena":
            yield traza.inicio("interprete", "Ubicando cada concepto de tu exógena en la declaración…")
            t0 = time.perf_counter()
            extraccion, modelo, enviados = await interprete.interpretar(anon, ult, 0)
            for f in extraccion.filas:
                f.documento, f.fuente = huella, "exogena"
            sumadas = sum(1 for f in extraccion.filas if f.tratamiento == "suma")
            revisar = sum(1 for f in extraccion.filas if f.tratamiento == "revisar")
            msg = f"{sumadas} conceptos ubicados, {revisar} para revisar"
            msg += f". {enviados} consultados a la IA, sin montos ni datos personales" if modelo else ". Todo resuelto con reglas"
            yield traza.fin("interprete", msg, t0, "advertencia" if revisar else "ok", modelo)
            nuevas = [f for f in nuevas if f.fuente != "exogena"] + extraccion.filas
            topes = dict(anon.topes)
            ultimos = ult or ultimos
            anio_exogena = anon.anio
            clasificacion_exogena = clas.model_dump()
            nuevos.append(DocumentoCargado(
                id=huella, nombre=nombre, tipo="exogena", etiqueta=f"Tu exógena {anon.anio}" if anon.anio else "Tu exógena",
                anio=anon.anio, cifras=sumadas + revisar,
                resumen=f"{len(extraccion.filas)} datos; ubiqué {sumadas} en tu declaración"
                + (f" y {revisar} {'necesita' if revisar == 1 else 'necesitan'} tu confirmación" if revisar else ""),
            ))
            continue

        yield traza.inicio("extractor", f"Sacando las cifras de {corto}…")
        t0 = time.perf_counter()
        filas, documento = extractor.extraer(anon, tipo, huella, nombre, clas.anio)
        if not filas:
            msg = "no encontré cifras que pueda usar en tu declaración"
            yield traza.fin("extractor", f"{corto}: {msg}", t0, "advertencia")
            errores.append(ErrorArchivo(nombre=nombre, mensaje=msg[:1].upper() + msg[1:]))
            continue
        revisar = sum(1 for f in filas if f.tratamiento == "revisar")
        yield traza.fin("extractor", f"{corto}: {documento.cifras} cifras" + (f", {revisar} para confirmar" if revisar else ""), t0, "advertencia" if revisar else "ok")
        nuevas.extend(filas)
        nuevos.append(documento)

    if not nuevos and errores:
        yield ErrorFlujo(mensaje="; ".join(f"{e.nombre}: {e.mensaje}" for e in errores), agente="lector")
        return
    if not nuevos:
        # Solo llegaron archivos que ya estaban: no cambia nada
        datos, perfil, resumen = interprete.construir_datos(previas.filas, previas.topes, previas.anio, previas.ultimos_dos_digitos_nit)
        extraccion = Extraccion(
            anio=previas.anio, ultimos_dos_digitos_nit=previas.ultimos_dos_digitos_nit, filas=previas.filas, datos=datos, perfil=perfil,
            resumen_campos=resumen, datos_enmascarados=previas.datos_enmascarados, topes=previas.topes, documentos=previas.documentos,
        )
        yield ResultadoDocumento(extraccion=extraccion, mensaje="Ya había leído ese documento; no lo cuento dos veces.", traza=traza.eventos)
        return

    yield traza.inicio("conciliador", "Cruzando los documentos para no contar nada dos veces…")
    t0 = time.perf_counter()
    documentos = [d for d in previas.documentos if not (d.tipo == "exogena" and any(n.tipo == "exogena" for n in nuevos))] + nuevos
    filas, cruces = conciliador.conciliar([f.model_copy(deep=True) for f in previas.filas], nuevas, documentos)
    reemplazadas = sum(1 for f in filas if f.reemplazada_por and f.documento not in {d.id for d in nuevos} | {None})
    reemplazadas += sum(1 for f in nuevas if f.reemplazada_por)
    yield traza.fin("conciliador", f"{len(documentos)} documentos cruzados" + (f", {reemplazadas} cifras de la exógena reemplazadas por certificados" if reemplazadas else ", sin cifras repetidas"), t0)

    anios = [d.anio for d in documentos if d.anio and d.tipo != "declaracion_anterior"]
    anio = anio_exogena or (max(set(anios), key=anios.count) if anios else None)
    datos, perfil, resumen = interprete.construir_datos(filas, topes, anio, ultimos)
    extraccion = Extraccion(
        anio=anio, ultimos_dos_digitos_nit=ultimos, filas=filas, datos=datos, perfil=perfil, resumen_campos=resumen,
        datos_enmascarados=enmascarados, topes=topes, documentos=documentos,
    )
    yield ResultadoDocumento(
        extraccion=extraccion, nuevos=nuevos, cruces=cruces, errores=errores, mensaje=mensaje_lectura(nuevos, cruces, errores, enmascarados - previas.datos_enmascarados),
        clasificacion=clasificacion_exogena, traza=traza.eventos,
    )


def mensaje_lectura(nuevos: list[DocumentoCargado], cruces: list[str], errores: list[ErrorArchivo], enmascarados: int) -> str:
    """Lo que el agente cuenta apenas lee los documentos (escrito por el código, sin IA)."""
    partes = []
    if len(nuevos) == 1:
        d = nuevos[0]
        nombre = d.etiqueta[:1].lower() + d.etiqueta[1:]
        partes.append(f"Leí {nombre if d.etiqueta.startswith('Tu ') else 'el ' + nombre}" + (f": {d.resumen}." if d.resumen else "."))
    else:
        partes.append(f"Leí {len(nuevos)} documentos:")
        partes.extend(f"• {d.etiqueta}" + (f": {d.resumen}." if d.resumen else ".") for d in nuevos)
    if cruces:
        partes.append("Crucé tus documentos para no contar nada dos veces:")
        partes.extend(f"• {c}" for c in cruces)
    for e in errores:
        partes.append(f"No pude usar {e.nombre}: {e.mensaje}.")
    if enmascarados:
        partes.append(f"Antes de usar IA quité {enmascarados} datos personales.")
    return "\n".join(partes)


async def procesar_documento(contenido: bytes, nombre: str, anio_esperado: int) -> AsyncIterator[Salida]:
    """Un solo archivo (se mantiene por compatibilidad)."""
    async for item in procesar_documentos([(contenido, nombre)], anio_esperado):
        yield item


def construir_declaracion(sol: SolicitudLiquidacion) -> DatosDeclaracion:
    datos, _, _ = interprete.construir_datos(sol.filas, sol.topes, sol.anio_gravable, sol.ultimos_dos_digitos_nit)
    d = DatosDeclaracion(**datos)
    d.anio_gravable = sol.anio_gravable
    r = sol.respuestas
    d.deducciones.dependientes = r.dependientes
    if r.salarios_no_reportados:
        d.laboral.salarios_y_pagos_laborales += r.salarios_no_reportados
        if not (d.laboral.aportes_obligatorios_pension or d.laboral.aportes_obligatorios_salud):
            # Sin certificado: se estiman los aportes del trabajador (4 % salud + 4 % pensión)
            d.laboral.aportes_obligatorios_pension = r.salarios_no_reportados * 0.04
            d.laboral.aportes_obligatorios_salud = r.salarios_no_reportados * 0.04
            d.fuentes.setdefault("estimado", []).append("aportes 4 % + 4 %")
    d.pagos.retenciones_renta += r.retenciones_no_reportadas
    d.dividendos.no_gravados_subcedula1 += r.dividendos_no_reportados
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
    d.pagos.impuesto_neto_anio_anterior = r.impuesto_neto_anio_anterior or d.pagos.impuesto_neto_anio_anterior
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
    yield traza.fin("motor", f"Reglas del año gravable {sol.anio_gravable} con UVT de ${reglas['uvt']:,.0f}".replace(",", ".") + f", {sum(len(s.lineas) for s in liq.secciones)} cálculos", t0, estado)  # type: ignore[arg-type]

    yield traza.inicio("auditor", "Buscando inconsistencias y riesgos…")
    t0 = time.perf_counter()
    extra = auditor.auditar(datos, liq, sol.filas)
    liq.alertas = liq.alertas + extra
    criticas = sum(1 for a in liq.alertas if a.nivel == "critica")
    yield traza.fin("auditor", f"{len(liq.alertas)} observaciones, {criticas} críticas", t0, "advertencia" if criticas else "ok")

    yield traza.inicio("explicador", "Redactando el resumen en lenguaje simple…")
    t0 = time.perf_counter()
    texto, modelo, con_ia = await explicador.explicar(liq, liq.alertas)
    msg = "Resumen escrito por IA y verificado cifra por cifra" if con_ia else "Resumen con plantilla" + (" (la IA citó cifras que no existen y se descartó)" if modelo else "")
    yield traza.fin("explicador", msg, t0, "ok", modelo)

    yield ResultadoLiquidacion(datos=datos, liquidacion=liq, explicacion=texto, explicacion_con_ia=con_ia, traza=traza.eventos)
