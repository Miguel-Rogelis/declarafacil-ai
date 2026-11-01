import { AnimatePresence, motion } from "motion/react";
import type { EventoAgente } from "../lib/api";

const TEXTO_SELLO: Record<string, string> = { ok: "Listo", advertencia: "Revisar", error: "Falló" };

export interface Fase {
  agente: string;
  nombre: string;
  descripcion: string;
  usa_ia: boolean;
}

/** Cada agente estampa su sello cuando termina. Es la animación central de la app. */
export function MesaAgentes({ fases, eventos, compacta = false }: { fases: Fase[]; eventos: EventoAgente[]; compacta?: boolean }) {
  const ultimo = (agente: string) => [...eventos].reverse().find((e) => e.agente === agente);
  return (
    <ol className={`mesa${compacta ? " compacta" : ""}`} aria-live="polite">
      {fases.map((f) => {
        const ev = ultimo(f.agente);
        const terminado = ev && ev.estado !== "inicio";
        const trabajando = ev?.estado === "inicio";
        return (
          <li key={f.agente} className={!ev ? "pendiente" : undefined}>
            <div>
              <div className="nombre">
                {f.nombre}
                {f.usa_ia ? <span className="etiqueta-ia">IA</span> : <span className="etiqueta-reglas">Reglas</span>}
              </div>
              <div className="mensaje">{ev ? ev.mensaje : f.descripcion}</div>
              {terminado && ev?.modelo ? <div className="modelo">Modelo: {ev.modelo}</div> : null}
              {terminado && ev?.duracion_ms != null && !compacta ? <div className="chico suave">{(ev.duracion_ms / 1000).toFixed(1)} s</div> : null}
            </div>
            <AnimatePresence>
              {trabajando ? <span className="trabajando" aria-label="Trabajando" /> : null}
              {terminado ? (
                <motion.span
                  key="sello"
                  className={`sello-agente ${ev.estado}`}
                  initial={{ scale: 1.9, rotate: -24, opacity: 0 }}
                  animate={{ scale: 1, rotate: -9, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 520, damping: 18 }}
                  aria-label={TEXTO_SELLO[ev.estado]}
                >
                  {TEXTO_SELLO[ev.estado]}
                </motion.span>
              ) : null}
            </AnimatePresence>
          </li>
        );
      })}
    </ol>
  );
}

export const FASES_DOCUMENTO: Fase[] = [
  { agente: "lector", nombre: "Lector", descripcion: "Lee tu archivo y lo convierte en filas.", usa_ia: false },
  { agente: "anonimizador", nombre: "Anonimizador", descripcion: "Quita tu cédula, tu nombre y tus números de cuenta.", usa_ia: false },
  { agente: "clasificador", nombre: "Clasificador", descripcion: "Confirma que es una exógena y de qué año.", usa_ia: true },
  { agente: "interprete", nombre: "Intérprete", descripcion: "Ubica cada dato en tu declaración y lo explica.", usa_ia: true },
];

export const FASES_CALCULO: Fase[] = [
  { agente: "motor", nombre: "Motor tributario", descripcion: "Aplica las reglas del año: UVT, topes, límites y tarifas.", usa_ia: false },
  { agente: "auditor", nombre: "Auditor", descripcion: "Busca errores, datos faltantes y vencimientos.", usa_ia: false },
  { agente: "explicador", nombre: "Explicador", descripcion: "Escribe el resumen en palabras simples.", usa_ia: true },
];
