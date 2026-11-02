import { motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useSesion, type Mensaje } from "../lib/estado";
import { NOMBRES_CAMPO, pesos } from "../lib/formato";
import { FASES_CALCULO, FASES_DOCUMENTO, MesaAgentes } from "./MesaAgentes";
import { Marca } from "./piezas";

const CAMPOS_ELEGIBLES = Object.entries(NOMBRES_CAMPO).filter(([k]) => !k.endsWith("salario_promedio_mensual_6m"));

function Burbuja({ m, children }: { m: Mensaje; children?: ReactNode }) {
  if (m.rol === "usuario") return <div className="burbuja usuario">{m.texto}</div>;
  return (
    <motion.div
      className={`burbuja bot${m.aviso ? " aviso" : ""}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className="quien"><Marca /> DeclaraFácil</div>
      {m.texto ? m.texto.split(/\n+/).map((p, i) => <p key={i}>{p}</p>) : null}
      {children}
      {m.fuentes?.length ? <div className="fuentes">Basado en: {m.fuentes.join("; ")}</div> : null}
    </motion.div>
  );
}

function SubirExogena() {
  const { procesarArchivo, usarEjemplo, enviar } = useSesion();
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
        <span className="chico suave">Excel (.xlsx) o PDF. La leemos en memoria y no la guardamos.</span>
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
      <div className="opciones">
        <button className="boton-texto" onClick={() => void enviar("¿Cómo descargo mi exógena?")}>¿Cómo la descargo?</button>
        <button className="boton-texto" onClick={() => void usarEjemplo()}>Usar un ejemplo ficticio</button>
        <button className="boton-texto" onClick={() => void enviar("No tengo la exógena")}>No la tengo</button>
      </div>
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
                <span className="chico">{decididas[f.id] ? "Lo incluimos." : "No lo incluimos."}</span>
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
      <span className="chico suave">{m.deshecho ? "Deshice estos datos:" : "Anoté en tu hoja de trabajo:"}</span>
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

function ResultadoCorto() {
  const { resultado, ir } = useSesion();
  if (!resultado) return <p className="chico suave">Este cálculo quedó desactualizado. Vuelve a calcular.</p>;
  const r = resultado.liquidacion.resumen;
  const pagar = r.total_a_pagar > 0;
  return (
    <div className="resultado-corto">
      <span className="chico suave">
        Año gravable {resultado.liquidacion.anio_gravable}. {resultado.liquidacion.obligacion.obligado ? "Estás obligado a declarar." : "No estás obligado a declarar."}
      </span>
      <strong className="titular t-24">
        {pagar ? `Te toca pagar ${pesos(r.total_a_pagar)}` : r.saldo_favor > 0 ? `Te queda saldo a favor de ${pesos(r.saldo_favor)}` : "No tienes saldo a pagar"}
      </strong>
      <p>{resultado.explicacion.split(/\n+/)[0]}</p>
      <button className="boton sello chico" onClick={() => ir("resultado")}>Ver el borrador completo</button>
    </div>
  );
}

function Widget({ m }: { m: Mensaje }) {
  const { calcular, calculando, resultado } = useSesion();
  switch (m.widget) {
    case "subir_exogena":
      return <SubirExogena />;
    case "como_descargar":
      return (
        <ol className="chico">
          <li>Entra a dian.gov.co y elige «Usuario registrado».</li>
          <li>Inicia sesión en MUISCA con tu cédula y contraseña.</li>
          <li>Busca «Consultar información exógena» y elige el año.</li>
          <li>Descarga el reporte en Excel y súbelo aquí.</li>
        </ol>
      );
    case "revisar":
      return <Revisar />;
    case "calcular":
      return (
        <div className="opciones">
          <button className="boton sello" onClick={() => void calcular()} disabled={calculando}>
            {calculando ? "Calculando…" : resultado ? "Calcular de nuevo" : "Calcular mi declaración"}
          </button>
        </div>
      );
    case "traza_documento":
      return <MesaAgentes fases={FASES_DOCUMENTO} eventos={m.eventos ?? []} compacta />;
    case "traza_calculo":
      return <MesaAgentes fases={FASES_CALCULO} eventos={m.eventos ?? []} compacta />;
    case "resultado":
      return <ResultadoCorto />;
    case "anotado":
      return <Anotado m={m} />;
    default:
      return null;
  }
}

/** El chat: se usa como pantalla principal y en el panel flotante, con el mismo hilo. */
export default function Conversacion({ compacta = false }: { compacta?: boolean }) {
  const { mensajes, enviar, escribiendo, sugerencias, procesarArchivo, archivoPendiente, setArchivoPendiente, extraccion } = useSesion();
  const [texto, setTexto] = useState("");
  const fin = useRef<HTMLDivElement>(null);
  const lista = useRef<HTMLDivElement>(null);
  const adjuntar = useRef<HTMLInputElement>(null);

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

  const mandar = (t: string) => {
    if (!t.trim() || escribiendo) return;
    setTexto("");
    void enviar(t);
  };

  return (
    <section className={`chat${compacta ? " compacta" : ""}`} aria-label="Conversación con DeclaraFácil">
      <div className="chat-mensajes" ref={lista} aria-live="polite">
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
        <div ref={fin} />
      </div>
      {sugerencias.length && !escribiendo ? (
        <div className="sugerencias">
          {sugerencias.map((s) => <button key={s} onClick={() => mandar(s)}>{s}</button>)}
        </div>
      ) : null}
      <form
        className="chat-entrada"
        onSubmit={(e) => {
          e.preventDefault();
          mandar(texto);
        }}
      >
        <button type="button" className="adjuntar" aria-label="Adjuntar exógena" title="Adjuntar exógena" onClick={() => adjuntar.current?.click()}>
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
        <label htmlFor={compacta ? "mensaje-compacto" : "mensaje"} className="visualmente-oculto">Escribe tu mensaje</label>
        <textarea
          id={compacta ? "mensaje-compacto" : "mensaje"}
          className="entrada"
          rows={1}
          value={texto}
          placeholder="Pregúntame o cuéntame algo"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              mandar(texto);
            }
          }}
        />
        <button className="boton" disabled={!texto.trim() || escribiendo}>Enviar</button>
      </form>
    </section>
  );
}
