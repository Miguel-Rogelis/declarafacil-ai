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

  if (!liq) {
    return (
      <div className="contenedor procesando-vacio">
        <h1 className="titular t-48">Primero arma tu borrador.</h1>
        <p className="lead">Cuéntale tus datos al agente o sube tus documentos; cuando calcules, aquí te llevo paso a paso a presentarla en la DIAN.</p>
        <div className="acciones-resultado"><button className="boton" onClick={() => ir("declarar")}>Ir al chat</button></div>
      </div>
    );
  }

  const r = liq.resumen;
  const pagar = r.total_a_pagar > 0;
  const favor = !pagar && r.saldo_favor > 0;
  const copiadas = casillas.filter((c) => hechos.has(`c${c.numero}`)).length;

  const pasos: { id: string; titulo: string; cuerpo: ReactNode }[] = [
    {
      id: "p1",
      titulo: "Entra a MUISCA",
      cuerpo: (
        <>
          <p>Abre <Enlace href={DIAN.muisca}>MUISCA</Enlace> y elige <strong>Persona natural</strong>, con tu cédula y tu contraseña.</p>
          <p className="suave">¿Nunca has entrado? Toca «Habilitar cuenta»: la DIAN te manda un código al correo que tienes en el RUT. ¿Olvidaste la clave? «¿Olvidó su contraseña?» la cambia con ese mismo correo.</p>
        </>
      ),
    },
    {
      id: "p2",
      titulo: "Ten lista tu firma electrónica",
      cuerpo: (
        <>
          <p>En el menú de MUISCA busca <strong>Firma electrónica</strong>. Si no la tienes, «Solicitar» y la activas con un código que llega a tu correo.</p>
          <p className="suave">Es personal: con ella firmas la declaración. Nadie más, ni esta app, debe usarla por ti.</p>
        </>
      ),
    },
    {
      id: "p3",
      titulo: `Abre el formulario 210 del año ${liq.anio_gravable}`,
      cuerpo: (
        <>
          <p>Menú <strong>Diligenciar y presentar</strong> → <strong>Formulario 210</strong> → año gravable {liq.anio_gravable}. Elige la versión para expertos: así ves todas las casillas.</p>
          <p className="suave">La DIAN te muestra una declaración sugerida. No la firmes tal cual: compárala con tu borrador en el paso siguiente.</p>
        </>
      ),
    },
    {
      id: "p4",
      titulo: "Copia casilla por casilla",
      cuerpo: casillas.length ? (
        <>
          <p>Escribe en cada casilla el valor de tu borrador. Al copiar, la casilla queda marcada. Las que no salen aquí las calcula la DIAN sola.</p>
          <div className="progreso-casillas" aria-hidden="true"><span style={{ transform: `scaleX(${casillas.length ? copiadas / casillas.length : 0})` }} /></div>
          <p className="chico suave" aria-live="polite">{copiadas} de {casillas.length} casillas listas</p>
          <ul className="casillas-dian">
            {casillas.map((c) => (
              <CasillaCopiar key={c.numero} c={c} hecha={hechos.has(`c${c.numero}`)} marcar={(si) => poner(`c${c.numero}`, si)} />
            ))}
          </ul>
        </>
      ) : (
        <p>Para este año la DIAN usaba otra numeración; copia los valores desde <button className="boton-texto" onClick={() => ir("resultado")}>tu borrador por secciones</button>.</p>
      ),
    },
    {
      id: "p5",
      titulo: "Firma y presenta",
      cuerpo: (
        <>
          <p>Revisa el resumen, toca <strong>Firmar</strong> y escribe la clave de tu firma electrónica. Luego <strong>Presentar</strong>.</p>
          <p className="suave">Descarga el PDF que te da la DIAN con el número de formulario: es tu comprobante.{liq.vencimiento ? ` Tu fecha límite es el ${fechaLarga(liq.vencimiento.fecha)}.` : ""}</p>
        </>
      ),
    },
    pagar
      ? {
          id: "p6",
          titulo: `Genera el recibo 490 y paga ${pesos(r.total_a_pagar)}`,
          cuerpo: (
            <>
              <p>En MUISCA, <strong>Recibo de pago (490)</strong>, con el valor a pagar de tu declaración. Pagas por PSE o en un banco autorizado.</p>
              <p className="suave">Paga a más tardar en tu fecha límite; después corren intereses de mora.</p>
            </>
          ),
        }
      : favor
        ? {
            id: "p6",
            titulo: `Pide tu saldo a favor de ${pesos(r.saldo_favor)}`,
            cuerpo: (
              <>
                <p>En MUISCA, <strong>Solicitud de devolución y/o compensación</strong>, con tu declaración ya presentada y una cuenta bancaria a tu nombre.</p>
                <p className="suave">Si no lo pides, lo puedes usar en tu declaración del próximo año.</p>
              </>
            ),
          }
        : {
            id: "p6",
            titulo: "Guarda tu comprobante",
            cuerpo: <p>No tienes saldo a pagar. Guarda el PDF de la declaración presentada; con eso terminaste.</p>,
          },
  ];
  const listos = pasos.filter((p) => hechos.has(p.id)).length;
  const siguiente = pasos.find((p) => !hechos.has(p.id))?.id;

  return (
    <div className="contenedor presentar">
      <FadeIn>
        <p className="suave sin-margen">Año gravable {liq.anio_gravable}</p>
        <h1 className="titular t-48 mt-1">Presenta tu declaración en la DIAN.</h1>
        <p className="lead">
          La DIAN exige que la presentes tú, con tu usuario y tu firma electrónica, así que ninguna app puede enviarla por ti. Lo demás ya está listo: sigue estos pasos con MUISCA abierto en otra pestaña.
        </p>
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
        <button className="boton secundario" onClick={() => ir("resultado")}>Volver a mi resultado</button>
        <button className="boton-texto" onClick={() => ir("declarar")}>Preguntarle algo al agente</button>
      </div>
    </div>
  );
}
