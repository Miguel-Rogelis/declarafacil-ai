import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import Conversacion from "../components/Conversacion";
import type { DocumentoCargado, Fila, Respuestas } from "../lib/api";
import { useSesion } from "../lib/estado";
import { GRUPOS, NOMBRES_CAMPO, pesos } from "../lib/formato";

function extrasDeRespuestas(r: Respuestas): { concepto: string; valor: number | null }[] {
  const go = r.ganancias_ocasionales;
  const pares: [string, number][] = [
    ["Salarios", r.salarios_no_reportados],
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
        <p className="vacio">Aquí verás cada dato de tu declaración y de dónde sale: lo que traigan tu exógena y tus certificados, y lo que me cuentes en el chat.</p>
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

export default function Declarar() {
  const { filas, respuestas, anio, mensajes, reiniciar, porRevisar, documentos } = useSesion();
  const [abierto, setAbierto] = useState(false);
  const cantidad = filas.filter((f) => f.campo && f.tratamiento !== "informativo").length + extrasDeRespuestas(respuestas).length;
  const barra = (
    <div className="chat-barra">
      <div className="chat-columna fila-barra">
        {mensajes.length ? (
          <button className="boton-texto chico" onClick={() => reiniciar()}>Empezar de nuevo</button>
        ) : <span />}
        <button className="boton secundario chico" onClick={() => setAbierto(true)} aria-expanded={abierto} aria-controls="panel-datos">
          Tus datos{cantidad ? ` (${cantidad})` : ""}{porRevisar.length ? ` · ${porRevisar.length} por confirmar` : ""}
        </button>
      </div>
    </div>
  );
  return (
    <div className="pantalla-chat">
      <Conversacion barra={barra} />
      <AnimatePresence>
        {abierto ? (
          <>
            <motion.div className="velo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setAbierto(false)} />
            <motion.aside
              id="panel-datos"
              className="panel-datos"
              role="dialog"
              aria-label="Tus datos"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "tween", duration: 0.22 }}
              onKeyDown={(e) => e.key === "Escape" && setAbierto(false)}
            >
              <header>
                <div>
                  <h2 className="titular t-21">Tus datos, año {anio}</h2>
                  <span className="chico suave">Lo que traen tus documentos y lo que me contaste. Cada cifra muestra de dónde sale.</span>
                </div>
                <button className="boton-texto" onClick={() => setAbierto(false)} autoFocus>Cerrar</button>
              </header>
              <HojaTrabajo filas={filas} respuestas={respuestas} documentos={documentos} />
            </motion.aside>
          </>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
