import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Formulario210 } from "../components/Formulario210";
import { FASES_CALCULO, FASES_DOCUMENTO, MesaAgentes } from "../components/MesaAgentes";
import { FadeIn, Revelar } from "../components/Movimiento";
import { Pestanas } from "../components/piezas";
import Counter from "../components/reactbits/Counter";
import type { Fila, Linea } from "../lib/api";
import { useSesion } from "../lib/estado";
import { fechaLarga, pesos } from "../lib/formato";
import { archivoCalendario, descargar, documentosDe } from "../lib/ayudas";
import SpotlightCard from "../components/reactbits/SpotlightCard";
import { leerDeLaNube } from "../lib/nube";
import type { Resumen } from "../lib/api";

/** Con cuenta: la declaración del año anterior, si está guardada, para comparar. */
function CompararAnios({ anio }: { anio: number }) {
  const { cuenta, resultado } = useSesion();
  const [antes, setAntes] = useState<Resumen | null>(null);
  useEffect(() => {
    if (!cuenta) return setAntes(null);
    let vivo = true;
    leerDeLaNube(anio - 1)
      .then((g) => vivo && setAntes(g?.resultado?.liquidacion.resumen ?? null))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [cuenta, anio]);
  const ahora = resultado?.liquidacion.resumen;
  if (!antes || !ahora) return null;
  const saldo = (r: Resumen) => r.total_a_pagar - r.saldo_favor;
  const filas: [string, number, number][] = [
    ["Ingresos del año", antes.ingresos_brutos_totales, ahora.ingresos_brutos_totales],
    ["Patrimonio líquido", antes.patrimonio_liquido, ahora.patrimonio_liquido],
    ["Impuesto de renta", antes.impuesto_neto_renta, ahora.impuesto_neto_renta],
    ["A pagar (o a favor, con −)", saldo(antes), saldo(ahora)],
  ];
  return (
    <section className="comparar-anios no-imprimir" aria-labelledby="t-comparar">
      <h2 id="t-comparar" className="titular t-24">Comparado con tu declaración de {anio - 1}</h2>
      <div className="tabla-scroll">
        <table>
          <thead><tr><th>Concepto</th><th>{anio - 1}</th><th>{anio}</th><th>Cambio</th></tr></thead>
          <tbody>
            {filas.map(([n, a, b]) => (
              <tr key={n}>
                <td>{n}</td>
                <td>{pesos(a)}</td>
                <td>{pesos(b)}</td>
                <td className={b > a ? "sube" : b < a ? "baja" : ""}>{b === a ? "igual" : `${b > a ? "+" : "−"} ${pesos(Math.abs(b - a))}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

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
  const [vista, setVista] = useState<"formulario" | "secciones">("formulario");

  useEffect(() => {
    if (resultado || !hayDatos || calculando || lanzado.current) return;
    lanzado.current = true;
    void calcular();
  }, [resultado, hayDatos, calculando, calcular]);

  if (!hayDatos) {
    return (
      <div className="contenedor procesando-vacio">
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
            <div className="alerta critica mt-2" role="alert">
              <strong>No se pudo calcular.</strong>
              <p>{errorCalculo}</p>
              <button className="boton chico mt-1" onClick={() => void calcular()}>Intentar de nuevo</button>
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
  const consejos = resultado.consejos ?? [];
  const docs = documentosDe(resultado.datos);

  return (
    <div className="contenedor">
      <section className="veredicto">
        <FadeIn>
          <p className="suave sin-margen">
            {liq.obligacion.obligado ? "Estás obligado a declarar" : "No estás obligado a declarar"} por el año gravable {liq.anio_gravable}.
          </p>
          <h1 className="titular t-48 mt-1">
            {pagar ? "Te toca pagar" : favor ? "Te queda un saldo a favor de" : "No tienes saldo a pagar."}
            {pagar || favor ? (
              <motion.span
                className={`cifra t-72 ${pagar ? "pagar" : "favor"}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
              >
                <Counter
                  value={Math.round(pagar ? r.total_a_pagar : r.saldo_favor)}
                  locale="es-CO"
                  format={{ maximumFractionDigits: 0 }}
                  prefix="$"
                  fontSize="1em"
                  duration={0.9}
                  stagger={0.05}
                />
              </motion.span>
            ) : null}
          </h1>
          {liq.vencimiento ? (
            <p className="sin-margen mt-1 fecha-limite">
              {liq.vencimiento.extemporanea
                ? `Tu plazo venció el ${fechaLarga(liq.vencimiento.fecha)}. Incluimos la sanción estimada por ${liq.vencimiento.meses_retraso} mes(es) de retraso.`
                : `Tienes plazo hasta el ${fechaLarga(liq.vencimiento.fecha)}.`}
              {!liq.vencimiento.extemporanea ? (
                <button type="button" className="boton-calendario no-imprimir" onClick={() => {
                  const b = archivoCalendario(liq);
                  if (b) descargar(b, `declarar-renta-${liq.anio_gravable}.ics`);
                }}>
                  <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="3.5" width="11" height="10" rx="2" /><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3M8 8.5v3M6.5 10h3" /></svg>
                  Agregar a mi calendario
                </button>
              ) : null}
            </p>
          ) : (
            <p className="sin-margen mt-1 suave">Dile al agente en qué dos números termina tu cédula y te digo tu fecha límite.</p>
          )}
        </FadeIn>
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

      <Revelar className="cuerpo-resultado">
        <section aria-labelledby="t-explicacion">
          <h2 id="t-explicacion" className="titular t-24">En palabras simples</h2>
          <div className="explicacion mt-1">
            {explicacion.split(/\n+/).map((p, i) => <p key={i}>{p}</p>)}
          </div>
          <span className="verificado">
            {conIa ? "Redactado por IA y verificado cifra por cifra contra el cálculo" : "Resumen generado con plantilla a partir del cálculo"}
          </span>

          <h2 className="titular t-24 mt-3">Antes de firmar, revisa</h2>
          <div className="alertas">
            {alertas.map((a, i) => (
              <div key={i} className={`alerta ${a.nivel}`}>
                <strong>{a.titulo}</strong>
                <p>{a.detalle}</p>
              </div>
            ))}
          </div>
        </section>

        <aside className="aside-resultado">
          <h2 className="titular t-24">Topes de obligación</h2>
          <p className="chico suave">Basta con superar uno para estar obligado a declarar.</p>
          <div className="tabla-scroll">
          <table className="tabla">
            <thead><tr><th>Tope</th><th>Tu valor</th><th>Límite</th></tr></thead>
            <tbody>
              {liq.obligacion.topes.map((t) => (
                <tr key={t.tope}>
                  <td>{t.tope}{t.supera ? <strong> (lo superas)</strong> : ""}</td>
                  <td>{pesos(t.valor)}</td>
                  <td>{pesos(t.limite)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>

          <h2 className="titular t-24 mt-3">Cómo se hizo</h2>
          <p className="chico suave">Cada agente hizo una sola tarea. La IA no hizo ningún cálculo.</p>
          <details className="plegable">
            <summary>Ver qué hizo cada agente</summary>
            <MesaAgentes fases={[...(trazaDocumento.length ? FASES_DOCUMENTO : []), ...FASES_CALCULO]} eventos={[...trazaDocumento, ...resultado.traza]} compacta soloActivos />
          </details>
        </aside>
      </Revelar>

      <Revelar className={`ayudas-resultado${consejos.length ? "" : " una"}`}>
        {consejos.length ? (
          <section className="consejos no-imprimir" aria-labelledby="t-consejos">
            <h2 id="t-consejos" className="titular t-24">Para pagar menos el próximo año</h2>
            <p className="chico suave">Calculado con tu mismo caso: es lo que te habrías ahorrado este año.</p>
            <div className="consejos-lista">
              {consejos.map((c) => (
                <SpotlightCard key={c.clave} className="consejo" spotlightColor="rgba(90, 59, 192, 0.12)">
                  <span className="consejo-ahorro">Ahorras unos {pesos(c.ahorro)}</span>
                  <h3>{c.titulo}</h3>
                  <p>{c.detalle}</p>
                </SpotlightCard>
              ))}
            </div>
          </section>
        ) : null}

        <section className="documentos-lista" aria-labelledby="t-docs">
          <h2 id="t-docs" className="titular t-24">Documentos para tener a mano</h2>
          <p className="chico suave">Según lo que trae tu declaración. Guárdalos: la DIAN te los puede pedir hasta 5 años después.</p>
          <ul>
            {docs.map((d) => (
              <li key={d.clave}>
                <strong>{d.nombre}</strong>
                <span>
                  {d.donde}
                  {d.enlace ? <> <a className="enlace-oficial" href={d.enlace} target="_blank" rel="noopener noreferrer">Abrir<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4.5 2.5h5v5M9.5 2.5 3 9" /></svg></a></> : null}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </Revelar>

      <CompararAnios anio={liq.anio_gravable} />

      <Pestanas
        className="no-imprimir"
        pegadas
        etiqueta="Cómo ver tu borrador"
        idPanel="panel-borrador"
        valor={vista}
        onCambio={setVista}
        opciones={[
          { valor: "formulario", texto: "Formulario 210 casilla por casilla" },
          { valor: "secciones", texto: "Explicado por secciones" },
        ]}
      />
      <div id="panel-borrador" role="tabpanel" aria-labelledby={`pestana-panel-borrador-${vista}`}>
      {vista === "formulario" && liq.formulario ? (
        <Formulario210 f={liq.formulario} fuentes={fuentes} filas={filas} />
      ) : (
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
          <div className="sello-borrador arriba" aria-hidden="true">BORRADOR</div>
        </section>
      )}
      </div>

      <div className="acciones-resultado">
        <button className="boton sello" onClick={() => ir("presentar")}>Presentar en la DIAN, paso a paso</button>
        <button className="boton secundario" onClick={() => window.print()}>Guardar como PDF</button>
        <button className="boton secundario" onClick={() => ir("declarar")}>Seguir en el chat</button>
        <button className="boton-texto" onClick={() => { reiniciar(); ir("inicio"); }}>Empezar de nuevo</button>
      </div>
    </div>
  );
}
