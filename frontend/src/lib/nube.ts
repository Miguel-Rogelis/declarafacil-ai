import type { Session, SupabaseClient, User } from "@supabase/supabase-js";
import type { Instantanea } from "./guardado";

/** Cuentas y guardado en la nube con Supabase. Solo se carga si el servidor trae su configuración. */

export interface Cuenta {
  id: string;
  nombre: string;
  correo: string;
  foto: string | null;
}

let cliente: SupabaseClient | null = null;
let sesion: Session | null = null;

const aCuenta = (u: User): Cuenta => ({
  id: u.id,
  nombre: (u.user_metadata?.full_name as string) || (u.user_metadata?.name as string) || (u.email ?? "").split("@")[0],
  correo: u.email ?? "",
  foto: (u.user_metadata?.avatar_url as string) || null,
});

/** El token de la sesión, para que el servidor sepa quién pregunta (cupo de IA propio). */
export const tokenActual = () => sesion?.access_token ?? null;

let googleId: string | null = null;

export async function iniciarNube(url: string, clave: string, alCambiar: (c: Cuenta | null) => void, idGoogle?: string | null): Promise<void> {
  googleId = idGoogle || null;
  if (cliente) return;
  const { createClient } = await import("@supabase/supabase-js");
  cliente = createClient(url, clave, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
  const { data } = await cliente.auth.getSession();
  sesion = data.session;
  alCambiar(sesion?.user ? aCuenta(sesion.user) : null);
  cliente.auth.onAuthStateChange((_evento, s) => {
    sesion = s;
    alCambiar(s?.user ? aCuenta(s.user) : null);
  });
}

/** Vuelve a esta misma página (GitHub Pages o Render) con la sesión iniciada. */
const regreso = () => window.location.origin + window.location.pathname;

export async function entrarConGoogle(): Promise<void> {
  if (!cliente) throw new Error("Las cuentas no están activas");
  const { error } = await cliente.auth.signInWithOAuth({ provider: "google", options: { redirectTo: regreso() } });
  if (error) throw new Error(error.message);
}

// ---------- Botón oficial de Google (Google Identity Services) ----------
// Google inicia sesión directo en esta página y le pasa a Supabase el token: la ventana y el correo
// de aviso dicen «DeclaraFácil» y esta dirección, no la de Supabase.

interface CredencialGoogle {
  credential: string;
}
interface GoogleId {
  initialize: (o: Record<string, unknown>) => void;
  renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

export const googleDirecto = () => !!googleId;

let gis: Promise<GoogleId> | null = null;
function cargarGis(): Promise<GoogleId> {
  if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
  gis ??= new Promise<GoogleId>((ok, mal) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => (window.google?.accounts?.id ? ok(window.google.accounts.id) : mal(new Error("Google no cargó")));
    s.onerror = () => mal(new Error("Google no cargó"));
    document.head.appendChild(s);
    window.setTimeout(() => mal(new Error("Google tardó demasiado")), 8000);
  }).catch((e) => {
    gis = null;
    throw e;
  });
  return gis;
}

async function nonce(): Promise<[string, string]> {
  const crudo = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(24)))).replace(/[+/=]/g, "");
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(crudo));
  return [crudo, [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("")];
}

/** Pone el botón de Google en «el». Devuelve false si no se pudo (entonces se usa el botón de siempre). */
export async function botonGoogle(el: HTMLElement, o: { oscuro: boolean; alFallar: (m: string) => void }): Promise<boolean> {
  if (!googleId || !cliente) return false;
  try {
    const id = await cargarGis();
    const [crudo, conHash] = await nonce();
    id.initialize({
      client_id: googleId,
      nonce: conHash,
      ux_mode: "popup",
      use_fedcm_for_button: true,
      callback: async ({ credential }: CredencialGoogle) => {
        const { error } = await cliente!.auth.signInWithIdToken({ provider: "google", token: credential, nonce: crudo });
        if (error) o.alFallar("Google respondió, pero no pude abrir tu sesión. Intenta de nuevo o entra con tu correo.");
      },
    });
    el.replaceChildren();
    id.renderButton(el, {
      type: "standard",
      theme: o.oscuro ? "filled_black" : "outline",
      size: "large",
      text: "continue_with",
      shape: "pill",
      logo_alignment: "left",
      locale: "es",
      width: Math.min(400, Math.max(220, Math.round(el.getBoundingClientRect().width))),
    });
    return true;
  } catch {
    return false;
  }
}

export async function entrarConCorreo(correo: string): Promise<void> {
  if (!cliente) throw new Error("Las cuentas no están activas");
  const { error } = await cliente.auth.signInWithOtp({ email: correo, options: { emailRedirectTo: regreso() } });
  if (error) throw new Error(error.message);
}

export async function salir(): Promise<void> {
  await cliente?.auth.signOut();
}

// Una fila por persona y año en la tabla «declaraciones» (con RLS: cada quien ve solo las suyas)
const sinColumnaAnio = (e: { code?: string; message?: string } | null) => !!e && (e.code === "42703" || e.code === "PGRST204" || /anio/.test(e.message ?? ""));

/** La declaración de un año (o la más reciente si no se dice el año). */
export async function leerDeLaNube(anio?: number): Promise<Instantanea | null> {
  if (!cliente || !sesion) return null;
  let q = cliente.from("declaraciones").select("datos").eq("user_id", sesion.user.id);
  if (anio) q = q.eq("anio", anio);
  let { data, error } = await q.order("actualizada", { ascending: false }).limit(1).maybeSingle();
  if (sinColumnaAnio(error)) {
    // La base todavía no tiene la columna «anio» (falta correr el SQL nuevo): una sola declaración
    ({ data, error } = await cliente.from("declaraciones").select("datos").eq("user_id", sesion.user.id).maybeSingle());
    const d = data?.datos as Instantanea | undefined;
    return d?.v === 1 && (!anio || d.anio === anio) ? d : null;
  }
  if (error) throw new Error(error.message);
  const datos = data?.datos as Instantanea | undefined;
  return datos?.v === 1 ? datos : null;
}

/** Los años que la persona tiene guardados, del más reciente al más viejo. */
export async function aniosEnLaNube(): Promise<number[]> {
  if (!cliente || !sesion) return [];
  const { data, error } = await cliente.from("declaraciones").select("anio").eq("user_id", sesion.user.id).order("anio", { ascending: false });
  if (error) return [];
  return (data ?? []).map((x) => x.anio as number).filter(Boolean);
}

export async function guardarEnLaNube(s: Instantanea): Promise<void> {
  if (!cliente || !sesion) return;
  const fila = { user_id: sesion.user.id, datos: s, actualizada: new Date().toISOString() };
  const { error } = await cliente.from("declaraciones").upsert({ ...fila, anio: s.anio }, { onConflict: "user_id,anio" });
  if (sinColumnaAnio(error) || error?.code === "42P10") {
    const r = await cliente.from("declaraciones").upsert(fila, { onConflict: "user_id" });
    if (r.error) throw new Error(r.error.message);
    return;
  }
  if (error) throw new Error(error.message);
}

export async function borrarDeLaNube(anio?: number): Promise<void> {
  if (!cliente || !sesion) return;
  let q = cliente.from("declaraciones").delete().eq("user_id", sesion.user.id);
  if (anio) q = q.eq("anio", anio);
  const { error } = await q;
  if (sinColumnaAnio(error)) await cliente.from("declaraciones").delete().eq("user_id", sesion.user.id);
  await borrarDocumentos(anio);
}

// ---------- Archivos de la persona (bucket privado «documentos», carpeta {user_id}/{año}/) ----------

const BUCKET = "documentos";

export interface ArchivoNube {
  ruta: string;
  nombre: string;
  subido: string;
  tamano: number;
}

const limpio = (n: string) => n.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^\w.\-]+/g, "_").slice(-90);
/** El nombre que se ve: sin el prefijo de tiempo que evita choques. */
const nombreVisible = (n: string) => n.replace(/^\d{13}-/, "");

export async function subirDocumento(anio: number, archivo: File): Promise<void> {
  if (!cliente || !sesion) return;
  const ruta = `${sesion.user.id}/${anio}/${Date.now()}-${limpio(archivo.name)}`;
  const { error } = await cliente.storage.from(BUCKET).upload(ruta, archivo, { contentType: archivo.type || undefined, upsert: false });
  if (error) throw new Error(error.message);
}

export async function listarDocumentos(anio: number): Promise<ArchivoNube[]> {
  if (!cliente || !sesion) return [];
  const carpeta = `${sesion.user.id}/${anio}`;
  const { data, error } = await cliente.storage.from(BUCKET).list(carpeta, { limit: 100, sortBy: { column: "created_at", order: "desc" } });
  if (error) throw new Error(error.message);
  return (data ?? [])
    .filter((x) => x.id)
    .map((x) => ({ ruta: `${carpeta}/${x.name}`, nombre: nombreVisible(x.name), subido: x.created_at ?? "", tamano: (x.metadata?.size as number) ?? 0 }));
}

export async function bajarDocumento(a: ArchivoNube): Promise<File> {
  if (!cliente) throw new Error("Las cuentas no están activas");
  const { data, error } = await cliente.storage.from(BUCKET).download(a.ruta);
  if (error || !data) throw new Error(error?.message ?? "No se pudo bajar el archivo");
  return new File([data], a.nombre, { type: data.type });
}

export async function borrarDocumento(a: ArchivoNube): Promise<void> {
  if (!cliente) return;
  const { error } = await cliente.storage.from(BUCKET).remove([a.ruta]);
  if (error) throw new Error(error.message);
}

/** Borra los archivos de un año, o de todos los años si no se dice. */
export async function borrarDocumentos(anio?: number): Promise<void> {
  if (!cliente || !sesion) return;
  const raiz = sesion.user.id;
  const anios = anio ? [String(anio)] : ((await cliente.storage.from(BUCKET).list(raiz)).data ?? []).map((x) => x.name);
  for (const a of anios) {
    const { data } = await cliente.storage.from(BUCKET).list(`${raiz}/${a}`, { limit: 1000 });
    const rutas = (data ?? []).filter((x) => x.id).map((x) => `${raiz}/${a}/${x.name}`);
    if (rutas.length) await cliente.storage.from(BUCKET).remove(rutas);
  }
}
