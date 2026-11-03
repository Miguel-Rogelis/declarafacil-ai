"""Agente Intérprete: ubica cada fila de la exógena en la casilla de la declaración.

1. Reglas: catálogo de conceptos conocidos + la columna "Uso declaración sugerida"
   de la DIAN (renglones del formulario 210).
2. IA: solo para filas que las reglas no reconocen o que piden revisión. Al modelo
   se le envía la descripción del concepto, NUNCA el monto ni datos personales.
   El modelo elige una casilla de una lista cerrada y explica el concepto.
3. Las cifras siempre se copian de la fila original: la IA no puede inventarlas.
"""

import re
import unicodedata
from typing import Any

from app.agents import revision
from app.agents.base import DocumentoLeido, Extraccion, FilaInterpretada, Perfil
from app.llm import cliente

CAMPOS: dict[str, str] = {
    "laboral.salarios_y_pagos_laborales": "Salarios y demás pagos laborales",
    "laboral.cesantias_e_intereses": "Cesantías e intereses sobre cesantías",
    "laboral.salario_promedio_mensual_6m": "Ingreso laboral promedio de los últimos 6 meses",
    "laboral.aportes_obligatorios_pension": "Aportes obligatorios a pensión del trabajador",
    "laboral.aportes_obligatorios_salud": "Aportes obligatorios a salud del trabajador",
    "laboral.aportes_voluntarios_rais": "Aportes voluntarios al fondo de pensiones obligatorias",
    "independiente.honorarios_y_servicios": "Honorarios, comisiones y servicios",
    "capital.rendimientos_financieros": "Intereses y rendimientos financieros",
    "capital.arrendamientos": "Arrendamientos recibidos",
    "capital.regalias_y_otros": "Regalías y otras rentas de capital",
    "no_laborales.ingresos": "Otros ingresos no laborales",
    "pensiones.pensiones_nacionales": "Pensiones recibidas",
    "pensiones.aportes_salud": "Aportes a salud del pensionado",
    "dividendos.no_gravados_subcedula1": "Dividendos no gravados",
    "dividendos.gravados_subcedula2": "Dividendos gravados",
    "ganancias_ocasionales.loterias_premios": "Loterías, rifas y premios",
    "ganancias_ocasionales.seguros_vida": "Indemnizaciones de seguros de vida",
    "ganancias_ocasionales.donaciones_recibidas": "Donaciones recibidas",
    "ganancias_ocasionales.herencia_porcion_heredero": "Herencias o legados",
    "ganancias_ocasionales.utilidad_venta_otros_activos": "Utilidad en venta de activos",
    "deducciones.medicina_prepagada": "Medicina prepagada",
    "deducciones.intereses_vivienda": "Intereses de crédito de vivienda",
    "deducciones.gmf_pagado": "Gravamen a los movimientos financieros (4x1000)",
    "deducciones.aportes_voluntarios_afc_fpv": "Aportes voluntarios a pensión o AFC",
    "deducciones.compras_factura_electronica": "Compras con factura electrónica que dan beneficio",
    "pagos.retenciones_renta": "Retenciones en la fuente que te practicaron",
    "pagos.saldo_favor_anterior": "Saldo a favor del año anterior",
    "pagos.anticipo_anio_anterior": "Anticipo pagado el año anterior",
    "pagos.impuesto_neto_anio_anterior": "Impuesto neto de renta del año anterior",
    "patrimonio.bienes": "Bienes (patrimonio bruto)",
    "patrimonio.deudas": "Deudas",
}
_MAXIMO = {"laboral.salario_promedio_mensual_6m"}


def _n(texto: str | None) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).lower()


# (patrón sobre el detalle, campo o None, tratamiento, explicación)
_REGLAS: list[tuple[str, str | None, str, str]] = [
    (r"retencion", "pagos.retenciones_renta", "suma", "Impuesto que te descontaron por adelantado durante el año. Se resta de lo que debes pagar."),
    (r"total saldo a favor", "pagos.saldo_favor_anterior", "suma", "Saldo a favor que quedó de tu declaración anterior y no pediste devolver. Se resta del impuesto."),
    (r"patrimonio bruto declarado en el ano anterior", None, "informativo", "Lo que declaraste como patrimonio el año pasado. Sirve para comparar, no se suma."),
    (r"aportes? voluntarios?.*(regimen de ahorro individual|rais|pensiones obligatorias)", "laboral.aportes_voluntarios_rais", "suma", "Aportes voluntarios al fondo de pensión obligatoria; una parte no paga impuesto."),
    (r"aporte.*obligatori.*pension|aporte.*fondos? de pensiones y solidaridad", "laboral.aportes_obligatorios_pension", "suma", "Lo que te descontaron para pensión. No paga impuesto."),
    (r"aporte.*obligatori.*salud", "laboral.aportes_obligatorios_salud", "suma", "Lo que te descontaron para salud. No paga impuesto."),
    (r"facturacion electronica susceptible de beneficio", "deducciones.compras_factura_electronica", "suma", "Compras con factura electrónica pagadas con tarjeta o transferencia. El 1 % se resta de tu renta."),
    (r"medicina prepagada|planes? complementarios? de salud|polizas? de salud", "deducciones.medicina_prepagada", "suma", "Lo que pagaste en medicina prepagada o pólizas de salud. Se puede deducir con tope."),
    (r"intereses.*(vivienda|hipotecari|leasing habitacional)", "deducciones.intereses_vivienda", "suma", "Intereses pagados por crédito de vivienda. Se pueden deducir con tope."),
    (r"gravamen a los movimientos financieros|\bgmf\b|4 ?x ?1000", "deducciones.gmf_pagado", "suma", "El 4x1000 que te cobró el banco. La mitad se puede deducir."),
    (r"aportes? voluntarios?|pensiones voluntarias|\bafc\b|\bavc\b|fomento de la construccion", "deducciones.aportes_voluntarios_afc_fpv", "suma", "Ahorro voluntario en pensión o AFC. Puede quedar exento con límites."),
    (r"activos aportes parafiscales", "patrimonio.bienes", "revisar", "La DIAN lo suma a tu patrimonio, pero son aportes que reportó tu empleador. Confirma si corresponde a un saldo real a tu nombre."),
    (r"rendimientos causados|intereses o rendimientos", "capital.rendimientos_financieros", "suma", "Intereses que te pagaron tus ahorros o inversiones. Una parte (componente inflacionario) no paga impuesto."),
    (r"promedio.*(ingreso|salario)", "laboral.salario_promedio_mensual_6m", "suma", "Tu salario promedio de los últimos 6 meses. Define qué parte de las cesantías queda exenta."),
    (r"cesantias", "laboral.cesantias_e_intereses", "suma", "Cesantías que te consignaron o pagaron en el año. Suelen quedar exentas."),
    (r"cdt.*inversion efectuada|inversion efectuada", None, "revisar", "Una inversión (CDT) que hiciste en el año. Si seguía vigente el 31 de diciembre, súmala a tu patrimonio."),
    (r"saldo cuentas? bancarias|saldo (de )?(la )?cuenta", "patrimonio.bienes", "suma", "Lo que tenías en esta cuenta el 31 de diciembre. Es parte de tu patrimonio."),
    (r"avaluo catastral|base (del )?impuesto predial", "patrimonio.bienes", "suma", "Valor de tu inmueble según el catastro. Se declara como patrimonio (mínimo este valor)."),
    (r"vehiculo|automotor", "patrimonio.bienes", "suma", "Valor de tu vehículo. Es parte de tu patrimonio."),
    (r"valor total de la inversion|aporte o derecho social|acciones|cuotas? o partes? de interes", "patrimonio.bienes", "suma", "Aportes o inversiones que tenías al 31 de diciembre (por ejemplo, en un fondo de empleados)."),
    (r"cuentas por cobrar", "patrimonio.bienes", "suma", "Dinero que te debían a 31 de diciembre. Cuenta como patrimonio."),
    (r"cuentas por pagar|saldo.*(credito|deuda|obligacion|prestamo)|pasivo", "patrimonio.deudas", "suma", "Lo que debías a esta entidad el 31 de diciembre. Se resta de tu patrimonio."),
    (r"consumos? .*tarjeta", None, "informativo", "Lo que gastaste con tarjeta. Solo sirve para saber si estás obligado a declarar."),
    (r"movimientos en cuentas|consignaciones", None, "informativo", "Dinero que entró a tus cuentas. Solo sirve para saber si estás obligado a declarar."),
    (r"suma valor total facturas", None, "informativo", "Total de tus compras con factura electrónica. Solo sirve para el tope de obligación."),
    (r"dividendos?.*no gravad", "dividendos.no_gravados_subcedula1", "suma", "Dividendos de utilidades que ya pagaron impuesto en la empresa."),
    (r"dividendos?.*gravad", "dividendos.gravados_subcedula2", "suma", "Dividendos de utilidades que no pagaron impuesto en la empresa."),
    (r"dividendos?|participaciones", "dividendos.no_gravados_subcedula1", "revisar", "Dividendos recibidos. Revisa en el certificado de la empresa si son gravados o no gravados."),
    (r"pension(es)? de (jubilacion|vejez|invalidez|sobrevivientes)|mesadas? pensional|pagos? por pensiones", "pensiones.pensiones_nacionales", "suma", "Pensión que recibiste en el año."),
    (r"honorarios|comisiones|servicios", "independiente.honorarios_y_servicios", "suma", "Pagos que recibiste como independiente."),
    (r"arrendamiento", "capital.arrendamientos", "suma", "Arriendos que recibiste."),
    (r"loteria|premio|rifa|apuesta", "ganancias_ocasionales.loterias_premios", "suma", "Premios de loterías o rifas. Pagan 20 %."),
    (r"revalorizacion", "no_laborales.ingresos", "suma", "Ganancia por la revalorización de tus aportes (por ejemplo, en un fondo de empleados)."),
    (r"intereses|rendimientos", "capital.rendimientos_financieros", "suma", "Intereses que te pagaron tus ahorros o inversiones. Una parte (componente inflacionario) no paga impuesto."),
    (r"salario|pagos laborales|prestaciones sociales|viaticos|gastos de representacion|compensaciones|pagos? por bonos|pagos? por alimentacion", "laboral.salarios_y_pagos_laborales", "suma", "Lo que te pagó tu empleador durante el año."),
]

# Renglones del formulario 210 que la DIAN pone en "Uso declaración sugerida"
_RENGLONES = {
    "R32": "laboral.salarios_y_pagos_laborales",
    "R43": "independiente.honorarios_y_servicios",
    "R58": "capital.rendimientos_financieros",
    "R74": "no_laborales.ingresos",
    "R99": "pensiones.pensiones_nacionales",
    "R29": "patrimonio.bienes",
    "R30": "patrimonio.deudas",
    "R131": "pagos.saldo_favor_anterior",
    "R132": "pagos.retenciones_renta",
}

_TOPES = {
    "tope 1": "ingresos_reportados_exogena",
    "tope 2": "patrimonio_reportado_exogena",
    "tope 3": "consumos_tarjeta_credito",
    "tope 4": "consignaciones_depositos_inversiones",
    "tope 5": "compras_consumos",
}


def mapear_por_reglas(fila: FilaInterpretada) -> FilaInterpretada:
    det = _n(fila.detalle)
    for patron, campo, tratamiento, explicacion in _REGLAS:
        if re.search(patron, det):
            fila.campo, fila.tratamiento, fila.explicacion, fila.origen_mapeo = campo, tratamiento, explicacion, "reglas"  # type: ignore[assignment]
            return fila
    renglon = re.search(r"\bR(\d{2,3})\b", fila.uso_sugerido or "")
    if renglon and f"R{renglon.group(1)}" in _RENGLONES:
        fila.campo = _RENGLONES[f"R{renglon.group(1)}"]
        fila.tratamiento = "suma"
        fila.explicacion = f"La DIAN sugiere llevarlo a: {CAMPOS[fila.campo].lower()}."
        fila.origen_mapeo = "reglas"
        return fila
    fila.campo, fila.tratamiento, fila.origen_mapeo = None, "revisar", "sin_mapeo"
    fila.explicacion = "No reconocimos este concepto automáticamente."
    return fila


SISTEMA = """Eres el agente Intérprete de un asistente de declaración de renta para personas naturales en Colombia.
Recibes conceptos del reporte de información exógena de la DIAN (sin montos ni datos personales).
Para cada concepto:
- "campo": elige UNA llave de la lista CAMPOS, o "informativo" si no se suma en la declaración, o "revisar" si no estás seguro.
- "explicacion": máximo 25 palabras, en español sencillo, dirigida a alguien sin formación contable. No inventes cifras.
Responde SOLO un JSON: {"conceptos": [{"i": <número>, "campo": "<llave>", "explicacion": "<texto>"}]}"""


async def _interpretar_con_ia(pendientes: list[FilaInterpretada]) -> str | None:
    """Pide al modelo campo + explicación para las filas pendientes. Devuelve el modelo usado."""
    if not pendientes or not cliente.disponible():
        return None
    unicos: dict[str, list[FilaInterpretada]] = {}
    for f in pendientes:
        unicos.setdefault(f.detalle, []).append(f)
    lista = list(unicos.items())
    usuario = "CAMPOS:\n" + "\n".join(f"- {k}: {v}" for k, v in CAMPOS.items())
    usuario += "\n\nCONCEPTOS:\n" + "\n".join(
        f'{i}. "{det}" | uso sugerido DIAN: {filas[0].uso_sugerido or "—"} | info: {(filas[0].info_adicional or "—")[:120]}'
        for i, (det, filas) in enumerate(lista)
    )
    try:
        r = await cliente.completar("interprete", SISTEMA, usuario, json_mode=True, max_tokens=1500)
        j = cliente.extraer_json(r.texto)
    except Exception:  # noqa: BLE001 - si falla la IA, las filas quedan para revisión humana
        return None
    for item in j.get("conceptos", []):
        try:
            det, filas = lista[int(item["i"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        campo = str(item.get("campo", "revisar"))
        explicacion = str(item.get("explicacion", ""))[:220]
        for f in filas:
            if explicacion:
                f.explicacion = explicacion
            if f.origen_mapeo == "sin_mapeo":  # la IA solo decide donde las reglas no pudieron
                if campo in CAMPOS:
                    f.campo, f.tratamiento, f.origen_mapeo = campo, "suma", "ia"
                elif campo == "informativo":
                    f.campo, f.tratamiento, f.origen_mapeo = None, "informativo", "ia"
    return r.modelo


def _poner(destino: dict[str, Any], ruta: str, valor: float, maximo: bool = False) -> None:
    seccion, campo = ruta.split(".", 1)
    sec = destino.setdefault(seccion, {})
    actual = sec.get(campo, 0)
    sec[campo] = max(actual, valor) if maximo else actual + valor


def construir_datos(filas: list[FilaInterpretada], topes: dict[str, float], anio: int | None, ultimos: str | None) -> tuple[dict[str, Any], Perfil, dict[str, float]]:
    """Convierte las filas aceptadas en la entrada del motor. Las cifras salen tal cual de cada fila."""
    datos: dict[str, Any] = {"anio_gravable": anio or 2025, "patrimonio": {"bienes": [], "deudas": []}, "fuentes": {}}
    resumen: dict[str, float] = {}
    perfil = Perfil()
    for f in filas:
        det = _n(f.detalle)
        if "patrimonio bruto declarado en el ano anterior" in det or "total saldo a favor" in det or f.fuente == "declaracion_anterior":
            perfil.declaro_antes = True
        if f.tratamiento != "suma" or not f.campo:
            continue
        if f.campo in ("patrimonio.bienes", "patrimonio.deudas"):
            lista = "deudas" if (f.campo == "patrimonio.deudas" or f.valor < 0) else "bienes"
            datos["patrimonio"][lista].append(
                {"concepto": f"{f.detalle[:70]} ({(f.informante or 'reportado')[:50]})", "valor": abs(f.valor), "fuente": f.id}
            )
            clave = f"patrimonio.{lista}"
            resumen[clave] = resumen.get(clave, 0) + abs(f.valor)
        else:
            _poner(datos, f.campo, f.valor, maximo=f.campo in _MAXIMO)
            resumen[f.campo] = max(resumen.get(f.campo, 0), f.valor) if f.campo in _MAXIMO else resumen.get(f.campo, 0) + f.valor
        datos["fuentes"].setdefault(f.campo, []).append(f.id)

    indicadores: dict[str, float] = {}
    for nombre, valor in topes.items():
        for prefijo, campo in _TOPES.items():
            if _n(nombre).startswith(prefijo):
                indicadores[campo] = valor
    datos["indicadores"] = indicadores

    # Si no hay salario pero sí honorarios, los aportes son del independiente
    lab = datos.get("laboral", {})
    if not lab.get("salarios_y_pagos_laborales") and datos.get("independiente", {}).get("honorarios_y_servicios"):
        for k in ("aportes_obligatorios_pension", "aportes_obligatorios_salud"):
            if lab.get(k):
                datos.setdefault("independiente", {})[k] = lab.pop(k)

    if perfil.declaro_antes:
        datos["pagos"] = {**datos.get("pagos", {}), "declaraciones_previas": 1}
    if ultimos:
        datos["control"] = {"ultimos_dos_digitos_nit": ultimos}

    perfil.empleado = bool(lab.get("salarios_y_pagos_laborales") or lab.get("cesantias_e_intereses"))
    perfil.independiente = bool(datos.get("independiente", {}).get("honorarios_y_servicios"))
    perfil.pensionado = bool(datos.get("pensiones", {}).get("pensiones_nacionales"))
    perfil.rentas_capital = bool(datos.get("capital"))
    perfil.dividendos = bool(datos.get("dividendos"))
    perfil.ganancias_ocasionales = bool(datos.get("ganancias_ocasionales"))
    return datos, perfil, resumen


async def interpretar(doc: DocumentoLeido, ultimos: str | None, enmascarados: int) -> tuple[Extraccion, str | None, int]:
    """Devuelve (extracción, modelo usado o None, filas enviadas al modelo)."""
    filas = [mapear_por_reglas(FilaInterpretada(**f.model_dump())) for f in doc.filas]
    revision.resolver_duplicados(filas)
    revision.resolver_alimentacion(filas, doc.anio)
    pendientes = [f for f in filas if f.tratamiento == "revisar"]
    modelo = await _interpretar_con_ia(pendientes)
    for f in filas:
        if f.tratamiento == "revisar" or f.origen_mapeo == "ia":
            revision.preparar(f, filas, doc.anio)
    datos, perfil, resumen = construir_datos(filas, doc.topes, doc.anio, ultimos)
    extraccion = Extraccion(
        anio=doc.anio,
        ultimos_dos_digitos_nit=ultimos,
        filas=filas,
        datos=datos,
        perfil=perfil,
        resumen_campos=resumen,
        datos_enmascarados=enmascarados,
        topes=doc.topes,
    )
    return extraccion, modelo, len(pendientes)
