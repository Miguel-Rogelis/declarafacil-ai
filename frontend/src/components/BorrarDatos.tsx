import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

/** Borrar la conversación guardada, en dos toques: el primero pide confirmar y se arrepiente solo a los 4 s. */
export function BorrarDatos({ onBorrar, nube = false }: { onBorrar: () => void; nube?: boolean }) {
  const [confirmando, setConfirmando] = useState(false);
  useEffect(() => {
    if (!confirmando) return;
    const t = window.setTimeout(() => setConfirmando(false), 4000);
    return () => window.clearTimeout(t);
  }, [confirmando]);
  return (
    <div className="borrar-datos">
      <span className="guardado-en" title={nube ? "Se guarda en tu cuenta" : "Se guarda solo en este navegador; no sale de tu dispositivo"}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 8.5l2.6 2.6L12 5.5" /></svg>
        {nube ? "Guardado en tu cuenta" : "Guardado en este dispositivo"}
      </span>
      <AnimatePresence mode="popLayout" initial={false}>
        {confirmando ? (
          <motion.span key="confirmar" className="confirmar-borrar" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ duration: 0.16, ease: [0.23, 1, 0.32, 1] }}>
            <button type="button" className="boton chico peligro" onClick={() => { setConfirmando(false); onBorrar(); }}>Sí, borrar todo</button>
            <button type="button" className="boton-texto chico" onClick={() => setConfirmando(false)}>Cancelar</button>
          </motion.span>
        ) : (
          <motion.button key="borrar" type="button" className="boton-texto chico" onClick={() => setConfirmando(true)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
            Borrar mis datos
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
