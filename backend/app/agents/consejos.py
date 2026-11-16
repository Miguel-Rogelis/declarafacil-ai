"""Agente Consejos: qué podría hacer la persona para pagar menos el próximo año.

Solo reglas, sin IA. Re-liquida el mismo caso con un cambio a la vez (aportar a AFC o pensión
voluntaria, pedir factura electrónica) y solo lo propone si el ahorro es real.
"""

from pydantic import BaseModel

from app.tax.modelos import DatosDeclaracion, Liquidacion
from app.tax.motor import cop, liquidar


class Consejo(BaseModel):
    clave: str
    titulo: str
    detalle: str
    ahorro: float
    monto: float = 0


def _impuesto(d: DatosDeclaracion, reglas: dict) -> float:
    return liquidar(d, reglas).resumen.total_impuesto_cargo


def _redondo(v: float) -> float:
    paso = 1_000_000 if v >= 10_000_000 else 100_000
    return max(paso, round(v / paso) * paso)


def consejos(d: DatosDeclaracion, liq: Liquidacion, reglas: dict) -> list[Consejo]:
    base = liq.resumen.total_impuesto_cargo
    if base <= 0:
        return []
    uvt = reglas["uvt"]
    cg = reglas["cedula_general"]
    minimo = max(100_000, base * 0.02)
    salida: list[Consejo] = []
    trabajo = d.laboral.salarios_y_pagos_laborales + d.independiente.honorarios_y_servicios

    # 1. Aportes voluntarios a pensión o AFC: se busca el menor aporte que logra casi todo el ahorro
    if trabajo > 0:
        tope = min(trabajo * cg["aportes_voluntarios_afc_fpv_pct"], cg["aportes_voluntarios_afc_fpv_tope_uvt"] * uvt) - d.deducciones.aportes_voluntarios_afc_fpv
        if tope > 1_000_000:
            pruebas = []
            for f in (0.1, 0.25, 0.5, 0.75, 1.0):
                monto = _redondo(tope * f)
                d2 = d.model_copy(deep=True)
                d2.deducciones.aportes_voluntarios_afc_fpv += monto
                pruebas.append((monto, base - _impuesto(d2, reglas)))
            mejor = max(a for _, a in pruebas)
            if mejor >= minimo:
                monto, ahorro = next((m, a) for m, a in pruebas if a >= mejor * 0.9)
                salida.append(Consejo(
                    clave="afc", monto=monto, ahorro=ahorro,
                    titulo=f"Aportar {cop(monto)} a una cuenta AFC o pensión voluntaria",
                    detalle=(f"Con un caso como el tuyo pagarías unos {cop(ahorro)} menos de impuesto. Tiene que quedar consignado antes del 31 de diciembre. "
                             "Ojo: esa plata queda ahorrada; si la retiras antes de 10 años o sin usarla para vivienda, pierdes el beneficio."),
                ))

    # 2. Pedir factura electrónica con la cédula (el 1 %, desde 2023, por fuera del límite del 40 %)
    if d.anio_gravable >= 2023 and cg.get("factura_electronica_pct") and not d.deducciones.compras_factura_electronica and trabajo > 0:
        compras = _redondo(min(trabajo * 0.3, cg["factura_electronica_tope_uvt"] * uvt / cg["factura_electronica_pct"]))
        d2 = d.model_copy(deep=True)
        d2.deducciones.compras_factura_electronica = compras
        ahorro = base - _impuesto(d2, reglas)
        if ahorro >= min(minimo, 50_000):
            salida.append(Consejo(
                clave="factura", monto=compras, ahorro=ahorro,
                titulo="Pedir factura electrónica con tu cédula",
                detalle=(f"Si en el año compras unos {cop(compras)} con factura a tu nombre (mercado, ropa, restaurantes), "
                         f"el 1 % se resta y pagarías unos {cop(ahorro)} menos. No cuesta nada: solo di tu cédula al pagar."),
            ))
    return salida
