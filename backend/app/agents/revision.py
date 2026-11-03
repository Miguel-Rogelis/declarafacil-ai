"""Preguntas en lenguaje sencillo para los datos de la exógena que hay que confirmar.

Parte del Intérprete. Cuando una fila no se puede ubicar con certeza, en lugar de mostrar
un menú con los nombres técnicos de la declaración, se arma una pregunta concreta
("¿Ese CDT seguía abierto el 31 de diciembre?") con dos o tres respuestas cortas, y se
marca la recomendada para quien no sepa qué contestar.
"""

import re
import unicodedata

from app.agents.base import FilaInterpretada, OpcionRevision
from app.tax import reglas as repo_reglas

_NOMBRES = {
    "laboral.salarios_y_pagos_laborales": "parte de tu salario",
    "laboral.cesantias_e_intereses": "cesantías",
    "independiente.honorarios_y_servicios": "honorarios por tu trabajo independiente",
    "capital.rendimientos_financieros": "intereses que te pagaron",
    "capital.arrendamientos": "arriendos que recibiste",
    "no_laborales.ingresos": "otros ingresos",
    "pensiones.pensiones_nacionales": "tu pensión",
    "dividendos.no_gravados_subcedula1": "dividendos",
    "dividendos.gravados_subcedula2": "dividendos gravados",
    "patrimonio.bienes": "algo que tenías (tu patrimonio)",
    "patrimonio.deudas": "una deuda",
    "pagos.retenciones_renta": "retención que te hicieron",
    "deducciones.medicina_prepagada": "medicina prepagada",
    "deducciones.intereses_vivienda": "intereses de vivienda",
    "deducciones.aportes_voluntarios_afc_fpv": "ahorro voluntario o AFC",
}

_FINANCIERA = re.compile(r"banco|bancolombia|davivienda|bbva|colpatria|scotiabank|itau|nequi|daviplata|fiduc|financ|cooperativ|fondo|credito|tarjeta|leasing|corporacion|caja")


def _n(t: str) -> str:
    s = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s)


def _pesos(v: float) -> str:
    return "$" + f"{abs(v):,.0f}".replace(",", ".")


def _corto(detalle: str) -> str:
    """'CDT  inversión efectuada (Titular secundario) (Concepto: 1020)' → 'CDT inversión efectuada'."""
    t = re.sub(r"\((concepto|titular|formato)[^)]*\)", "", detalle, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:1].lower() + t[1:] if t[:2] != t[:2].upper() else t


def _quien(f: FilaInterpretada) -> str:
    return (f.informante or "Una entidad").strip()


def _si(texto: str, campo: str | None, recomendada: bool = False) -> OpcionRevision:
    return OpcionRevision(texto=texto, incluir=True, campo=campo, recomendada=recomendada)


def _no(texto: str, recomendada: bool = False) -> OpcionRevision:
    return OpcionRevision(texto=texto, incluir=False, campo=None, recomendada=recomendada)


def preparar(f: FilaInterpretada, filas: list[FilaInterpretada], anio: int | None) -> None:
    """Llena pregunta, ayuda y opciones de una fila que hay que confirmar."""
    d = _n(f.detalle)
    quien, valor = _quien(f), _pesos(f.valor)
    del_mismo = [x for x in filas if x.informante == f.informante and x.id != f.id]

    if "aportes parafiscales" in d:
        f.pregunta = (f"{quien} reportó {valor} como aportes a salud, pensión, cesantías y parafiscales. "
                      "Esa plata está en los fondos, no a tu disposición, así que normalmente no se suma a tu patrimonio. ¿La dejo por fuera?")
        f.ayuda = "Tus cesantías ya las reporta tu fondo por aparte. Si tienes dudas, déjala por fuera y pregúntale a un contador."
        f.opciones = [_no("Sí, déjala por fuera", recomendada=True), _si("No, súmala a mi patrimonio", "patrimonio.bienes")]
    elif "cdt" in d or "inversion efectuada" in d:
        secundario = "secundario" in d
        f.pregunta = (f"{quien} reporta un CDT de {valor} abierto en {anio or 'el año'}"
                      + (", donde apareces como segundo titular" if secundario else "") + ". ¿Seguía abierto el 31 de diciembre?")
        f.ayuda = "Si seguía abierto, va en tu patrimonio. Si lo cerraste antes de fin de año, esa plata ya volvió a tu cuenta y no se cuenta dos veces."
        if secundario:
            f.opciones = [_si("Sí, y la plata es mía", "patrimonio.bienes"), _no("Sí, pero la plata es del titular principal"), _no("No, ya se había cerrado")]
        else:
            f.opciones = [_si("Sí, seguía abierto", "patrimonio.bienes", recomendada=True), _no("No, ya se había cerrado")]
    elif f.campo and f.campo.startswith("dividendos"):
        f.pregunta = f"{quien} te pagó {valor} en dividendos. ¿Son gravados o no gravados? Lo dice el certificado que te da la empresa."
        f.ayuda = "La mayoría de dividendos de personas naturales son no gravados."
        f.opciones = [_si("No gravados", "dividendos.no_gravados_subcedula1", recomendada=True), _si("Gravados", "dividendos.gravados_subcedula2"), _no("No me corresponden")]
    elif f.origen_mapeo == "ia" and f.campo:
        f.pregunta = f"{quien} reportó {valor} por «{_corto(f.detalle)}». Lo tomé como {_NOMBRES.get(f.campo, 'parte de tu declaración')}. ¿Está bien?"
        f.ayuda = f.explicacion
        f.opciones = [_si("Sí, está bien", f.campo, recomendada=True), _no("No, déjalo por fuera")]
    elif any((x.campo or "").startswith("laboral") for x in del_mismo):
        f.pregunta = f"Tu empleador, {quien}, reportó {valor} por «{_corto(f.detalle)}». ¿Fue parte de lo que te pagaron?"
        f.ayuda = "Todo lo que te paga tu empleador cuenta como ingreso, aunque no sea salario."
        f.opciones = [_si("Sí, me lo pagaron", "laboral.salarios_y_pagos_laborales", recomendada=True), _no("No me corresponde")]
    elif _FINANCIERA.search(_n(quien)):
        f.pregunta = f"{quien} reportó {valor} por «{_corto(f.detalle)}». ¿Qué es?"
        sugerido = ("capital.rendimientos_financieros" if re.search(r"interes|rendimiento", d)
                    else "patrimonio.deudas" if re.search(r"credito|prestamo|deuda|por pagar|pasivo", d)
                    else "patrimonio.bienes" if re.search(r"saldo|cuenta|inversion|ahorro|deposito", d) else None)
        f.opciones = [
            _si("Plata que tenía ahí", "patrimonio.bienes", sugerido == "patrimonio.bienes"),
            _si("Intereses que me pagaron", "capital.rendimientos_financieros", sugerido == "capital.rendimientos_financieros"),
            _si("Algo que les debía", "patrimonio.deudas", sugerido == "patrimonio.deudas"),
            _no("No me corresponde"),
        ]
    else:
        f.pregunta = f"{quien} reportó {valor} por «{_corto(f.detalle)}». ¿Qué es?"
        f.opciones = [_si("Plata que recibí", "no_laborales.ingresos"), _si("Algo que tenía", "patrimonio.bienes"),
                      _si("Algo que debía", "patrimonio.deudas"), _no("No me corresponde")]
    if not f.ayuda:
        f.ayuda = "Si no sabes, elige «No sé»: " + ("uso la opción recomendada." if any(o.recomendada for o in f.opciones) else "lo dejo por fuera y te lo recuerdo antes de firmar.")


def resolver_duplicados(filas: list[FilaInterpretada]) -> None:
    """Un CDT abierto en el año que el mismo banco ya reporta con su saldo a 31 de diciembre no se cuenta dos veces."""
    for f in filas:
        if f.tratamiento != "revisar" or "inversion efectuada" not in _n(f.detalle):
            continue
        if any(x.informante == f.informante and "saldo" in _n(x.detalle) and "cdt" in _n(x.detalle) and x.tratamiento == "suma" for x in filas):
            f.campo, f.tratamiento = None, "informativo"
            f.explicacion = "Ya está incluido en el saldo del CDT a 31 de diciembre que reportó el mismo banco."


_ALIMENTACION = re.compile(r"bonos? de alimentacion|vales? (de|para) alimentacion|tiquetes? de alimentacion|bonos? (electronicos|de papel) .*alimentacion")


def resolver_alimentacion(filas: list[FilaInterpretada], anio: int | None) -> None:
    """Bonos de alimentación del empleador (art. 387-1 ET).

    No son ingreso del trabajador si su salario no pasa de 310 UVT al mes y los bonos no
    pasan de 41 UVT al mes. Si el salario pasa de 310 UVT, sí son ingreso. Se usa el
    promedio mensual del año; si los bonos pasan el límite, se le pregunta al usuario.
    """
    try:
        uvt = float(repo_reglas.cargar(anio or 2025)["uvt"])
    except Exception:  # noqa: BLE001 - sin reglas del año, la fila queda para confirmar
        return
    for f in filas:
        if f.tratamiento != "revisar" or not _ALIMENTACION.search(_n(f.detalle)):
            continue
        salario = sum(x.valor for x in filas if x.informante == f.informante and x.campo == "laboral.salarios_y_pagos_laborales" and x.tratamiento == "suma")
        if not salario:
            continue
        if salario / 12 > 310 * uvt:
            f.campo, f.tratamiento, f.origen_mapeo = "laboral.salarios_y_pagos_laborales", "suma", "reglas"
            f.explicacion = "Como tu salario pasa de 310 UVT al mes, los bonos de alimentación sí cuentan como ingreso (art. 387-1 del Estatuto Tributario)."
        elif f.valor / 12 <= 41 * uvt:
            f.campo, f.tratamiento, f.origen_mapeo = None, "informativo", "reglas"
            f.explicacion = ("Tus bonos de alimentación no cuentan como ingreso: tu salario no pasa de 310 UVT al mes y los bonos no pasan "
                             "de 41 UVT al mes (art. 387-1 del Estatuto Tributario).")
