import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { FadeIn } from "../components/Movimiento";
import type { Casilla } from "../lib/api";
import { DIAN } from "../lib/ayudas";
import { useSesion } from "../lib/estado";
import { fechaLarga, pesos } from "../lib/formato";

const CURVA = [0.23, 1, 0.32, 1] as const;

/** Lo que la persona ya marcó, por año (solo en este navegador). */
function useHechos(anio: number) {
  const clave = `df-presentar-${anio}`;
  const [hechos, setHechos] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(clave) ?? "[]") as string[]);
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(clave, JSON.stringify([...hechos]));
    } catch {
      /* sin almacenamiento: igual funciona mientras la página esté abierta */
    }
  }, [clave, hechos]);
  const poner = (id: string, si: boolean) =>
    setHechos((h) => {
      const n = new Set(h);
      if (si) n.add(id);
      else n.delete(id);
      return n;
    });
  return { hechos, poner };
}

function Enlace({ href, children }: { href: string; children: string }) {
  return (
    <a className="enlace-oficial" href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4.5 2.5h5v5M9.5 2.5 3 9" /></svg>
      <span className="visualmente-oculto"> (se abre en otra pestaña)</span>
    </a>
  );
}

function CasillaCopiar({ c, hecha, marcar }: { c: Casilla; hecha: boolean; marcar: (si: boolean) => void }) {
  const [copiada, setCopiada] = useState(false);
  const valor = c.texto ?? String(Math.round(c.valor));
  const copiar = async () => {
    marcar(true); // la tocó para pasarla: queda marcada aunque el navegador no deje copiar
    try {
      await navigator.clipboard.writeText(valor);
      setCopiada(true);
      window.setTimeout(() => setCopiada(false), 1400);
    } catch {
      /* el navegador no dejó copiar: el valor está a la vista para escribirlo */
    }
  };
  return (
    <li className={`casilla-dian${hecha ? " hecha" : ""}`}>
      <label className="casilla-check">
        <input type="checkbox" checked={hecha} onChange={(e) => marcar(e.target.checked)} />
        <span className="casilla-num">{c.numero}</span>
        <span className="casilla-nombre">{c.nombre}</span>
      </label>
      <span className="casilla-valor">{c.texto ?? pesos(c.valor)}</span>
      <button type="button" className={`f210-copiar${copiada ? " hecho" : ""}`} onClick={() => void copiar()} aria-label={`Copiar el valor de la casilla ${c.numero}`}>
        {copiada ? "Copiado" : "Copiar"}
      </button>
    </li>
  );
}

export default function Presentar() {
  const { resultado, ir, anio } = useSesion();
  const liq = resultado?.liquidacion;
  const { hechos, poner } = useHechos(liq?.anio_gravable ?? anio);
  const casillas = useMemo(
    () => (liq?.formulario?.secciones ?? []).flatMap((s) => s.casillas).filter((c) => c.tipo === "dato" && (c.valor || c.texto)),
    [liq],
  );
  // Con todas las casillas copiadas, el paso 4 queda hecho solo
  const todasCopiadas = casillas.length > 0 && casillas.every((c) => hechos.has(`c${c.numero}`));
  useEffect(() => {
    if (todasCopiadas && !hechos.has("p4")) poner("p4", true);
  }, [todasCopiadas]); // eslint-disable-line react-hooks/exhaustive-deps

  const r = liq?.resumen;
  const pagar = !!r && r.total_a_pagar > 0;
  const favor = !!r && !pagar && r.saldo_favor > 0;
  const anioG = liq?.anio_gravable ?? anio;
  const copiadas = casillas.filter((c) => hechos.has(`c${c.numero}`)).length;

  const pasos: { id: string; titulo: string; cuerpo: ReactNode }[] = [
    {
      id: "p1",
      titulo: "Entra a MUISCA",
      cuerpo: (
        <>
          <p>Abre <Enlace href={DIAN.muisca}>MUISCA</Enlace> y elige <strong>Persona natural</strong>.</p>
          <p className="suave">¿Primera vez? Usa «Habilitar cuenta»: te llega un código al correo de tu RUT.</p>
        </>
      ),
    },
    {
      id: "p2",
      titulo: "Activa tu firma electrónica",
      cuerpo: <p>En el menú, <strong>Firma electrónica</strong>. Si no la tienes, «Solicitar» y la activas con un código del correo.</p>,
    },
    {
      id: "p3",
      titulo: `Abre el formulario 210 de ${anioG}`,
      cuerpo: <p><strong>Diligenciar y presentar</strong> → <strong>Formulario 210</strong> → año {anioG}, versión para expertos.</p>,
    },
    {
      id: "p4",
      titulo: "Copia tus casillas",
      cuerpo: !liq ? (
        <>
          <p>Primero arma tu borrador en el chat; aquí aparecen tus casillas listas para copiar.</p>
          <button type="button" className="boton chico secundario" onClick={() => ir("declarar")}>Armar mi borrador</button>
        </>
      ) : casillas.length ? (
        <>
          <p>Escribe cada valor en su casilla. Las demás las calcula la DIAN.</p>
          <div className="progreso-casillas" aria-hidden="true"><span style={{ transform: `scaleX(${copiadas / casillas.length})` }} /></div>
          <p className="chico suave" aria-live="polite">{copiadas} de {casillas.length} casillas listas</p>
          <ul className="casillas-dian">
            {casillas.map((c) => (
              <CasillaCopiar key={c.numero} c={c} hecha={hechos.has(`c${c.numero}`)} marcar={(si) => poner(`c${c.numero}`, si)} />
            ))}
          </ul>
        </>
      ) : (
        <p>Para este año copia los valores de <button className="boton-texto" onClick={() => ir("resultado")}>tu borrador por secciones</button>.</p>
      ),
    },
    {
      id: "p5",
      titulo: "Firma y presenta",
      cuerpo: <p><strong>Firmar</strong> con tu clave de firma y luego <strong>Presentar</strong>. Guarda el PDF: es tu comprobante.{liq?.vencimiento ? ` Plazo: ${fechaLarga(liq.vencimiento.fecha)}.` : ""}</p>,
    },
    pagar
      ? { id: "p6", titulo: `Paga ${pesos(r!.total_a_pagar)}`, cuerpo: <p>Genera el <strong>recibo 490</strong> en MUISCA y paga por PSE o en el banco.</p> }
      : favor
        ? { id: "p6", titulo: `Pide tu saldo a favor de ${pesos(r!.saldo_favor)}`, cuerpo: <p>En MUISCA, <strong>Solicitud de devolución</strong>, o déjalo para el próximo año.</p> }
        : { id: "p6", titulo: "Paga o pide tu devolución", cuerpo: <p>Si te toca pagar: <strong>recibo 490</strong> y PSE. Si te queda saldo a favor: <strong>Solicitud de devolución</strong>.</p> },
  ];
  const listos = pasos.filter((p) => hechos.has(p.id)).length;
  const siguiente = pasos.find((p) => !hechos.has(p.id))?.id;

  return (
    <div className="contenedor presentar">
      <FadeIn>
        <p className="suave sin-margen">Año gravable {anioG}</p>
        <h1 className="titular t-48 mt-1">Presenta tu declaración en la DIAN.</h1>
        <p className="lead">Seis pasos, con MUISCA abierto en otra pestaña. La firma es tuya.</p>
        <div className="avance-pasos" role="status">
          <div className="barra" aria-hidden="true"><motion.span initial={false} animate={{ scaleX: listos / pasos.length }} transition={{ duration: 0.35, ease: CURVA }} /></div>
          <span>{listos === pasos.length ? "¡Listo! Terminaste todos los pasos." : `${listos} de ${pasos.length} pasos`}</span>
        </div>
      </FadeIn>

      <ol className="pasos-dian">
        {pasos.map((p, i) => {
          const hecho = hechos.has(p.id);
          return (
            <motion.li
              key={p.id}
              className={`paso-dian${hecho ? " hecho" : ""}${p.id === siguiente ? " actual" : ""}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: Math.min(i * 0.05, 0.25), ease: CURVA }}
            >
              <span className="paso-marca" aria-hidden="true">
                <AnimatePresence mode="popLayout" initial={false}>
                  {hecho ? (
                    <motion.svg key="si" viewBox="0 0 16 16" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.6 }} transition={{ duration: 0.18, ease: CURVA }}>
                      <path d="M4 8.5l2.6 2.6L12 5.5" />
                    </motion.svg>
                  ) : (
                    <motion.span key="no" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>{i + 1}</motion.span>
                  )}
                </AnimatePresence>
              </span>
              <div className="paso-cuerpo">
                <h2 className="titular t-24">{p.titulo}</h2>
                {p.cuerpo}
                <button type="button" className={`boton chico ${hecho ? "secundario" : ""}`} onClick={() => poner(p.id, !hecho)} aria-pressed={hecho}>
                  {hecho ? "Hecho · deshacer" : "Ya lo hice"}
                </button>
              </div>
            </motion.li>
          );
        })}
      </ol>

      <div className="acciones-resultado">
        <a className="boton sello" href={DIAN.muisca} target="_blank" rel="noopener noreferrer">Abrir MUISCA<span className="visualmente-oculto"> (se abre en otra pestaña)</span></a>
        {liq ? <button className="boton secundario" onClick={() => ir("resultado")}>Volver a mi resultado</button> : null}
        <button className="boton-texto" onClick={() => ir("declarar")}>Preguntarle algo al agente</button>
      </div>
    </div>
  );
}
