"""Agente Auditor: revisa la declaración antes de que el usuario la firme.

Solo reglas, sin IA. Busca inconsistencias, datos que suelen faltar y riesgos.
"""

from app.agents.base import FilaInterpretada
from app.tax.modelos import Alerta, DatosDeclaracion, Liquidacion
from app.tax.motor import cop


def auditar(datos: DatosDeclaracion, liq: Liquidacion, filas: list[FilaInterpretada]) -> list[Alerta]:
    alertas: list[Alerta] = []

    def agregar(nivel: str, titulo: str, detalle: str) -> None:
        alertas.append(Alerta(nivel=nivel, titulo=titulo, detalle=detalle, origen="auditor"))  # type: ignore[arg-type]

    # 1. Filas que necesitan confirmación humana
    revisar = [f for f in filas if f.tratamiento == "revisar"]
    if revisar:
        agregar(
            "advertencia",
            f"{len(revisar)} dato(s) de la exógena necesitan tu confirmación",
            "No los sumamos todavía: " + "; ".join(f"{f.detalle[:60]} ({cop(f.valor)})" for f in revisar[:4]) + ". Revísalos en la tabla de datos.",
        )
    por_ia = [f for f in filas if f.origen_mapeo == "ia" and f.tratamiento == "suma"]
    if por_ia:
        agregar(
            "advertencia",
            f"La IA ubicó {len(por_ia)} concepto(s) que las reglas no reconocieron",
            "Confírmalos antes de firmar: " + "; ".join(f.detalle[:60] for f in por_ia[:4]) + ".",
        )

    # 2. Ingresos declarados vs. lo que reportaron terceros
    reportado = datos.indicadores.ingresos_reportados_exogena
    if reportado and liq.resumen.ingresos_brutos_totales < reportado * 0.97:
        agregar(
            "critica",
            "Declaras menos ingresos de los que reportaron terceros",
            f"La exógena suma {cop(reportado)} en ingresos y la declaración {cop(liq.resumen.ingresos_brutos_totales)}. "
            "La DIAN cruza esta información; si la diferencia es correcta, guarda los soportes.",
        )

    # 3. Patrimonio
    if liq.resumen.deudas > liq.resumen.patrimonio_bruto > 0:
        agregar(
            "advertencia",
            "Tus deudas superan tus bienes",
            "Revisa que las deudas sean saldos a 31 de diciembre y que no falten bienes (vehículos, cuentas, inversiones).",
        )
    anterior = next((f.valor for f in filas if "patrimonio bruto declarado en el a" in f.detalle.lower()), 0)
    if anterior and liq.resumen.patrimonio_bruto < anterior * 0.6:
        agregar(
            "advertencia",
            "Tu patrimonio bajó mucho frente al año anterior",
            f"El año pasado declaraste {cop(anterior)} y ahora suma {cop(liq.resumen.patrimonio_bruto)}. "
            "Puede faltar algún bien o un dato por confirmar.",
        )
    if anterior and liq.resumen.patrimonio_bruto - anterior > liq.resumen.ingresos_brutos_totales:
        agregar(
            "advertencia",
            "Aumento de patrimonio mayor que tus ingresos",
            "La DIAN puede pedir que justifiques ese aumento (renta por comparación patrimonial, art. 236 ET).",
        )
    if any("avaluo catastral" in f.detalle.lower().replace("ú", "u") for f in filas):
        agregar(
            "info",
            "Inmueble: el avalúo catastral es el valor mínimo",
            "Declara el mayor entre el avalúo catastral y el costo fiscal del inmueble (art. 277 ET).",
        )
    agregar("info", "La exógena no trae vehículos ni todo tu patrimonio", "Si tienes carro, moto u otros bienes, agrégalos con su valor fiscal.")

    # 4. Beneficios que suelen quedar por fuera
    hay_trabajo = datos.laboral.salarios_y_pagos_laborales > 0 or datos.independiente.honorarios_y_servicios > 0
    if hay_trabajo and datos.deducciones.dependientes == 0:
        agregar("info", "¿Tienes personas a cargo?", "Hijos, cónyuge o padres que dependan de ti pueden bajar tu impuesto hasta 384 UVT más 72 UVT por cada uno.")
    if liq.resumen.deudas > 0 and datos.deducciones.intereses_vivienda == 0:
        agregar("info", "¿Alguna deuda es crédito de vivienda?", "Los intereses que pagaste en el año se pueden deducir hasta 1.200 UVT. Pide el certificado al banco.")

    # 5. Resultado
    if liq.resumen.saldo_favor > 0:
        agregar("info", "Te queda saldo a favor", f"Puedes pedir la devolución de {cop(liq.resumen.saldo_favor)} o usarlo en tu próxima declaración.")
    if liq.resumen.anticipo_siguiente > 0 and datos.pagos.declaraciones_previas >= 1 and datos.pagos.impuesto_neto_anio_anterior == 0:
        agregar(
            "info",
            "Puedes bajar el anticipo",
            "Si nos das el impuesto neto de renta de tu declaración anterior, calculamos el anticipo por el procedimiento que te resulte menor.",
        )
    if not liq.obligacion.obligado and liq.resumen.saldo_favor == 0:
        agregar("info", "No estás obligado a declarar", "Según los topes no tienes que presentar declaración este año.")
    if liq.vencimiento is None:
        agregar("info", "No sabemos tu fecha límite", "Danos los dos últimos dígitos de tu cédula para revisar el vencimiento.")

    agregar(
        "info",
        "Este es un borrador",
        "Revísalo y fírmalo tú en el portal MUISCA de la DIAN. Para casos complejos (herencias, exterior, negocios) consulta a un contador.",
    )
    return alertas
