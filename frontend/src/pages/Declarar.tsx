import { AnimatePresence, motion } from "motion/react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import Conversacion from "../components/Conversacion";
import { BorrarDatos } from "../components/BorrarDatos";
import { VentanaEntrar } from "../components/CuentaBoton";
import { Ficha } from "../components/Ficha";
import { MisDocumentos } from "../components/MisDocumentos";
import type { DocumentoCargado, Fila, Respuestas } from "../lib/api";
import { useDialogoModal } from "../lib/dialogo";
import { useSesion } from "../lib/estado";
import { GRUPOS, NOMBRES_CAMPO, pesos } from "../lib/formato";

function extrasDeRespuestas(r: Respuestas): { concepto: string; valor: number | null }[] {
  const go = r.ganancias_ocasionales;
  const pares: [string, number][] = [
    ["Salarios", r.salarios_no_reportados],
    ["Cesantías", r.cesantias_no_reportadas ?? 0],
    ["Honorarios", r.honorarios_no_reportados],
    ["Pensión", r.pensiones_no_reportadas],
    ["Arriendos", r.arriendos_no_reportados],
    ["Otros ingresos", r.otros_ingresos_no_reportados],
    ["Dividendos", r.dividendos_no_reportados],
    ["Retenciones", r.retenciones_no_reportadas],
    ["Medicina prepagada", r.medicina_prepagada],
    ["Intereses de vivienda", r.intereses_vivienda],
    ["Aportes voluntarios y AFC", r.aportes_voluntarios_afc_fpv],
    ["4x1000 pagado", r.gmf_pagado],
    ["Intereses del ICETEX", r.intereses_icetex],
    ["Gastos del inmueble que arriendas", r.costos_arriendos],
    ["Donaciones que hiciste", r.donaciones_realizadas],
    ["Costos de tu trabajo independiente", r.costos_independiente],
    ["Venta de tu casa (utilidad)", go.utilidad_venta_casa_habitacion],
    ["Venta de otros bienes (utilidad)", go.utilidad_venta_otros_activos],
    ["Herencias", go.herencia_porcion_heredero + go.herencia_vivienda_causante + go.herencia_otros_inmuebles],
    ["Donaciones", go.donaciones_recibidas],
    ["Seguro de vida", go.seguros_vida],
    ["Loterías y premios", go.loterias_premios],
    ["Impuesto del año anterior", r.impuesto_neto_anio_anterior],
    ["Anticipo del año anterior", r.anticipo_anio_anterior],
  ];
  const salida: { concepto: string; valor: number | null }[] = pares.filter(([, v]) => v > 0).map(([concepto, valor]) => ({ concepto, valor }));
  if (r.dependientes) salida.unshift({ concepto: `Personas a cargo: ${r.dependientes}`, valor: null });
  r.bienes_adicionales.forEach((b) => salida.push({ concepto: `Bien: ${b.concepto}`, valor: b.valor }));
  r.deudas_adicionales.forEach((b) => salida.push({ concepto: `Deuda: ${b.concepto}`, valor: b.valor }));
  if (r.declaraciones_previas !== null) salida.push({ concepto: `Declaraciones anteriores: ${["ninguna", "una", "dos o más", "tres o más"][r.declaraciones_previas]}`, valor: null });
  if (r.ultimos_dos_digitos_nit) salida.push({ concepto: `Cédula terminada en ${r.ultimos_dos_digitos_nit}`, valor: null });
  return salida;
}

const FUENTE_CORTA: Record<string, string> = {
  exogena: "exógena",
  certificado_220: "certificado de ingresos",
  certificado_bancario: "certificado del banco",
  certificado_vivienda: "certificado de vivienda",
  certificado_prepagada: "certificado de prepagada",
  certificado_voluntarios: "certificado de aportes",
  certificado_cesantias: "certificado de cesantías",
  certificado_retencion: "certificado de retención",
  declaracion_anterior: "declaración anterior",
  predial: "predial",
  desconocido: "documento",
};

function HojaTrabajo({ filas, respuestas, documentos }: { filas: Fila[]; respuestas: Respuestas; documentos: DocumentoCargado[] }) {
  const grupos = useMemo(
    () =>
      GRUPOS.map((g) => ({
        ...g,
        filas: filas.filter((f) => f.campo && g.prefijos.some((p) => f.campo!.startsWith(p)) && f.tratamiento !== "informativo"),
      })).filter((g) => g.filas.length),
    [filas],
  );
  const extras = extrasDeRespuestas(respuestas);
  return (
    <div className="hoja-trabajo-cuerpo">
      {!filas.length && !extras.length ? (
        <p className="vacio">Aquí aparece cada dato de tu declaración y de dónde sale.</p>
      ) : null}
      {documentos.length ? (
        <div className="grupo">
          <h3>Documentos que leí</h3>
          {documentos.map((d) => (
            <div key={d.id} className="fila-hoja">
              <span className="concepto">{d.etiqueta}</span>
              <span className="monto" />
              <span className="origen">{d.nombre}</span>
            </div>
          ))}
        </div>
      ) : null}
      {grupos.map((g) => (
        <div className="grupo" key={g.titulo}>
          <h3>{g.titulo}</h3>
          {g.filas.map((f) => (
            <div key={f.id} className={`fila-hoja${f.tratamiento === "revisar" ? " revisar" : ""}`}>
              <span className="concepto">{NOMBRES_CAMPO[f.campo!] ?? f.detalle}</span>
              <span className="monto">{pesos(f.valor)}</span>
              <span className="origen">
                {f.informante ?? "Reportado"} · {FUENTE_CORTA[f.fuente ?? "exogena"] ?? "documento"}
                {f.tratamiento === "revisar" ? ", falta tu confirmación" : f.origen_mapeo === "ia" ? ", ubicado por IA" : ""}
              </span>
            </div>
          ))}
        </div>
      ))}
      {extras.length ? (
        <div className="grupo">
          <h3>Lo que me contaste</h3>
          {extras.map((e) => (
            <div key={e.concepto} className="fila-hoja">
              <span className="concepto">{e.concepto}</span>
              <span className="monto">{e.valor == null ? "" : pesos(e.valor)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** El panel lateral de datos: un <dialog> nativo que entra desde la derecha. */
function PanelDatos({ onCerrar, anio, children }: { onCerrar: () => void; anio: number; children: ReactNode }) {
  const panel = useRef<HTMLDialogElement>(null);
  useDialogoModal(panel, onCerrar);
  return (
    <motion.dialog
      id="panel-datos"
      className="panel-datos"
      ref={panel}
      aria-labelledby="titulo-panel-datos"
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "tween", duration: 0.22 }}
    >
      <header>
        <div>
          <h2 id="titulo-panel-datos" className="titular t-21">Tus datos, año {anio}</h2>
          <span className="chico suave">Cada cifra muestra de dónde sale.</span>
        </div>
        <button className="boton-texto" onClick={onCerrar} autoFocus>Cerrar</button>
      </header>
      {children}
    </motion.dialog>
  );
}

/** Sin sesión no hay chat: la declaración siempre queda en la cuenta de la persona. */
function PedirEntrar() {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="pedir-entrar">
      <motion.div className="pedir-entrar-caja" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}>
        <h1 className="titular t-36">Entra para empezar tu declaración</h1>
        <p className="suave">Así queda guardada en tu cuenta, con tus documentos.</p>
        <button type="button" className="boton" onClick={() => setAbierta(true)}>Entrar</button>
      </motion.div>
      <AnimatePresence>{abierta ? <VentanaEntrar onCerrar={() => setAbierta(false)} /> : null}</AnimatePresence>
    </div>
  );
}

export default function Declarar() {
  const { cuentaLista, nubeActiva, cuenta } = useSesion();
  if (!cuentaLista) {
    return (
      <div className="pedir-entrar" aria-busy="true">
        <p className="suave">Conectando…</p>
      </div>
    );
  }
  if (nubeActiva && !cuenta) return <PedirEntrar />;
  return <Chat />;
}

function Chat() {
  const { filas, respuestas, anio, mensajes, reiniciar, porRevisar, documentos, ficha, cuenta } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const boton = useRef<HTMLButtonElement>(null);

  const cantidad = filas.filter((f) => f.campo && f.tratamiento !== "informativo").length + extrasDeRespuestas(respuestas).length;
  const barra = (
    <div className="chat-barra">
      <div className="chat-columna fila-barra">
        {mensajes.length ? <BorrarDatos onBorrar={() => reiniciar({ nube: true })} nube={!!cuenta} /> : <span />}
        <button ref={boton} className="boton secundario chico" onClick={() => setAbierto(true)} aria-expanded={abierto} aria-controls="panel-datos">
          {cuenta ? "Tus datos y documentos" : "Tus datos"}{cantidad ? ` (${cantidad})` : ""}{porRevisar.length ? ` · ${porRevisar.length} por confirmar` : ""}
        </button>
      </div>
      {mensajes.length ? <div className="chat-columna"><Ficha items={ficha} /></div> : null}
    </div>
  );
  return (
    <div className="pantalla-chat">
      <Conversacion barra={barra} />
      <AnimatePresence>
        {abierto ? (
          <PanelDatos onCerrar={() => setAbierto(false)} anio={anio}>
            <MisDocumentos onCerrar={() => setAbierto(false)} />
            <HojaTrabajo filas={filas} respuestas={respuestas} documentos={documentos} />
          </PanelDatos>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
