import { AnimatePresence, motion } from "motion/react";
import type { EventoAgente } from "../lib/api";

const TEXTO_SELLO: Record<string, string> = { ok: "Listo", advertencia: "Revisar", error: "Falló" };

/** Si un archivo falló pero otros no, el agente queda en "Revisar"; si todos fallaron, "Falló". */
const PEOR = (estados: EventoAgente["estado"][]): EventoAgente["estado"] =>
  estados.every((e) => e === "error") ? "error" : estados.some((e) => e !== "ok") ? "advertencia" : "ok";

export interface Fase {
  agente: string;
  nombre: string;
  descripcion: string;
  usa_ia: boolean;
}

/** Cada agente estampa su sello cuando termina. Es la animación central de la app. */
export function MesaAgentes({ fases, eventos, compacta = false, soloActivos = false }: { fases: Fase[]; eventos: EventoAgente[]; compacta?: boolean; soloActivos?: boolean }) {
  const ultimo = (agente: string) => [...eventos].reverse().find((e) => e.agente === agente);
  // Con varios documentos no todos los agentes trabajan (el Intérprete es para la exógena, el Extractor para los certificados)
  const visibles = soloActivos ? fases.filter((f) => eventos.some((e) => e.agente === f.agente)) : fases;
  return (
    <ol className={`mesa${compacta ? " compacta" : ""}`} aria-live="polite">
      {visibles.map((f) => {
        const ultimoEv = ultimo(f.agente);
        // Con varios archivos un agente trabaja varias veces: se muestra una línea por archivo y el peor estado
        const hechos = eventos.filter((e) => e.agente === f.agente && e.estado !== "inicio");
        const ev =
          ultimoEv && ultimoEv.estado !== "inicio" && hechos.length > 1
            ? { ...ultimoEv, mensaje: hechos.map((e) => e.mensaje).join("\n"), estado: PEOR(hechos.map((e) => e.estado)) }
            : ultimoEv;
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
  { agente: "clasificador", nombre: "Clasificador", descripcion: "Reconoce cada documento y de qué año es.", usa_ia: true },
  { agente: "interprete", nombre: "Intérprete", descripcion: "Ubica cada dato de la exógena en tu declaración.", usa_ia: true },
  { agente: "extractor", nombre: "Extractor", descripcion: "Saca las cifras de tus certificados.", usa_ia: false },
  { agente: "conciliador", nombre: "Conciliador", descripcion: "Cruza tus documentos para no contar nada dos veces.", usa_ia: false },
];

export const FASES_CALCULO: Fase[] = [
  { agente: "motor", nombre: "Motor tributario", descripcion: "Aplica las reglas del año: UVT, topes, límites y tarifas.", usa_ia: false },
  { agente: "auditor", nombre: "Auditor", descripcion: "Busca errores, datos faltantes y vencimientos.", usa_ia: false },
  { agente: "explicador", nombre: "Explicador", descripcion: "Escribe el resumen en palabras simples.", usa_ia: true },
];
