"""Varios documentos a la vez: certificados, cruce con la exógena y lo que el agente dice (modo simulado, sin red)."""

import asyncio
import json
import os
from pathlib import Path

os.environ["LLM_MODE"] = "simulado"

from fastapi.testclient import TestClient

from app import orquestador
from app.agents import asistente, clasificador, extractor
from app.agents.base import DocumentoLeido
from app.main import app
from app.tax import reglas as repo_reglas
from app.tax.modelos import DatosDeclaracion
from app.tax.motor import liquidar

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo"
EXOGENA, C220, BANCO = "exogena_demo_2025.xlsx", "certificado_220_demo_2025.pdf", "certificado_banco_demo_2025.pdf"
PERSONALES = ["1012345678", "1.012.345.678", "PEREZ GOMEZ", "LAURA", "1098765432", "SOFIA"]


def _procesar(nombres: list[str], previas: orquestador.Previas | None = None) -> orquestador.ResultadoDocumento | orquestador.ErrorFlujo:
    archivos = [((DEMO / n).read_bytes(), n) for n in nombres]

    async def correr():
        final = None
        async for item in orquestador.procesar_documentos(archivos, 2025, previas):
            if isinstance(item, (orquestador.ResultadoDocumento, orquestador.ErrorFlujo)):
                final = item
        return final

    return asyncio.run(correr())


def _previas(r: orquestador.ResultadoDocumento) -> orquestador.Previas:
    ex = r.extraccion
    return orquestador.Previas(filas=ex.filas, topes=ex.topes, documentos=ex.documentos, ultimos_dos_digitos_nit=ex.ultimos_dos_digitos_nit,
                               anio=ex.anio, datos_enmascarados=ex.datos_enmascarados)


def _estado(r: orquestador.ResultadoDocumento, recien: list[str] | None = None) -> asistente.EstadoChat:
    ex = r.extraccion
    return asistente.EstadoChat(
        anio_gravable=2025, tiene_exogena=any(d.tipo == "exogena" for d in ex.documentos), anio_exogena=ex.anio, perfil=ex.perfil.model_dump(),
        resumen_exogena=ex.resumen_campos, filas=ex.filas, topes=ex.topes, documentos=ex.documentos, recien=recien or [],
        por_revisar=[f.detalle for f in ex.filas if f.tratamiento == "revisar"],
        respuestas=asistente.Respuestas(ultimos_dos_digitos_nit=ex.ultimos_dos_digitos_nit),
    )


def _doc(lineas: list[str]) -> DocumentoLeido:
    return DocumentoLeido(formato="pdf", lineas=lineas)


# ---------- Certificados uno por uno ----------


def test_certificado_220_saca_cada_casilla_sin_datos_personales():
    r = _procesar([C220])
    assert isinstance(r, orquestador.ResultadoDocumento)
    d = r.nuevos[0]
    assert d.tipo == "certificado_220" and d.entidad == "COMERCIALIZADORA ANDINA S.A.S." and d.nit == "900111222" and d.anio == 2025
    assert d.pistas == ["dependiente:hija"]
    ex = r.extraccion.resumen_campos
    assert ex["laboral.salarios_y_pagos_laborales"] == 96_000_000  # salarios 84 M + prestaciones 12 M
    assert ex["laboral.cesantias_e_intereses"] == 8_000_000
    assert ex["laboral.aportes_obligatorios_salud"] == ex["laboral.aportes_obligatorios_pension"] == 3_840_000
    assert ex["deducciones.aportes_voluntarios_afc_fpv"] == 2_400_000
    assert ex["pagos.retenciones_renta"] == 2_350_000  # la casilla 60, no también el total de la 75
    assert ex["laboral.salario_promedio_mensual_6m"] == 8_000_000
    texto = r.model_dump_json()
    assert not [p for p in PERSONALES if p in texto]


def test_certificado_del_banco_por_producto_sin_contar_totales():
    r = _procesar([BANCO])
    filas = [f for f in r.extraccion.filas if f.tratamiento == "suma"]
    saldos = sorted(f.valor for f in filas if f.campo == "patrimonio.bienes")
    assert saldos == [4_500_000, 20_000_000]  # la fila "Totales" no se suma otra vez
    assert sum(f.valor for f in filas if f.campo == "capital.rendimientos_financieros") == 1_250_000
    assert [f.valor for f in filas if f.campo == "pagos.retenciones_renta"] == [50_000]
    assert [f.valor for f in filas if f.campo == "deducciones.gmf_pagado"] == [440_000]
    assert all(f.informante == "BANCO EJEMPLO S.A." and f.nit_informante == "860000001" for f in filas)
    assert not [p for p in PERSONALES if p in r.model_dump_json()]


def test_banco_en_texto_con_productos_y_deuda():
    lineas = [
        "BANCOLOMBIA S.A. NIT 890.903.938-8",
        "Certificado tributario año gravable 2025",
        "CUENTA DE AHORROS ****1234",
        "Saldo a 31 de diciembre de 2025: $ 3.200.000,00",
        "Intereses abonados: $ 45.000,00 Retención en la fuente: $ 1.800,00",
        "Gravamen a los movimientos financieros: $ 150.000",
        "TARJETA DE CRÉDITO ****9876",
        "Saldo a 31 de diciembre: $ 2.500.000",
        "Intereses pagados: $ 380.000",
    ]
    filas, doc = extractor.extraer(_doc(lineas), "certificado_bancario", "aaaaaa000000", "banco.pdf", 2025)
    campos = {(f.campo, f.valor) for f in filas if f.tratamiento == "suma"}
    assert ("patrimonio.bienes", 3_200_000) in campos
    assert ("capital.rendimientos_financieros", 45_000) in campos
    assert ("pagos.retenciones_renta", 1_800) in campos
    assert ("deducciones.gmf_pagado", 150_000) in campos
    assert ("patrimonio.deudas", 2_500_000) in campos  # el saldo de la tarjeta es una deuda
    assert not any(f.campo == "capital.rendimientos_financieros" and f.valor == 380_000 for f in filas)  # intereses de la tarjeta no son ingreso
    assert doc.entidad == "Bancolombia" or "BANCOLOMBIA" in (doc.entidad or "")
    assert doc.nit == "890903938"


def test_prepagada_mes_a_mes_usa_el_total():
    lineas = ["COLSANITAS S.A. NIT 800.149.496-2", "Certificado de pagos medicina prepagada año 2025"]
    lineas += [f"{m} valor pagado 350.000" for m in ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")]
    lineas.append("Total pagado 4.200.000")
    tipo, _ = clasificador.tipo_por_reglas(_doc(lineas))
    assert tipo == "certificado_prepagada"
    filas, _ = extractor.extraer(_doc(lineas), tipo, "bbbbbb000000", "prepagada.pdf", 2025)
    assert [(f.campo, f.valor) for f in filas] == [("deducciones.medicina_prepagada", 4_200_000)]


def test_declaracion_anterior_trae_impuesto_y_anticipo():
    lineas = [
        "Declaración de Renta y Complementario Personas Naturales y Asimiladas Residentes 210 Año 2024",
        "Impuesto neto de renta 126 1.500.000 Impuesto de ganancias ocasionales 127 0",
        "Anticipo renta liquidado año gravable anterior 128 300.000",
        "Anticipo renta para el año gravable siguiente 133 800.000",
        "Total saldo a favor 137 250.000",
    ]
    tipo, _ = clasificador.tipo_por_reglas(_doc(lineas))
    assert tipo == "declaracion_anterior"
    filas, doc = extractor.extraer(_doc(lineas), tipo, "cccccc000000", "210.pdf", 2024)
    valores = {f.campo: f for f in filas if f.campo}
    assert valores["pagos.impuesto_neto_anio_anterior"].valor == 1_500_000
    assert valores["pagos.anticipo_anio_anterior"].valor == 800_000  # el de este año, no el de 2023
    assert valores["pagos.saldo_favor_anterior"].tratamiento == "revisar"  # se pregunta si pidió la devolución
    assert "devolvieran" in valores["pagos.saldo_favor_anterior"].pregunta
    assert doc.pistas == ["declaro_antes"]


def test_documento_desconocido_pregunta_cada_cifra():
    lineas = ["Constancia de la cooperativa", "Saldo de aportes sociales 2.000.000", "Intereses reconocidos 120.000"]
    filas, _ = extractor.extraer(_doc(lineas), "desconocido", "dddddd000000", "constancia.pdf", 2025)
    assert filas and all(f.tratamiento == "revisar" and f.pregunta and f.opciones for f in filas)


def test_foto_no_se_lee():
    archivos = [(b"\xff\xd8\xff\xe0 jpg", "certificado.jpg")]

    async def correr():
        return [x async for x in orquestador.procesar_documentos(archivos, 2025)]

    salida = asyncio.run(correr())
    assert isinstance(salida[-1], orquestador.ErrorFlujo) and "PDF" in salida[-1].mensaje


# ---------- Cruce con la exógena ----------


def test_los_certificados_reemplazan_a_la_exogena_sin_contar_dos_veces():
    r = _procesar([EXOGENA, C220, BANCO])
    assert [d.tipo for d in r.nuevos] == ["exogena", "certificado_220", "certificado_bancario"]
    ex = r.extraccion.resumen_campos
    assert ex["laboral.salarios_y_pagos_laborales"] == 96_000_000
    assert ex["laboral.cesantias_e_intereses"] == 8_000_000  # las del 220 reemplazan las que reporta el fondo
    assert ex["pagos.retenciones_renta"] == 2_400_000  # 2.350.000 del 220 + 50.000 del banco (no los 2.100.000 de la exógena)
    assert ex["capital.rendimientos_financieros"] == 1_250_000
    assert ex["patrimonio.bienes"] == 204_500_000  # 24,5 M del banco + 180 M del inmueble (lo demás está por confirmar)
    reemplazadas = [f for f in r.extraccion.filas if f.reemplazada_por]
    assert len(reemplazadas) == 8 and all(f.fuente == "exogena" and f.tratamiento == "informativo" for f in reemplazadas)
    avisos = " ".join(r.cruces)
    assert "la exógena dice $2.100.000 y el certificado $2.350.000" in avisos
    assert "la exógena dice $1.200.000 y el certificado $1.250.000" in avisos
    assert "4x1000" in avisos
    assert r.mensaje.startswith("Leí 3 documentos:")


def test_mismo_resultado_si_el_certificado_llega_despues():
    juntos = _procesar([EXOGENA, BANCO]).extraccion.resumen_campos
    primero = _procesar([EXOGENA])
    despues = _procesar([BANCO], _previas(primero))
    assert despues.extraccion.resumen_campos == juntos
    assert len(despues.extraccion.documentos) == 2
    otra_vez = _procesar([BANCO], _previas(despues))
    assert otra_vez.nuevos == [] and "Ya había leído" in otra_vez.mensaje
    assert otra_vez.extraccion.resumen_campos == juntos


def test_el_motor_usa_lo_cruzado():
    r = _procesar([EXOGENA, C220, BANCO])
    sol = orquestador.SolicitudLiquidacion(anio_gravable=2025, filas=r.extraccion.filas, topes=r.extraccion.topes,
                                           ultimos_dos_digitos_nit=r.extraccion.ultimos_dos_digitos_nit)
    liq = liquidar(orquestador.construir_declaracion(sol), repo_reglas.cargar(2025))
    assert liq.resumen.retenciones == 2_400_000


# ---------- Lo que dice el agente ----------


def test_el_agente_usa_lo_que_traen_los_certificados():
    r = _procesar([EXOGENA, C220, BANCO])
    d = asistente.diagnosticar(_estado(r, [x.id for x in r.nuevos]))
    assert d.pregunta and d.pregunta.intro == "Lo que tus documentos no me dicen:"
    assert "registra un dependiente económico (hija)" in d.pregunta.partes[0].texto
    assert "retenciones ($2.400.000)" in d.respuesta

    e = _estado(r)
    resp = asyncio.run(asistente.responder(asistente.TurnoChat(mensaje="¿qué documentos necesito?", estado=e)))
    assert "Ya tengo:" in resp.respuesta
    pendientes = resp.respuesta.split("Te falta:")[1]
    assert "BANCO EJEMPLO" not in pendientes and "COMERCIALIZADORA" not in pendientes  # ya los subió
    assert "BANCO HIPOTECARIO DEMO" in pendientes


def test_al_sumar_un_certificado_no_repite_el_diagnostico():
    primero = _procesar([EXOGENA])
    despues = _procesar([BANCO], _previas(primero))
    d = asistente.diagnosticar(_estado(despues, [x.id for x in despues.nuevos]))
    assert "Por lo que reportaron" not in d.respuesta


def test_contexto_de_la_ia_marca_lo_reemplazado():
    r = _procesar([EXOGENA, BANCO])
    texto = asistente._tabla_exogena(_estado(r))
    assert "| certificado del banco | BANCO EJEMPLO S.A. |" in texto
    assert "reemplazado" in texto


# ---------- API ----------


def test_api_recibe_varios_archivos():
    archivos = [("archivos", (n, (DEMO / n).read_bytes())) for n in (EXOGENA, C220, BANCO)]
    r = TestClient(app).post("/api/documentos/analizar", files=archivos, data={"anio_gravable": "2025"})
    assert r.status_code == 200
    eventos = []
    tipo = "message"
    for linea in r.text.splitlines():
        if linea.startswith("event:"):
            tipo = linea.split(":", 1)[1].strip()
        elif linea.startswith("data:"):
            eventos.append((tipo, json.loads(linea.split(":", 1)[1])))
    agentes = {d["agente"] for t, d in eventos if t == "agente"}
    assert {"lector", "anonimizador", "clasificador", "interprete", "extractor", "conciliador"} <= agentes
    res = next(d for t, d in eventos if t == "resultado")
    assert len(res["nuevos"]) == 3 and len(res["extraccion"]["documentos"]) == 3
    assert not [p for p in PERSONALES if p in json.dumps(res)]


def test_api_demo_lista_los_documentos_ficticios():
    c = TestClient(app)
    assert set(c.get("/api/demo/archivos").json()) == {EXOGENA, C220, BANCO}
    assert c.get(f"/api/demo/archivo/{C220}").content[:4] == b"%PDF"
    assert c.get("/api/demo/archivo/otro.pdf").status_code == 404


# ---------- Reglas por año ----------


def test_las_etiquetas_del_motor_cambian_con_el_anio():
    datos = DatosDeclaracion(anio_gravable=2022)
    datos.laboral.salarios_y_pagos_laborales = 90_000_000
    texto_2022 = json.dumps(liquidar(datos, repo_reglas.cargar(2022)).model_dump(), ensure_ascii=False)
    datos.anio_gravable = 2025
    texto_2025 = json.dumps(liquidar(datos, repo_reglas.cargar(2025)).model_dump(), ensure_ascii=False)
    assert "2.880 UVT al año" in texto_2022 and "5.040 UVT" in texto_2022
    assert "790 UVT al año" in texto_2025 and "1.340 UVT" in texto_2025
