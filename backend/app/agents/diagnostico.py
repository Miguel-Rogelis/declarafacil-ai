"""Diagnóstico del caso: qué se deduce de los datos y qué falta preguntar.

Lo usa el Asistente para:
- Decir qué entendió de la exógena apenas se sube: quién le reportó qué, su perfil, si
  está obligado y qué beneficios ya vienen incluidos.
- Decidir qué preguntar antes de calcular: solo lo que cambia el resultado o lo que la
  exógena no muestra (vehículos, ingresos que no pasan por un banco, ventas, herencias).
- Señalar cifras que no cuadran (consignaciones muy por encima de los ingresos).
- Armar la lista de documentos de SU caso a partir de las entidades que le reportaron.
Todo con reglas, sin IA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agents.conocimiento import norm, pesos

if TYPE_CHECKING:
    from app.agents.asistente import EstadoChat
    from app.orquestador import Respuestas
    from app.tax.modelos import Liquidacion


@dataclass
class Vacio:
    tema: str
    etiqueta: str  # para listar lo que falta ("si alguien depende de ti")
    pregunta: str
    fuente: str = ""  # de dónde sale el dato o el documento


# ---------- Lo que trae la exógena ----------


def exogena(e: EstadoChat) -> dict[str, float]:
    """Totales por campo de la declaración que vienen en la exógena."""
    if e.resumen_exogena:
        return dict(e.resumen_exogena)
    salida: dict[str, float] = {}
    for f in e.filas:
        if f.campo and f.tratamiento == "suma":
            salida[f.campo] = salida.get(f.campo, 0) + f.valor
    return salida


def _suma(ex: dict[str, float], *prefijos: str) -> float:
    return sum(v for k, v in ex.items() if k.startswith(prefijos))


def tope(e: EstadoChat, n: int) -> float:
    return next((v for k, v in e.topes.items() if norm(k).startswith(f"tope {n}")), 0.0)


_NO_ENTIDAD = re.compile(r"contribuyente|impuestos y aduanas|^\[")


def _rol(campo: str | None, detalle: str) -> str | None:
    d = norm(detalle)
    if not campo:
        return None
    if campo.startswith("pensiones"):
        return "pension"
    if campo.startswith("laboral.cesantias"):
        return "cesantias"
    if campo.startswith("laboral"):
        return "empleador"
    if campo.startswith("independiente"):
        return "contratante"
    if campo.startswith("dividendos"):
        return "dividendos"
    if campo.startswith("deducciones.medicina"):
        return "prepagada"
    if campo.startswith("deducciones.intereses_vivienda"):
        return "vivienda"
    if campo.startswith("deducciones.aportes_voluntarios"):
        return "voluntarios"
    if campo.startswith("patrimonio.deudas"):
        return "credito"
    if campo.startswith("patrimonio.bienes") and "avaluo" in d:
        return "inmueble"
    if campo.startswith("patrimonio.bienes") and "parafiscal" in d:
        return None
    if campo.startswith(("patrimonio.bienes", "capital.rendimientos")):
        return "banco"
    if campo.startswith("capital.arrendamientos"):
        return "arriendos"
    return None


def entidades(e: EstadoChat) -> dict[str, list[str]]:
    """Quién le reportó qué, agrupado por tipo (empleador, banco, crédito…)."""
    salida: dict[str, list[str]] = {}
    for f in e.filas:
        quien = (f.informante or "").strip()
        if not quien or _NO_ENTIDAD.search(norm(quien)) or f.tratamiento == "informativo":
            continue
        rol = _rol(f.campo, f.detalle)
        if rol and quien not in salida.setdefault(rol, []):
            salida[rol].append(quien)
    # Un crédito de vivienda ya se nombra como tal
    salida["credito"] = [x for x in salida.get("credito", []) if x not in salida.get("vivienda", [])]
    return {k: v for k, v in salida.items() if v}


def tiene_inmueble_en_exogena(e: EstadoChat) -> bool:
    return any("avaluo" in norm(f.detalle) for f in e.filas)


def perfil(e: EstadoChat, r: Respuestas) -> dict[str, bool]:
    p: dict[str, Any] = dict(e.perfil)
    p["empleado"] = bool(p.get("empleado") or r.salarios_no_reportados)
    p["independiente"] = bool(p.get("independiente") or r.honorarios_no_reportados)
    p["pensionado"] = bool(p.get("pensionado") or r.pensiones_no_reportadas)
    p["arrendador"] = bool(r.arriendos_no_reportados or exogena(e).get("capital.arrendamientos"))
    p["declaro_antes"] = bool(p.get("declaro_antes") or (r.declaraciones_previas or 0) > 0)
    return p


def _lista(cosas: list[str], y: str = "y") -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + f" {y} " + cosas[-1]


def _hay_ingresos(e: EstadoChat, r: Respuestas) -> bool:
    return bool(e.tiene_exogena or e.filas) or any(
        [r.salarios_no_reportados, r.honorarios_no_reportados, r.pensiones_no_reportadas, r.otros_ingresos_no_reportados,
         r.arriendos_no_reportados, r.dividendos_no_reportados]
    )


_VEHICULOS = ("carro", "moto", "vehiculo", "camioneta", "camion")


# ---------- Lo que falta ----------


def inconsistencias(e: EstadoChat, vp: Liquidacion | None) -> list[Vacio]:
    """Cifras de la exógena que no cuadran y que hay que aclarar antes de firmar."""
    if not e.tiene_exogena or not vp:
        return []
    salida = []
    ingresos = vp.resumen.ingresos_brutos_totales
    movimientos = tope(e, 4)
    if movimientos > max(ingresos * 1.5, ingresos + 20_000_000):
        salida.append(Vacio(
            "consignaciones", "de dónde salió la diferencia entre tus consignaciones y tus ingresos",
            f"Tus consignaciones y movimientos del año suman {pesos(movimientos)}, bastante más que tus ingresos ({pesos(ingresos)}). "
            "¿De dónde salió la diferencia? Si fue un préstamo, la venta de algo o plata que pasaste entre tus cuentas, no es ingreso; "
            "si te pagaron algo que no aparece, sí lo es.",
            "Tus extractos bancarios del año.",
        ))
    return salida


def vacios(e: EstadoChat, r: Respuestas, vp: Liquidacion | None) -> list[Vacio]:
    """Todo lo que falta y cambia el resultado, en orden de importancia (sin filtrar lo ya preguntado)."""
    anio = e.anio_gravable
    if not _hay_ingresos(e, r) and not r.bienes_adicionales:
        return [Vacio("ingresos", "tus ingresos del año",
                      f"¿Cuánto recibiste en {anio}? Por ejemplo, tu salario mensual o lo que te pagaron por honorarios en el año.",
                      "Si no los tienes claros, tu exógena de la DIAN los trae.")]
    ex = exogena(e) if e.tiene_exogena else {}
    con_exo = bool(e.tiene_exogena)
    impuesto = vp.resumen.impuesto_neto_renta if vp else 0
    sancion = vp.resumen.sancion if vp else 0
    p = perfil(e, r)
    trabajo = p["empleado"] or p["independiente"]
    salida: list[Vacio] = [*inconsistencias(e, vp)]

    def agregar(cond: Any, v: Vacio) -> None:
        if cond:
            salida.append(v)

    agregar(not con_exo and not r.retenciones_no_reportadas and (r.salarios_no_reportados + r.honorarios_no_reportados) > 0, Vacio(
        "retenciones", "cuánto te retuvieron en la fuente",
        f"¿Te hicieron retención en la fuente en {anio}? Si sí, ¿de cuánto fue en total? Sale en tu certificado de ingresos y retenciones.",
        "Certificado de ingresos y retenciones (formulario 220) de tu empleador, o el de quien te pagó.",
    ))
    agregar(impuesto > 0 and not r.dependientes and trabajo, Vacio(
        "dependientes", "si alguien depende económicamente de ti",
        "¿Alguien depende económicamente de ti, como hijos, tu pareja o tus papás?",
        "Registro civil de tus hijos y, si tienen entre 18 y 23 años, certificado de estudio.",
    ))
    falta = []
    if not (r.medicina_prepagada or ex.get("deducciones.medicina_prepagada")):
        falta.append("medicina prepagada")
    if not (r.intereses_vivienda or ex.get("deducciones.intereses_vivienda")):
        falta.append("intereses de un crédito de vivienda")
    if not (r.aportes_voluntarios_afc_fpv or _suma(ex, "deducciones.aportes_voluntarios")):
        falta.append("aportes voluntarios a pensión o AFC")
    ya_vienen = [x for x in ("medicina prepagada", "intereses de un crédito de vivienda", "aportes voluntarios a pensión o AFC") if x not in falta]
    agregar(impuesto > 0 and falta and trabajo, Vacio(
        "deducciones", "si pagas " + _lista(falta, "o"),
        f"¿Pagas {_lista(falta, 'o')}?" + (f" Lo de {_lista(ya_vienen)} ya viene en tu exógena." if con_exo and ya_vienen else ""),
        "Cada entidad te da un certificado de lo que pagaste en el año, en su portal o banca virtual.",
    ))
    honorarios = r.honorarios_no_reportados + _suma(ex, "independiente.honorarios")
    agregar(impuesto > 0 and honorarios and not r.costos_independiente, Vacio(
        "costos", "si tuviste costos de tu actividad como independiente",
        "Como independiente, ¿tuviste costos o gastos de tu actividad con factura a tu nombre? Si no, uso el 25 % exento, que suele convenir más.",
        "Las facturas electrónicas a tu nombre las ves en el portal de facturación de la DIAN.",
    ))
    vehiculo = any(any(v in norm(b.concepto) for v in _VEHICULOS) for b in r.bienes_adicionales)
    if con_exo:
        cosas = "carro o moto" if tiene_inmueble_en_exogena(e) else "carro, moto, casa o lote"
        agregar(not vehiculo and not r.bienes_adicionales, Vacio(
            "bienes", f"si tienes {cosas}",
            f"¿Tienes {cosas} a tu nombre? Tu exógena no los muestra y van en tu patrimonio. Si sí, dime cuánto pagaste.",
            "Vehículos: factura o contrato de compra. Inmuebles: recibo del impuesto predial (avalúo catastral).",
        ))
    else:
        agregar(not (r.bienes_adicionales or r.deudas_adicionales), Vacio(
            "patrimonio", f"qué tenías y cuánto debías al 31 de diciembre de {anio}",
            f"¿Qué tenías al 31 de diciembre de {anio} (plata en cuentas, casa, carro) y cuánto debías?",
            "Certificados de tus bancos (saldo a 31 de diciembre), predial de tus inmuebles y factura de compra de tus vehículos.",
        ))
    agregar(not r.ultimos_dos_digitos_nit, Vacio(
        "cedula", "en qué termina tu cédula", "¿En qué dos números termina tu cédula? Con eso sé tu fecha límite y si hay sanción.",
    ))
    if r.declaraciones_previas is None and p["declaro_antes"]:
        agregar(impuesto > 0, Vacio(
            "historial", "cuántas veces has declarado",
            "Veo en tu exógena que ya habías declarado. ¿Esta es tu segunda declaración o ya llevas más? Eso cambia el anticipo.",
            "Tus declaraciones anteriores están en MUISCA, en «Consultar declaraciones».",
        ))
    else:
        agregar(impuesto > 0 and r.declaraciones_previas is None, Vacio(
            "historial", "si es tu primera declaración", "¿Es la primera vez que declaras renta? Eso cambia el anticipo.",
        ))
    agregar(con_exo and not (r.otros_ingresos_no_reportados or r.arriendos_no_reportados or r.honorarios_no_reportados), Vacio(
        "otros_ingresos", "si recibiste plata que no pasó por un banco ni un empleador",
        "¿Recibiste plata que no pasó por un banco ni un empleador, como arriendos que te pagan personas, trabajos por tu cuenta o ventas?",
    ))
    go = r.ganancias_ocasionales.model_dump()
    agregar(not any(v for v in go.values() if not isinstance(v, bool)), Vacio(
        "ganancias", "si vendiste un bien o recibiste herencia, donación o premio",
        f"¿En {anio} vendiste algún bien que tenías hace más de dos años, o recibiste una herencia, una donación o un premio?",
        "Escritura o contrato de venta; documentos de la sucesión.",
    ))
    agregar(sancion > 0 and r.sin_sanciones_ultimos_2_anios, Vacio(
        "sanciones", "si te han sancionado por declarar tarde",
        "Como ya pasó tu fecha, hay sanción. ¿La DIAN te ha sancionado por declarar tarde en los últimos dos años? Si no, la sanción baja a la mitad.",
    ))
    agregar(impuesto > 0 and p["declaro_antes"] and not r.impuesto_neto_anio_anterior, Vacio(
        "anterior", "tu impuesto del año pasado",
        "¿Cuánto fue el impuesto neto de renta en tu declaración del año pasado? Puede bajar el anticipo que te cobran.",
        "Está en tu declaración anterior (formulario 210), en MUISCA, «Consultar declaraciones».",
    ))
    return salida


# ---------- Lo que se le dice al usuario ----------


def diagnostico(e: EstadoChat, r: Respuestas, vp: Liquidacion | None) -> str:
    """Lo que el agente entendió de la exógena, en pocas frases."""
    ent = entidades(e)
    ex = exogena(e)
    quien = []
    if ent.get("empleador"):
        quien.append(f"trabajas para {_lista(ent['empleador'])}")
    if ent.get("contratante"):
        quien.append(f"recibiste honorarios de {_lista(ent['contratante'])}")
    if ent.get("pension"):
        quien.append(f"recibes pensión de {_lista(ent['pension'])}")
    if ent.get("banco"):
        quien.append(f"tienes cuentas o inversiones en {_lista(ent['banco'])}")
    if ent.get("vivienda"):
        quien.append(f"pagas un crédito de vivienda con {_lista(ent['vivienda'])}")
    if ent.get("credito"):
        quien.append(f"tienes deudas con {_lista(ent['credito'])}")
    if ent.get("inmueble"):
        quien.append("tienes un inmueble registrado en el catastro")
    if ent.get("dividendos"):
        quien.append(f"recibiste dividendos de {_lista(ent['dividendos'])}")
    partes = []
    if quien:
        partes.append("Por lo que reportaron, " + _lista(quien) + ".")
    if vp:
        ob = vp.obligacion
        if ob.obligado:
            partes.append("Con eso sí estás obligado a declarar: " + ob.razones[0][0].lower() + ob.razones[0][1:] + ".")
        else:
            partes.append("Con eso, por ahora no llegas a los topes para estar obligado.")
    vienen = []
    if ex.get("pagos.retenciones_renta"):
        vienen.append(f"tus retenciones ({pesos(ex['pagos.retenciones_renta'])})")
    if ex.get("deducciones.medicina_prepagada"):
        vienen.append("lo que pagaste de prepagada")
    if ex.get("deducciones.intereses_vivienda"):
        vienen.append("los intereses de vivienda")
    if ex.get("deducciones.compras_factura_electronica"):
        vienen.append("tus compras con factura electrónica (para el 1 %)")
    if vienen:
        partes.append("Ya vienen incluidos " + _lista(vienen) + ".")
    return "\n".join(partes)


def documentos(e: EstadoChat, r: Respuestas) -> list[str]:
    """Los documentos de SU caso, nombrando las entidades que le reportaron."""
    ent = entidades(e)
    p = perfil(e, r)
    docs = []
    for x in ent.get("empleador", []):
        docs.append(f"Certificado de ingresos y retenciones (formulario 220) de {x}: lo pides en recursos humanos o en el portal de nómina.")
    if p["empleado"] and not ent.get("empleador"):
        docs.append("Certificado de ingresos y retenciones (formulario 220) de tu empleador: lo pides en recursos humanos.")
    for x in ent.get("contratante", []):
        docs.append(f"Certificado de retenciones de {x}, si te retuvieron.")
    for x in ent.get("pension", []):
        docs.append(f"Certificado de ingresos y retenciones de tu pensión, de {x}.")
    for x in ent.get("cesantias", []):
        docs.append(f"Certificado de cesantías de {x}: en el portal o la app del fondo.")
    for x in ent.get("banco", []):
        docs.append(f"Certificado tributario de {x} (saldos al 31 de diciembre, intereses y retenciones): en la banca virtual, sección de certificados.")
    for x in ent.get("vivienda", []):
        docs.append(f"Certificado de intereses pagados y saldo del crédito de vivienda de {x}: en su banca virtual.")
    for x in ent.get("credito", []):
        docs.append(f"Certificado o extracto con el saldo a 31 de diciembre de lo que debes en {x}.")
    for x in ent.get("prepagada", []):
        docs.append(f"Certificado de pagos de {x}: en el portal de la entidad.")
    if ent.get("inmueble"):
        docs.append("Recibo del impuesto predial de tu inmueble (ahí está el avalúo catastral).")
    for x in ent.get("dividendos", []):
        docs.append(f"Certificado de dividendos de {x}.")
    if r.dependientes:
        docs.append("Soportes de tus personas a cargo: registro civil y, para hijos de 18 a 23 años, certificado de estudio.")
    if any(any(v in norm(b.concepto) for v in _VEHICULOS) for b in r.bienes_adicionales):
        docs.append("Factura o contrato de compra de tu vehículo.")
    if p["declaro_antes"]:
        docs.append("Tu declaración del año pasado: en MUISCA, «Consultar declaraciones».")
    if not e.tiene_exogena:
        docs.insert(0, "Tu reporte de información exógena: en MUISCA, «Consultar información exógena».")
    docs.append("RUT actualizado y firma electrónica de la DIAN, para presentar.")
    return docs
