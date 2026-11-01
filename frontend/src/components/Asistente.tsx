import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useSesion } from "../lib/estado";
import { pesos } from "../lib/formato";

interface Mensaje {
  rol: "usuario" | "asistente";
  texto: string;
  fuentes?: string[];
}

const SUGERENCIAS = ["¿Cómo descargo mi exógena?", "¿Quién cuenta como dependiente?", "¿Qué pasa si declaro tarde?", "¿Qué es el anticipo?"];

export default function Asistente() {
  const { resultado, extraccion } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState<Mensaje[]>([
    { rol: "asistente", texto: "Hola. Pregúntame lo que no entiendas de tu declaración o de la exógena." },
  ]);
  const [texto, setTexto] = useState("");
  const [esperando, setEsperando] = useState(false);
  const lista = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    lista.current?.scrollTo({ top: lista.current.scrollHeight, behavior: "smooth" });
  }, [mensajes, esperando]);
  useEffect(() => {
    if (abierto) entrada.current?.focus();
  }, [abierto]);

  const contexto = () => {
    if (resultado) {
      const r = resultado.liquidacion.resumen;
      return `Obligado a declarar: ${resultado.liquidacion.obligacion.obligado ? "sí" : "no"}. Impuesto a cargo ${pesos(r.total_impuesto_cargo)}, retenciones ${pesos(r.retenciones)}, anticipo ${pesos(r.anticipo_siguiente)}, sanción ${pesos(r.sancion)}, total a pagar ${pesos(r.total_a_pagar)}, saldo a favor ${pesos(r.saldo_favor)}. Alertas: ${resultado.liquidacion.alertas.slice(0, 5).map((a) => a.titulo).join("; ")}.`;
    }
    if (extraccion) {
      const p = extraccion.perfil;
      const tipos = [p.empleado && "empleado", p.independiente && "independiente", p.pensionado && "pensionado", p.rentas_capital && "tiene rentas de capital", p.dividendos && "recibe dividendos"].filter(Boolean);
      return `Ya subió su exógena. Perfil: ${tipos.join(", ") || "sin identificar"}. Declaró el año pasado: ${p.declaro_antes ? "sí" : "no se sabe"}.`;
    }
    return null;
  };

  const enviar = async (pregunta: string) => {
    const q = pregunta.trim();
    if (!q || esperando) return;
    const historial = mensajes.map((m) => ({ rol: m.rol, texto: m.texto }));
    setMensajes((m) => [...m, { rol: "usuario", texto: q }]);
    setTexto("");
    setEsperando(true);
    try {
      const r = await api.asistente(q, historial, contexto());
      setMensajes((m) => [...m, { rol: "asistente", texto: r.respuesta, fuentes: r.fuentes }]);
    } catch (e) {
      setMensajes((m) => [...m, { rol: "asistente", texto: `No pude responder: ${(e as Error).message}` }]);
    } finally {
      setEsperando(false);
    }
  };

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
              <strong>Asistente</strong>
              <button className="boton-texto" onClick={() => setAbierto(false)}>Cerrar</button>
            </header>
            <div className="mensajes" ref={lista} aria-live="polite">
              {mensajes.map((m, i) => (
                <div key={i} className={`burbuja ${m.rol === "usuario" ? "usuario" : "bot"}`}>
                  <p>{m.texto}</p>
                  {m.fuentes?.length ? <div className="fuentes">Basado en: {m.fuentes.join("; ")}</div> : null}
                </div>
              ))}
              {esperando ? (
                <div className="burbuja bot"><span className="escribiendo" aria-label="Escribiendo"><i /><i /><i /></span></div>
              ) : null}
              {mensajes.length === 1 ? (
                <div className="sugerencias">
                  {SUGERENCIAS.map((s) => <button key={s} onClick={() => enviar(s)}>{s}</button>)}
                </div>
              ) : null}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); void enviar(texto); }}>
              <label htmlFor="pregunta" className="visualmente-oculto">Tu pregunta</label>
              <input id="pregunta" ref={entrada} className="entrada" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Escribe tu pregunta" autoComplete="off" />
              <button className="boton chico" disabled={!texto.trim() || esperando}>Enviar</button>
            </form>
          </motion.section>
        ) : null}
      </AnimatePresence>
      <button className="asistente-boton" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>
        {abierto ? "Cerrar ayuda" : "¿Dudas? Pregúntame"}
      </button>
    </>
  );
}
