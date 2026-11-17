import { useEffect, useState } from "react";
import type { Formulario210 } from "./api";

/**
 * Conversación con la extensión de DeclaraFácil para Chrome (carpeta extension/ del repo).
 * La extensión pone un puente en esta página; se le habla con window.postMessage.
 * - formulario: le pasa el borrador del 210 para que lo escriba en MUISCA.
 * - pedir-exogena: abre MUISCA y trae la exógena con la sesión de la persona.
 * La extensión nunca firma ni presenta, y la contraseña la escribe siempre la persona.
 */

export const DESCARGA_EXTENSION = `${import.meta.env.BASE_URL}declarafacil-extension.zip`;
export const GUIA_EXTENSION = "https://github.com/Miguel-Rogelis/declarafacil-ai/tree/main/extension#readme";

type Respuesta = { ok?: boolean; error?: string; [k: string]: unknown };

let version: string | null = typeof document !== "undefined" ? (document.documentElement.dataset.declarafacilExtension ?? null) : null;
const oyentesVersion = new Set<(v: string | null) => void>();
const esperando = new Map<number, (r: Respuesta) => void>();
const oyentesArchivo = new Set<(f: File) => void>();
const oyentesDescargas = new Set<() => void>();
let siguiente = 1;
let escuchando = false;

const decir = (m: Record<string, unknown>) => window.postMessage({ origen: "declarafacil-app", ...m }, window.location.origin);

function aArchivo(nombre: string, mime: string, base64: string): File {
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const tipo = mime && !/octet-stream/.test(mime) ? mime : /\.pdf$/i.test(nombre) ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  return new File([bytes], nombre || "exogena.xlsx", { type: tipo });
}

function escuchar() {
  if (escuchando || typeof window === "undefined") return;
  escuchando = true;
  window.addEventListener("message", (e: MessageEvent) => {
    if (e.source !== window || e.origin !== window.location.origin) return;
    const m = e.data as Record<string, unknown> | null;
    if (!m || m.origen !== "declarafacil-extension") return;
    if (m.tipo === "lista") {
      version = String(m.version ?? "");
      oyentesVersion.forEach((f) => f(version));
    } else if (m.tipo === "respuesta" && typeof m.id === "number") {
      esperando.get(m.id)?.(m as Respuesta);
      esperando.delete(m.id);
    } else if (m.tipo === "exogena" && typeof m.base64 === "string" && oyentesArchivo.size) {
      // Solo se confirma si la app ya está lista para leerlo; si no, la extensión lo guarda un rato
      decir({ tipo: "exogena-recibida" });
      const archivo = aArchivo(String(m.nombre ?? ""), String(m.mime ?? ""), m.base64);
      oyentesArchivo.forEach((f) => f(archivo));
    } else if (m.tipo === "exogena-en-descargas") {
      oyentesDescargas.forEach((f) => f());
    }
  });
}

function pedir(tipo: string, datos: Record<string, unknown> = {}, ms = 8000): Promise<Respuesta> {
  escuchar();
  const id = siguiente++;
  return new Promise((listo) => {
    const espera = window.setTimeout(() => {
      esperando.delete(id);
      listo({ ok: false, error: "La extensión no respondió. Recarga la página e intenta otra vez." });
    }, ms);
    esperando.set(id, (r) => {
      window.clearTimeout(espera);
      listo(r);
    });
    decir({ tipo, id, ...datos });
  });
}

/** La versión de la extensión si está instalada en este navegador; null si no. */
export function useExtension(): string | null {
  const [v, setV] = useState(version);
  useEffect(() => {
    escuchar();
    oyentesVersion.add(setV);
    decir({ tipo: "hola", id: 0 });
    return () => {
      oyentesVersion.delete(setV);
    };
  }, []);
  return v;
}

/** Le pasa a la extensión el borrador del 210 (todas las casillas: las que se escriben y las que calcula MUISCA, para comparar). */
export function enviarFormulario(f: Formulario210): Promise<Respuesta> {
  const casillas = f.secciones.flatMap((s) => s.casillas).map((c) => ({ numero: c.numero, nombre: c.nombre, valor: c.valor, tipo: c.tipo, texto: c.texto }));
  return pedir("formulario", { datos: { anio_gravable: f.anio_gravable, casillas } });
}

export function pedirExogena(anio: number): Promise<Respuesta> {
  return pedir("pedir-exogena", { anio });
}

/** Avisa cuando la extensión trae la exógena (o cuando quedó en la carpeta de Descargas). */
export function alTraerExogena(alArchivo: (f: File) => void, enDescargas: () => void): () => void {
  escuchar();
  oyentesArchivo.add(alArchivo);
  oyentesDescargas.add(enDescargas);
  decir({ tipo: "hola", id: 0 }); // por si llegó mientras DeclaraFácil estaba cerrado
  return () => {
    oyentesArchivo.delete(alArchivo);
    oyentesDescargas.delete(enDescargas);
  };
}
