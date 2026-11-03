import { motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Fila, OpcionRevision, Respuestas, ResultadoLiquidacion, Simulacion } from "../lib/api";
import { useSesion, type Mensaje } from "../lib/estado";
import { pesos } from "../lib/formato";
import { FASES_CALCULO, FASES_DOCUMENTO, MesaAgentes } from "./MesaAgentes";
import { Marca } from "./piezas";

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

function opcionesDe(f: Fila): OpcionRevision[] {
  if (f.opciones?.length) return f.opciones;
  return [
    { texto: "Sí, inclúyelo", incluir: true, campo: f.campo, recomendada: !!f.campo },
    { texto: "No, déjalo por fuera", incluir: false, campo: null, recomendada: !f.campo },
  ];
}

/** En el hilo: lo que ya se confirmó de la exógena (las preguntas van en el cuadro de abajo). */
function Revisar() {
  const { porRevisar, filas, decididas, elecciones, cambiarDecision } = useSesion();
  const hechas = filas.filter((f) => f.id in decididas);
  if (!hechas.length) {
    return <p className="chico suave" style={{ margin: 0 }}>{porRevisar.length ? "Te pregunto abajo, uno por uno." : "No hay datos pendientes por confirmar."}</p>;
  }
  return (
    <div className="revision">
      {hechas.map((f) => (
        <div key={f.id} className="revision-hecha">
          <span className="chulo" aria-hidden="true">✓</span>
          <span>
            {f.informante ?? "Dato"} ({pesos(f.valor)}): <strong>{elecciones[f.id] ?? (decididas[f.id] ? "lo incluí" : "lo dejé por fuera")}</strong>
          </span>
          <button className="boton-texto chico" onClick={() => cambiarDecision(f.id)}>Cambiar</button>
        </div>
      ))}
      {porRevisar.length ? <p className="chico suave" style={{ margin: 0 }}>Quedan {porRevisar.length}; te pregunto abajo.</p> : null}
    </div>
  );
}

/** Cuadro de preguntas arriba de la barra del chat, al estilo de un formulario corto: primero los datos de la exógena por confirmar, luego lo que pregunta el agente. */
function CuadroPregunta() {
  const { porRevisar, decidir, pregunta, enviar, escribiendo, calculando, cerrarPregunta } = useSesion();
  const [paso, setPaso] = useState(0);
  const [dichas, setDichas] = useState<string[]>([]);
  const [otra, setOtra] = useState("");
  useEffect(() => {
    setPaso(0);
    setDichas([]);
    setOtra("");
  }, [pregunta]);
  const ocupado = escribiendo || calculando;
  const fila = porRevisar[0];

  if (fila) {
    const opciones = opcionesDe(fila);
    const recomendada = opciones.find((o) => o.recomendada);
    const elegir = (o: OpcionRevision | undefined, texto: string) => decidir(fila.id, o ? o.incluir : false, o?.campo ?? null, texto);
    return (
      <div className="cuadro-pregunta" role="group" aria-label="Confirma un dato de tu exógena">
        <div className="cuadro-cabeza">
          <span className="cuadro-titulo">Confirma un dato de tu exógena</span>
          <span className="chico suave">{porRevisar.length > 1 ? `Quedan ${porRevisar.length}` : "Último"}</span>
        </div>
        <p className="cuadro-texto">{fila.pregunta || `${fila.informante ?? "Una entidad"} reportó ${pesos(fila.valor)} por «${fila.detalle}». ¿Lo incluyo en tu declaración?`}</p>
        {fila.ayuda ? <p className="chico suave cuadro-ayuda">{fila.ayuda}</p> : null}
        <div className="cuadro-opciones">
          {opciones.map((o, i) => (
            <button key={o.texto} className={`opcion${o.recomendada ? " recomendada" : ""}`} onClick={() => elegir(o, o.texto)}>
              <span className="num">{i + 1}</span>
              <span>{o.texto}</span>
              {o.recomendada ? <span className="sello-chico">Recomendado</span> : null}
            </button>
          ))}
          <button className="opcion" onClick={() => elegir(recomendada, recomendada ? `No sé (${recomendada.texto.toLowerCase()})` : "No sé (lo dejé por fuera)")}>
            <span className="num">{opciones.length + 1}</span>
            <span>No sé</span>
          </button>
        </div>
      </div>
    );
  }

  const partes = pregunta?.partes ?? [];
  if (!pregunta || !partes.length) return null;
  const parte = partes[Math.min(paso, partes.length - 1)];
  const responder = (texto: string) => {
    if (ocupado) return;
    const todas = [...dichas, texto];
    if (paso + 1 < partes.length) {
      setDichas(todas);
      setPaso(paso + 1);
      setOtra("");
    } else {
      void enviar(todas.join(". "));
    }
  };
  return (
    <div className="cuadro-pregunta" role="group" aria-label="Pregunta de DeclaraFácil">
      <div className="cuadro-cabeza">
        <span className="cuadro-titulo">{(pregunta.intro || "Necesito un dato").replace(/[:.]\s*$/, "")}</span>
        {partes.length > 1 ? <span className="chico suave cuadro-paso">{paso + 1} de {partes.length}</span> : null}
        <button className="cuadro-cerrar" aria-label="Cerrar la pregunta" title="Cerrar (puedes escribir tu respuesta abajo)" onClick={cerrarPregunta}>×</button>
      </div>
      <p className="cuadro-texto">{parte.texto}</p>
      {parte.opciones.length ? (
        <div className="cuadro-opciones">
          {parte.opciones.map((o, i) => (
            <button key={o} className="opcion" disabled={ocupado} onClick={() => responder(o)}>
              <span className="num">{i + 1}</span>
              <span>{o}</span>
            </button>
          ))}
        </div>
      ) : null}
      <form
        className="cuadro-otra"
        onSubmit={(e) => {
          e.preventDefault();
          if (otra.trim()) responder(otra.trim());
        }}
      >
        <label htmlFor="otra-respuesta" className="visualmente-oculto">Tu respuesta</label>
        <input
          id="otra-respuesta"
          className="entrada"
          value={otra}
          placeholder={parte.opciones.length ? "Otra respuesta" : "Escribe tu respuesta"}
          onChange={(e) => setOtra(e.target.value)}
          autoFocus={!parte.opciones.length}
        />
        <button className="boton chico" disabled={!otra.trim() || ocupado}>{paso + 1 < partes.length ? "Siguiente" : "Responder"}</button>
      </form>
      {pregunta.intencion === "calcular" ? (
        <button className="boton-texto chico cuadro-saltar" disabled={ocupado} onClick={() => void enviar("calcula así")}>Calcular con lo que hay</button>
      ) : null}
    </div>
  );
}

function Anotado({ m }: { m: Mensaje }) {
  const { deshacer } = useSesion();
  return (
    <div className={`anotado${m.deshecho ? " deshecho" : ""}`}>
      {m.anotaciones?.length ? (
        <>
          <span className="chico suave">{m.deshecho ? "Deshice estos datos:" : "Anoté:"}</span>
          <ul>
            {m.anotaciones.map((a) => (
              <li key={a.clave + a.etiqueta}>
                {a.etiqueta}: <strong>{a.valor}</strong>
                {a.detalle ? <span className="chico suave"> ({a.detalle})</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {m.quitadas?.length ? (
        <>
          <span className="chico suave">{m.deshecho ? "Volví a poner:" : "Quité:"}</span>
          <ul>{m.quitadas.map((q) => <li key={q}>{q}</li>)}</ul>
        </>
      ) : null}
      {!m.deshecho ? <button className="boton-texto chico" onClick={() => deshacer(m.id)}>Deshacer</button> : null}
    </div>
  );
}

function TarjetaSimulacion({ s }: { s: Simulacion }) {
  const filas: [string, number, number][] = [
    ["Impuesto a cargo", s.impuesto_antes, s.impuesto_despues],
    ["Total a pagar", s.total_antes, s.total_despues],
    ["Saldo a favor", s.favor_antes, s.favor_despues],
  ];
  return (
    <div className="simulacion">
      <span className="chico suave">Simulación con: {s.cambios.join("; ")}</span>
      <table>
        <thead>
          <tr><th scope="col"></th><th scope="col">Hoy</th><th scope="col">Con el cambio</th></tr>
        </thead>
        <tbody>
          {filas.filter(([, a, b]) => a || b).map(([nombre, a, b]) => (
            <tr key={nombre}>
              <th scope="row">{nombre}</th>
              <td>{pesos(a)}</td>
              <td className={b < a ? "baja" : b > a ? "sube" : undefined}>{pesos(b)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function supuestos(r: Respuestas, conExogena: boolean): string[] {
  const s: string[] = [];
  if (!conExogena && !r.retenciones_no_reportadas) s.push("sin retenciones");
  if (!r.dependientes) s.push("sin personas a cargo");
  if (!r.medicina_prepagada && !r.intereses_vivienda && !r.aportes_voluntarios_afc_fpv) s.push("sin deducciones");
  if (r.declaraciones_previas === null) s.push("primera declaración");
  if (!r.ultimos_dos_digitos_nit) s.push("sin fecha límite (falta tu cédula)");
  return s;
}

function ResultadoCorto({ r, actual, recalculo }: { r: ResultadoLiquidacion; actual: boolean; recalculo?: boolean }) {
  const { ir, respuestas, extraccion } = useSesion();
  const sup = actual ? supuestos(respuestas, !!extraccion) : [];
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
      {sup.length ? <span className="chico suave">Calculé {sup.join(", ")}. Si algo no aplica, dímelo y lo actualizo.</span> : null}
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
    case "simulacion":
      return m.simulacion ? <TarjetaSimulacion s={m.simulacion} /> : null;
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
          {mensajes.filter((m) => !m.oculto).map((m) =>
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
      <div className="chat-entrada">
        <div className="chat-columna">
        <CuadroPregunta />
        <form
          className="fila-entrada"
          onSubmit={(e) => {
            e.preventDefault();
            mandar(texto);
          }}
        >
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
        </form>
        </div>
      </div>
    </section>
  );
}
