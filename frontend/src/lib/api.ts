// Tipos y llamadas a la API del backend (FastAPI).

export type Tratamiento = "suma" | "informativo" | "revisar";

export interface Fila {
  id: string;
  nit_informante: string | null;
  informante: string | null;
  detalle: string;
  valor: number;
  uso_sugerido: string | null;
  info_adicional: string | null;
  campo: string | null;
  tratamiento: Tratamiento;
  explicacion: string;
  origen_mapeo: "reglas" | "ia" | "sin_mapeo";
  pregunta?: string;
  ayuda?: string;
  opciones?: OpcionRevision[];
  /** Documento del que salió la cifra (huella) y su tipo: "exogena", "certificado_220", "certificado_bancario"… */
  documento?: string | null;
  fuente?: string;
  /** Si un certificado trae el mismo dato, esta fila queda como referencia. */
  reemplazada_por?: string | null;
}

export interface DocumentoCargado {
  id: string;
  nombre: string;
  tipo: string;
  etiqueta: string;
  entidad: string | null;
  nit: string | null;
  anio: number | null;
  cifras: number;
  resumen: string;
  pistas: string[];
}

export interface OpcionRevision {
  texto: string;
  incluir: boolean;
  campo: string | null;
  recomendada: boolean;
}

export interface Perfil {
  empleado: boolean;
  independiente: boolean;
  pensionado: boolean;
  rentas_capital: boolean;
  dividendos: boolean;
  ganancias_ocasionales: boolean;
  declaro_antes: boolean;
}

export interface Extraccion {
  anio: number | null;
  ultimos_dos_digitos_nit: string | null;
  filas: Fila[];
  datos: Record<string, unknown>;
  perfil: Perfil;
  resumen_campos: Record<string, number>;
  datos_enmascarados: number;
  topes: Record<string, number>;
  documentos?: DocumentoCargado[];
}

export interface EventoAgente {
  agente: string;
  nombre: string;
  estado: "inicio" | "ok" | "advertencia" | "error";
  mensaje: string;
  duracion_ms: number | null;
  modelo: string | null;
  usa_ia: boolean;
}

export interface Linea {
  clave: string;
  concepto: string;
  valor: number;
  norma: string | null;
  nota: string | null;
  campos: string[];
}

export interface Seccion {
  id: string;
  titulo: string;
  lineas: Linea[];
}

export interface Alerta {
  nivel: "info" | "advertencia" | "critica";
  titulo: string;
  detalle: string;
  origen: string;
}

export interface Resumen {
  patrimonio_bruto: number;
  deudas: number;
  patrimonio_liquido: number;
  ingresos_brutos_totales: number;
  renta_liquida_gravable: number;
  impuesto_renta: number;
  descuentos: number;
  impuesto_neto_renta: number;
  impuesto_ganancias_ocasionales: number;
  total_impuesto_cargo: number;
  anticipo_siguiente: number;
  anticipo_anterior: number;
  saldo_favor_anterior: number;
  retenciones: number;
  saldo_pagar: number;
  saldo_favor: number;
  sancion: number;
  total_a_pagar: number;
}

export interface Casilla {
  numero: number;
  nombre: string;
  valor: number;
  /** dato: se escribe (o se compara con la sugerida); calculada: la calcula MUISCA sola; informativa */
  tipo: "dato" | "calculada" | "informativa";
  formula: string | null;
  campos: string[];
  nota: string | null;
  texto: string | null;
}

export interface Formulario210 {
  numero: string;
  anio_gravable: number;
  disponible: boolean;
  motivo: string;
  secciones: { id: string; titulo: string; casillas: Casilla[] }[];
  pago_total: number;
  notas: string[];
}

export interface Liquidacion {
  anio_gravable: number;
  uvt: number;
  obligacion: { obligado: boolean; razones: string[]; topes: { tope: string; valor: number; limite: number; supera: boolean }[] };
  resumen: Resumen;
  secciones: Seccion[];
  alertas: Alerta[];
  vencimiento: { fecha: string; fecha_presentacion: string; extemporanea: boolean; meses_retraso: number } | null;
  opcion_independiente: string | null;
  formulario: Formulario210 | null;
}

export interface ItemPatrimonio {
  concepto: string;
  valor: number;
  fuente?: string | null;
}

export interface GananciasOcasionales {
  utilidad_venta_casa_habitacion: number;
  cumple_requisitos_exencion_casa: boolean;
  utilidad_venta_otros_activos: number;
  herencia_vivienda_causante: number;
  herencia_otros_inmuebles: number;
  herencia_porcion_heredero: number;
  donaciones_recibidas: number;
  seguros_vida: number;
  loterias_premios: number;
}

export interface Respuestas {
  dependientes: number;
  salarios_no_reportados: number;
  retenciones_no_reportadas: number;
  dividendos_no_reportados: number;
  medicina_prepagada: number;
  intereses_vivienda: number;
  aportes_voluntarios_afc_fpv: number;
  gmf_pagado: number;
  intereses_icetex: number;
  honorarios_no_reportados: number;
  costos_independiente: number;
  arriendos_no_reportados: number;
  costos_arriendos: number;
  otros_ingresos_no_reportados: number;
  pensiones_no_reportadas: number;
  dividendos_gravados: number;
  ganancias_ocasionales: GananciasOcasionales;
  donaciones_realizadas: number;
  bienes_adicionales: ItemPatrimonio[];
  deudas_adicionales: ItemPatrimonio[];
  declaraciones_previas: number | null;
  impuesto_neto_anio_anterior: number;
  anticipo_anio_anterior: number;
  ultimos_dos_digitos_nit: string | null;
  sin_sanciones_ultimos_2_anios: boolean;
  responsable_iva: boolean;
}

export const respuestasIniciales = (): Respuestas => ({
  dependientes: 0,
  salarios_no_reportados: 0,
  retenciones_no_reportadas: 0,
  dividendos_no_reportados: 0,
  medicina_prepagada: 0,
  intereses_vivienda: 0,
  aportes_voluntarios_afc_fpv: 0,
  gmf_pagado: 0,
  intereses_icetex: 0,
  honorarios_no_reportados: 0,
  costos_independiente: 0,
  arriendos_no_reportados: 0,
  costos_arriendos: 0,
  donaciones_realizadas: 0,
  otros_ingresos_no_reportados: 0,
  pensiones_no_reportadas: 0,
  dividendos_gravados: 0,
  ganancias_ocasionales: {
    utilidad_venta_casa_habitacion: 0,
    cumple_requisitos_exencion_casa: true,
    utilidad_venta_otros_activos: 0,
    herencia_vivienda_causante: 0,
    herencia_otros_inmuebles: 0,
    herencia_porcion_heredero: 0,
    donaciones_recibidas: 0,
    seguros_vida: 0,
    loterias_premios: 0,
  },
  bienes_adicionales: [],
  deudas_adicionales: [],
  declaraciones_previas: null,
  impuesto_neto_anio_anterior: 0,
  anticipo_anio_anterior: 0,
  ultimos_dos_digitos_nit: null,
  sin_sanciones_ultimos_2_anios: true,
  responsable_iva: false,
});

export interface ResultadoDocumento {
  extraccion: Extraccion;
  nuevos: DocumentoCargado[];
  cruces: string[];
  errores: { nombre: string; mensaje: string }[];
  /** Lo que el agente cuenta apenas lee los documentos (lo escribe el código). */
  mensaje: string;
  clasificacion: Partial<{ es_exogena: boolean; anio: number | null; confianza: number; motivo: string; modelo: string | null }>;
  traza: EventoAgente[];
}

export interface ResultadoLiquidacion {
  datos: Record<string, unknown>;
  liquidacion: Liquidacion;
  explicacion: string;
  explicacion_con_ia: boolean;
  traza: EventoAgente[];
}

export interface AnioDisponible {
  anio_gravable: number;
  estado: string;
  uvt: number;
  descripcion: string;
}

export interface Estado {
  modo_llm: string;
  anios: AnioDisponible[];
  admin_protegido: boolean;
}

export interface AgenteConfig {
  nombre: string;
  responsabilidad: string;
  usa_ia: boolean;
  activo: boolean;
  modelos?: string[];
  temperatura?: number;
}

export interface EstadoChat {
  pantalla: string;
  anio_gravable: number;
  tiene_exogena: boolean;
  anio_exogena: number | null;
  perfil: Partial<Perfil>;
  resumen_exogena: Record<string, number>;
  por_revisar: string[];
  filas: Fila[];
  topes: Record<string, number>;
  respuestas: Respuestas;
  resultado: Record<string, unknown> | null;
  pregunta_pendiente: PreguntaPendiente | null;
  ya_preguntado: string[];
  documentos: DocumentoCargado[];
  recien: string[];
}

export interface PreguntaPendiente {
  texto: string;
  temas: string[];
  intencion: "calcular" | "obligacion" | "vencimiento" | "simular" | null;
  campo: string | null;
  valor: number | null;
  concepto?: string | null;
  simular: Record<string, unknown>[];
  rondas?: number;
  intro?: string;
  partes?: ParteDePregunta[];
}

export interface ParteDePregunta {
  tema: string;
  texto: string;
  opciones: string[];
}

export interface Simulacion {
  cambios: string[];
  impuesto_antes: number;
  impuesto_despues: number;
  total_antes: number;
  total_despues: number;
  favor_antes: number;
  favor_despues: number;
}

export interface Anotacion {
  clave: string;
  etiqueta: string;
  valor: string;
  detalle: string | null;
}

export interface RespuestaChat {
  respuesta: string;
  respuestas: Respuestas;
  anotaciones: Anotacion[];
  quitadas: string[];
  rechazadas: string[];
  widgets: string[];
  cambiar_anio: number | null;
  calcular: boolean;
  simulacion: Simulacion | null;
  pregunta: PreguntaPendiente | null;
  pregunta_nueva?: boolean;
  texto_visible?: string;
  ya_preguntado: string[];
  fuentes: string[];
  modelo: string | null;
  con_ia: boolean;
}

type Manejadores<R> = {
  onAgente: (e: EventoAgente) => void;
  onResultado: (r: R) => void;
  onError: (mensaje: string) => void;
};

/** Lee una respuesta Server-Sent Events de un POST y despacha cada evento. */
async function flujo<R>(url: string, init: RequestInit, m: Manejadores<R>): Promise<void> {
  let resp: Response;
  try {
    resp = await fetch(url, { ...init, headers: { Accept: "text/event-stream", ...(init.headers || {}) } });
  } catch {
    m.onError("No hay conexión con el servidor. Si acaba de despertar, espera unos segundos y vuelve a intentar.");
    return;
  }
  if (!resp.ok || !resp.body) {
    let detalle = `El servidor respondió ${resp.status}.`;
    try {
      const j = await resp.json();
      if (j?.detail) detalle = typeof j.detail === "string" ? j.detail : "Revisa los datos enviados.";
    } catch {
      /* sin cuerpo JSON */
    }
    m.onError(detalle);
    return;
  }
  const lector = resp.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    let corte: number;
    while ((corte = buffer.indexOf("\n\n")) >= 0) {
      const bloque = buffer.slice(0, corte);
      buffer = buffer.slice(corte + 2);
      let tipo = "message";
      const datos: string[] = [];
      for (const linea of bloque.split("\n")) {
        if (linea.startsWith("event:")) tipo = linea.slice(6).trim();
        else if (linea.startsWith("data:")) datos.push(linea.slice(5).trimStart());
      }
      if (!datos.length) continue;
      const payload = JSON.parse(datos.join("\n"));
      if (tipo === "agente") m.onAgente(payload);
      else if (tipo === "resultado") m.onResultado(payload);
      else if (tipo === "error") m.onError(payload.mensaje ?? "Algo falló en el proceso.");
    }
  }
}

/** Lo que ya se había leído: los documentos nuevos se cruzan con esto en el servidor. */
export interface Previas {
  filas: Fila[];
  topes: Record<string, number>;
  documentos: DocumentoCargado[];
  ultimos_dos_digitos_nit: string | null;
  anio: number | null;
  datos_enmascarados: number;
}

export function analizarDocumentos(archivos: File[], anio: number, previas: Previas | null, m: Manejadores<ResultadoDocumento>) {
  const fd = new FormData();
  archivos.forEach((a) => fd.append("archivos", a));
  fd.append("anio_gravable", String(anio));
  if (previas) fd.append("previas", JSON.stringify(previas));
  return flujo("/api/documentos/analizar", { method: "POST", body: fd }, m);
}

export function liquidar(
  cuerpo: { anio_gravable: number; filas: Fila[]; topes: Record<string, number>; ultimos_dos_digitos_nit: string | null; respuestas: Respuestas; fecha_presentacion?: string },
  m: Manejadores<ResultadoLiquidacion>,
) {
  return flujo("/api/declaracion/liquidar", { method: "POST", body: JSON.stringify(cuerpo), headers: { "Content-Type": "application/json" } }, m);
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let detalle = `Error ${r.status}`;
    try {
      const j = await r.json();
      if (j?.detail) detalle = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* nada */
    }
    throw new Error(detalle);
  }
  return r.json() as Promise<T>;
}

export const api = {
  estado: () => json<Estado>("/api/estado"),
  reglas: (anio: number) => json<Record<string, unknown>>(`/api/reglas/${anio}`),
  guardarReglas: (anio: number, datos: Record<string, unknown>, token: string) =>
    json<Record<string, unknown>>(`/api/reglas/${anio}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Admin-Token": token },
      body: JSON.stringify(datos),
    }),
  clonarReglas: (anio: number, destino: number, uvt: number | null, token: string) =>
    json<Record<string, unknown>>(`/api/reglas/${anio}/clonar`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": token },
      body: JSON.stringify({ destino, uvt }),
    }),
  agentes: () => json<Record<string, AgenteConfig>>("/api/agentes"),
  guardarAgente: (id: string, cambios: Partial<AgenteConfig>, token: string) =>
    json<AgenteConfig>(`/api/agentes/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Admin-Token": token },
      body: JSON.stringify(cambios),
    }),
  probarAgente: (id: string) => json<{ ok: boolean; modelo?: string; detalle?: string }>(`/api/agentes/${id}/probar`, { method: "POST" }),
  modelosGratis: () => json<{ id: string; nombre: string; contexto: number }[]>("/api/agentes/modelos-gratis"),
  diagnostico: (estado: EstadoChat) =>
    json<RespuestaChat>("/api/chat/diagnostico", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(estado),
    }),
  chat: (mensaje: string, historial: { rol: string; texto: string }[], estado: EstadoChat) =>
    json<RespuestaChat>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje, historial, estado }),
    }),
  exogenaDemo: async (): Promise<File> => {
    const r = await fetch("/api/demo/exogena");
    if (!r.ok) throw new Error("No se pudo descargar el ejemplo");
    const b = await r.blob();
    return new File([b], "exogena_demo_2025.xlsx", { type: b.type });
  },
  /** Exógena y certificados ficticios, para probar sin datos reales. */
  documentosDemo: async (): Promise<File[]> => {
    const nombres = await json<string[]>("/api/demo/archivos");
    return Promise.all(
      nombres.map(async (n) => {
        const r = await fetch(`/api/demo/archivo/${encodeURIComponent(n)}`);
        if (!r.ok) throw new Error("No se pudo descargar el ejemplo");
        const b = await r.blob();
        return new File([b], n, { type: b.type });
      }),
    );
  },
};
