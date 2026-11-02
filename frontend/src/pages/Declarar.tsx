import { useMemo } from "react";
import Conversacion from "../components/Conversacion";
import type { Fila, Respuestas } from "../lib/api";
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

function HojaTrabajo({ filas, respuestas }: { filas: Fila[]; respuestas: Respuestas }) {
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
        <p className="vacio">Aquí verás cada dato de tu declaración y de dónde sale: lo que traiga tu exógena y lo que me cuentes en el chat.</p>
      ) : null}
      {grupos.map((g) => (
        <div className="grupo" key={g.titulo}>
          <h3>{g.titulo}</h3>
          {g.filas.map((f) => (
            <div key={f.id} className={`fila-hoja${f.tratamiento === "revisar" ? " revisar" : ""}`}>
              <span className="concepto">{NOMBRES_CAMPO[f.campo!] ?? f.detalle}</span>
              <span className="monto">{pesos(f.valor)}</span>
              <span className="origen">
                {f.informante ?? "Reportado"}
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

function LoQueFalta() {
  const { extraccion, temas, porRevisar, resultado, respuestas } = useSesion();
  const sinExogena = !extraccion && temas.includes("exogena");
  const items = [
    sinExogena
      ? { texto: "Tus ingresos", hecho: temas.includes("ingresos") || respuestas.salarios_no_reportados + respuestas.honorarios_no_reportados + respuestas.pensiones_no_reportadas > 0 }
      : { texto: "Tu exógena", hecho: !!extraccion },
    ...(extraccion ? [{ texto: "Confirmar datos dudosos", hecho: porRevisar.length === 0 }] : []),
    { texto: "Personas a cargo", hecho: temas.includes("dependientes") },
    { texto: "Gastos que bajan el impuesto", hecho: temas.includes("gastos") },
    { texto: "Otros ingresos y bienes", hecho: temas.includes("otros") },
    { texto: "Tu historial con la DIAN", hecho: temas.includes("historial") },
    { texto: "Calcular el borrador", hecho: !!resultado },
  ];
  return (
    <ol className="falta" aria-label="Lo que falta">
      {items.map((i) => (
        <li key={i.texto} className={i.hecho ? "hecho" : undefined}>
          <span className="marca-falta" aria-hidden="true">{i.hecho ? "✓" : ""}</span>
          {i.texto}
          <span className="visualmente-oculto">{i.hecho ? " (listo)" : " (pendiente)"}</span>
        </li>
      ))}
    </ol>
  );
}

export default function Declarar() {
  const { filas, respuestas, anio } = useSesion();
  return (
    <div className="contenedor taller">
      <Conversacion />
      <aside className="hoja-trabajo" aria-label="Tu declaración en construcción">
        <header>
          <h2 className="titular t-21">Tu declaración, año {anio}</h2>
          <span className="chico suave">No hay un orden obligatorio: pregunta o cuéntame lo que quieras.</span>
          <LoQueFalta />
        </header>
        <HojaTrabajo filas={filas} respuestas={respuestas} />
      </aside>
    </div>
  );
}
