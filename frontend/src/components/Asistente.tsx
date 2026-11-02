import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useSesion } from "../lib/estado";
import Conversacion from "./Conversacion";

/** Botón flotante: el mismo chat de la pantalla Declarar, disponible en las demás pantallas. */
export default function Asistente() {
  const { ruta } = useSesion();
  const [abierto, setAbierto] = useState(false);
  if (ruta === "declarar") return null;
  return (
    <>
      <AnimatePresence>
        {abierto ? (
          <motion.section
            className="asistente-panel"
            role="dialog"
            aria-label="Asistente"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            onKeyDown={(e) => e.key === "Escape" && setAbierto(false)}
          >
            <header>
              <strong>DeclaraFácil</strong>
              <button className="boton-texto" onClick={() => setAbierto(false)}>Cerrar</button>
            </header>
            <Conversacion compacta />
          </motion.section>
        ) : null}
      </AnimatePresence>
      <button className="asistente-boton" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>
        {abierto ? "Cerrar chat" : "¿Dudas? Pregúntame"}
      </button>
    </>
  );
}
