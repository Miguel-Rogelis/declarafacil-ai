/** Autorización de tratamiento de datos personales (Ley 1581 de 2012), antes de subir el primer documento.
 *  Se guarda en el navegador con su versión: si el texto cambia, se vuelve a pedir. */

export const VERSION_CONSENTIMIENTO = "2026-11";
const CLAVE = "df-consentimiento";

export function consentimientoDado(): boolean {
  try {
    const g = JSON.parse(localStorage.getItem(CLAVE) ?? "null") as { version?: string } | null;
    return g?.version === VERSION_CONSENTIMIENTO;
  } catch {
    return false;
  }
}

export function guardarConsentimiento(): void {
  try {
    localStorage.setItem(CLAVE, JSON.stringify({ version: VERSION_CONSENTIMIENTO, fecha: new Date().toISOString() }));
  } catch {
    /* sin almacenamiento: se volverá a preguntar */
  }
}

export function retirarConsentimiento(): void {
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    /* nada */
  }
}

type Responder = (acepta: boolean) => void;
let mostrar: ((responder: Responder) => void) | null = null;

/** El diálogo se registra al montarse; quien necesite el permiso lo pide con pedirConsentimiento(). */
export function registrarDialogo(f: (responder: Responder) => void): () => void {
  mostrar = f;
  return () => {
    if (mostrar === f) mostrar = null;
  };
}

export function pedirConsentimiento(): Promise<boolean> {
  if (consentimientoDado() || !mostrar) return Promise.resolve(consentimientoDado() || !mostrar);
  const abrir = mostrar;
  return new Promise((resolver) => abrir(resolver));
}
