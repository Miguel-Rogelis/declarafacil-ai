import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useSesion } from "../lib/estado";
import { pesos } from "../lib/formato";
import { bajarDocumento, borrarDocumento, listarDocumentos, type ArchivoNube } from "../lib/nube";

const CURVA = [0.23, 1, 0.32, 1] as const;

const fecha = (iso: string) => (iso ? new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "short" }) : "");
const peso = (b: number) => (b > 1_000_000 ? `${(b / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1000))} KB`);

/** Los archivos que la persona guardó en su cuenta para este año: qué reconoció la app, qué falta y cuánto va. */
export function MisDocumentos({ onCerrar }: { onCerrar: () => void }) {
  const { cuenta, nubeActiva, anio, versionDocs, refrescarDocs, documentos, procesarArchivos, ficha, resultado, ir } = useSesion();
  const [archivos, setArchivos] = useState<ArchivoNube[] | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [borrando, setBorrando] = useState<string | null>(null);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!cuenta) return;
    let vivo = true;
    setError("");
    listarDocumentos(anio)
      .then((a) => vivo && setArchivos(a))
      .catch(() => vivo && (setArchivos([]), setError("No pude ver tus archivos guardados. Si acabas de activar las cuentas, falta crear el espacio «documentos» en Supabase.")));
    return () => {
      vivo = false;
    };
  }, [cuenta, anio, versionDocs]);

  if (!nubeActiva) return null;
  if (!cuenta) {
    return (
      <section className="mis-documentos invitacion">
        <strong>Guarda tus documentos en tu cuenta</strong>
        <p className="suave">Entra con «Entrar», arriba a la derecha: tus archivos quedan guardados en privado y los vuelves a leer desde cualquier dispositivo.</p>
      </section>
    );
  }

  const leidos = new Set(documentos.map((d) => d.nombre));
  const etiqueta = (a: ArchivoNube) => documentos.find((d) => d.nombre === a.nombre)?.etiqueta;
  const sinLeer = (archivos ?? []).filter((a) => !leidos.has(a.nombre));
  const faltan = ficha.filter((i) => i.estado === "falta").map((i) => i.etiqueta.toLowerCase());
  const r = resultado?.liquidacion.resumen;

  const releer = async () => {
    setOcupado(true);
    try {
      const files = await Promise.all(sinLeer.map(bajarDocumento));
      onCerrar();
      await procesarArchivos(files, { subir: false });
    } catch {
      setError("No pude bajar tus archivos. Intenta de nuevo.");
    } finally {
      setOcupado(false);
    }
  };
  const subir = async (lista: FileList | null) => {
    if (!lista?.length) return;
    onCerrar();
    await procesarArchivos([...lista]);
  };
  const quitar = async (a: ArchivoNube) => {
    try {
      await borrarDocumento(a);
      refrescarDocs();
    } catch {
      setError("No pude borrar ese archivo.");
    } finally {
      setBorrando(null);
    }
  };

  return (
    <section className="mis-documentos" aria-labelledby="t-mis-docs">
      <div className="mis-docs-cabeza">
        <h3 id="t-mis-docs">Mis documentos guardados</h3>
        <button type="button" className="boton chico secundario" onClick={() => entrada.current?.click()}>Subir documentos</button>
        <input ref={entrada} type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.txt" hidden onChange={(e) => void subir(e.target.files)} />
      </div>

      <dl className="mis-docs-resumen">
        <div><dt>Reconocí</dt><dd>{documentos.length ? `${documentos.length} documento${documentos.length > 1 ? "s" : ""}` : "ninguno todavía"}</dd></div>
        <div><dt>Te falta</dt><dd>{faltan.length ? faltan.join(", ") : "nada clave"}</dd></div>
        <div>
          <dt>Tu declaración</dt>
          <dd>
            {r ? (r.total_a_pagar > 0 ? `pagas ${pesos(r.total_a_pagar)}` : r.saldo_favor > 0 ? `saldo a favor de ${pesos(r.saldo_favor)}` : "sin saldo a pagar") : "sin calcular"}
            {r ? <> · <button type="button" className="boton-texto chico" onClick={() => { onCerrar(); ir("resultado"); }}>ver</button></> : null}
          </dd>
        </div>
      </dl>

      {archivos === null ? (
        <p className="chico suave">Buscando tus archivos…</p>
      ) : archivos.length ? (
        <ul className="mis-docs-lista">
          <AnimatePresence initial={false}>
            {archivos.map((a) => (
              <motion.li key={a.ruta} layout initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.18, ease: CURVA }}>
                <span className="doc-icono" aria-hidden="true">
                  <svg viewBox="0 0 16 16"><path d="M4 1.5h5l3 3v10H4z M9 1.5v3h3" /></svg>
                </span>
                <span className="doc-info">
                  <span className="doc-nombre">{a.nombre}</span>
                  <span className="doc-meta">{etiqueta(a) ?? "sin leer en esta sesión"} · {fecha(a.subido)} · {peso(a.tamano)}</span>
                </span>
                {borrando === a.ruta ? (
                  <span className="doc-confirmar">
                    <button type="button" className="boton chico peligro" onClick={() => void quitar(a)}>Borrar</button>
                    <button type="button" className="boton-texto chico" onClick={() => setBorrando(null)}>No</button>
                  </span>
                ) : (
                  <button type="button" className="doc-quitar" onClick={() => setBorrando(a.ruta)} aria-label={`Borrar ${a.nombre}`}>
                    <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" /></svg>
                  </button>
                )}
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      ) : (
        <p className="chico suave">Todavía no has guardado archivos del {anio}. Los que subas en el chat con tu sesión iniciada quedan aquí.</p>
      )}

      {sinLeer.length ? (
        <button type="button" className="boton chico" disabled={ocupado} onClick={() => void releer()}>
          {ocupado ? "Bajando…" : `Volver a leer ${sinLeer.length === 1 ? "este archivo" : `estos ${sinLeer.length} archivos`}`}
        </button>
      ) : null}
      {error ? <p className="mensaje-estado error" role="alert">{error}</p> : null}
      <p className="nota-privada">
        <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></svg>
        Solo tú puedes verlos. Antes de usar IA, la app quita tus datos personales.
      </p>
    </section>
  );
}
