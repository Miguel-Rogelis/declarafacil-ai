import type { EventoAgente, Extraccion, Fila, ItemFicha, PreguntaPendiente, Respuestas, ResultadoLiquidacion } from "./api";
import type { Mensaje } from "./estado";

/** Lo que se guarda de una conversación: basta para seguir donde se iba (en este navegador o en la nube). */
export interface Instantanea {
  v: 1;
  guardada: string;
  anio: number;
  extraccion: Extraccion | null;
  filas: Fila[];
  decididas: Record<string, boolean>;
  elecciones: Record<string, string>;
  trazaDocumento: EventoAgente[];
  respuestas: Respuestas;
  resultado: ResultadoLiquidacion | null;
  mensajes: Mensaje[];
  conversacion: { pregunta: PreguntaPendiente | null; ya: string[]; descartados: string[] };
  ficha: ItemFicha[];
}

const CLAVE = "df-sesion-v1";

/** Lee la sesión guardada en este navegador (null si no hay o si el almacenamiento está bloqueado). */
export function leerLocal(): Instantanea | null {
  try {
    const crudo = localStorage.getItem(CLAVE);
    if (!crudo) return null;
    const s = JSON.parse(crudo) as Instantanea;
    return s?.v === 1 && Array.isArray(s.mensajes) ? s : null;
  } catch {
    return null;
  }
}

export function guardarLocal(s: Instantanea): void {
  try {
    if (!s.mensajes.length && !s.extraccion) localStorage.removeItem(CLAVE);
    else localStorage.setItem(CLAVE, JSON.stringify(s));
  } catch {
    /* almacenamiento lleno o bloqueado: la app sigue sin guardar */
  }
}

export function borrarLocal(): void {
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    /* nada que borrar */
  }
}

/** Los mensajes que se restauran no se vuelven a «escribir»: aparecen quietos. */
export const sinAnimar = (ms: Mensaje[]): Mensaje[] => ms.map(({ nuevo: _nuevo, ...m }) => m);
