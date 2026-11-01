"""Agente Explicador: resumen en lenguaje simple.

El modelo recibe SOLO cifras ya calculadas. Después se verifica que cada cifra en
pesos que escribió exista en el cálculo; si inventó alguna, se usa la plantilla.
"""

import re

from app.llm import cliente
from app.tax.modelos import Alerta, Liquidacion
from app.tax.motor import cop

SISTEMA = """Eres el agente Explicador de DeclaraFácil, un asistente de renta para personas naturales en Colombia.
Explica el resultado a alguien sin formación contable, en español claro, segunda persona (tú), 90 a 140 palabras, 2 párrafos cortos, sin títulos ni viñetas.
Reglas estrictas:
- Usa ÚNICAMENTE las cifras que aparecen en DATOS, escritas igual ($1.234.000). No calcules ni redondees cifras nuevas.
- Di si debe pagar o si le queda saldo a favor, y la causa principal.
- Si hay alertas críticas, menciónalas en una frase.
- Termina recordando que es un borrador que debe revisar y firmar en la DIAN."""


def _plantilla(liq: Liquidacion) -> str:
    r = liq.resumen
    partes = []
    if liq.obligacion.obligado:
        partes.append("Estás obligado a declarar renta este año.")
    else:
        partes.append("Según los topes, no estás obligado a declarar, pero puedes hacerlo de forma voluntaria.")
    partes.append(
        f"Tus ingresos del año suman {cop(r.ingresos_brutos_totales)}. Después de restar aportes, rentas exentas y deducciones, "
        f"tu renta líquida gravable queda en {cop(r.renta_liquida_gravable)} y el impuesto a cargo en {cop(r.total_impuesto_cargo)}."
    )
    if r.sancion:
        partes.append(f"Como la declaración está vencida, se suma una sanción estimada de {cop(r.sancion)}.")
    if r.saldo_pagar > 0:
        partes.append(
            f"Descontando las retenciones de {cop(r.retenciones)} que ya te hicieron, te queda un saldo a pagar de {cop(r.saldo_pagar)}"
            + (f", que incluye un anticipo de {cop(r.anticipo_siguiente)} para el próximo año." if r.anticipo_siguiente else ".")
        )
    elif r.saldo_favor > 0:
        partes.append(f"Lo que ya pagaste por retenciones supera lo que debes, así que te queda un saldo a favor de {cop(r.saldo_favor)}.")
    else:
        partes.append("No te queda saldo a pagar ni a favor.")
    partes.append("Es un borrador: revísalo y fírmalo tú en el portal de la DIAN.")
    return " ".join(partes)


def _cifras_permitidas(liq: Liquidacion) -> set[int]:
    valores = set(int(v) for v in liq.resumen.model_dump().values() if isinstance(v, (int, float)))
    for s in liq.secciones:
        for ln in s.lineas:
            valores.add(int(ln.valor))
    return valores


def verificar_cifras(texto: str, permitidas: set[int]) -> list[str]:
    """Devuelve las cifras en pesos del texto que NO existen en el cálculo."""
    invalidas = []
    for m in re.finditer(r"\$\s?([\d.]{4,})", texto):
        n = int(m.group(1).replace(".", "").rstrip("."))
        if n not in permitidas:
            invalidas.append(m.group(0))
    return invalidas


async def explicar(liq: Liquidacion, alertas: list[Alerta]) -> tuple[str, str | None, bool]:
    """Devuelve (texto, modelo usado, se_uso_ia)."""
    if not cliente.disponible():
        return _plantilla(liq), None, False
    r = liq.resumen
    datos = {
        "obligado_a_declarar": liq.obligacion.obligado,
        "ingresos_brutos": cop(r.ingresos_brutos_totales),
        "patrimonio_liquido": cop(r.patrimonio_liquido),
        "renta_liquida_gravable": cop(r.renta_liquida_gravable),
        "impuesto_a_cargo": cop(r.total_impuesto_cargo),
        "retenciones": cop(r.retenciones),
        "anticipo_proximo_anio": cop(r.anticipo_siguiente),
        "saldo_a_pagar": cop(r.saldo_pagar),
        "saldo_a_favor": cop(r.saldo_favor),
        "sancion_estimada": cop(r.sancion),
        "total_a_pagar": cop(r.total_a_pagar),
        "alertas_criticas": [a.titulo for a in alertas if a.nivel == "critica"],
    }
    try:
        resp = await cliente.completar("explicador", SISTEMA, f"DATOS: {datos}", max_tokens=500)
    except Exception:  # noqa: BLE001
        return _plantilla(liq), None, False
    texto = resp.texto.strip()
    if verificar_cifras(texto, _cifras_permitidas(liq)) or len(texto) < 60:
        return _plantilla(liq), resp.modelo, False
    return texto, resp.modelo, True
