import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import type { Casilla, Fila, Formulario210 as F210 } from "../lib/api";
import { pesos } from "../lib/formato";

/** Casillas que siempre se muestran, aunque den cero: son las que la persona compara primero. */
const CLAVE = new Set([29, 31, 91, 92, 97, 111, 116, 121, 126, 129, 132, 133, 136, 137]);

function origenDe(c: Casilla, fuentes: Record<string, string[]>, filas: Fila[]): Fila[] {
  const ids = new Set(c.campos.flatMap((x) => fuentes[x] ?? []));
  return filas.filter((f) => ids.has(f.id) && !f.reemplazada_por);
}

function Fila210({ c, fuentes, filas }: { c: Casilla; fuentes: Record<string, string[]>; filas: Fila[] }) {
  const [abierta, setAbierta] = useState(false);
  const [copiada, setCopiada] = useState(false);
  const origen = useMemo(() => origenDe(c, fuentes, filas), [c, fuentes, filas]);
  const valor = c.texto ?? pesos(c.valor);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(c.texto ?? String(Math.round(c.valor)));
      setCopiada(true);
      window.setTimeout(() => setCopiada(false), 1400);
    } catch {
      /* el navegador no dejó copiar */
    }
  };
  const detalle = c.nota || c.formula || origen.length > 0;
  return (
    <div className={`f210-fila ${c.tipo}${c.valor ? "" : " cero"}`}>
      <span className="f210-num" aria-label={`Casilla ${c.numero}`}>{c.numero}</span>
      <div className="f210-nombre">
        {detalle ? (
          <button className="f210-abrir" onClick={() => setAbierta(!abierta)} aria-expanded={abierta}>{c.nombre}</button>
        ) : (
          <span>{c.nombre}</span>
        )}
        {c.tipo === "calculada" ? <span className="f210-etiqueta">La calcula la DIAN{c.formula ? ` · ${c.formula}` : ""}</span> : null}
        {c.tipo === "informativa" ? <span className="f210-etiqueta">Informativa</span> : null}
        <AnimatePresence initial={false}>
          {abierta ? (
            <motion.div className="f210-detalle" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
              {c.nota ? <p>{c.nota}</p> : null}
              {origen.length ? (
                <ul>
                  {origen.map((f) => (
                    <li key={f.id}>{f.detalle} · {f.informante ?? "reportado"}: {pesos(f.valor)}</li>
                  ))}
                </ul>
              ) : c.tipo === "dato" && c.valor && c.campos.length ? (
                <p>Sale de lo que me contaste en el chat o de un cálculo con tus datos.</p>
              ) : null}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
      <span className="f210-valor">{valor}</span>
      {c.tipo !== "calculada" && (c.valor || c.texto) ? (
        <button className={`f210-copiar no-imprimir${copiada ? " hecho" : ""}`} onClick={() => void copiar()} aria-label={`Copiar el valor de la casilla ${c.numero}`}>
          {copiada ? "Copiado" : "Copiar"}
        </button>
      ) : (
        <span className="f210-copiar-vacio" />
      )}
    </div>
  );
}

/** El borrador del formulario 210 casilla por casilla, en el orden de la DIAN, para copiarlo en MUISCA. */
export function Formulario210({ f, fuentes, filas }: { f: F210; fuentes: Record<string, string[]>; filas: Fila[] }) {
  const [todas, setTodas] = useState(false);
  const [copiadoTodo, setCopiadoTodo] = useState(false);

  if (!f.disponible) {
    return (
      <section className="f210 no-disponible" aria-label="Formulario 210">
        <header className="f210-cabeza">
          <div>
            <strong className="f210-titulo">Formulario 210</strong>
            <span className="chico suave">Año gravable {f.anio_gravable}</span>
          </div>
        </header>
        <p className="f210-motivo">{f.motivo}</p>
      </section>
    );
  }

  const visible = (c: Casilla) => todas || c.valor > 0 || (c.texto !== null && c.texto !== "0" && c.texto !== "No") || CLAVE.has(c.numero);
  const secciones = f.secciones.map((s) => ({ ...s, casillas: s.casillas.filter(visible) })).filter((s) => s.casillas.length);
  const conValor = f.secciones.flatMap((s) => s.casillas).filter((c) => c.tipo !== "calculada" && c.valor);

  const copiarTodo = async () => {
    const texto = conValor.map((c) => `Casilla ${c.numero}\t${Math.round(c.valor)}\t${c.nombre}`).join("\n");
    try {
      await navigator.clipboard.writeText(texto);
      setCopiadoTodo(true);
      window.setTimeout(() => setCopiadoTodo(false), 1600);
    } catch {
      /* sin permiso para copiar */
    }
  };

  return (
    <section className="f210" aria-labelledby="t-f210">
      <header className="f210-cabeza">
        <div>
          <h2 id="t-f210" className="f210-titulo">Formulario 210</h2>
          <span className="chico suave">Declaración de renta de personas naturales residentes · Año gravable {f.anio_gravable}</span>
        </div>
        <div className="f210-acciones no-imprimir">
          <label className="f210-todas">
            <input type="checkbox" checked={todas} onChange={(e) => setTodas(e.target.checked)} /> Ver todas las casillas
          </label>
          <button className="boton secundario chico" onClick={() => void copiarTodo()}>{copiadoTodo ? "Copiado" : "Copiar las que escribes"}</button>
        </div>
      </header>
      <div className="f210-leyenda">
        <span><i className="muestra dato" /> La escribes o la comparas con la sugerida</span>
        <span><i className="muestra calculada" /> La calcula la DIAN sola</span>
        {!todas ? <span className="suave">Las casillas que no aparecen van en 0.</span> : null}
      </div>

      {secciones.map((s) => (
        <section key={s.id} className="f210-seccion" aria-label={s.titulo}>
          <h3>{s.titulo}</h3>
          {s.casillas.map((c) => <Fila210 key={c.numero} c={c} fuentes={fuentes} filas={filas} />)}
        </section>
      ))}

      <div className="f210-pago">
        <span className="f210-num">980</span>
        <strong>Pago total</strong>
        <span className="f210-valor">{pesos(f.pago_total)}</span>
      </div>
      <ul className="f210-notas">
        {f.notas.map((n) => <li key={n}>{n}</li>)}
        <li>Es un borrador para copiar en MUISCA, no un documento oficial. La firma y la presentación son tuyas.</li>
      </ul>
      <div className="sello-borrador">BORRADOR</div>
    </section>
  );
}
