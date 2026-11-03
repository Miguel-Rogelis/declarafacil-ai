"""Agente Conciliador: cruza los documentos para no contar nada dos veces.

Reglas, sin IA:
- Un certificado es la fuente directa: si la exógena trae el mismo dato de la misma entidad
  (mismo NIT o mismo nombre) y del mismo tipo (saldo, intereses, retención…), se usa la cifra
  del certificado y la de la exógena queda solo como referencia. Si no coinciden, se avisa.
- Las cesantías del certificado de ingresos y retenciones (220) reemplazan las que reporta el
  fondo de cesantías, en la exógena o en su propio certificado.
- Un CDT que la exógena pregunta ("¿seguía abierto?") se resuelve si el certificado del banco
  ya trae los saldos a 31 de diciembre.
- Un predial con el mismo avalúo que trae la exógena no se suma otra vez; si es distinto,
  se le pregunta a la persona si es otro inmueble.
- Una exógena nueva reemplaza a la anterior.
"""

from __future__ import annotations

import re
import unicodedata

from app.agents.base import DocumentoCargado, FilaInterpretada, OpcionRevision

_GENERICAS = {
    "banco", "bancos", "sa", "sas", "s", "a", "de", "del", "la", "el", "los", "y", "compania", "corporacion", "financiera", "colombia",
    "establecimiento", "bancario", "fondo", "fondos", "pensiones", "cesantias", "fiduciaria", "seguros", "entidad", "promotora", "salud",
    "medicina", "prepagada", "ltda", "bic", "eps", "grupo", "servicios", "sociedad", "administradora", "nacional", "en",
}

_NOMBRE_CAMPO = {
    "laboral.salarios_y_pagos_laborales": "ingresos laborales",
    "laboral.cesantias_e_intereses": "cesantías",
    "laboral.aportes_obligatorios_salud": "aportes a salud",
    "laboral.aportes_obligatorios_pension": "aportes a pensión",
    "independiente.honorarios_y_servicios": "honorarios",
    "capital.rendimientos_financieros": "intereses",
    "patrimonio.bienes": "saldos",
    "patrimonio.deudas": "deudas",
    "pagos.retenciones_renta": "retención",
    "deducciones.gmf_pagado": "4x1000",
    "deducciones.intereses_vivienda": "intereses de vivienda",
    "deducciones.medicina_prepagada": "medicina prepagada",
    "deducciones.aportes_voluntarios_afc_fpv": "aportes voluntarios",
    "pensiones.pensiones_nacionales": "pensión",
}


def _n(t: str | None) -> str:
    s = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _pesos(v: float) -> str:
    return "$" + f"{abs(v):,.0f}".replace(",", ".")


def _nit(f: FilaInterpretada) -> str:
    d = re.sub(r"\D", "", f.nit_informante or "")
    return d[:9] if len(d) >= 9 else ""


def _palabras(nombre: str | None) -> set[str]:
    return {p for p in re.split(r"[^a-z0-9]+", _n(nombre)) if len(p) >= 3 and p not in _GENERICAS}


def misma_entidad(a: FilaInterpretada, b: FilaInterpretada) -> bool:
    na, nb = _nit(a), _nit(b)
    if na and nb:
        return na == nb
    pa, pb = _palabras(a.informante), _palabras(b.informante)
    return bool(pa and pb and (pa <= pb or pb <= pa or len(pa & pb) >= 2))


def _cuenta(f: FilaInterpretada) -> bool:
    return f.tratamiento in ("suma", "revisar") and not f.reemplazada_por


def _es_certificado(f: FilaInterpretada) -> bool:
    return f.fuente not in ("exogena", "desconocido")


def conciliar(previas: list[FilaInterpretada], nuevas: list[FilaInterpretada], documentos: list[DocumentoCargado]) -> tuple[list[FilaInterpretada], list[str]]:
    """Une las filas que ya había con las de los documentos nuevos. Devuelve (filas, avisos de los cruces)."""
    avisos: list[str] = []
    ids_nuevos = {f.documento for f in nuevas}
    etiquetas = {d.id: d for d in documentos}
    if any(f.fuente == "exogena" for f in nuevas):
        viejas = [f for f in previas if f.fuente == "exogena"]
        if viejas:
            avisos.append("Reemplacé la exógena que tenía por la nueva.")
        previas = [f for f in previas if f.fuente != "exogena"]
    filas = previas + nuevas

    certificados = [f for f in filas if _es_certificado(f) and _cuenta(f) and f.campo]
    exogena = [f for f in filas if f.fuente == "exogena" and f.tratamiento in ("suma", "revisar") and not f.reemplazada_por]

    # 1. El certificado reemplaza a la exógena (misma entidad y mismo campo)
    grupos: dict[tuple[str, str, str], tuple[list[FilaInterpretada], list[FilaInterpretada]]] = {}
    for e in exogena:
        for c in certificados:
            if c.documento not in ids_nuevos and e.documento not in ids_nuevos:
                continue
            cubre = c.campo == e.campo and misma_entidad(c, e)
            # Cesantías: las del 220 reemplazan las que reporta el fondo
            cubre = cubre or (c.fuente == "certificado_220" and c.campo == e.campo == "laboral.cesantias_e_intereses")
            # Un CDT "por confirmar" se resuelve con los saldos del certificado del banco
            cubre = cubre or (e.tratamiento == "revisar" and not e.campo and c.campo == "patrimonio.bienes" and misma_entidad(c, e)
                              and re.search(r"cdt|inversion|saldo|deposito", _n(e.detalle)) is not None)
            if not cubre:
                continue
            clave = (c.documento or "", c.informante or "", e.campo or c.campo or "")
            g = grupos.setdefault(clave, ([], []))
            if e not in g[0]:
                g[0].append(e)
            break
    for (doc_id, entidad, campo), (exo, _) in grupos.items():
        certs = [c for c in certificados if c.documento == doc_id and c.campo == campo and (c.informante or "") == entidad]
        for e in exo:
            e.tratamiento, e.reemplazada_por = "informativo", doc_id
            e.explicacion = f"Lo reemplaza tu {etiquetas[doc_id].etiqueta[:1].lower() + etiquetas[doc_id].etiqueta[1:] if doc_id in etiquetas else 'certificado'}, que es la fuente directa."
        total_exo = sum(e.valor for e in exo if e.campo)
        total_cert = sum(c.valor for c in certs)
        if total_exo and certs and abs(total_exo - total_cert) > max(1000, total_cert * 0.005):
            nombre = _NOMBRE_CAMPO.get(campo, "ese dato")
            avisos.append(f"{nombre[:1].upper() + nombre[1:]} de {entidad}: la exógena dice {_pesos(total_exo)} y el certificado {_pesos(total_cert)}. Usé el certificado.")

    # 2. Cesantías: si hay 220, las del certificado del fondo sobran
    if any(c.fuente == "certificado_220" and c.campo == "laboral.cesantias_e_intereses" for c in certificados):
        for f in filas:
            if f.fuente == "certificado_cesantias" and f.campo == "laboral.cesantias_e_intereses" and _cuenta(f):
                f.tratamiento, f.reemplazada_por = "informativo", next(c.documento for c in certificados if c.fuente == "certificado_220")
                f.explicacion = "Ya vienen en tu certificado de ingresos y retenciones."

    # 3. El mismo certificado subido dos veces con otro nombre: cifras idénticas de la misma entidad
    for f in nuevas:
        if not _cuenta(f) or not f.campo:
            continue
        gemela = next((x for x in previas if x.fuente == f.fuente and x.campo == f.campo and x.valor == f.valor and misma_entidad(x, f) and _cuenta(x)), None)
        if gemela:
            f.tratamiento, f.reemplazada_por = "informativo", gemela.documento
            f.explicacion = "Ya la tenía de otro documento igual."

    # 4. Predial frente al avalúo de la exógena
    for f in nuevas:
        if f.fuente != "predial" or f.campo != "patrimonio.bienes" or not _cuenta(f):
            continue
        avaluos = [x for x in filas if x.fuente == "exogena" and "avaluo" in _n(x.detalle) and x.tratamiento != "informativo"]
        if any(abs(x.valor - f.valor) <= max(1000, f.valor * 0.01) for x in avaluos):
            f.tratamiento, f.reemplazada_por = "informativo", avaluos[0].documento
            f.explicacion = "Es el mismo avalúo que ya trae tu exógena."
        elif avaluos:
            f.tratamiento = "revisar"
            f.pregunta = (f"Tu exógena ya trae un inmueble con avalúo de {_pesos(avaluos[0].valor)} y este predial dice {_pesos(f.valor)}. "
                          "¿Es otro inmueble?")
            f.ayuda = "Si es el mismo inmueble, no lo sumo dos veces."
            f.opciones = [OpcionRevision(texto="Sí, es otro inmueble: súmalo", incluir=True, campo="patrimonio.bienes"),
                          OpcionRevision(texto="No, es el mismo", incluir=False, recomendada=True)]

    # 5. Lo que el certificado trae y la exógena no
    if any(f.fuente == "exogena" for f in filas):
        for doc_id in ids_nuevos:
            if doc_id not in etiquetas or etiquetas[doc_id].tipo in ("exogena", "declaracion_anterior", "desconocido"):
                continue
            entidad_filas = [f for f in filas if f.documento == doc_id and _cuenta(f) and f.campo]
            nuevos_campos = []
            for c in entidad_filas:
                if c.campo in ("laboral.salario_promedio_mensual_6m",):
                    continue
                if not any(e.fuente == "exogena" and e.campo == c.campo and (misma_entidad(c, e) or e.reemplazada_por == doc_id) for e in filas):
                    nombre = _NOMBRE_CAMPO.get(c.campo or "")
                    if nombre and nombre not in nuevos_campos:
                        nuevos_campos.append(nombre)
            if nuevos_campos:
                quien = etiquetas[doc_id].entidad or "el certificado"
                lista = nuevos_campos[0] if len(nuevos_campos) == 1 else ", ".join(nuevos_campos[:-1]) + " y " + nuevos_campos[-1]
                avisos.append(f"De {quien} también tomé {lista}, que la exógena no traía.")
    return filas, avisos
