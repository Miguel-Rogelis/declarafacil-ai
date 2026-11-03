"""Agente Extractor: saca las cifras de los certificados con reglas, sin IA.

Cada tipo de certificado tiene sus reglas:
- 220 (ingresos y retenciones): cada casilla tiene un título fijo ("Pagos por salarios",
  "Aportes obligatorios por salud…", "Valor de la retención en la fuente…").
- Banco, crédito de vivienda, aportes voluntarios, cesantías y prepagada: se buscan los
  conceptos (saldo, intereses, retención, 4x1000…) y el producto al que pertenecen (cuenta de
  ahorros, CDT, crédito, tarjeta…), en el texto y en las tablas.
- Declaración del año anterior: impuesto neto, anticipo para este año y saldo a favor.
- Si no reconoce el documento, propone las cifras que encuentre y las pregunta una por una.

Cada fila guarda de qué documento y de qué entidad salió. Las cifras se copian del texto:
nada se calcula ni se inventa aquí.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.agents.base import (
    NOMBRE_TIPO,
    DocumentoCargado,
    DocumentoLeido,
    FilaInterpretada,
    OpcionRevision,
)
from app.agents.lector import _a_numero


def _n(t: str | None) -> str:
    s = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def pesos(v: float) -> str:
    return "$" + f"{abs(v):,.0f}".replace(",", ".")


# ---------- Cifras dentro de una línea ----------

_MONTO = re.compile(r"(?<![\w.,*/-])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{5,9}(?:[.,]\d{1,2})?)(?![\w*/%-]|[.,]\d)")
# Lo que va antes de un número que NO es plata (cédula, cuenta, NIT, teléfono…)
_ANTES_NO_MONTO = re.compile(r"(\bnit|\bc\.?\s?c\.?|cedula|identificacion|\bno\.?|numero|\bnro\.?|cuenta|producto|#|\bn|telefono|celular|tarjeta|radicado|matricula|chip|referencia|codigo)\s*[:.]?\s*$")


@dataclass
class Monto:
    valor: float
    inicio: int
    fin: int


def montos(linea_n: str) -> list[Monto]:
    """Cifras en pesos de una línea ya normalizada (sin años, casillas, cuentas ni cédulas)."""
    salida = []
    for m in _MONTO.finditer(linea_n):
        if _ANTES_NO_MONTO.search(linea_n[max(0, m.start() - 16):m.start()]):
            continue
        v = _a_numero(m.group(1))
        if v is not None and v >= 1000:
            salida.append(Monto(v, m.start(), m.end()))
    return salida


# ---------- Entidad que expide el certificado ----------

_CONOCIDAS = [
    "Bancolombia", "Davivienda", "BBVA", "Banco de Bogotá", "Banco Popular", "Banco de Occidente", "Banco AV Villas", "Banco Caja Social",
    "Itaú", "Scotiabank Colpatria", "Banco Falabella", "Banco Pichincha", "Banco GNB Sudameris", "Bancoomeva", "Banco Agrario", "Banco W",
    "Banco Finandina", "Banco Serfinanza", "Nu Colombia", "Lulo Bank", "Nequi", "Daviplata", "Fondo Nacional del Ahorro", "ICETEX", "Porvenir",
    "Protección", "Colfondos", "Skandia", "Colpensiones", "Colsanitas", "Sura", "Coomeva", "Compensar", "Allianz", "Mapfre", "Bolívar",
    "Fiduciaria Bancolombia", "Fiduciaria Bogotá", "Credicorp Capital", "Confiar", "Cotrafa",
]
_EMPRESA = re.compile(r"\b(s\.?\s?a\.?\s?s\.?|s\.?\s?a\.?|ltda\.?|e\.?\s?s\.?\s?p\.?|e\.?\s?p\.?\s?s\.?|banco|bancolombia|davivienda|bbva|fondo|fiduciaria|compania|corporacion|cooperativa|seguros|caja de compensacion|alcaldia|secretaria de hacienda|municipio|distrito|gobernacion)\b", re.IGNORECASE)
_NO_NOMBRE = re.compile(r"certific|senor|cliente|\bnit\b|direccion|\[datos|telefono|pagina|fecha|ciudad|correo|www\.|@|informacion tributaria|razon social\s*$", re.IGNORECASE)
_NIT = re.compile(r"\bnit\b[^0-9]{0,20}(\d{3}[.\s]?\d{3}[.\s]?\d{3})(?:\s*-\s*\d)?")
_NIT_SUELTO = re.compile(r"(?<![\d.])([89]\d{2}\.?\d{3}\.?\d{3})(?:\s*-\s*\d)?(?![\d.,])")


def entidad_de(doc: DocumentoLeido, nombre_archivo: str = "") -> tuple[str | None, str | None]:
    """(nombre, NIT sin dígito de verificación) de quien expide el documento."""
    lineas = doc.lineas[:120]
    nit = None
    for linea in lineas:
        m = _NIT.search(_n(linea))
        if m:
            nit = re.sub(r"\D", "", m.group(1))
            break
    if not nit:
        for linea in lineas[:60]:
            if "[DATOS" in linea:
                continue
            m = _NIT_SUELTO.search(_n(linea))
            if m:
                nit = re.sub(r"\D", "", m.group(1))
                break

    nombre = None
    # En el 220 y en las declaraciones: el valor que sigue al título "razón social" o "nombre del pagador"
    for i, linea in enumerate(lineas):
        n = _n(linea)
        if re.search(r"razon social|nombre del pagador|agente retenedor", n):
            resto = re.split(r"raz[oó]n social|nombre del pagador o agente retenedor|nombre del pagador|agente retenedor", linea, flags=re.IGNORECASE)[-1]
            candidatos = [resto] + [x for x in lineas[i + 1:i + 3]]
            for c in candidatos:
                c = re.sub(r"\b\d{1,2}\.\s*", " ", c)
                c = re.split(r"\bNIT\b", c, flags=re.IGNORECASE)[0].strip(" :-").lstrip(". ")
                if len(c) >= 4 and _EMPRESA.search(c) and not _NO_NOMBRE.search(_n(c)):
                    nombre = c
                    break
            if nombre:
                break
    if not nombre:
        texto = _n(" ".join(lineas[:80]) + " " + nombre_archivo.replace("_", " "))
        for conocida in _CONOCIDAS:
            if re.search(r"\b" + re.escape(_n(conocida)) + r"\b", texto):
                nombre = conocida
                break
    if not nombre:
        for linea in lineas[:25]:
            c = re.split(r"\bNIT\b", linea, flags=re.IGNORECASE)[0].strip(" :-").lstrip(". ")
            if 4 <= len(c) <= 80 and _EMPRESA.search(c) and not _NO_NOMBRE.search(_n(c)) and not re.search(r"\d{4,}", c):
                nombre = c
                break
    if nombre:
        nombre = re.sub(r"\s+", " ", nombre).strip()[:70]
    return nombre, nit


# ---------- Reglas por tipo de documento ----------


@dataclass
class Regla:
    patron: str
    campo: str | None  # None = solo informativo
    etiqueta: str
    explicacion: str = ""
    total: bool = False  # es un total: solo se usa si no está el detalle
    revisar: bool = False


_R220 = [
    Regla(r"bonos electronicos|bonos .*de papel|cheques, tarjetas|vales", "laboral.salarios_y_pagos_laborales", "Pagos con bonos, tarjetas o vales",
          "Lo que tu empleador te pagó con bonos o tarjetas. Cuenta como ingreso."),
    Regla(r"exceso de los pagos por alimentacion", "laboral.salarios_y_pagos_laborales", "Pagos por alimentación por encima de 41 UVT",
          "La parte de los bonos de alimentación que sí es ingreso (art. 387-1 ET)."),
    Regla(r"pagos? (por|de) salarios|pagos al empleado|salarios y demas (ingresos|pagos) laborales", "laboral.salarios_y_pagos_laborales", "Salarios",
          "Lo que te pagó tu empleador en el año."),
    Regla(r"pagos? por honorarios", "independiente.honorarios_y_servicios", "Honorarios", "Pagos por honorarios que te certificaron."),
    Regla(r"pagos? por servicios", "independiente.honorarios_y_servicios", "Pagos por servicios", "Pagos por servicios que te certificaron."),
    Regla(r"pagos? por comisiones", "laboral.salarios_y_pagos_laborales", "Comisiones", "Comisiones que te pagó tu empleador."),
    Regla(r"prestaciones sociales", "laboral.salarios_y_pagos_laborales", "Prestaciones sociales", "Primas, vacaciones y demás prestaciones."),
    Regla(r"pagos? por viaticos", "laboral.salarios_y_pagos_laborales", "Viáticos", "Viáticos que te pagaron."),
    Regla(r"gastos de representacion", "laboral.salarios_y_pagos_laborales", "Gastos de representación", "Gastos de representación que te pagaron."),
    Regla(r"trabajo asociado cooperativo", "laboral.salarios_y_pagos_laborales", "Compensaciones del trabajo asociado", "Compensaciones de tu cooperativa de trabajo."),
    Regla(r"^\W*(\d{1,2}\.?\s*)?otros pagos", "laboral.salarios_y_pagos_laborales", "Otros pagos laborales", "Otros pagos de tu empleador."),
    Regla(r"cesantias? (consignad|.*consignado al fondo)|consignado al fondo de cesantias", "laboral.cesantias_e_intereses", "Cesantías consignadas al fondo",
          "Cesantías que tu empleador consignó en el año. Suelen quedar exentas."),
    Regla(r"regimen tradicional", "laboral.cesantias_e_intereses", "Cesantías del régimen tradicional", "Cesantías reconocidas en el año. Suelen quedar exentas."),
    Regla(r"(auxilio de )?cesantias? .*(efectivamente pagad|pagados al empleado|intereses)", "laboral.cesantias_e_intereses", "Cesantías e intereses pagados",
          "Cesantías e intereses que te pagaron directamente. Suelen quedar exentos."),
    Regla(r"pensiones? de jubilacion|pensiones? de vejez|jubilacion, vejez", "pensiones.pensiones_nacionales", "Pensión", "Pensión que recibiste."),
    Regla(r"apoyos economicos educativos", None, "Apoyos educativos", "Apoyos educativos financiados con recursos públicos: no constituyen renta."),
    Regla(r"total (de )?ingresos brutos", None, "Total de ingresos brutos", "Es la suma de lo anterior; no se cuenta otra vez.", total=True),
    Regla(r"aportes? obligatorios? (por|a|de) salud", "laboral.aportes_obligatorios_salud", "Aportes a salud", "Lo que te descontaron para salud. No paga impuesto."),
    Regla(r"aportes? obligatorios? a fondos? de pensiones", "laboral.aportes_obligatorios_pension", "Aportes a pensión", "Lo que te descontaron para pensión. No paga impuesto."),
    Regla(r"cotizaciones voluntarias|voluntari.*(rais|ahorro individual)", "laboral.aportes_voluntarios_rais", "Aportes voluntarios a tu fondo de pensión obligatoria",
          "Una parte no paga impuesto."),
    Regla(r"aportes? voluntarios? a fondos? de pensiones", "deducciones.aportes_voluntarios_afc_fpv", "Aportes voluntarios a pensiones voluntarias",
          "Ahorro voluntario que te descontaron de nómina. Puede quedar exento con límites."),
    Regla(r"aportes? a cuentas? afc|\bafc\b", "deducciones.aportes_voluntarios_afc_fpv", "Aportes a cuentas AFC", "Ahorro para vivienda que te descontaron de nómina."),
    Regla(r"aportes? a cuentas? avc|\bavc\b", "deducciones.aportes_voluntarios_afc_fpv", "Aportes a cuentas AVC", "Ahorro voluntario contractual descontado de nómina."),
    Regla(r"ingreso laboral promedio", "laboral.salario_promedio_mensual_6m", "Ingreso laboral promedio de los últimos 6 meses",
          "Define qué parte de tus cesantías queda exenta."),
    Regla(r"valor de la retencion en la fuente|retencion en la fuente por (ingresos laborales|rentas de trabajo|salarios)", "pagos.retenciones_renta",
          "Retención en la fuente", "Impuesto que te descontaron durante el año. Se resta de lo que debes pagar."),
    Regla(r"total retenciones ano gravable", "pagos.retenciones_renta", "Total de retenciones del año", "Impuesto que te descontaron durante el año.", total=True),
]

_RDECLARACION = [
    Regla(r"anticipo .*(ano gravable siguiente|siguiente)", "pagos.anticipo_anio_anterior", "Anticipo pagado para este año",
          "Lo que pagaste por adelantado en tu declaración anterior. Se resta del impuesto de este año."),
    Regla(r"anticipo", None, "Anticipo del año anterior", "Anticipo de un año anterior: ya se usó."),
    Regla(r"impuesto neto de renta", "pagos.impuesto_neto_anio_anterior", "Impuesto neto de renta del año anterior", "Sirve para calcular el anticipo de este año."),
    Regla(r"saldo a favor .*(anterior|sin solicitud)", None, "Saldo a favor de un año anterior", "Viene de otra declaración; ya se usó."),
    Regla(r"total saldo a favor|^\W*(\d{1,3}\s*)?saldo a favor", "pagos.saldo_favor_anterior", "Saldo a favor de tu declaración anterior",
          "Si no pediste que te lo devolvieran, se resta de lo que debes pagar este año.", revisar=True),
    Regla(r"total patrimonio (bruto|liquido)|patrimonio (bruto|liquido)", None, "Patrimonio declarado el año anterior", "Sirve para comparar; no se suma."),
    Regla(r"total impuesto a cargo|saldo a pagar|total saldo a pagar|renta liquida gravable", None, "Valor de la declaración anterior", "Sirve de referencia; no se suma."),
]

# Conceptos que se buscan en los certificados de banco, fondos y prepagadas (el orden importa: lo más específico primero)
_CONCEPTOS = [
    ("excluir", r"\b(rete)?iva\b|\b(rete)?ica\b|timbre|cuota de manejo|comision(es)? bancaria"),
    ("gmf", r"gravamen a los movimientos financieros|\bgmf\b|4 ?x ?1\.?000|cuatro por mil"),
    ("componente", r"componente inflacionario"),
    ("retencion", r"retencion(es)?|retefuente|valor retenido"),
    ("retiro", r"retiros?\b"),
    ("correccion", r"correccion monetaria"),
    ("base", r"base (sometida|de retencion|gravable)|valor (del pago|pagado o abonado|base)|monto del pago"),
    ("aportes", r"aportes?|depositos?|consignacion(es)?|abonos?|cesantias (abonadas|consignadas)"),
    ("intereses", r"intereses?|rendimientos?"),
    ("pagado", r"valor (total )?(pagado|cancelado|facturado)|total pagado|pagos? (realizados|efectuados)|valor del plan|valor total"),
    ("avaluo", r"avaluo( catastral)?"),
    ("saldo", r"saldo|valor (a|al) 31|valor patrimonial|valor (de la |del )?(inversion|titulo|cdt)|valor de mercado|valor en pesos"),
]
_CONCEPTOS_RE = [(c, re.compile(p)) for c, p in _CONCEPTOS]

_PRODUCTOS = [
    ("vivienda", r"credito (de )?vivienda|credito hipotecario|hipotecari|leasing habitacional|prestamo de vivienda", "crédito de vivienda"),
    ("tarjeta", r"tarjeta de credito", "tarjeta de crédito"),
    ("educativo", r"icetex|credito educativo|prestamo educativo", "crédito educativo del ICETEX"),
    ("credito", r"credito|prestamo|obligacion(es)? financiera|obligacion (no|nro|numero|#)|libranza|cartera de credito|leasing|sobregiro", "crédito"),
    ("cdt", r"\bcdt\b|certificado de deposito|deposito a termino", "CDT"),
    ("voluntario", r"pensiones voluntarias|fondo voluntario|pension voluntaria|\bafc\b|\bavc\b|fomento de la construccion", "ahorro voluntario"),
    ("inversion", r"fiducia|fondo de inversion|cartera colectiva|fondos? de inversion colectiva|encargo fiduciario|acciones|titulos|fic\b", "inversión"),
    ("corriente", r"cuenta corriente", "cuenta corriente"),
    ("ahorros", r"cuenta de ahorros?|cta\.? (de )?ahorros?|ahorros", "cuenta de ahorros"),
    ("cesantias", r"cesantias", "cesantías"),
]
_PRODUCTOS_RE = [(k, re.compile(p), nombre) for k, p, nombre in _PRODUCTOS]
_MESES = re.compile(r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b")


_NO_PRODUCTO = re.compile(r"establecimiento (de credito|bancario)|entidad(es)? de credito|obligaciones tributarias|vigilad[ao]|superintendencia")


def _producto(n: str) -> tuple[str, str] | None:
    n = _NO_PRODUCTO.sub(" ", n)
    for k, rx, nombre in _PRODUCTOS_RE:
        if rx.search(n):
            return k, nombre
    return None


@dataclass
class Candidato:
    concepto: str
    valor: float
    producto: tuple[str, str] | None
    texto: str  # línea normalizada (para la etiqueta y para detectar totales)
    referencia: str = ""  # "****8901" del producto, si se ve
    total: bool = False
    mes: bool = False


def _referencia(linea: str) -> str:
    m = re.search(r"\*{2,}\d{3,4}|x{3,}\d{3,4}", linea, re.IGNORECASE)
    return m.group(0) if m else ""


def _conceptos_en(n: str) -> list[tuple[int, str]]:
    """(posición, concepto) de cada concepto en la línea; si dos se pisan, gana el más específico."""
    vistos: list[tuple[int, int, str]] = []
    for c, rx in _CONCEPTOS_RE:
        for m in rx.finditer(n):
            if any(m.start() < f and m.end() > i for i, f, _ in vistos):
                continue
            vistos.append((m.start(), m.end(), c))
    return sorted((i, c) for i, _, c in vistos)


def _candidatos_de_lineas(lineas: list[str], ya: list[tuple[str, float]]) -> list[Candidato]:
    salida: list[Candidato] = []
    producto: tuple[str, str] | None = None
    referencia = ""
    columnas: list[str] = []
    pendientes = list(ya)
    for linea in lineas:
        if "[DATOS PERSONALES]" in linea:
            continue
        n = _n(linea)
        cs = _conceptos_en(n)
        ms = montos(n)
        # El producto de una línea con cifras, o de un título corto ("CUENTA DE AHORROS ****8901"), rige las líneas siguientes
        p = _producto(n) if (ms or len(n.split()) <= 10) else None
        if p:
            producto, referencia = p, _referencia(linea) or (referencia if p == producto else "")
        if not ms:
            if len({c for _, c in cs if c != "excluir"}) >= 2:
                columnas = [c for _, c in cs]  # encabezado de una tabla escrita como texto
            continue
        total = bool(re.search(r"\btotal(es)?\b", n))
        mes = bool(_MESES.search(n))
        asignados: list[tuple[str, Monto]] = []
        if columnas and not any(c for _, c in cs if c != "excluir") and len(ms) == len(columnas):
            asignados = list(zip(columnas, ms, strict=True))
        else:
            previo = 0
            for m in ms:
                # el primer concepto que aparece entre la cifra anterior y esta
                entre = [c for i, c in cs if previo <= i < m.inicio]
                if entre:
                    asignados.append((entre[0], m))
                elif asignados:
                    pass  # una segunda cifra sin título: puede ser otra columna; no se adivina
                previo = m.fin
        for concepto, m in asignados:
            if concepto == "excluir":
                continue
            if (concepto, m.valor) in pendientes:
                pendientes.remove((concepto, m.valor))  # ya salió de una tabla
                continue
            salida.append(Candidato(concepto, m.valor, producto, n, _referencia(linea) or referencia, total, mes))
    return salida


def _candidatos_de_tablas(tablas: list[list[list[str]]]) -> list[Candidato]:
    salida = []
    for tabla in tablas:
        columnas: dict[int, str] = {}
        for fila in tabla:
            celdas = [_n(c) for c in fila]
            conceptos = {}
            for i, c in enumerate(celdas):
                cs = _conceptos_en(c)
                if cs and not montos(c):
                    conceptos[i] = cs[0][1]
            if len([c for c in conceptos.values() if c != "excluir"]) >= 2:
                columnas = conceptos
                continue
            if not columnas:
                continue
            texto = " ".join(celdas)
            producto = _producto(texto)
            for i, concepto in columnas.items():
                if i >= len(celdas) or concepto == "excluir":
                    continue
                for m in montos(celdas[i])[:1]:
                    salida.append(Candidato(concepto, m.valor, producto, texto, _referencia(" ".join(fila)), bool(re.search(r"\btotal", texto)), bool(_MESES.search(texto))))
    return salida


def _quitar_totales(cs: list[Candidato]) -> list[Candidato]:
    """Una cifra por dato: ni el total encima del detalle, ni la misma cifra repetida en el resumen."""
    salida: list[Candidato] = []
    for concepto in dict.fromkeys(c.concepto for c in cs):
        del_concepto = [c for c in cs if c.concepto == concepto]
        totales = [c for c in del_concepto if c.total]
        detalle = [c for c in del_concepto if not c.total]
        if totales and any(c.mes for c in detalle):
            salida.append(max(totales, key=lambda c: c.valor))  # pagos mes a mes con su total: vale el total
            continue
        elegidos = detalle or totales
        unicos: list[Candidato] = []
        for c in elegidos:
            repetida = not c.mes and any(u.valor == c.valor and (u.producto or ("",))[0] == (c.producto or ("",))[0] and not u.mes for u in unicos)
            if not repetida:
                unicos.append(c)
        salida.extend(unicos)
    return salida


# ---------- Del concepto al campo de la declaración ----------


@dataclass
class Dato:
    campo: str | None
    etiqueta: str
    valor: float
    explicacion: str
    referencia: str = ""
    revisar: bool = False
    agrupar: bool = False  # se suma con los demás del mismo campo (pagos de prepagada, intereses de vivienda…)
    extra: dict = field(default_factory=dict)


def _de_banco(c: Candidato, tipo: str) -> Dato | None:
    k, nombre = c.producto or ("", "")
    deuda = k in ("credito", "tarjeta", "vivienda", "educativo")
    if c.concepto == "saldo":
        if tipo == "certificado_cesantias" or k == "cesantias":
            return Dato("patrimonio.bienes", "Saldo de cesantías a 31 de diciembre", c.valor, "Tus cesantías en el fondo son parte de tu patrimonio.", c.referencia)
        if tipo == "certificado_voluntarios" or k == "voluntario":
            return Dato("patrimonio.bienes", "Saldo en pensiones voluntarias o AFC a 31 de diciembre", c.valor, "Ese ahorro es parte de tu patrimonio.", c.referencia)
        if deuda or tipo == "certificado_vivienda":
            return Dato("patrimonio.deudas", f"Saldo de {nombre or 'tu crédito'} a 31 de diciembre", c.valor, "Lo que debías el 31 de diciembre. Se resta de tu patrimonio.", c.referencia)
        return Dato("patrimonio.bienes", f"Saldo de {nombre or 'tus productos'} a 31 de diciembre", c.valor, "Lo que tenías el 31 de diciembre. Es parte de tu patrimonio.", c.referencia)
    if c.concepto in ("intereses", "correccion"):
        if k == "vivienda" or (tipo == "certificado_vivienda" and k in ("", "credito")):
            if c.concepto == "correccion":
                return Dato(None, "Corrección monetaria del crédito de vivienda", c.valor, "No la sumé: pregúntale al banco si ya va dentro de los intereses que certifica.", c.referencia)
            return Dato("deducciones.intereses_vivienda", "Intereses pagados del crédito de vivienda", c.valor, "Se pueden restar con tope (art. 119 ET).", c.referencia, agrupar=True)
        if k == "educativo":
            return Dato("deducciones.intereses_icetex", "Intereses pagados del crédito educativo del ICETEX", c.valor, "Se restan hasta 100 UVT al año (art. 119 ET).", c.referencia, agrupar=True)
        if deuda:
            return Dato(None, f"Intereses pagados de {nombre}", c.valor, "Los intereses de créditos que no son de vivienda ni del ICETEX no se restan.", c.referencia)
        if tipo in ("certificado_voluntarios", "certificado_cesantias") or k in ("voluntario", "cesantias"):
            return Dato(None, "Rendimientos del fondo", c.valor, "Se miran cuando retiras la plata; por ahora no se suman.", c.referencia)
        if c.concepto == "correccion":
            return None
        return Dato("capital.rendimientos_financieros", f"Intereses y rendimientos de {nombre or 'tus productos'}", c.valor,
                    "Lo que te pagaron tus ahorros o inversiones. Una parte (componente inflacionario) no paga impuesto.", c.referencia)
    if c.concepto == "retencion":
        return Dato("pagos.retenciones_renta", "Retención en la fuente", c.valor, "Impuesto que te descontaron por adelantado. Se resta de lo que debes pagar.", agrupar=True)
    if c.concepto == "gmf":
        return Dato("deducciones.gmf_pagado", "4x1000 que te cobraron", c.valor, "La mitad del 4x1000 se puede restar.", c.referencia, agrupar=True)
    if c.concepto == "componente":
        return Dato(None, "Componente inflacionario", c.valor, "Lo calculo con el porcentaje del año; no se suma aparte.")
    if c.concepto == "aportes":
        if tipo == "certificado_cesantias" or k == "cesantias":
            return Dato("laboral.cesantias_e_intereses", "Cesantías consignadas en el año", c.valor, "Cesantías que te consignaron en el año. Suelen quedar exentas.", agrupar=True)
        if tipo == "certificado_voluntarios" or k == "voluntario":
            return Dato("deducciones.aportes_voluntarios_afc_fpv", "Aportes voluntarios a pensión o AFC", c.valor, "Ahorro voluntario. Puede quedar exento con límites.", agrupar=True)
        return None
    if c.concepto == "retiro":
        return Dato(None, "Retiros del fondo", c.valor, "Retiros del año: si no cumpliste los requisitos de permanencia, pueden pagar impuesto. Pregúntale al fondo.")
    if c.concepto == "pagado" and tipo == "certificado_prepagada":
        return Dato("deducciones.medicina_prepagada", "Pagos de medicina prepagada o póliza de salud", c.valor, "Se pueden restar con tope.", agrupar=True)
    if c.concepto == "pagado" and tipo == "certificado_vivienda":
        return None
    if c.concepto == "avaluo":
        return Dato("patrimonio.bienes", "Avalúo catastral de tu inmueble", c.valor, "Tu inmueble se declara como mínimo por este valor.")
    return None


_BASE_RETENCION = [
    (r"honorarios", "independiente.honorarios_y_servicios", "Honorarios"),
    (r"servicios", "independiente.honorarios_y_servicios", "Servicios"),
    (r"comisiones", "independiente.honorarios_y_servicios", "Comisiones"),
    (r"arrendamiento|arriendo", "capital.arrendamientos", "Arriendos"),
    (r"rendimientos|intereses", "capital.rendimientos_financieros", "Rendimientos"),
    (r"dividendos", "dividendos.no_gravados_subcedula1", "Dividendos"),
]


def _de_retencion(c: Candidato) -> Dato | None:
    if c.concepto == "retencion":
        return Dato("pagos.retenciones_renta", "Retención en la fuente", c.valor, "Impuesto que te descontaron por adelantado.")
    if c.concepto in ("base", "pagado"):
        for patron, campo, etiqueta in _BASE_RETENCION:
            if re.search(patron, c.texto):
                return Dato(campo, f"{etiqueta} que te pagaron", c.valor, "Lo que te pagaron según el certificado de retención.")
        return Dato("no_laborales.ingresos", "Pago que te hicieron", c.valor, "Lo que te pagaron según el certificado de retención.", revisar=True)
    return None


def _generico(c: Candidato) -> Dato | None:
    """Documento que no reconocí: propongo la cifra y la pregunto."""
    d = _de_banco(c, "certificado_bancario")
    if d and d.campo:
        d.revisar = True
        return d
    if c.concepto == "pagado":
        return Dato("no_laborales.ingresos", "Valor pagado", c.valor, "No sé qué es este valor.", revisar=True)
    return None


# ---------- Reglas línea a línea (220 y declaración anterior) ----------


def _por_titulos(lineas: list[str], reglas: list[Regla]) -> list[Dato]:
    salida: list[Dato] = []
    usados: set[int] = set()
    for i, linea in enumerate(lineas):
        if "[DATOS PERSONALES]" in linea:
            continue
        n = _n(linea)
        encontrada = next(((r, m) for r in reglas if (m := re.search(r.patron, n))), None)
        if not encontrada:
            continue
        regla, m = encontrada
        # La cifra que sigue al título (los formularios de dos columnas traen dos casillas por línea)
        ms = [x for x in montos(n) if x.inicio >= m.end()]
        if ms:
            siguiente = next((x.start() for r in reglas if r is not regla and (x := re.search(r.patron, n[m.end():]))), None)
            if siguiente is not None:
                ms = [x for x in ms if x.inicio < m.end() + siguiente] or ms
        if not ms:
            # El valor puede ir en la línea siguiente (formularios con el número abajo)
            for j in range(i + 1, min(i + 3, len(lineas))):
                if j in usados:
                    continue
                nj = _n(lineas[j])
                if any(re.search(r.patron, nj) for r in reglas):
                    break
                ms = montos(nj)
                if ms:
                    usados.add(j)
                    break
        if not ms:
            continue
        salida.append(Dato(regla.campo, regla.etiqueta, ms[0].valor, regla.explicacion, revisar=regla.revisar, extra={"total": regla.total}))
    # Los totales solo se usan si no está el detalle del mismo campo
    con_detalle = {d.campo for d in salida if not d.extra.get("total")}
    return [d for d in salida if not d.extra.get("total") or d.campo not in con_detalle and d.campo]


_PARENTESCO = re.compile(r"\b(hij[oa]s?|conyuge|esposa|esposo|companer[oa] permanente|padre|madre|herman[oa])\b")


def _pistas_220(lineas: list[str]) -> list[str]:
    """El 220 trae el dependiente económico (sin datos personales queda solo el parentesco)."""
    for i, linea in enumerate(lineas):
        if "dependiente economico" in _n(linea):
            m = _PARENTESCO.search(" ".join(_n(x) for x in lineas[i + 1:i + 6]))
            if m:
                return [f"dependiente:{m.group(1)}"]
    return []


# ---------- Armar las filas ----------


def _fila(i: int, huella: str, tipo: str, entidad: str | None, nit: str | None, d: Dato) -> FilaInterpretada:
    f = FilaInterpretada(
        id=f"{huella[:6]}-{i:02d}",
        nit_informante=nit,
        informante=entidad or NOMBRE_TIPO[tipo],
        detalle=d.etiqueta,
        valor=d.valor,
        info_adicional=(f"Producto {d.referencia}" if d.referencia else None),
        documento=huella,
        fuente=tipo,
        campo=d.campo,
        tratamiento="suma" if d.campo else "informativo",
        explicacion=d.explicacion,
        origen_mapeo="reglas",
    )
    if d.revisar:
        f.tratamiento = "revisar"
    return f


def preguntar(f: FilaInterpretada, nombre_doc: str) -> None:
    """Pregunta sencilla para una cifra de un certificado que hay que confirmar."""
    from app.agents.revision import _NOMBRES  # nombres sencillos de cada campo

    if f.campo == "pagos.saldo_favor_anterior":
        f.pregunta = f"Tu declaración anterior dejó un saldo a favor de {pesos(f.valor)}. ¿Pediste que te lo devolvieran?"
        f.ayuda = "Si no lo pediste, se resta de lo que debes pagar este año."
        f.opciones = [OpcionRevision(texto="No, lo dejé para este año", incluir=True, campo=f.campo, recomendada=True),
                      OpcionRevision(texto="Sí, pedí la devolución", incluir=False)]
        return
    nombre = _NOMBRES.get(f.campo or "", "parte de tu declaración")
    f.pregunta = f"En «{nombre_doc}» aparece «{f.detalle}» por {pesos(f.valor)}. ¿Lo tomo como {nombre}?"
    f.ayuda = "No reconocí bien este documento; por eso te confirmo cada cifra."
    f.opciones = [OpcionRevision(texto="Sí, está bien", incluir=True, campo=f.campo, recomendada=True),
                  OpcionRevision(texto="No, déjalo por fuera", incluir=False)]


_RESUMEN = {
    "laboral.salarios_y_pagos_laborales": "ingresos laborales",
    "laboral.cesantias_e_intereses": "cesantías",
    "laboral.aportes_obligatorios_salud": "aportes a salud",
    "laboral.aportes_obligatorios_pension": "aportes a pensión",
    "laboral.aportes_voluntarios_rais": "aportes voluntarios al fondo obligatorio",
    "independiente.honorarios_y_servicios": "honorarios",
    "pensiones.pensiones_nacionales": "pensión",
    "capital.rendimientos_financieros": "intereses",
    "capital.arrendamientos": "arriendos",
    "patrimonio.bienes": "saldos",
    "patrimonio.deudas": "deudas",
    "pagos.retenciones_renta": "retención",
    "deducciones.gmf_pagado": "4x1000",
    "deducciones.intereses_vivienda": "intereses de vivienda",
    "deducciones.medicina_prepagada": "prepagada",
    "deducciones.aportes_voluntarios_afc_fpv": "aportes voluntarios o AFC",
    "deducciones.intereses_icetex": "intereses del ICETEX",
    "pagos.impuesto_neto_anio_anterior": "impuesto neto",
    "pagos.anticipo_anio_anterior": "anticipo para este año",
    "pagos.saldo_favor_anterior": "saldo a favor",
    "no_laborales.ingresos": "otros ingresos",
}


def _resumen(filas: list[FilaInterpretada]) -> str:
    totales: dict[str, float] = {}
    for f in filas:
        if f.campo and f.tratamiento != "informativo" and f.campo in _RESUMEN and f.campo != "laboral.salario_promedio_mensual_6m":
            totales[f.campo] = totales.get(f.campo, 0) + f.valor
    partes = [f"{_RESUMEN[k]} {pesos(v)}" for k, v in totales.items()]
    return ", ".join(partes[:6])


def etiqueta_de(tipo: str, entidad: str | None, anio: int | None) -> str:
    base = NOMBRE_TIPO.get(tipo, "Documento")
    if tipo == "certificado_220":
        base = "Certificado de ingresos y retenciones"
    if tipo == "certificado_bancario":
        base = "Certificado tributario"
    if tipo == "declaracion_anterior":
        return f"Tu declaración de renta del año gravable {anio}" if anio else "Tu declaración de renta anterior"
    return f"{base} de {entidad}" if entidad and tipo != "desconocido" else (f"Documento de {entidad}" if entidad else base)


def extraer(doc: DocumentoLeido, tipo: str, huella: str, nombre_archivo: str, anio: int | None) -> tuple[list[FilaInterpretada], DocumentoCargado]:
    """Convierte un certificado ya anonimizado en filas como las de la exógena."""
    entidad, nit = entidad_de(doc, nombre_archivo)
    pistas: list[str] = []
    datos: list[Dato] = []
    if tipo == "certificado_220":
        datos = _por_titulos(doc.lineas, _R220)
        pistas = _pistas_220(doc.lineas)
        campos = {d.campo for d in datos}
        if "pensiones.pensiones_nacionales" in campos and "laboral.salarios_y_pagos_laborales" not in campos:
            for d in datos:
                if d.campo == "laboral.aportes_obligatorios_salud":
                    d.campo, d.etiqueta = "pensiones.aportes_salud", "Aportes a salud del pensionado"
    elif tipo == "declaracion_anterior":
        datos = _por_titulos(doc.lineas, _RDECLARACION)
        pistas = ["declaro_antes"]
    else:
        tabla = _candidatos_de_tablas(doc.tablas)
        lineas = _candidatos_de_lineas(doc.lineas, [(c.concepto, c.valor) for c in tabla])
        candidatos = _quitar_totales(tabla + lineas)
        for c in candidatos:
            if tipo == "certificado_retencion":
                d = _de_retencion(c)
            elif tipo == "desconocido":
                d = _generico(c)
            else:
                d = _de_banco(c, tipo)
            if d:
                datos.append(d)
        if tipo == "desconocido":
            datos = sorted(datos, key=lambda d: -d.valor)[:6]
        # Pagos que se suman en una sola cifra (los 12 meses de prepagada, varios créditos de vivienda…)
        agrupados: list[Dato] = []
        for d in datos:
            igual = next((a for a in agrupados if a.agrupar and d.agrupar and a.campo == d.campo), None)
            if igual:
                igual.valor += d.valor
            else:
                agrupados.append(d)
        datos = agrupados
    filas = [_fila(i + 1, huella, tipo, entidad, nit, d) for i, d in enumerate(datos)]
    etiqueta = etiqueta_de(tipo, entidad, anio)
    for f in filas:
        if f.tratamiento == "revisar":
            preguntar(f, nombre_archivo)
    documento = DocumentoCargado(
        id=huella, nombre=nombre_archivo, tipo=tipo, etiqueta=etiqueta, entidad=entidad, nit=nit, anio=anio,
        cifras=sum(1 for f in filas if f.tratamiento != "informativo"), resumen=_resumen(filas), pistas=pistas,
    )
    return filas, documento
