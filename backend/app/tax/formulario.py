"""Formulario 210 casilla por casilla (años gravables 2023 y siguientes).

Numeración y fórmulas del formulario prescrito por la Resolución DIAN 000044 de 2024
(instructivo modificado por la Resolución 000120 de 2024), que también se usa para el año
gravable 2025. Cada valor se aproxima al múltiplo de mil más cercano y las casillas que el
servicio de la DIAN calcula solo se recalculan aquí con las mismas fórmulas, a partir de las
casillas ya aproximadas, para que lo que la persona copia cuadre con lo que MUISCA calcula.

Las cifras salen del motor tributario: aquí no hay reglas nuevas, solo la ubicación de cada
valor en su casilla. Para 2021 y 2022 el formulario tenía otra numeración y no se arma.
"""

from __future__ import annotations

import math
from typing import Any

from app.tax.modelos import (
    Casilla,
    DatosDeclaracion,
    Formulario,
    SeccionFormulario,
    TipoCasilla,
)


def _r(v: float) -> float:
    """Aproximación de la DIAN al múltiplo de mil más cercano; nunca negativo."""
    v = max(v, 0)
    return float(math.floor(v / 1000 + 0.5) * 1000)


def disponible(anio: int) -> bool:
    return anio >= 2023


def armar(d: DatosDeclaracion, r: dict[str, Any], v: dict[str, Any], liq: dict[str, float], impuesto_241) -> Formulario:
    """v: cifras intermedias del motor (calc.valores); liq: patrimonio, anticipo, sanción y pagos ya calculados."""
    anio = d.anio_gravable
    if not disponible(anio):
        return Formulario(
            anio_gravable=anio, disponible=False,
            motivo=f"Para el año gravable {anio} la DIAN usó un formulario 210 con otra numeración. La vista casilla por casilla está para 2023, 2024 y 2025; "
                   "el borrador por secciones sí sirve para ese año.",
        )
    c: dict[int, float] = {}
    cas: dict[int, Casilla] = {}

    def poner(n: int, nombre: str, valor: float, tipo: TipoCasilla = "dato", formula: str | None = None, campos: list[str] | None = None,
              nota: str | None = None, texto: str | None = None) -> None:
        c[n] = valor if texto is not None else _r(valor)
        cas[n] = Casilla(numero=n, nombre=nombre, valor=c[n], tipo=tipo, formula=formula, campos=campos or [], nota=nota, texto=texto)

    def pos(x: float) -> float:
        return max(x, 0)

    cg = v["cg"]
    sub, lim = cg["sub"], cg["limitadas"]
    t, n43, cap, nl = cg["trab"], cg["43"], cg["cap"], cg["nl"]
    pen = v.get("pen", {"ingresos": 0, "incr": 0, "exenta": 0})
    div = v.get("div", {"sub1": 0, "sub2": 0, "impuesto_sub2": 0})
    go = v.get("go", {"ingresos": 0, "exentas": 0, "impuesto": 0})
    lq = v["liq"]

    # ---- Datos del declarante ----
    poner(28, "Uno por ciento (1%) de compras con factura electrónica", cg["factura"], "dato", campos=["deducciones.compras_factura_electronica"],
          nota="En línea, MUISCA pregunta por tus compras con factura electrónica pagadas con tarjeta o transferencia (casilla 299) y calcula el 1 %, con máximo 240 UVT.")

    # ---- Patrimonio ----
    poner(29, "Total patrimonio bruto", liq["patrimonio_bruto"], campos=["patrimonio.bienes"])
    poner(30, "Deudas", liq["deudas"], campos=["patrimonio.deudas"])
    poner(31, "Total patrimonio líquido", pos(c[29] - c[30]), "calculada", "29 - 30")

    def subcedula(k: str, base: int, nombre: str) -> None:
        """Casillas de exentas y deducciones de una subcédula, en el orden del formulario."""
        s = sub[k]
        n_exe1, n_exe2, n_totexe, n_viv, n_otras, n_totded, n_lim = base, base + 1, base + 2, base + 3, base + 4, base + 5, base + 6
        poner(n_exe1, f"Rentas exentas de {nombre} – Aportes voluntarios AFC, FVP y/o AVC", s["afc"], campos=["deducciones.aportes_voluntarios_afc_fpv"])
        poner(n_exe2, f"Rentas exentas de {nombre} – Otras rentas exentas", s["otras_exentas"],
              campos=["laboral.cesantias_e_intereses", "laboral.salario_promedio_mensual_6m"] if k == "trab" else [],
              nota="El 25 % exento de los pagos laborales y las cesantías exentas." if k == "trab" and s["otras_exentas"] else None)
        poner(n_totexe, f"Total rentas exentas de {nombre}", c[n_exe1] + c[n_exe2], "calculada", f"{n_exe1} + {n_exe2}")
        poner(n_viv, f"Deducciones imputables a {nombre} – Intereses de vivienda", s["intereses"], campos=["deducciones.intereses_vivienda"])
        poner(n_otras, f"Deducciones imputables a {nombre} – Otras deducciones imputables", s["otras_deducciones"],
              campos=["deducciones.dependientes", "deducciones.medicina_prepagada", "deducciones.gmf_pagado", "deducciones.intereses_icetex"],
              nota="Dependiente (10 % de tus ingresos de trabajo), medicina prepagada, 50 % del 4x1000 y los intereses del ICETEX, según lo que tengas." if s["otras_deducciones"] else None)
        poner(n_totded, f"Total deducciones imputables a {nombre}", c[n_viv] + c[n_otras], "calculada", f"{n_viv} + {n_otras}")
        poner(n_lim, f"Rentas exentas y/o deducciones imputables a {nombre} (Limitadas)", lim[k], "calculada",
              nota="La DIAN la calcula: tus exentas y deducciones hasta el 40 % de tus ingresos netos, con máximo "
                   f"{r['cedula_general']['limite_rentas_exentas_deducciones_uvt']:,} UVT, repartido primero a las rentas de trabajo.".replace(",", "."))

    # ---- Rentas de trabajo (32-42) ----
    poner(32, "Ingresos brutos de las Rentas de trabajo", t["ingresos"],
          campos=["laboral.salarios_y_pagos_laborales", "laboral.cesantias_e_intereses"] + (["independiente.honorarios_y_servicios"] if not n43["ingresos"] else []))
    poner(33, "Ingresos no constitutivos de renta de las Rentas de trabajo", t["incr"],
          campos=["laboral.aportes_obligatorios_pension", "laboral.aportes_obligatorios_salud", "laboral.aportes_voluntarios_rais",
                  "independiente.aportes_obligatorios_pension", "independiente.aportes_obligatorios_salud"],
          nota="Tus aportes obligatorios a salud y pensión (y los voluntarios al fondo obligatorio).")
    poner(34, "Renta líquida de las Rentas de trabajo", pos(c[32] - c[33]), "calculada", "32 - 33")
    subcedula("trab", 35, "las Rentas de trabajo")
    poner(42, "Renta líquida ordinaria de las Rentas de trabajo", pos(c[34] - c[41]), "calculada", "34 - 41")

    # ---- Rentas de trabajo que no provengan de una relación laboral (43-57) ----
    nombre43 = "las Rentas de trabajo que no provengan de una relación laboral"
    poner(43, "Ingresos brutos de las Rentas de trabajo que no provengan de una relación laboral o legal y reglamentaria", n43["ingresos"],
          campos=["independiente.honorarios_y_servicios"], nota="Honorarios por los que restas costos (si no, van en la casilla 32 con el 25 % exento)." if n43["ingresos"] else None)
    poner(44, "Ingresos no constitutivos de renta de " + nombre43, n43["incr"], campos=["independiente.aportes_obligatorios_pension", "independiente.aportes_obligatorios_salud"])
    poner(45, "Costos y deducciones procedentes de " + nombre43, n43["costos"], campos=["independiente.costos_gastos_procedentes"])
    poner(46, "Renta líquida de " + nombre43, pos(c[43] - c[44] - c[45]), "calculada", "43 - 44 - 45")
    subcedula("43", 47, nombre43)
    poner(54, "Renta líquida ordinaria del ejercicio de " + nombre43, pos(c[46] - c[53]), "calculada", "46 - 53")
    poner(55, "Pérdida líquida ordinaria del ejercicio de " + nombre43, pos(c[44] + c[45] - c[43]), "calculada", "44 + 45 - 43")
    poner(56, "Compensaciones por pérdidas de " + nombre43, 0)
    poner(57, "Renta líquida ordinaria de " + nombre43, pos(c[54] - c[56]), "calculada", "54 - 56")

    # ---- Rentas de capital (58-73) ----
    poner(58, "Ingresos brutos de las Rentas de capital", cap["ingresos"], campos=["capital.rendimientos_financieros", "capital.arrendamientos", "capital.regalias_y_otros"])
    poner(59, "Ingresos no constitutivos de renta de las Rentas de capital", cap["incr"], campos=["capital.rendimientos_financieros"],
          nota=f"El componente inflacionario de tus rendimientos financieros ({r['cedula_general']['componente_inflacionario_rendimientos_pct'] * 100:.2f} % en {anio}).".replace(".", ",")
          if cap["incr"] else None)
    poner(60, "Costos y deducciones procedentes de las Rentas de capital", cap["costos"], campos=["capital.costos_gastos_procedentes"])
    poner(61, "Renta líquida de las Rentas de capital", pos(c[58] - c[59] - c[60]), "calculada", "58 - 59 - 60")
    poner(62, "Rentas líquidas pasivas – ECE de las Rentas de capital", 0)
    subcedula("cap", 63, "las Rentas de capital")
    poner(70, "Renta líquida ordinaria del ejercicio de las Rentas de capital", pos(c[61] + c[62] - c[69]), "calculada", "61 + 62 - 69")
    poner(71, "Pérdida líquida del ejercicio de las Rentas de capital", pos(c[59] + c[60] - c[58]), "calculada", "59 + 60 - 58")
    poner(72, "Compensaciones por pérdidas de las Rentas de capital", 0)
    poner(73, "Renta líquida ordinaria de las Rentas de capital", pos(c[70] - c[72]), "calculada", "70 - 72")

    # ---- Rentas no laborales (74-90) ----
    poner(74, "Ingresos brutos de las Rentas no laborales", nl["ingresos"], campos=["no_laborales.ingresos"])
    poner(75, "Devoluciones, rebajas y descuentos de las Rentas no laborales", 0)
    poner(76, "Ingresos no constitutivos de renta de las Rentas no laborales", nl["incr"], campos=["no_laborales.ingresos_no_constitutivos"])
    poner(77, "Costos y deducciones procedentes de las Rentas no laborales", nl["costos"], campos=["no_laborales.costos_gastos_procedentes"])
    poner(78, "Renta líquida de las Rentas no laborales", pos(c[74] - c[75] - c[76] - c[77]), "calculada", "74 - 75 - 76 - 77")
    poner(79, "Rentas líquidas pasivas – ECE de las Rentas no laborales", 0)
    subcedula("nl", 80, "las Rentas no laborales")
    poner(87, "Renta líquida ordinaria del ejercicio de las Rentas no laborales", pos(c[78] + c[79] - c[86]), "calculada", "78 + 79 - 86")
    poner(88, "Pérdida líquida del ejercicio de las Rentas no laborales", pos(c[75] + c[76] + c[77] - c[74]), "calculada", "75 + 76 + 77 - 74")
    poner(89, "Compensaciones por pérdidas de las Rentas no laborales", 0)
    poner(90, "Renta líquida ordinaria de las Rentas no laborales", pos(c[87] - c[89]), "calculada", "87 - 89")

    # ---- Renta líquida de la cédula general (91-98) ----
    poner(91, "Renta líquida cédula general", (c[41] + c[42]) + (c[53] + c[57]) + (c[69] + c[73]) + (c[86] + c[90]), "calculada",
          "(41 + 42) + (53 + 57) + (69 + 73) + (86 + 90)")
    poner(138, "Número de dependientes económicos", cg["n_dependientes"], "informativa", texto=str(cg["n_dependientes"]), campos=["deducciones.dependientes"])
    poner(139, "Adición por dependientes a la casilla 92", cg["dep_72"], "dato", campos=["deducciones.dependientes"],
          nota=f"{r['cedula_general']['dependiente_adicional_uvt']} UVT por dependiente, hasta 4, por fuera del límite del 40 %." if cg["dep_72"] else None)
    poner(92, "Rentas exentas y deducciones imputables (Limitadas)", c[28] + c[41] + c[53] + c[69] + c[86] + c[139], "calculada", "28 + 41 + 53 + 69 + 86 + 139")
    poner(93, "Renta líquida ordinaria cédula general", pos(c[91] - c[92]), "calculada", "91 - 92")
    poner(94, "Compensaciones por pérdidas año gravable 2018 y anteriores", 0)
    poner(95, "Compensaciones por exceso de renta presuntiva", 0)
    poner(96, "Rentas gravables", 0, nota="Activos omitidos, pasivos inexistentes o renta por comparación patrimonial, si la DIAN los determina.")
    poner(97, "Renta líquida gravable cédula general", pos(c[93] + c[96] - c[94] - c[95]), "calculada", "93 + 96 - 94 - 95")
    poner(98, "Renta presuntiva", 0, nota="Es del 0 % desde el año gravable 2021.")

    # ---- Cédula de pensiones (99-103) ----
    poner(99, "Ingresos brutos por rentas de pensiones del país y del exterior", pen["ingresos"], campos=["pensiones.pensiones_nacionales"])
    poner(100, "Ingresos no constitutivos de renta de pensiones", pen["incr"], campos=["pensiones.aportes_salud"])
    poner(101, "Renta líquida de pensiones", pos(c[99] - c[100]), "calculada", "99 - 100")
    poner(102, "Rentas exentas de pensiones", min(pen["exenta"], c[101]), nota="Hasta 1.000 UVT al mes." if pen["exenta"] else None)
    poner(103, "Renta líquida gravable cédula de pensiones", pos(c[101] - c[102]), "calculada", "101 - 102")

    # ---- Cédula de dividendos y participaciones (104-111) ----
    poner(104, "Dividendos y participaciones 2016 y anteriores, y otros", 0)
    poner(105, "Ingresos no constitutivos de renta de dividendos", 0)
    poner(106, "Renta líquida ordinaria año 2016 y anteriores", pos(c[104] - c[105]), "calculada", "104 - 105")
    poner(107, "1a. Subcédula año 2017 y siguientes (num. 3 art. 49 ET)", div["sub1"], campos=["dividendos.no_gravados_subcedula1"])
    poner(108, "2a. Subcédula año 2017 y siguientes (par. 2 art. 49 ET)", div["sub2"], campos=["dividendos.gravados_subcedula2"])
    poner(109, "Renta líquida pasiva dividendos – ECE y/o recibidos del exterior", 0)
    poner(110, "Rentas exentas de la casilla 109", 0)
    tarifa_240 = r["dividendos"].get("tarifa_subcedula_gravada", 0.35)
    poner(118, "Por dividendos y participaciones año 2017 y siguientes, 2a. subcédula (Art. 240 ET)", c[108] * tarifa_240, "calculada", f"108 × {tarifa_240:.0%}")
    poner(111, "Renta líquida gravable (Cédula general o Renta presuntiva, de pensiones y de dividendos y participaciones art. 241 ET)",
          max(c[97], c[98]) + c[103] + c[107] + c[108] - c[118], "calculada", "97 (o 98) + 103 + 107 + 108 - 118")

    # ---- Ganancias ocasionales (112-115) ----
    poner(112, "Ingresos por ganancias ocasionales del país y del exterior", go["ingresos"],
          campos=["ganancias_ocasionales.utilidad_venta_casa_habitacion", "ganancias_ocasionales.utilidad_venta_otros_activos", "ganancias_ocasionales.herencia_porcion_heredero",
                  "ganancias_ocasionales.herencia_vivienda_causante", "ganancias_ocasionales.herencia_otros_inmuebles", "ganancias_ocasionales.donaciones_recibidas",
                  "ganancias_ocasionales.seguros_vida", "ganancias_ocasionales.loterias_premios"],
          nota="Si vendiste un bien, aquí va la utilidad; en MUISCA también puedes poner el precio de venta aquí y lo que te costó en la casilla 113: el resultado es el mismo." if go["ingresos"] else None)
    poner(113, "Costos por ganancias ocasionales", 0)
    poner(114, "Ganancias ocasionales no gravadas y exentas", min(go["exentas"], c[112]))
    poner(115, "Ganancias ocasionales gravables", pos(c[112] - c[113] - c[114]), "calculada", "112 - 113 - 114")

    # ---- Liquidación privada (116-137) ----
    poner(116, "Impuesto sobre la renta: cédula general, de pensiones y de dividendos y participaciones (base casilla 111)",
          impuesto_241(c[111]), "calculada", "Tabla del art. 241 sobre la casilla 111")
    poner(117, "Impuesto sobre la renta presuntiva, de pensiones y de dividendos y participaciones", 0, "calculada")
    poner(119, "Por dividendos y participaciones año 2016 (base casilla 106)", 0, "calculada")
    poner(120, "Por dividendos y participaciones recibidas del exterior", 0, "calculada")
    poner(121, "Total impuesto sobre las rentas líquidas gravables", c[116] + c[117] + c[118] + c[119] + c[120], "calculada", "116 + 117 + 118 + 119 + 120")
    poner(122, "Descuentos: impuestos pagados en el exterior", 0)
    poner(123, "Descuentos: donaciones", lq["desc_donaciones"], campos=["descuentos.donaciones", "descuentos.donaciones_alimentos"],
          nota="El 25 % de lo donado a entidades sin ánimo de lucro (37 % si fueron alimentos a bancos de alimentos), con máximo el 25 % del impuesto." if lq["desc_donaciones"] else None)
    desc_div = lq["desc_div"]
    poner(124, "Descuentos: dividendos, participaciones y otros", desc_div, campos=["dividendos.no_gravados_subcedula1", "dividendos.gravados_subcedula2"],
          nota="El 19 % de los dividendos que pasan de 1.090 UVT (art. 254-1 ET)." if desc_div else None)
    poner(125, "Total descuentos tributarios", min(c[122] + c[123] + c[124], c[121]), "calculada", "122 + 123 + 124")
    poner(126, "Impuesto neto de renta", pos(c[121] - c[125]), "calculada", "121 - 125")
    poner(127, "Impuesto de ganancias ocasionales", go["impuesto"], "calculada", "Tarifa sobre la casilla 115")
    poner(128, "Descuento por impuestos pagados en el exterior por ganancias ocasionales", 0)
    poner(129, "Total impuesto a cargo", pos(c[126] + c[127] - c[128]), "calculada", "126 + 127 - 128")
    poner(130, "Anticipo renta liquidado año gravable anterior", d.pagos.anticipo_anio_anterior, campos=["pagos.anticipo_anio_anterior"],
          nota="Es la casilla «Anticipo renta para el año gravable siguiente» de tu declaración del año pasado.")
    poner(131, "Saldo a favor del año gravable anterior sin solicitud de devolución y/o compensación", d.pagos.saldo_favor_anterior, campos=["pagos.saldo_favor_anterior"])
    poner(132, "Retenciones año gravable a declarar", d.pagos.retenciones_renta, campos=["pagos.retenciones_renta"])
    poner(133, "Anticipo renta para el año gravable siguiente", liq["anticipo_de"](c[126], c[132]), "calculada", "Art. 807 ET",
          campos=["pagos.declaraciones_previas", "pagos.impuesto_neto_anio_anterior"])
    poner(134, "Saldo a pagar por impuesto", pos(c[129] + c[133] - c[130] - c[131] - c[132]), "calculada", "129 + 133 - 130 - 131 - 132")
    poner(135, "Sanciones", liq["sancion"], nota="Sanción por extemporaneidad, si presentas después de tu fecha límite." if liq["sancion"] else None)
    poner(136, "Total saldo a pagar", pos(c[129] + c[133] + c[135] - c[130] - c[131] - c[132]), "calculada", "129 + 133 + 135 - 130 - 131 - 132")
    poner(137, "Total saldo a favor", pos(c[130] + c[131] + c[132] - c[129] - c[133] - c[135]), "calculada", "130 + 131 + 132 - 129 - 133 - 135")
    poner(140, "Usted superó tope indicativo artículo 336-1 del E.T.", 0, "informativa", texto="No",
          nota="Solo aplica si restas costos como independiente y pasan el tope que fija la DIAN para tu actividad.")
    poner(141, "Aporte voluntario (art. 244-1 ET)", 0, "informativa", nota="Es opcional: un aporte adicional de quien quiera hacerlo.")

    def seccion(id_: str, titulo: str, numeros: list[int]) -> SeccionFormulario:
        return SeccionFormulario(id=id_, titulo=titulo, casillas=[cas[n] for n in numeros])

    secciones = [
        seccion("inicial", "Datos iniciales", [28]),
        seccion("patrimonio", "Patrimonio", [29, 30, 31]),
        seccion("trabajo", "Cédula general · Rentas de trabajo", list(range(32, 43))),
        seccion("trabajo_no_laboral", "Cédula general · Rentas de trabajo que no provengan de una relación laboral", list(range(43, 58))),
        seccion("capital", "Cédula general · Rentas de capital", list(range(58, 74))),
        seccion("no_laborales", "Cédula general · Rentas no laborales", list(range(74, 91))),
        seccion("cedula_general", "Renta líquida de la cédula general", list(range(91, 99))),
        seccion("pensiones", "Cédula de pensiones", list(range(99, 104))),
        seccion("dividendos", "Cédula de dividendos y participaciones", list(range(104, 112))),
        seccion("ganancias", "Ganancias ocasionales", list(range(112, 116))),
        seccion("impuesto", "Liquidación privada · Impuesto sobre las rentas líquidas gravables", [116, 117, 118, 119, 120, 121]),
        seccion("descuentos", "Liquidación privada · Descuentos e impuesto neto", [122, 123, 124, 125, 126, 127, 128, 129]),
        seccion("saldos", "Liquidación privada · Anticipos, retenciones y saldos", [130, 131, 132, 133, 134, 135, 136, 137]),
        seccion("informativos", "Datos informativos", [138, 139, 140, 141]),
    ]
    notas = [
        "Los valores van aproximados al múltiplo de mil más cercano, sin decimales ni signos negativos, como pide la DIAN.",
        "Las casillas marcadas «La calcula la DIAN» no se escriben: MUISCA las calcula sola. Revisa que te den lo mismo.",
        "En la versión para expertos de MUISCA se ven todas las casillas. Si la DIAN ya trae una declaración sugerida, compara cada casilla y corrige la que no coincida.",
    ]
    return Formulario(anio_gravable=anio, secciones=secciones, pago_total=c[136], notas=notas)
