/** Enlaces del chat: «[texto](url)» se vuelve un enlace solo si va a la DIAN; cualquier otro queda como texto. */

export interface Trozo {
  texto: string;
  href?: string;
}

const PERMITIDOS = ["dian.gov.co"];

export function enlaceOficial(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:") return null;
    return PERMITIDOS.some((d) => u.hostname === d || u.hostname.endsWith("." + d)) ? u.href : null;
  } catch {
    return null;
  }
}

const RE = /\[([^\]\n]{1,80})\]\((https?:\/\/[^\s)]+)\)/g;

/** Parte un párrafo en texto y enlaces. */
export function trozos(parrafo: string): Trozo[] {
  const salida: Trozo[] = [];
  let ultimo = 0;
  for (const m of parrafo.matchAll(RE)) {
    const i = m.index ?? 0;
    if (i > ultimo) salida.push({ texto: parrafo.slice(ultimo, i) });
    const href = enlaceOficial(m[2]);
    salida.push(href ? { texto: m[1], href } : { texto: m[1] });
    ultimo = i + m[0].length;
  }
  if (ultimo < parrafo.length) salida.push({ texto: parrafo.slice(ultimo) });
  return salida;
}

/** El texto tal como se lee (sin la sintaxis de los enlaces). */
export const textoPlano = (t: string) => t.replace(RE, "$1");
