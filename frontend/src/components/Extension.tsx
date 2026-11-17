import { useState } from "react";
import type { Formulario210 } from "../lib/api";
import { useSesion } from "../lib/estado";
import { DESCARGA_EXTENSION, enviarFormulario, GUIA_EXTENSION, useExtension } from "../lib/extension";

function Instalar({ para }: { para: string }) {
  return (
    <p className="chico suave sin-margen extension-instalar">
      {para}{" "}
      <a href={DESCARGA_EXTENSION} download>Descarga la extensión</a>, descomprímela y cárgala en <code>chrome://extensions</code> (en Opera,{" "}
      <code>opera://extensions</code>; en Edge, <code>edge://extensions</code>): modo de desarrollador → «Cargar descomprimida». <a href={GUIA_EXTENSION} target="_blank" rel="noopener noreferrer">Cómo instalarla<span className="visualmente-oculto"> (se abre en otra pestaña)</span></a>
    </p>
  );
}

/** Pasa el borrador del 210 a la extensión, que lo escribe casilla por casilla en MUISCA. */
export function LlenarConExtension({ f, compacto = false }: { f: Formulario210; compacto?: boolean }) {
  const version = useExtension();
  const [estado, setEstado] = useState<{ ok: boolean; texto: string } | null>(null);
  const [enviando, setEnviando] = useState(false);
  if (!f.disponible) return null;
  if (!version) return compacto ? null : <Instalar para="¿Quieres que las casillas se llenen solas en MUISCA?" />;

  const enviar = async () => {
    setEnviando(true);
    const r = await enviarFormulario(f);
    setEnviando(false);
    setEstado(
      r.ok
        ? { ok: true, texto: `Listo: le pasé ${r.escribir} casillas a la extensión. Abre el formulario 210 de ${f.anio_gravable} en MUISCA y toca «Llenar casillas» en el recuadro de DeclaraFácil. Revisa todo antes de firmar.` }
        : { ok: false, texto: r.error ?? "No pude hablar con la extensión." },
    );
  };

  return (
    <div className={`extension-accion${compacto ? " compacto" : ""}`}>
      <button type="button" className={`boton chico${compacto ? " secundario" : ""}`} onClick={() => void enviar()} disabled={enviando}>
        {enviando ? "Enviando…" : "Llenar con la extensión"}
      </button>
      <p role="status" className={`chico sin-margen${estado && !estado.ok ? " texto-error" : " suave"}`}>{estado?.texto ?? ""}</p>
    </div>
  );
}

/** Pide a la extensión que traiga la exógena del año desde MUISCA, con la sesión de la persona (el aviso sale en el chat). */
export function TraerExogena() {
  const version = useExtension();
  const { traerExogena } = useSesion();
  if (!version) return <Instalar para="¿Prefieres que la traiga yo de la DIAN?" />;
  return (
    <div className="extension-accion">
      <button type="button" className="boton secundario chico" onClick={() => void traerExogena()}>
        Traer mi exógena de la DIAN
      </button>
    </div>
  );
}

/** En el chat vacío: la misma acción como sugerencia, solo si la extensión está instalada. */
export function SugerenciaExogena({ deshabilitada }: { deshabilitada: boolean }) {
  const version = useExtension();
  const { traerExogena } = useSesion();
  if (!version) return null;
  return (
    <button type="button" className="sugerencia" disabled={deshabilitada} onClick={() => void traerExogena()}>
      Traer mi exógena de la DIAN
    </button>
  );
}
