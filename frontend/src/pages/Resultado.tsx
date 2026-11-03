import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { FASES_CALCULO, FASES_DOCUMENTO, MesaAgentes } from "../components/MesaAgentes";
import type { Fila, Linea } from "../lib/api";
import { useSesion } from "../lib/estado";
import { fechaLarga, pesos } from "../lib/formato";

const ORDEN = { critica: 0, advertencia: 1, info: 2 } as const;
const TOTALES = new Set(["patrimonio_liquido", "renta_liquida_cg", "rlg_cg", "rlg_pen", "rlg_total", "impuesto_neto", "total_cargo", "saldo_pagar", "saldo_favor", "go_impuesto"]);

function LineaFormulario({ linea, fuentes, filas }: { linea: Linea; fuentes: Record<string, string[]>; filas: Fila[] }) {
  const [abierta, setAbierta] = useState(false);
  const origen = useMemo(() => {
    const ids = new Set(linea.campos.flatMap((c) => fuentes[c] ?? fuentes[c.split(".").slice(0, 2).join(".")] ?? []));
    return filas.filter((f) => ids.has(f.id));
  }, [linea, fuentes, filas]);
  return (
    <>
      <button className={`linea-210${TOTALES.has(linea.clave) ? " total" : ""}`} onClick={() => setAbierta(!abierta)} aria-expanded={abierta}>
        <span className="concepto">{linea.concepto}</span>
        <span className="valor">{pesos(linea.valor)}</span>
      </button>
      <AnimatePresence initial={false}>
        {abierta ? (
          <motion.div className="detalle-linea" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
            {linea.norma ? <div>Norma: {linea.norma}{linea.nota ? `. ${linea.nota}` : ""}</div> : <div>Resultado de un cálculo del motor{linea.nota ? `: ${linea.nota}` : ""}.</div>}
            {origen.length ? (
              <ul>
                {origen.map((f) => (
                  <li key={f.id}>{f.detalle} ({f.informante ?? "reportado"}): {pesos(f.valor)}</li>
                ))}
              </ul>
            ) : linea.campos.length ? (
              <div>Sale de tus respuestas o de un valor calculado.</div>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}

export default function Resultado() {
  const { filas, resultado, trazaDocumento, ir, reiniciar, calcular, calculando, eventosCalculo, errorCalculo, hayDatos } = useSesion();
  const lanzado = useRef(false);

  useEffect(() => {
    if (resultado || !hayDatos || calculando || lanzado.current) return;
    lanzado.current = true;
    void calcular();
  }, [resultado, hayDatos, calculando, calcular]);

  if (!hayDatos) {
    return (
      <div className="contenedor" style={{ paddingTop: "4rem" }}>
        <h1 className="titular t-48">Todavía no hay nada que calcular.</h1>
        <p className="lead">En el chat adjunta tu exógena o cuéntame tus ingresos, y aquí verás tu borrador.</p>
        <div className="acciones-resultado"><button className="boton" onClick={() => ir("declarar")}>Ir al chat</button></div>
      </div>
    );
  }

  if (!resultado) {
    return (
      <div className="contenedor procesando">
        <div>
          <h1 className="titular t-48">Armando tu borrador.</h1>
          <p className="lead">Cada agente hace una sola tarea y deja su sello cuando termina. Los cálculos no usan IA.</p>
          {errorCalculo ? (
            <div className="alerta critica" style={{ marginTop: "1.5rem" }}>
              <strong>No se pudo calcular.</strong>
              <p>{errorCalculo}</p>
              <button className="boton chico" style={{ marginTop: "0.7rem" }} onClick={() => void calcular()}>Intentar de nuevo</button>
            </div>
          ) : null}
        </div>
        <MesaAgentes fases={FASES_CALCULO} eventos={eventosCalculo} />
      </div>
    );
  }

  const { liquidacion: liq, explicacion, explicacion_con_ia: conIa } = resultado;
  const r = liq.resumen;
  const fuentes = (resultado.datos.fuentes ?? {}) as Record<string, string[]>;
  const alertas = [...liq.alertas].sort((a, b) => ORDEN[a.nivel] - ORDEN[b.nivel]);
  const pagar = r.total_a_pagar > 0;
  const favor = !pagar && r.saldo_favor > 0;

  return (
    <div className="contenedor">
      <section className="veredicto">
        <div>
          <p className="suave" style={{ margin: 0 }}>
            {liq.obligacion.obligado ? "Estás obligado a declarar" : "No estás obligado a declarar"} por el año gravable {liq.anio_gravable}.
          </p>
          <h1 className="titular t-48" style={{ marginTop: "0.6rem" }}>
            {pagar ? "Te toca pagar" : favor ? "Te queda un saldo a favor de" : "No tienes saldo a pagar."}
            {pagar || favor ? (
              <motion.span
                className={`cifra t-72 ${pagar ? "pagar" : "favor"}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
              >
                {pesos(pagar ? r.total_a_pagar : r.saldo_favor)}
              </motion.span>
            ) : null}
          </h1>
          {liq.vencimiento ? (
            <p style={{ marginBottom: 0 }}>
              {liq.vencimiento.extemporanea
                ? `Tu plazo venció el ${fechaLarga(liq.vencimiento.fecha)}. Incluimos la sanción estimada por ${liq.vencimiento.meses_retraso} mes(es) de retraso.`
                : `Tienes plazo hasta el ${fechaLarga(liq.vencimiento.fecha)}.`}
            </p>
          ) : null}
        </div>
        <dl className="desglose">
          <div><dt>Impuesto a cargo</dt><dd>{pesos(r.total_impuesto_cargo)}</dd></div>
          {r.anticipo_siguiente ? <div><dt>Anticipo del próximo año</dt><dd>+ {pesos(r.anticipo_siguiente)}</dd></div> : null}
          {r.retenciones ? <div><dt>Retenciones que ya te hicieron</dt><dd>− {pesos(r.retenciones)}</dd></div> : null}
          {r.saldo_favor_anterior ? <div><dt>Saldo a favor anterior</dt><dd>− {pesos(r.saldo_favor_anterior)}</dd></div> : null}
          {r.anticipo_anterior ? <div><dt>Anticipo pagado el año pasado</dt><dd>− {pesos(r.anticipo_anterior)}</dd></div> : null}
          {r.sancion ? <div><dt>Sanción por extemporaneidad</dt><dd>+ {pesos(r.sancion)}</dd></div> : null}
          <div className="total"><dt>{favor ? "Saldo a favor" : "Total a pagar"}</dt><dd>{pesos(favor ? r.saldo_favor : r.total_a_pagar)}</dd></div>
        </dl>
      </section>

      <div className="cuerpo-resultado">
        <section aria-labelledby="t-explicacion">
          <h2 id="t-explicacion" className="titular t-24">En palabras simples</h2>
          <div className="explicacion" style={{ marginTop: "0.8rem" }}>
            {explicacion.split(/\n+/).map((p, i) => <p key={i}>{p}</p>)}
          </div>
          <span className="verificado">
            {conIa ? "Redactado por IA y verificado cifra por cifra contra el cálculo" : "Resumen generado con plantilla a partir del cálculo"}
          </span>

          <h2 className="titular t-24" style={{ marginTop: "2.2rem" }}>Antes de firmar, revisa</h2>
          <div className="alertas">
            {alertas.map((a, i) => (
              <div key={i} className={`alerta ${a.nivel}`}>
                <strong>{a.titulo}</strong>
                <p>{a.detalle}</p>
              </div>
            ))}
          </div>
        </section>

        <aside>
          <h2 className="titular t-24">Cómo se hizo</h2>
          <p className="chico suave">Cada agente hizo una sola tarea. La IA no hizo ningún cálculo.</p>
          <MesaAgentes fases={[...(trazaDocumento.length ? FASES_DOCUMENTO : []), ...FASES_CALCULO]} eventos={[...trazaDocumento, ...resultado.traza]} compacta soloActivos />

          <h2 className="titular t-24" style={{ marginTop: "2rem" }}>Topes de obligación</h2>
          <table className="tabla" style={{ marginTop: "0.6rem" }}>
            <thead><tr><th>Tope</th><th>Tu valor</th><th>Límite</th></tr></thead>
            <tbody>
              {liq.obligacion.topes.map((t) => (
                <tr key={t.tope}>
                  <td>{t.tope}{t.supera ? " (lo superas)" : ""}</td>
                  <td>{pesos(t.valor)}</td>
                  <td>{pesos(t.limite)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </aside>
      </div>

      <section className="hoja-210" aria-labelledby="t-borrador">
        <header>
          <h2 id="t-borrador" className="titular t-24">Borrador de tu declaración</h2>
          <span className="chico suave">Año gravable {liq.anio_gravable}, UVT {pesos(liq.uvt)}. Toca una línea para ver de dónde sale.</span>
        </header>
        {liq.secciones.map((s) => (
          <section key={s.id}>
            <h3>{s.titulo}</h3>
            {s.lineas.map((l) => <LineaFormulario key={l.clave} linea={l} fuentes={fuentes} filas={filas} />)}
          </section>
        ))}
        <div className="sello-borrador" style={{ bottom: "auto", top: "-1.1rem" }}>BORRADOR</div>
      </section>

      <div className="acciones-resultado">
        <a className="boton sello" href="https://www.dian.gov.co" target="_blank" rel="noreferrer">Ir a la DIAN a firmar</a>
        <button className="boton secundario" onClick={() => window.print()}>Descargar en PDF</button>
        <button className="boton secundario" onClick={() => ir("declarar")}>Seguir en el chat</button>
        <button className="boton-texto" onClick={() => { reiniciar(); ir("inicio"); }}>Empezar de nuevo</button>
      </div>
    </div>
  );
}
