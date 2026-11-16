import { AnimatePresence, motion } from "motion/react";
import { useDemo } from "../lib/demo";

const CURVA = [0.23, 1, 0.32, 1] as const;

function Icono({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

/** El control flotante de la demo guiada: en qué paso va, pausar, seguir, saltar o tomar el control. */
export function ControlDemo() {
  const d = useDemo();
  const visible = d.activa || d.terminada;
  return (
    <AnimatePresence>
      {visible ? (
        <motion.div
          className="control-demo"
          role="region"
          aria-label="Demo guiada"
          initial={{ opacity: 0, y: 14, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.98 }}
          transition={{ duration: 0.24, ease: CURVA }}
        >
          <div className="demo-info">
            <span className={`demo-punto${d.pausada ? " pausada" : ""}`} aria-hidden="true" />
            <div className="demo-textos" aria-live="polite">
              <span className="demo-etiqueta">{d.terminada ? "Demo guiada" : `Demo · paso ${d.paso} de ${d.total}`}</span>
              <AnimatePresence mode="popLayout" initial={false}>
                <motion.span
                  key={d.titulo}
                  className="demo-titulo"
                  initial={{ opacity: 0, y: 6, filter: "blur(2px)" }}
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  exit={{ opacity: 0, y: -6, filter: "blur(2px)" }}
                  transition={{ duration: 0.2, ease: CURVA }}
                >
                  {d.terminada ? "Ya viste el caso completo" : d.titulo}
                </motion.span>
              </AnimatePresence>
            </div>
          </div>
          <span className="demo-progreso" aria-hidden="true">
            <motion.span
              className="demo-relleno"
              initial={false}
              animate={{ scaleX: d.terminada ? 1 : (d.paso - 1) / d.total }}
              transition={{ duration: 0.4, ease: CURVA }}
            />
          </span>
          <div className="demo-botones">
            {d.terminada ? (
              <>
                <button type="button" className="demo-boton" onClick={d.iniciar}>
                  <Icono d="M3 8a5 5 0 1 0 1.5-3.5M3 3v2.5h2.5" />
                  Repetir
                </button>
                <button type="button" className="demo-boton destacado" onClick={d.tomarControl}>Seguir yo</button>
                <button type="button" className="demo-cerrar" onClick={d.cerrar} aria-label="Cerrar la demo">
                  <Icono d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
                </button>
              </>
            ) : (
              <>
                {d.pausada ? (
                  <button type="button" className="demo-boton" onClick={d.seguir} aria-label="Seguir la demo">
                    <Icono d="M5 3.5v9l7-4.5z" />
                    Seguir
                  </button>
                ) : (
                  <button type="button" className="demo-boton" onClick={d.pausar} aria-label="Pausar la demo">
                    <Icono d="M5.5 3.5v9M10.5 3.5v9" />
                    Pausar
                  </button>
                )}
                <button type="button" className="demo-boton" onClick={d.siguiente} aria-label="Siguiente paso">
                  <Icono d="M4 3.5l5 4.5-5 4.5M11.5 3.5v9" />
                </button>
                <button type="button" className="demo-boton destacado" onClick={d.tomarControl}>Tomar el control</button>
              </>
            )}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
