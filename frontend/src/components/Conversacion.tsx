import { motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ResultadoLiquidacion } from "../lib/api";
import { useSesion, type Mensaje } from "../lib/estado";
import { NOMBRES_CAMPO, pesos } from "../lib/formato";
import { FASES_CALCULO, FASES_DOCUMENTO, MesaAgentes } from "./MesaAgentes";
import { Marca } from "./piezas";

const CAMPOS_ELEGIBLES = Object.entries(NOMBRES_CAMPO).filter(([k]) => !k.endsWith("salario_promedio_mensual_6m"));

function Burbuja({ m, children }: { m: Mensaje; children?: ReactNode }) {
  if (m.rol === "usuario") return <div className="burbuja usuario">{m.texto}</div>;
  return (
    <motion.div
      className={`burbuja bot${m.aviso ? " aviso" : ""}${m.widget ? " con-widget" : ""}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      {m.texto ? m.texto.split(/\n+/).map((p, i) => <p key={i}>{p}</p>) : null}
      {children}
      {m.fuentes?.length ? <div className="fuentes">Fuente: {m.fuentes.join("; ")}</div> : null}
    </motion.div>
  );
}

function SubirExogena() {
  const { procesarArchivo, usarEjemplo } = useSesion();
  const input = useRef<HTMLInputElement>(null);
  const [arrastrando, setArrastrando] = useState(false);
  return (
    <>
      <div
        className={`zona-carga${arrastrando ? " activa" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setArrastrando(true);
        }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={(e) => {
          e.preventDefault();
          setArrastrando(false);
          const f = e.dataTransfer.files[0];
          if (f) void procesarArchivo(f);
        }}
      >
        <strong>Arrastra tu exógena o haz clic para elegirla</strong>
        <span className="chico suave">Excel (.xlsx) o PDF. La leo en memoria y no la guardo.</span>
      </div>
      <input
        ref={input}
        type="file"
        accept=".xlsx,.pdf"
        className="visualmente-oculto"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void procesarArchivo(f);
          e.target.value = "";
        }}
      />
      <p className="chico suave" style={{ margin: "0.5rem 0 0" }}>
        Para probar sin datos reales: <button className="boton-texto chico" onClick={() => void usarEjemplo()}>usar una exógena ficticia</button>
      </p>
    </>
  );
}

function Revisar() {
  const { porRevisar, filas, decididas, decidir } = useSesion();
  const [destino, setDestino] = useState<Record<string, string>>({});
  const ids = useRef(new Set([...porRevisar.map((f) => f.id), ...Object.keys(decididas)]));
  const tarjetas = filas.filter((f) => ids.current.has(f.id));
  if (!tarjetas.length) return <p className="chico suave">No hay datos pendientes por confirmar.</p>;
  return (
    <>
      <p className="chico" style={{ margin: 0 }}>Confirma si cada dato va en tu declaración:</p>
      {tarjetas.map((f) => {
        const decidida = f.id in decididas;
        return (
          <div key={f.id} className={`tarjeta-revisar${decidida ? " decidida" : ""}`}>
            <div className="monto">{pesos(f.valor)}</div>
            <div>{f.detalle}</div>
            <div className="chico suave">{f.informante}</div>
            <p className="chico" style={{ marginTop: "0.4rem" }}>{f.explicacion}</p>
            {f.origen_mapeo === "ia" && f.campo ? <p className="chico"><span className="etiqueta-ia">IA</span> Lo ubicó en: {NOMBRES_CAMPO[f.campo]}</p> : null}
            {!f.campo && !decidida ? (
              <div className="campo">
                <label htmlFor={`destino-${f.id}`}>¿Dónde va?</label>
                <select id={`destino-${f.id}`} className="entrada" value={destino[f.id] ?? ""} onChange={(e) => setDestino((x) => ({ ...x, [f.id]: e.target.value }))}>
                  <option value="">Elige una opción</option>
                  {CAMPOS_ELEGIBLES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            ) : null}
            <div className="acciones">
              {decidida ? (
                <span className="chico">{decididas[f.id] ? "Lo incluí." : "No lo incluí."}</span>
              ) : (
                <>
                  <button className="boton chico" onClick={() => decidir(f.id, true, f.campo ?? destino[f.id])} disabled={!f.campo && !destino[f.id]}>Incluirlo</button>
                  <button className="boton secundario chico" onClick={() => decidir(f.id, false)}>No incluirlo</button>
                </>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}

function Anotado({ m }: { m: Mensaje }) {
  const { deshacer } = useSesion();
  return (
    <div className={`anotado${m.deshecho ? " deshecho" : ""}`}>
      <span className="chico suave">{m.deshecho ? "Deshice estos datos:" : "Anoté:"}</span>
      <ul>
        {m.anotaciones!.map((a) => (
          <li key={a.clave + a.etiqueta}>
            {a.etiqueta}: <strong>{a.valor}</strong>
            {a.detalle ? <span className="chico suave"> ({a.detalle})</span> : null}
          </li>
        ))}
      </ul>
      {!m.deshecho ? <button className="boton-texto chico" onClick={() => deshacer(m.id)}>Deshacer</button> : null}
    </div>
  );
}

function ResultadoCorto({ r, actual, recalculo }: { r: ResultadoLiquidacion; actual: boolean; recalculo?: boolean }) {
  const { ir } = useSesion();
  const res = r.liquidacion.resumen;
  const pagar = res.total_a_pagar > 0;
  return (
    <div className={`resultado-corto${actual ? "" : " viejo"}`}>
      <span className="chico suave">
        {recalculo ? "Actualicé el cálculo con tus cambios. " : ""}
        Año gravable {r.liquidacion.anio_gravable}. {r.liquidacion.obligacion.obligado ? "Estás obligado a declarar." : "No estás obligado a declarar."}
      </span>
      <strong className="titular t-24">
        {pagar ? `Te toca pagar ${pesos(res.total_a_pagar)}` : res.saldo_favor > 0 ? `Te queda saldo a favor de ${pesos(res.saldo_favor)}` : "No tienes saldo a pagar"}
      </strong>
      <p>{r.explicacion.split(/\n+/)[0]}</p>
      {actual ? <button className="boton sello chico" onClick={() => ir("resultado")}>Ver el borrador completo</button> : <span className="chico suave">Este cálculo ya fue reemplazado.</span>}
    </div>
  );
}

function Widget({ m }: { m: Mensaje }) {
  const { resultado } = useSesion();
  switch (m.widget) {
    case "subir_exogena":
      return <SubirExogena />;
    case "revisar":
      return <Revisar />;
    case "traza_documento":
      return <MesaAgentes fases={FASES_DOCUMENTO} eventos={m.eventos ?? []} compacta />;
    case "traza_calculo":
      return <MesaAgentes fases={FASES_CALCULO} eventos={m.eventos ?? []} compacta />;
    case "resultado":
      return m.resultado ? <ResultadoCorto r={m.resultado} actual={m.resultado === resultado} recalculo={m.aviso} /> : null;
    case "anotado":
      return <Anotado m={m} />;
    default:
      return null;
  }
}

/** El chat a pantalla completa. El usuario lleva la conversación de inicio a fin. */
export default function Conversacion({ barra }: { barra?: ReactNode }) {
  const { mensajes, enviar, escribiendo, calculando, procesarArchivo, archivoPendiente, setArchivoPendiente, extraccion, anio } = useSesion();
  const [texto, setTexto] = useState("");
  const lista = useRef<HTMLDivElement>(null);
  const adjuntar = useRef<HTMLInputElement>(null);
  const caja = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (archivoPendiente && !extraccion) {
      const a = archivoPendiente;
      setArchivoPendiente(null);
      void procesarArchivo(a);
    }
  }, [archivoPendiente, extraccion, procesarArchivo, setArchivoPendiente]);

  useEffect(() => {
    const el = lista.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [mensajes, escribiendo]);

  useEffect(() => {
    caja.current?.focus();
  }, []);

  // La caja crece con el texto hasta un máximo
  useEffect(() => {
    const el = caja.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [texto]);

  const ocupado = escribiendo || calculando;
  const mandar = (t: string) => {
    if (!t.trim() || ocupado) return;
    setTexto("");
    void enviar(t);
  };
  const vacio = mensajes.length === 0;

  return (
    <section className={`chat${vacio ? " vacio-inicial" : ""}`} aria-label="Conversación con DeclaraFácil">
      {barra}
      <div className="chat-mensajes" ref={lista} aria-live="polite">
        <div className="chat-columna">
          {vacio ? (
            <div className="chat-bienvenida">
              <Marca />
              <h1 className="titular t-36">¿En qué te ayudo con tu renta?</h1>
              <p className="suave">Pregúntame lo que quieras, cuéntame tus ingresos o adjunta tu exógena con el clip. Uso las reglas del año gravable {anio}.</p>
            </div>
          ) : null}
          {mensajes.map((m) =>
            m.widget ? (
              <Burbuja key={m.id} m={m}><Widget m={m} /></Burbuja>
            ) : (
              <Burbuja key={m.id} m={m} />
            ),
          )}
          {escribiendo ? (
            <div className="burbuja bot"><span className="escribiendo" aria-label="Escribiendo"><i /><i /><i /></span></div>
          ) : null}
        </div>
      </div>
      <form
        className="chat-entrada"
        onSubmit={(e) => {
          e.preventDefault();
          mandar(texto);
        }}
      >
        <div className="chat-columna fila-entrada">
          <button type="button" className="adjuntar" aria-label="Adjuntar exógena" title="Adjuntar exógena (Excel o PDF)" onClick={() => adjuntar.current?.click()}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M21 12.5l-8.5 8.5a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.8-2.8l8.3-8.3" /></svg>
          </button>
          <input
            ref={adjuntar}
            type="file"
            accept=".xlsx,.pdf"
            className="visualmente-oculto"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void procesarArchivo(f);
              e.target.value = "";
            }}
          />
          <label htmlFor="mensaje" className="visualmente-oculto">Escribe tu mensaje</label>
          <textarea
            id="mensaje"
            ref={caja}
            className="entrada"
            rows={1}
            value={texto}
            placeholder="Escribe aquí"
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                mandar(texto);
              }
            }}
          />
          <button className="boton" disabled={!texto.trim() || ocupado}>Enviar</button>
        </div>
      </form>
    </section>
  );
}
