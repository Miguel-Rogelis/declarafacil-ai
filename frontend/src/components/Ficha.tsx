import { AnimatePresence, motion } from "motion/react";
import type { ItemFicha } from "../lib/api";

const TEXTO_ESTADO: Record<ItemFicha["estado"], string> = {
  tengo: "lo tengo",
  falta: "falta",
  omitido: "sin respuesta",
  no_aplica: "no aplica",
};

function Marca({ estado }: { estado: ItemFicha["estado"] }) {
  return (
    <span className={`ficha-marca ${estado}`} aria-hidden="true">
      <AnimatePresence initial={false} mode="popLayout">
        {estado === "tengo" ? (
          <motion.svg
            key="tengo"
            viewBox="0 0 16 16"
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0 }}
            transition={{ type: "spring", stiffness: 520, damping: 24 }}
          >
            <path d="M4 8.5l2.6 2.6L12 5.5" />
          </motion.svg>
        ) : estado === "no_aplica" ? (
          <motion.svg key="no" viewBox="0 0 16 16" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <path d="M5 8h6" />
          </motion.svg>
        ) : null}
      </AnimatePresence>
    </span>
  );
}

/** Lo que el agente ya sabe de tu declaración y lo que le falta: se llena mientras conversas. */
export function Ficha({ items }: { items: ItemFicha[] }) {
  if (!items.length) return null;
  const listos = items.filter((i) => i.estado === "tengo" || i.estado === "no_aplica").length;
  return (
    <section className="ficha" aria-label={`Tu declaración: ${listos} de ${items.length} datos listos`}>
      <div className="ficha-cabeza">
        <span className="ficha-titulo">Tu declaración</span>
        <span className="ficha-cuenta">
          {listos} de {items.length}
        </span>
        <span className="ficha-barra" aria-hidden="true">
          <motion.span
            className="ficha-relleno"
            initial={false}
            animate={{ scaleX: listos / items.length }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
          />
        </span>
      </div>
      <ul className="ficha-lista">
        {items.map((i) => (
          <li
            key={i.tema}
            className={`ficha-item ${i.estado}`}
            title={i.detalle ? `${i.etiqueta}: ${i.detalle}` : `${i.etiqueta}: ${TEXTO_ESTADO[i.estado]}`}
          >
            <Marca estado={i.estado} />
            <span>{i.etiqueta}</span>
            <span className="visualmente-oculto">, {i.detalle || TEXTO_ESTADO[i.estado]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
