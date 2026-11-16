import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { useSesion } from "../lib/estado";

/** Aviso flotante mientras el servidor gratuito despierta (la primera visita tras un rato sin uso tarda hasta un minuto). */
export function AvisoServidor() {
  const { servidor } = useSesion();
  const [visible, setVisible] = useState(false);
  const [desperto, setDesperto] = useState(false);

  useEffect(() => {
    if (servidor === "despertando" || servidor === "sin_conexion") setVisible(true);
    if (servidor === "listo" && visible) {
      setDesperto(true);
      const t = window.setTimeout(() => setVisible(false), 1800);
      return () => window.clearTimeout(t);
    }
  }, [servidor, visible]);

  const texto = desperto
    ? "Listo, ya estoy en línea."
    : servidor === "sin_conexion"
      ? "No pude conectarme al servidor. Revisa tu internet y recarga la página."
      : "Despertando el servidor… la primera visita del día tarda hasta un minuto.";

  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          className={`aviso-servidor${servidor === "sin_conexion" ? " error" : ""}`}
          role="status"
          initial={{ opacity: 0, y: 16, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ type: "spring", stiffness: 420, damping: 32 }}
        >
          {desperto ? (
            <span className="aviso-icono listo" aria-hidden="true">
              <svg viewBox="0 0 16 16"><path d="M4 8.5l2.6 2.6L12 5.5" /></svg>
            </span>
          ) : servidor === "sin_conexion" ? null : (
            <span className="aviso-icono girando" aria-hidden="true" />
          )}
          <span>{texto}</span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
