const cop = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });

/** $1.234.567 (sin espacio, como lo escribe la DIAN). */
export const pesos = (v: number) => (v < 0 ? "-$" : "$") + cop.format(Math.abs(Math.round(v)));

export const fechaLarga = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString("es-CO", { day: "numeric", month: "long", year: "numeric" });

/** Convierte "1.234.567" o "1234567" en número. */
export const aNumero = (texto: string) => {
  const limpio = texto.replace(/[^\d]/g, "");
  return limpio ? Number(limpio) : 0;
};

export const NOMBRES_CAMPO: Record<string, string> = {
  "laboral.salarios_y_pagos_laborales": "Salarios",
  "laboral.cesantias_e_intereses": "Cesantías",
  "laboral.salario_promedio_mensual_6m": "Salario promedio 6 meses",
  "laboral.aportes_obligatorios_pension": "Aportes a pensión",
  "laboral.aportes_obligatorios_salud": "Aportes a salud",
  "laboral.aportes_voluntarios_rais": "Aportes voluntarios a pensión obligatoria",
  "independiente.honorarios_y_servicios": "Honorarios y servicios",
  "independiente.aportes_obligatorios_pension": "Aportes a pensión (independiente)",
  "independiente.aportes_obligatorios_salud": "Aportes a salud (independiente)",
  "capital.rendimientos_financieros": "Intereses y rendimientos",
  "capital.arrendamientos": "Arriendos",
  "capital.regalias_y_otros": "Otras rentas de capital",
  "no_laborales.ingresos": "Otros ingresos",
  "pensiones.pensiones_nacionales": "Pensiones",
  "pensiones.aportes_salud": "Salud del pensionado",
  "dividendos.no_gravados_subcedula1": "Dividendos no gravados",
  "dividendos.gravados_subcedula2": "Dividendos gravados",
  "ganancias_ocasionales.loterias_premios": "Premios y loterías",
  "ganancias_ocasionales.seguros_vida": "Seguros de vida",
  "ganancias_ocasionales.donaciones_recibidas": "Donaciones",
  "ganancias_ocasionales.herencia_porcion_heredero": "Herencias",
  "ganancias_ocasionales.utilidad_venta_otros_activos": "Venta de activos",
  "deducciones.medicina_prepagada": "Medicina prepagada",
  "deducciones.intereses_vivienda": "Intereses de vivienda",
  "deducciones.gmf_pagado": "4x1000",
  "deducciones.aportes_voluntarios_afc_fpv": "Aportes voluntarios y AFC",
  "deducciones.compras_factura_electronica": "Compras con factura electrónica",
  "deducciones.intereses_icetex": "Intereses del ICETEX",
  "pagos.impuesto_neto_anio_anterior": "Impuesto del año anterior",
  "pagos.retenciones_renta": "Retenciones",
  "pagos.saldo_favor_anterior": "Saldo a favor anterior",
  "pagos.anticipo_anio_anterior": "Anticipo del año anterior",
  "patrimonio.bienes": "Bienes",
  "patrimonio.deudas": "Deudas",
};

/** Grupos de la hoja de trabajo, en el orden en que se leen. */
export const GRUPOS: { titulo: string; prefijos: string[] }[] = [
  { titulo: "Ingresos", prefijos: ["laboral.salarios", "laboral.cesantias", "independiente.honorarios", "capital.", "no_laborales.", "pensiones.pensiones", "dividendos.", "ganancias_ocasionales."] },
  { titulo: "No paga impuesto", prefijos: ["laboral.aportes", "independiente.aportes", "pensiones.aportes"] },
  { titulo: "Deducciones", prefijos: ["deducciones."] },
  { titulo: "Patrimonio", prefijos: ["patrimonio.bienes"] },
  { titulo: "Deudas", prefijos: ["patrimonio.deudas"] },
  { titulo: "Lo que ya pagaste", prefijos: ["pagos."] },
];
