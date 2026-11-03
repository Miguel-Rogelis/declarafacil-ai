"""Motor tributario determinista.

Aquí NO hay IA: cada cifra sale de una regla del Estatuto Tributario cuyo parámetro
vive en el archivo de reglas del año (data/reglas/agAAAA.json).
"""

import math
from datetime import date
from typing import Any

from app.tax import reglas as repo_reglas
from app.tax.modelos import (
    Alerta,
    DatosDeclaracion,
    Linea,
    Liquidacion,
    Obligacion,
    Resumen,
    Seccion,
    TopeObligacion,
    Vencimiento,
)


def cop(valor: float) -> str:
    """Formato de pesos colombianos: $1.234.567"""
    return "$" + f"{valor:,.0f}".replace(",", ".")


def _redondear(valor: float, multiplo: int = 1000) -> float:
    """La DIAN aproxima los valores del formulario al múltiplo de mil más cercano."""
    if multiplo <= 1:
        return round(valor)
    return float(int(math.floor(valor / multiplo + 0.5)) * multiplo)


def impuesto_tabla_241(renta_gravable: float, uvt: float, tabla: list[dict[str, Any]]) -> float:
    base_uvt = max(renta_gravable, 0) / uvt
    for tramo in tabla:
        hasta = tramo["hasta_uvt"]
        if hasta is None or base_uvt <= hasta:
            impuesto_uvt = (base_uvt - tramo["base_uvt"]) * tramo["tarifa"] + tramo["impuesto_fijo_uvt"]
            return max(impuesto_uvt, 0) * uvt
    return 0.0


def _pct_cesantias(salario_promedio: float, uvt: float, tabla: list[dict[str, Any]]) -> float:
    if salario_promedio <= 0:
        return 1.0
    en_uvt = salario_promedio / uvt
    for tramo in tabla:
        if tramo["hasta_uvt"] is None or en_uvt <= tramo["hasta_uvt"]:
            return tramo["exento_pct"]
    return 0.0


def _meses_o_fraccion(desde: date, hasta: date) -> int:
    if hasta <= desde:
        return 0
    meses = (hasta.year - desde.year) * 12 + (hasta.month - desde.month)
    if hasta.day > desde.day:
        meses += 1
    return max(meses, 1)


def _uvt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


class _Calculo:
    """Una liquidación completa para una opción de independiente dada."""

    def __init__(self, d: DatosDeclaracion, r: dict[str, Any], opcion_ind: str):
        self.d = d
        self.r = r
        self.uvt = float(r["uvt"])
        self.opcion_ind = opcion_ind
        self.secciones: list[Seccion] = []
        self.alertas: list[Alerta] = []

    def u(self, cantidad_uvt: float) -> float:
        return cantidad_uvt * self.uvt

    # ---------- Cédula general ----------
    def cedula_general(self) -> dict[str, float]:
        d, cg = self.d, self.r["cedula_general"]
        lab, ind, cap, nl, ded = d.laboral, d.independiente, d.capital, d.no_laborales, d.deducciones

        ingresos_lab = lab.salarios_y_pagos_laborales + lab.cesantias_e_intereses
        vol_rais = min(
            lab.aportes_voluntarios_rais,
            ingresos_lab * cg["aportes_voluntarios_rais_pct"],
            self.u(cg["aportes_voluntarios_rais_tope_uvt"]),
        )
        incr_lab = lab.aportes_obligatorios_pension + lab.aportes_obligatorios_salud + vol_rais
        neto_lab = max(ingresos_lab - incr_lab, 0)

        ingresos_ind = ind.honorarios_y_servicios
        incr_ind = ind.aportes_obligatorios_pension + ind.aportes_obligatorios_salud
        neto_ind = max(ingresos_ind - incr_ind, 0)
        costos_ind = min(ind.costos_gastos_procedentes, neto_ind) if self.opcion_ind == "costos" else 0

        ingresos_cap = cap.rendimientos_financieros + cap.arrendamientos + cap.regalias_y_otros
        incr_cap = cap.rendimientos_financieros * cg["componente_inflacionario_rendimientos_pct"]
        costos_cap = min(cap.costos_gastos_procedentes, max(ingresos_cap - incr_cap, 0))
        neto_cap = max(ingresos_cap - incr_cap - costos_cap, 0)

        ingresos_nl = nl.ingresos
        incr_nl = min(nl.ingresos_no_constitutivos, ingresos_nl)
        costos_nl = min(nl.costos_gastos_procedentes, ingresos_nl - incr_nl)
        neto_nl = max(ingresos_nl - incr_nl - costos_nl, 0)

        ingresos_total = ingresos_lab + ingresos_ind + ingresos_cap + ingresos_nl
        incr_total = incr_lab + incr_ind + incr_cap + incr_nl
        ingreso_neto = max(ingresos_total - incr_total, 0)
        renta_liquida = neto_lab + (neto_ind - costos_ind) + neto_cap + neto_nl

        ingresos_trabajo = ingresos_lab + ingresos_ind
        hay_trabajo = ingresos_trabajo > 0

        # Deducciones y rentas exentas sujetas al límite del 40 % (1.340 UVT desde 2023; 5.040 UVT antes)
        dep_387 = 0.0
        if ded.dependientes >= 1 and hay_trabajo:
            dep_387 = min(ingresos_trabajo * cg["dependiente_art387_pct"], self.u(cg["dependiente_art387_tope_uvt"]))
        prepagada = min(ded.medicina_prepagada, self.u(cg["medicina_prepagada_tope_uvt"])) if hay_trabajo else 0
        intereses = min(ded.intereses_vivienda, self.u(cg["intereses_vivienda_tope_uvt"]))
        gmf = ded.gmf_pagado * cg["gmf_deducible_pct"]
        afc = min(
            ded.aportes_voluntarios_afc_fpv,
            ingresos_total * cg["aportes_voluntarios_afc_fpv_pct"],
            self.u(cg["aportes_voluntarios_afc_fpv_tope_uvt"]),
        )
        pct_ces = _pct_cesantias(lab.salario_promedio_mensual_6m, self.uvt, cg["cesantias_exencion_por_salario_promedio_uvt"])
        cesantias_exentas = lab.cesantias_e_intereses * pct_ces

        base_trabajo_25 = neto_lab + (neto_ind if self.opcion_ind == "renta_exenta_25" else 0)
        otras = dep_387 + prepagada + intereses + gmf + afc + cesantias_exentas
        base_25 = max(base_trabajo_25 - otras, 0)
        exenta_25 = min(base_25 * cg["renta_exenta_laboral_pct"], self.u(cg["renta_exenta_laboral_tope_uvt"]))

        sujetas = otras + exenta_25
        limite = min(ingreso_neto * cg["limite_rentas_exentas_deducciones_pct"], self.u(cg["limite_rentas_exentas_deducciones_uvt"]))
        aceptadas = min(sujetas, limite, renta_liquida)
        recorte = sujetas - aceptadas
        if recorte > 1000:
            self.alertas.append(
                Alerta(
                    nivel="info",
                    titulo="Tus beneficios superan el límite legal",
                    detalle=(
                        f"Sumaste {cop(sujetas)} en rentas exentas y deducciones, pero la ley solo deja restar "
                        f"{cop(aceptadas)} (40 % del ingreso neto, máximo {_uvt(cg['limite_rentas_exentas_deducciones_uvt'])} UVT). La diferencia no reduce tu impuesto."
                    ),
                )
            )

        # Fuera del límite
        n_72 = 0
        if hay_trabajo and ded.dependientes > 0:
            if ingresos_lab > 0:
                n_72 = min(ded.dependientes, cg["dependiente_adicional_max"])
            else:
                n_72 = min(max(ded.dependientes - 1, 0), cg["dependiente_adicional_max"])
        dep_72 = n_72 * self.u(cg["dependiente_adicional_uvt"])
        factura = min(ded.compras_factura_electronica * cg["factura_electronica_pct"], self.u(cg["factura_electronica_tope_uvt"]))
        fuera = min(dep_72 + factura, max(renta_liquida - aceptadas, 0))

        rlg = max(renta_liquida - aceptadas - fuera, 0)

        lineas = [
            Linea(clave="ing_lab", concepto="Ingresos por rentas de trabajo (salarios y cesantías)", valor=ingresos_lab, norma="Art. 103 ET", campos=["laboral.salarios_y_pagos_laborales", "laboral.cesantias_e_intereses"]),
            Linea(clave="incr_lab", concepto="Aportes obligatorios a pensión y salud (no constituyen renta)", valor=incr_lab, norma="Arts. 55 y 56 ET", campos=["laboral.aportes_obligatorios_pension", "laboral.aportes_obligatorios_salud", "laboral.aportes_voluntarios_rais"]),
            Linea(clave="ing_ind", concepto="Ingresos por honorarios y servicios (independiente)", valor=ingresos_ind, norma="Art. 335 ET", campos=["independiente.honorarios_y_servicios"]),
            Linea(clave="incr_ind", concepto="Aportes a seguridad social como independiente", valor=incr_ind, campos=["independiente.aportes_obligatorios_pension", "independiente.aportes_obligatorios_salud"]),
            Linea(clave="costos_ind", concepto="Costos y gastos del independiente", valor=costos_ind, norma="Num. 4 art. 336 ET", campos=["independiente.costos_gastos_procedentes"]),
            Linea(clave="ing_cap", concepto="Ingresos por rentas de capital (intereses, arriendos)", valor=ingresos_cap, norma="Art. 338 ET", campos=["capital.rendimientos_financieros", "capital.arrendamientos", "capital.regalias_y_otros"]),
            Linea(clave="incr_cap", concepto="Componente inflacionario de los rendimientos (no constituye renta)", valor=incr_cap, norma="Art. 38 ET y decreto anual", campos=["capital.rendimientos_financieros"]),
            Linea(clave="costos_cap", concepto="Costos y gastos de rentas de capital", valor=costos_cap, campos=["capital.costos_gastos_procedentes"]),
            Linea(clave="ing_nl", concepto="Ingresos por rentas no laborales", valor=ingresos_nl, norma="Art. 340 ET", campos=["no_laborales.ingresos"]),
            Linea(clave="incr_nl", concepto="Ingresos no constitutivos de rentas no laborales", valor=incr_nl, campos=["no_laborales.ingresos_no_constitutivos"]),
            Linea(clave="costos_nl", concepto="Costos y gastos de rentas no laborales", valor=costos_nl, campos=["no_laborales.costos_gastos_procedentes"]),
            Linea(clave="renta_liquida_cg", concepto="Renta líquida de la cédula general", valor=renta_liquida),
            Linea(clave="dep_387", concepto="Deducción por dependiente (10 % de los ingresos de trabajo)", valor=dep_387, norma="Art. 387 ET", campos=["deducciones.dependientes"]),
            Linea(clave="prepagada", concepto="Medicina prepagada", valor=prepagada, norma="Art. 387 ET", campos=["deducciones.medicina_prepagada"]),
            Linea(clave="intereses_vivienda", concepto="Intereses de crédito de vivienda", valor=intereses, norma="Art. 119 ET", campos=["deducciones.intereses_vivienda"]),
            Linea(clave="gmf", concepto="50 % del gravamen a los movimientos financieros (4x1000)", valor=gmf, norma="Art. 115 ET", campos=["deducciones.gmf_pagado"]),
            Linea(clave="afc_fpv", concepto="Aportes voluntarios a pensión y cuentas AFC", valor=afc, norma="Arts. 126-1 y 126-4 ET", campos=["deducciones.aportes_voluntarios_afc_fpv"]),
            Linea(clave="cesantias_exentas", concepto=f"Cesantías exentas ({pct_ces:.0%})", valor=cesantias_exentas, norma="Num. 4 art. 206 ET", campos=["laboral.cesantias_e_intereses", "laboral.salario_promedio_mensual_6m"]),
            Linea(clave="exenta_25", concepto=f"Renta exenta del 25 % (máx. {_uvt(cg['renta_exenta_laboral_tope_uvt'])} UVT al año)", valor=exenta_25, norma="Num. 10 art. 206 ET"),
            Linea(clave="limite_40", concepto=f"Límite legal de exentas y deducciones (40 % o {_uvt(cg['limite_rentas_exentas_deducciones_uvt'])} UVT)", valor=limite, norma="Art. 336 ET"),
            Linea(clave="aceptadas", concepto="Rentas exentas y deducciones que sí se restan", valor=aceptadas, norma="Art. 336 ET"),
            Linea(clave="dep_72", concepto=f"Deducción adicional por {n_72} dependiente(s) (72 UVT c/u)", valor=dep_72, norma="Num. 3 art. 336 ET", campos=["deducciones.dependientes"]),
            Linea(clave="factura_1", concepto="1 % de compras con factura electrónica (máx. 240 UVT)", valor=factura, norma="Num. 5 art. 336 ET", campos=["deducciones.compras_factura_electronica"]),
            Linea(clave="rlg_cg", concepto="Renta líquida gravable de la cédula general", valor=rlg, norma="Art. 336 ET"),
        ]
        self.secciones.append(
            Seccion(id="cedula_general", titulo="Cédula general", lineas=[ln for ln in lineas if ln.valor or ln.clave in {"renta_liquida_cg", "rlg_cg"}])
        )
        return {
            "ingresos": ingresos_total,
            "rlg": rlg,
            "ingresos_trabajo": ingresos_trabajo,
        }

    # ---------- Pensiones ----------
    def cedula_pensiones(self) -> dict[str, float]:
        p = self.d.pensiones
        if p.pensiones_nacionales <= 0:
            return {"ingresos": 0, "rlg": 0}
        neto = max(p.pensiones_nacionales - p.aportes_salud, 0)
        exenta = min(neto, self.u(self.r["cedula_pensiones"]["renta_exenta_mensual_uvt"] * 12))
        rlg = neto - exenta
        self.secciones.append(
            Seccion(
                id="cedula_pensiones",
                titulo="Cédula de pensiones",
                lineas=[
                    Linea(clave="ing_pen", concepto="Ingresos por pensiones", valor=p.pensiones_nacionales, norma="Art. 337 ET", campos=["pensiones.pensiones_nacionales"]),
                    Linea(clave="incr_pen", concepto="Aportes a salud", valor=p.aportes_salud, campos=["pensiones.aportes_salud"]),
                    Linea(clave="exenta_pen", concepto="Renta exenta (hasta 1.000 UVT mensuales)", valor=exenta, norma="Num. 5 art. 206 ET"),
                    Linea(clave="rlg_pen", concepto="Renta líquida gravable de pensiones", valor=rlg),
                ],
            )
        )
        return {"ingresos": p.pensiones_nacionales, "rlg": rlg}

    # ---------- Dividendos ----------
    def cedula_dividendos(self) -> dict[str, float]:
        dv, rd = self.d.dividendos, self.r["dividendos"]
        sub1, sub2 = dv.no_gravados_subcedula1, dv.gravados_subcedula2
        if sub1 + sub2 <= 0:
            return {"ingresos": 0, "base_241": 0, "impuesto_sub2": 0, "descuento": 0}
        if rd.get("regimen") == "tabla_propia":
            return self._dividendos_tabla_propia(sub1, sub2, rd)
        impuesto_sub2 = sub2 * rd["tarifa_subcedula_gravada"]
        base_241 = sub1 + (sub2 - impuesto_sub2)
        descuento = max(base_241 / self.uvt - rd["descuento_art254_1_umbral_uvt"], 0) * rd["descuento_art254_1_pct"] * self.uvt
        self.secciones.append(
            Seccion(
                id="cedula_dividendos",
                titulo="Cédula de dividendos y participaciones",
                lineas=[
                    Linea(clave="div_sub1", concepto="Dividendos no gravados (subcédula 1)", valor=sub1, norma="Art. 242 ET", campos=["dividendos.no_gravados_subcedula1"]),
                    Linea(clave="div_sub2", concepto="Dividendos gravados (subcédula 2)", valor=sub2, norma="Inc. 2 art. 242 ET", campos=["dividendos.gravados_subcedula2"]),
                    Linea(clave="imp_sub2", concepto="Impuesto del 35 % sobre dividendos gravados", valor=impuesto_sub2, norma="Art. 240 ET"),
                    Linea(clave="div_base", concepto="Dividendos que se suman a la tabla del art. 241", valor=base_241, norma="Art. 331 ET"),
                    Linea(clave="desc_div", concepto="Descuento por dividendos (19 % sobre lo que pase de 1.090 UVT)", valor=descuento, norma="Art. 254-1 ET"),
                ],
            )
        )
        return {"ingresos": sub1 + sub2, "base_241": base_241, "impuesto_sub2": impuesto_sub2, "descuento": descuento}

    def _dividendos_tabla_propia(self, sub1: float, sub2: float, rd: dict[str, Any]) -> dict[str, float]:
        """Antes de la Ley 2277 (AG 2021-2022): los dividendos tributan aparte con su propia tabla."""
        impuesto_sub2 = sub2 * rd["tarifa_subcedula_gravada"]
        base = sub1 + (sub2 - impuesto_sub2)
        base_uvt = base / self.uvt
        impuesto_tabla = 0.0
        for tramo in rd["tabla_dividendos"]:
            hasta = tramo["hasta_uvt"] if tramo["hasta_uvt"] is not None else float("inf")
            if base_uvt > tramo["desde_uvt"]:
                impuesto_tabla += (min(base_uvt, hasta) - tramo["desde_uvt"]) * tramo["tarifa"] * self.uvt
        self.secciones.append(
            Seccion(
                id="cedula_dividendos",
                titulo="Cédula de dividendos y participaciones",
                lineas=[
                    Linea(clave="div_sub1", concepto="Dividendos no gravados (subcédula 1)", valor=sub1, norma="Art. 242 ET (Ley 2010 de 2019)", campos=["dividendos.no_gravados_subcedula1"]),
                    Linea(clave="div_sub2", concepto="Dividendos gravados (subcédula 2)", valor=sub2, campos=["dividendos.gravados_subcedula2"]),
                    Linea(clave="imp_sub2", concepto=f"Impuesto del {rd['tarifa_subcedula_gravada']:.0%} sobre dividendos gravados", valor=impuesto_sub2, norma="Art. 240 ET"),
                    Linea(clave="imp_div_tabla", concepto="Impuesto de dividendos (10 % sobre lo que pase de 300 UVT)", valor=impuesto_tabla, norma="Art. 242 ET"),
                ],
            )
        )
        return {"ingresos": sub1 + sub2, "base_241": 0, "impuesto_sub2": impuesto_sub2 + impuesto_tabla, "descuento": 0}

    # ---------- Ganancias ocasionales ----------
    def ganancias_ocasionales(self) -> dict[str, float]:
        g, rg = self.d.ganancias_ocasionales, self.r["ganancias_ocasionales"]
        exencion_casa = self.u(rg["exencion_venta_casa_habitacion_uvt"]) if g.cumple_requisitos_exencion_casa else 0
        partes = [
            ("Venta de casa o apartamento de habitación", g.utilidad_venta_casa_habitacion, min(g.utilidad_venta_casa_habitacion, exencion_casa), "Art. 311-1 ET"),
            ("Venta de otros activos poseídos 2 años o más", g.utilidad_venta_otros_activos, 0, "Art. 300 ET"),
            ("Herencia: vivienda del causante", g.herencia_vivienda_causante, min(g.herencia_vivienda_causante, self.u(rg["exencion_herencia_vivienda_causante_uvt"])), "Num. 1 art. 307 ET"),
            ("Herencia: otros inmuebles", g.herencia_otros_inmuebles, min(g.herencia_otros_inmuebles, self.u(rg["exencion_herencia_otros_inmuebles_uvt"])), "Num. 2 art. 307 ET"),
            ("Herencia o legado recibido como heredero", g.herencia_porcion_heredero, min(g.herencia_porcion_heredero, self.u(rg["exencion_herencia_porcion_heredero_uvt"])), "Num. 3 art. 307 ET"),
            ("Donaciones recibidas", g.donaciones_recibidas, min(g.donaciones_recibidas * rg["exencion_donaciones_pct"], self.u(rg["exencion_donaciones_tope_uvt"])), "Num. 4 art. 307 ET"),
            ("Indemnizaciones de seguros de vida", g.seguros_vida, min(g.seguros_vida, self.u(rg["exencion_seguros_vida_uvt"])), "Art. 303-1 ET"),
        ]
        bruto = sum(p[1] for p in partes) + g.loterias_premios
        if bruto <= 0:
            return {"ingresos": 0, "impuesto": 0}
        exentas = sum(p[2] for p in partes)
        gravable_general = sum(p[1] - p[2] for p in partes)
        impuesto = gravable_general * rg["tarifa_general"] + g.loterias_premios * rg["tarifa_loterias"]
        lineas = [Linea(clave=f"go_{i}", concepto=p[0], valor=p[1], norma=p[3]) for i, p in enumerate(partes) if p[1]]
        if g.loterias_premios:
            lineas.append(Linea(clave="go_loterias", concepto="Loterías, rifas y premios (tarifa 20 %)", valor=g.loterias_premios, norma="Art. 317 ET"))
        lineas += [
            Linea(clave="go_exentas", concepto="Ganancias ocasionales exentas", valor=exentas),
            Linea(clave="go_gravables", concepto="Ganancias ocasionales gravables", valor=gravable_general + g.loterias_premios),
            Linea(clave="go_impuesto", concepto="Impuesto de ganancias ocasionales", valor=impuesto, norma="Arts. 314 y 317 ET"),
        ]
        self.secciones.append(Seccion(id="ganancias_ocasionales", titulo="Ganancias ocasionales", lineas=lineas))
        if g.utilidad_venta_casa_habitacion and not g.cumple_requisitos_exencion_casa:
            self.alertas.append(
                Alerta(
                    nivel="advertencia",
                    titulo="Venta de vivienda sin exención",
                    detalle="Para que las primeras 5.000 UVT de la utilidad queden exentas, el dinero debe ir a una cuenta AFC, a otra vivienda o al crédito hipotecario.",
                )
            )
        return {"ingresos": bruto, "impuesto": impuesto}

    # ---------- Ejecución ----------
    def ejecutar(self) -> dict[str, Any]:
        cg = self.cedula_general()
        pen = self.cedula_pensiones()
        div = self.cedula_dividendos()
        go = self.ganancias_ocasionales()

        rlg_total = cg["rlg"] + pen["rlg"] + div["base_241"]
        impuesto_241 = impuesto_tabla_241(rlg_total, self.uvt, self.r["tabla_renta_art241"])
        impuesto_renta = impuesto_241 + div["impuesto_sub2"]
        descuentos = min(div["descuento"], impuesto_241)  # art. 259 ET
        impuesto_neto = max(impuesto_renta - descuentos, 0)
        return {
            "cg": cg,
            "pen": pen,
            "div": div,
            "go": go,
            "rlg_total": rlg_total,
            "impuesto_241": impuesto_241,
            "impuesto_renta": impuesto_renta,
            "descuentos": descuentos,
            "impuesto_neto": impuesto_neto,
        }


def _obligacion(d: DatosDeclaracion, r: dict[str, Any], ingresos_totales: float, patrimonio_bruto: float) -> Obligacion:
    uvt = float(r["uvt"])
    t = r["topes_obligacion_uvt"]
    ind = d.indicadores
    ingresos = max(ingresos_totales, ind.ingresos_reportados_exogena)
    patrimonio = max(patrimonio_bruto, ind.patrimonio_reportado_exogena)
    filas = [
        ("Patrimonio bruto a 31 de diciembre", patrimonio, t["patrimonio_bruto"] * uvt),
        ("Ingresos brutos del año", ingresos, t["ingresos_brutos"] * uvt),
        ("Consumos con tarjeta de crédito", ind.consumos_tarjeta_credito, t["consumos_tarjeta_credito"] * uvt),
        ("Compras y consumos totales", ind.compras_consumos, t["compras_consumos"] * uvt),
        ("Consignaciones, depósitos e inversiones", ind.consignaciones_depositos_inversiones, t["consignaciones_depositos_inversiones"] * uvt),
    ]
    topes = []
    razones = []
    for nombre, valor, limite in filas:
        # Patrimonio: "superior a"; ingresos y demás: "iguales o superiores a"
        supera = valor > limite if nombre.startswith("Patrimonio") else valor >= limite
        topes.append(TopeObligacion(tope=nombre, valor=valor, limite=limite, supera=supera))
        if supera:
            razones.append(f"{nombre}: {cop(valor)} supera el tope de {cop(limite)}")
    if ind.responsable_iva:
        razones.append("Eres responsable de IVA")
    return Obligacion(obligado=bool(razones), razones=razones, topes=topes)


def _vencimiento(d: DatosDeclaracion, r: dict[str, Any]) -> Vencimiento | None:
    digitos = d.control.ultimos_dos_digitos_nit
    calendario = r.get("vencimientos") or {}
    if not digitos or not calendario:
        return None
    n = int(digitos)
    n = 100 if n == 0 else n
    clave = next((k for k in calendario if int(k[:2]) <= n <= (100 if k[3:] == "00" else int(k[3:]))), None)
    if clave is None:
        return None
    fecha = date.fromisoformat(calendario[clave])
    presentacion = d.control.fecha_presentacion or date.today()
    meses = _meses_o_fraccion(fecha, presentacion)
    return Vencimiento(fecha=fecha, fecha_presentacion=presentacion, extemporanea=meses > 0, meses_retraso=meses)


def liquidar(d: DatosDeclaracion, r: dict[str, Any] | None = None) -> Liquidacion:
    r = r or repo_reglas.cargar(d.anio_gravable)
    uvt = float(r["uvt"])
    redondeo = int(r.get("redondeo_pesos", 1000))

    # Independientes: elegir costos o renta exenta del 25 %, lo que resulte más favorable
    opcion = d.independiente.opcion
    if d.independiente.honorarios_y_servicios <= 0:
        opcion = "renta_exenta_25"
    if opcion == "auto":
        a = _Calculo(d, r, "costos")
        b = _Calculo(d, r, "renta_exenta_25")
        ra, rb = a.ejecutar(), b.ejecutar()
        calc, res = (a, ra) if ra["impuesto_neto"] < rb["impuesto_neto"] else (b, rb)
        opcion_elegida = calc.opcion_ind
        calc.alertas.append(
            Alerta(
                nivel="info",
                titulo="Elegimos la opción más favorable para tus honorarios",
                detalle=(
                    "Restar tus costos y gastos" if opcion_elegida == "costos" else "Tomar la renta exenta del 25 %"
                )
                + " te deja un impuesto menor. La ley no permite usar ambas a la vez.",
            )
        )
    else:
        calc = _Calculo(d, r, opcion)
        res = calc.ejecutar()
        opcion_elegida = opcion if d.independiente.honorarios_y_servicios > 0 else None

    # Patrimonio
    bruto = sum(b.valor for b in d.patrimonio.bienes)
    deudas = sum(x.valor for x in d.patrimonio.deudas)
    liquido = max(bruto - deudas, 0)
    calc.secciones.insert(
        0,
        Seccion(
            id="patrimonio",
            titulo="Patrimonio",
            lineas=[
                Linea(clave="patrimonio_bruto", concepto="Patrimonio bruto", valor=bruto, norma="Art. 261 ET", campos=["patrimonio.bienes"]),
                Linea(clave="deudas", concepto="Deudas", valor=deudas, norma="Art. 283 ET", campos=["patrimonio.deudas"]),
                Linea(clave="patrimonio_liquido", concepto="Patrimonio líquido", valor=liquido),
            ],
        ),
    )

    ingresos_totales = res["cg"]["ingresos"] + res["pen"]["ingresos"] + res["div"]["ingresos"] + res["go"]["ingresos"]
    obligacion = _obligacion(d, r, ingresos_totales, bruto)

    # Anticipo del año siguiente (art. 807 ET)
    pagos, ra = d.pagos, r["anticipo"]
    if pagos.declaraciones_previas == 0:
        pct = ra["pct_primera_declaracion"]
    elif pagos.declaraciones_previas == 1:
        pct = ra["pct_segunda_declaracion"]
    else:
        pct = ra["pct_siguientes"]
    impuesto_neto = res["impuesto_neto"]
    proc1 = impuesto_neto * pct - pagos.retenciones_renta
    opciones = [proc1]
    if pagos.declaraciones_previas >= 1 and pagos.impuesto_neto_anio_anterior > 0:
        opciones.append((impuesto_neto + pagos.impuesto_neto_anio_anterior) / 2 * pct - pagos.retenciones_renta)
    anticipo = max(min(opciones), 0)

    total_cargo = impuesto_neto + res["go"]["impuesto"]
    saldo_sin_sancion = total_cargo + anticipo - pagos.anticipo_anio_anterior - pagos.saldo_favor_anterior - pagos.retenciones_renta
    favor_sin_sancion = max(-saldo_sin_sancion, 0)

    # Sanción por extemporaneidad (art. 641 ET)
    venc = _vencimiento(d, r)
    sancion = 0.0
    rs = r["sanciones"]
    if venc and venc.extemporanea:
        uvt_pres = repo_reglas.uvt_del_anio(venc.fecha_presentacion.year) or float(r.get("uvt_anio_presentacion") or uvt)
        if total_cargo > 0:
            plena = min(total_cargo * rs["extemporaneidad_pct_mes_impuesto"] * venc.meses_retraso, total_cargo * rs["extemporaneidad_tope_pct_impuesto"])
        else:
            tope = min(
                ingresos_totales * rs["extemporaneidad_tope_pct_ingresos"],
                2 * favor_sin_sancion if favor_sin_sancion > 0 else rs["extemporaneidad_tope_uvt_sin_saldo_favor"] * uvt_pres,
            )
            plena = min(ingresos_totales * rs["extemporaneidad_pct_mes_ingresos_sin_impuesto"] * venc.meses_retraso, tope)
        minima = rs["sancion_minima_uvt"] * uvt_pres
        plena = max(plena, minima)
        sancion = max(plena * rs["reduccion_art640_pct"], minima) if d.control.sin_sanciones_ultimos_2_anios else plena
        sancion = _redondear(sancion, redondeo)
        calc.alertas.append(
            Alerta(
                nivel="critica",
                titulo="La declaración ya está vencida",
                detalle=(
                    f"Tu plazo era el {venc.fecha.strftime('%d/%m/%Y')}. Con {venc.meses_retraso} mes(es) o fracción de retraso, "
                    f"la sanción estimada es de {cop(sancion)}"
                    + (" (ya reducida al 50 % por el art. 640, si no te han sancionado por lo mismo en los últimos 2 años)" if d.control.sin_sanciones_ultimos_2_anios else "")
                    + ". Entre más pronto declares, menor es."
                ),
            )
        )

    # Como en el formulario 210, la sanción se suma antes de determinar el saldo
    saldo = saldo_sin_sancion + sancion
    saldo_pagar, saldo_favor = (saldo, 0.0) if saldo > 0 else (0.0, -saldo)

    calc.secciones.append(
        Seccion(
            id="liquidacion",
            titulo="Liquidación del impuesto",
            lineas=[
                Linea(clave="rlg_total", concepto="Renta líquida gravable (general + pensiones + dividendos)", valor=res["rlg_total"], norma="Art. 331 ET"),
                Linea(clave="impuesto_241", concepto="Impuesto según la tabla del art. 241", valor=res["impuesto_241"], norma="Art. 241 ET", nota=f"{res['rlg_total'] / uvt:,.0f} UVT".replace(",", ".")),
                Linea(clave="impuesto_renta", concepto="Impuesto sobre la renta", valor=res["impuesto_renta"]),
                Linea(clave="descuentos", concepto="Descuentos tributarios", valor=res["descuentos"], norma="Arts. 254-1 y 259 ET"),
                Linea(clave="impuesto_neto", concepto="Impuesto neto de renta", valor=impuesto_neto),
                Linea(clave="impuesto_go", concepto="Impuesto de ganancias ocasionales", valor=res["go"]["impuesto"]),
                Linea(clave="total_cargo", concepto="Total impuesto a cargo", valor=total_cargo),
                Linea(clave="anticipo_sig", concepto=f"Anticipo del año siguiente ({pct:.0%})", valor=anticipo, norma="Art. 807 ET", campos=["pagos.declaraciones_previas", "pagos.impuesto_neto_anio_anterior"]),
                Linea(clave="anticipo_ant", concepto="Menos: anticipo liquidado el año anterior", valor=pagos.anticipo_anio_anterior, campos=["pagos.anticipo_anio_anterior"]),
                Linea(clave="saldo_favor_ant", concepto="Menos: saldo a favor del año anterior", valor=pagos.saldo_favor_anterior, campos=["pagos.saldo_favor_anterior"]),
                Linea(clave="retenciones", concepto="Menos: retenciones en la fuente", valor=pagos.retenciones_renta, campos=["pagos.retenciones_renta"]),
                Linea(clave="sancion", concepto="Más: sanción por extemporaneidad (estimada)", valor=sancion, norma="Arts. 639, 640 y 641 ET"),
                Linea(clave="saldo_pagar", concepto="Saldo a pagar", valor=saldo_pagar),
                Linea(clave="saldo_favor", concepto="Saldo a favor", valor=saldo_favor),
            ],
        )
    )

    # Redondeo DIAN a miles en todo lo que se muestra
    for s in calc.secciones:
        for ln in s.lineas:
            ln.valor = _redondear(ln.valor, redondeo)

    resumen = Resumen(
        patrimonio_bruto=_redondear(bruto, redondeo),
        deudas=_redondear(deudas, redondeo),
        patrimonio_liquido=_redondear(liquido, redondeo),
        ingresos_brutos_totales=_redondear(ingresos_totales, redondeo),
        renta_liquida_gravable=_redondear(res["rlg_total"], redondeo),
        impuesto_renta=_redondear(res["impuesto_renta"], redondeo),
        descuentos=_redondear(res["descuentos"], redondeo),
        impuesto_neto_renta=_redondear(impuesto_neto, redondeo),
        impuesto_ganancias_ocasionales=_redondear(res["go"]["impuesto"], redondeo),
        total_impuesto_cargo=_redondear(total_cargo, redondeo),
        anticipo_siguiente=_redondear(anticipo, redondeo),
        anticipo_anterior=_redondear(pagos.anticipo_anio_anterior, redondeo),
        saldo_favor_anterior=_redondear(pagos.saldo_favor_anterior, redondeo),
        retenciones=_redondear(pagos.retenciones_renta, redondeo),
        saldo_pagar=_redondear(saldo_pagar, redondeo),
        saldo_favor=_redondear(saldo_favor, redondeo),
        sancion=sancion,
        total_a_pagar=_redondear(saldo_pagar, redondeo),
    )

    if not obligacion.obligado:
        calc.alertas.insert(
            0,
            Alerta(
                nivel="info",
                titulo="Según los topes, no estás obligado a declarar",
                detalle="Puedes declarar de forma voluntaria (por ejemplo, para pedir la devolución de un saldo a favor).",
            ),
        )

    return Liquidacion(
        anio_gravable=d.anio_gravable,
        uvt=uvt,
        obligacion=obligacion,
        resumen=resumen,
        secciones=calc.secciones,
        alertas=calc.alertas,
        vencimiento=venc,
        opcion_independiente=opcion_elegida,
    )
