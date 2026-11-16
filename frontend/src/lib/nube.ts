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

export async function iniciarNube(url: string, clave: string, alCambiar: (c: Cuenta | null) => void): Promise<void> {
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

export async function entrarConCorreo(correo: string): Promise<void> {
  if (!cliente) throw new Error("Las cuentas no están activas");
  const { error } = await cliente.auth.signInWithOtp({ email: correo, options: { emailRedirectTo: regreso() } });
  if (error) throw new Error(error.message);
}

export async function salir(): Promise<void> {
  await cliente?.auth.signOut();
}

// Una fila por persona en la tabla «declaraciones» (con RLS: cada quien ve solo la suya)
export async function leerDeLaNube(): Promise<Instantanea | null> {
  if (!cliente || !sesion) return null;
  const { data, error } = await cliente.from("declaraciones").select("datos").eq("user_id", sesion.user.id).maybeSingle();
  if (error) throw new Error(error.message);
  const datos = data?.datos as Instantanea | undefined;
  return datos?.v === 1 ? datos : null;
}

export async function guardarEnLaNube(s: Instantanea): Promise<void> {
  if (!cliente || !sesion) return;
  const { error } = await cliente
    .from("declaraciones")
    .upsert({ user_id: sesion.user.id, datos: s, actualizada: new Date().toISOString() }, { onConflict: "user_id" });
  if (error) throw new Error(error.message);
}

export async function borrarDeLaNube(): Promise<void> {
  if (!cliente || !sesion) return;
  await cliente.from("declaraciones").delete().eq("user_id", sesion.user.id);
}
