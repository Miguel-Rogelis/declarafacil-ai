"""Modelos de entrada y salida del motor tributario.

Todos los valores monetarios están en pesos colombianos (COP) del año gravable.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class RentasTrabajoLaboral(BaseModel):
    salarios_y_pagos_laborales: float = 0
    cesantias_e_intereses: float = 0
    salario_promedio_mensual_6m: float = Field(
        default=0, description="Ingreso mensual promedio de los últimos 6 meses (para la exención de cesantías)"
    )
    aportes_obligatorios_pension: float = 0
    aportes_obligatorios_salud: float = 0
    aportes_voluntarios_rais: float = 0


class RentasTrabajoIndependiente(BaseModel):
    honorarios_y_servicios: float = 0
    aportes_obligatorios_pension: float = 0
    aportes_obligatorios_salud: float = 0
    costos_gastos_procedentes: float = 0
    opcion: Literal["auto", "costos", "renta_exenta_25"] = "auto"


class RentasCapital(BaseModel):
    rendimientos_financieros: float = 0
    arrendamientos: float = 0
    regalias_y_otros: float = 0
    costos_gastos_procedentes: float = 0


class RentasNoLaborales(BaseModel):
    ingresos: float = 0
    ingresos_no_constitutivos: float = 0
    costos_gastos_procedentes: float = 0


class Pensiones(BaseModel):
    pensiones_nacionales: float = 0
    aportes_salud: float = 0


class Dividendos(BaseModel):
    no_gravados_subcedula1: float = Field(default=0, description="Dividendos de utilidades no gravadas (art. 49 num. 3)")
    gravados_subcedula2: float = Field(default=0, description="Dividendos de utilidades gravadas (par. 2 art. 49)")


class GananciasOcasionales(BaseModel):
    utilidad_venta_casa_habitacion: float = 0
    cumple_requisitos_exencion_casa: bool = True
    utilidad_venta_otros_activos: float = 0
    herencia_vivienda_causante: float = 0
    herencia_otros_inmuebles: float = 0
    herencia_porcion_heredero: float = 0
    donaciones_recibidas: float = 0
    seguros_vida: float = 0
    loterias_premios: float = 0


class Deducciones(BaseModel):
    dependientes: int = Field(default=0, ge=0, le=10)
    medicina_prepagada: float = 0
    intereses_vivienda: float = 0
    gmf_pagado: float = 0
    aportes_voluntarios_afc_fpv: float = 0
    compras_factura_electronica: float = 0
    intereses_icetex: float = 0


class Descuentos(BaseModel):
    """Lo que se resta directamente del impuesto (arts. 257 y 258 ET)."""

    donaciones: float = Field(default=0, description="Donaciones a entidades sin ánimo de lucro del régimen especial (25 %)")
    donaciones_alimentos: float = Field(default=0, description="Donaciones de alimentos a bancos de alimentos (37 % desde 2025)")


class RentasExterior(BaseModel):
    """Rentas de fuente extranjera de un residente, en pesos (TRM de cada pago o del 31 de diciembre)."""

    salarios: float = Field(default=0, description="Salarios pagados por un empleador del exterior (casilla 32)")
    honorarios: float = Field(default=0, description="Honorarios o servicios cobrados en el exterior")
    rentas_capital: float = Field(default=0, description="Intereses, arriendos o regalías del exterior (casilla 58)")
    otras_rentas: float = Field(default=0, description="Otras rentas no laborales del exterior (casilla 74)")
    pensiones: float = Field(default=0, description="Pensiones del exterior (casilla 99)")
    dividendos: float = Field(default=0, description="Dividendos de sociedades del exterior (casilla 109)")
    dividendos_exentos: float = Field(default=0, description="Parte exenta de esos dividendos, p. ej. de la Comunidad Andina (casilla 110)")
    ganancias_ocasionales: float = Field(default=0, description="Ganancias ocasionales del exterior (casilla 112)")
    impuesto_pagado_renta: float = Field(default=0, description="Impuesto de renta pagado en el exterior sobre esas rentas (art. 254 ET)")
    impuesto_pagado_go: float = Field(default=0, description="Impuesto pagado en el exterior sobre ganancias ocasionales")
    ece_rentas_pasivas_capital: float = Field(default=0, description="Rentas pasivas de capital de una ECE (casilla 62, arts. 882-893 ET)")
    ece_rentas_pasivas_no_laborales: float = Field(default=0, description="Rentas pasivas no laborales de una ECE (casilla 79)")


class Perdidas(BaseModel):
    """Pérdidas fiscales de años anteriores que aún se pueden compensar (12 años, arts. 147 y 330 ET)."""

    trabajo_no_laboral: float = Field(default=0, description="De rentas de trabajo sin relación laboral (casilla 56)")
    capital: float = Field(default=0, description="De rentas de capital (casilla 72)")
    no_laborales: float = Field(default=0, description="De rentas no laborales (casilla 89)")
    anios_2018_y_anteriores: float = Field(default=0, description="De los años gravables 2018 y anteriores (casilla 94)")


class ComparacionPatrimonial(BaseModel):
    """Datos para la renta por comparación patrimonial (arts. 236 a 239 ET)."""

    patrimonio_liquido_anterior: float | None = Field(default=None, description="Patrimonio líquido del 31 de diciembre del año anterior")
    impuestos_pagados_en_el_anio: float | None = Field(default=None, description="Impuesto de renta pagado durante el año (art. 237)")
    causas_justificativas: float = Field(default=0, description="Aumentos que la persona puede probar: valorizaciones, ingresos no gravados, préstamos…")


class ItemPatrimonio(BaseModel):
    concepto: str
    valor: float
    fuente: str | None = None


class Patrimonio(BaseModel):
    bienes: list[ItemPatrimonio] = []
    deudas: list[ItemPatrimonio] = []


class Indicadores(BaseModel):
    """Valores que solo sirven para decidir si la persona está obligada a declarar."""

    consumos_tarjeta_credito: float = 0
    compras_consumos: float = 0
    consignaciones_depositos_inversiones: float = 0
    responsable_iva: bool = False
    ingresos_reportados_exogena: float = 0
    patrimonio_reportado_exogena: float = 0


class Pagos(BaseModel):
    retenciones_renta: float = 0
    anticipo_anio_anterior: float = 0
    saldo_favor_anterior: float = 0
    declaraciones_previas: int = Field(default=0, ge=0, description="0 = es la primera vez que declara")
    impuesto_neto_anio_anterior: float = 0


class Control(BaseModel):
    ultimos_dos_digitos_nit: str | None = Field(default=None, pattern=r"^\d{2}$")
    fecha_presentacion: date | None = None
    sin_sanciones_ultimos_2_anios: bool = True


class DatosDeclaracion(BaseModel):
    anio_gravable: int = 2025
    laboral: RentasTrabajoLaboral = RentasTrabajoLaboral()
    independiente: RentasTrabajoIndependiente = RentasTrabajoIndependiente()
    capital: RentasCapital = RentasCapital()
    no_laborales: RentasNoLaborales = RentasNoLaborales()
    pensiones: Pensiones = Pensiones()
    dividendos: Dividendos = Dividendos()
    ganancias_ocasionales: GananciasOcasionales = GananciasOcasionales()
    deducciones: Deducciones = Deducciones()
    descuentos: Descuentos = Descuentos()
    exterior: RentasExterior = RentasExterior()
    perdidas: Perdidas = Perdidas()
    comparacion: ComparacionPatrimonial = ComparacionPatrimonial()
    patrimonio: Patrimonio = Patrimonio()
    indicadores: Indicadores = Indicadores()
    pagos: Pagos = Pagos()
    control: Control = Control()
    fuentes: dict[str, list[str]] = Field(
        default={}, description="Campo → ids de filas de la exógena (o 'usuario') de donde salió el valor"
    )


# ---------- Salida ----------


class Linea(BaseModel):
    clave: str
    concepto: str
    valor: float
    norma: str | None = None
    nota: str | None = None
    campos: list[str] = []


class Seccion(BaseModel):
    id: str
    titulo: str
    lineas: list[Linea]


class Alerta(BaseModel):
    nivel: Literal["info", "advertencia", "critica"]
    titulo: str
    detalle: str
    origen: str = "motor"


class TopeObligacion(BaseModel):
    tope: str
    valor: float
    limite: float
    supera: bool


class Obligacion(BaseModel):
    obligado: bool
    razones: list[str]
    topes: list[TopeObligacion]


class Vencimiento(BaseModel):
    fecha: date
    fecha_presentacion: date
    extemporanea: bool
    meses_retraso: int


class Resumen(BaseModel):
    patrimonio_bruto: float
    deudas: float
    patrimonio_liquido: float
    ingresos_brutos_totales: float
    renta_liquida_gravable: float
    impuesto_renta: float
    descuentos: float
    impuesto_neto_renta: float
    impuesto_ganancias_ocasionales: float
    total_impuesto_cargo: float
    anticipo_siguiente: float
    anticipo_anterior: float
    saldo_favor_anterior: float
    retenciones: float
    saldo_pagar: float
    saldo_favor: float
    sancion: float
    total_a_pagar: float


# ---------- Formulario 210 casilla por casilla ----------

TipoCasilla = Literal["dato", "calculada", "informativa"]


class Casilla(BaseModel):
    numero: int
    nombre: str
    valor: float
    tipo: TipoCasilla = "dato"  # dato: se escribe (o se revisa contra la sugerida); calculada: la calcula MUISCA
    formula: str | None = None
    campos: list[str] = []  # datos de la declaración de donde sale (para mostrar su origen)
    nota: str | None = None
    texto: str | None = None  # para casillas que no son pesos ("Sí" / "No", número de personas)


class SeccionFormulario(BaseModel):
    id: str
    titulo: str
    casillas: list[Casilla]


class Formulario(BaseModel):
    numero: str = "210"
    anio_gravable: int
    disponible: bool = True
    motivo: str = ""
    secciones: list[SeccionFormulario] = []
    pago_total: float = 0
    notas: list[str] = []



class Liquidacion(BaseModel):
    anio_gravable: int
    uvt: float
    obligacion: Obligacion
    resumen: Resumen
    secciones: list[Seccion]
    alertas: list[Alerta]
    vencimiento: Vencimiento | None = None
    opcion_independiente: str | None = None
    formulario: Formulario | None = None
