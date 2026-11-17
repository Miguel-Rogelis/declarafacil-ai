import { motion } from "motion/react";
import { Fragment, type ReactNode } from "react";
import { Candado, LetraD } from "../components/piezas";
import { DeboDeclarar } from "../components/DeboDeclarar";
import { FadeIn, Revelar } from "../components/Movimiento";
import { selloHex, useTemaActual } from "../components/Navegacion";
import SpotlightCard from "../components/reactbits/SpotlightCard";
import { useDemo } from "../lib/demo";
import { useSesion, type Ruta } from "../lib/estado";


const PALABRAS = ["Tu", "declaración", "de", "renta,", "lista", "para", "revisar."];
const CURVA = [0.22, 1, 0.36, 1] as const;

/** El titular entra palabra por palabra desenfocándose; la d de «declaración» es el logo y llega al final, desvaneciéndose en su sitio. */
function TituloPortada() {
  const finPalabras = 0.15 + PALABRAS.length * 0.08;
  return (
    <span className="titulo-portada">
      <span className="visualmente-oculto">{PALABRAS.join(" ")}</span>
      {PALABRAS.map((p, i) => (
        <Fragment key={p}>
        {i > 0 ? " " : null}
        <motion.span
          aria-hidden="true"
          className="palabra"
          initial={{ opacity: 0, y: 18, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.7, delay: 0.15 + i * 0.08, ease: CURVA }}
        >
          {p === "declaración" ? (
            <>
              <motion.span
                className="d-logo"
                initial={{ opacity: 0, scale: 1.35, filter: "blur(14px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                transition={{ duration: 1.1, delay: finPalabras + 0.2, ease: CURVA }}
              >
                <LetraD />
              </motion.span>
              eclaración
            </>
          ) : p}
        </motion.span>
        </Fragment>
      ))}
    </span>
  );
}

type Paso = { n: string; titulo: string; texto: string; ruta: Ruta; icono: ReactNode };

const RUTA: Paso[] = [
  {
    n: "1", titulo: "Cuéntale tus datos", texto: "Sube tu exógena o escribe «gano 4 millones al mes».", ruta: "declarar",
    icono: <path d="M4 5.5h16v10H9l-5 4z" />,
  },
  {
    n: "2", titulo: "Pide el cálculo", texto: "Ves cuánto pagas o te devuelven, y por qué.", ruta: "resultado",
    icono: <><rect x="5" y="3.5" width="14" height="17" rx="2.5" /><path d="M8.5 8h7M8.5 12h2M13.5 12h2M8.5 16h2M13.5 16h2" /></>,
  },
  {
    n: "3", titulo: "Preséntala en la DIAN", texto: "Te guiamos en MUISCA, casilla por casilla.", ruta: "presentar",
    icono: <><path d="M5 12.5l4.5 4.5L19 7.5" /></>,
  },
];

/** La ruta completa en tres tarjetas que llevan a cada parte de la app. */
function RutaPortada({ ir, hayResultado }: { ir: (r: Ruta) => void; hayResultado: boolean }) {
  return (
    <ol className="ruta-portada" aria-label="Cómo funciona">
      {RUTA.map((p, i) => (
        <motion.li
          key={p.n}
          initial={{ opacity: 0, y: 14, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.6, delay: 0.35 + i * 0.12, ease: CURVA }}
        >
          <button type="button" className="paso-ruta" onClick={() => ir(p.ruta === "resultado" && !hayResultado ? "declarar" : p.ruta)}>
            <span className="paso-ruta-icono" aria-hidden="true">
              <svg viewBox="0 0 24 24">{p.icono}</svg>
            </span>
            <span className="paso-ruta-texto">
              <span className="paso-ruta-num">Paso {p.n}</span>
              <strong>{p.titulo}</strong>
              <span>{p.texto}</span>
            </span>
            <svg className="paso-ruta-flecha" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5l4.5 4.5L6 12.5" /></svg>
          </button>
        </motion.li>
      ))}
    </ol>
  );
}

const AGENTES = [
  { nombre: "Lector", tarea: "Lee tu exógena y tus certificados.", ia: false },
  { nombre: "Anonimizador", tarea: "Quita tus datos personales antes de usar IA.", ia: false },
  { nombre: "Clasificador", tarea: "Reconoce cada documento y su año.", ia: true },
  { nombre: "Intérprete", tarea: "Ubica cada concepto en la declaración, sin ver tus montos.", ia: true },
  { nombre: "Extractor", tarea: "Saca las cifras de tus certificados.", ia: false },
  { nombre: "Conciliador", tarea: "Cruza tus documentos para no contar nada dos veces.", ia: false },
  { nombre: "Motor tributario", tarea: "Hace los cálculos con las reglas del año.", ia: false },
  { nombre: "Auditor", tarea: "Busca errores y datos faltantes.", ia: false },
  { nombre: "Explicador", tarea: "Resume el resultado en palabras simples.", ia: true },
  { nombre: "Asistente", tarea: "Te responde, anota tus datos y calcula.", ia: true },
];

export default function Inicio() {
  const { ir, cuenta, resultado } = useSesion();
  const tema = useTemaActual();
  const demo = useDemo();

  const empezar = () => ir("declarar");

  return (
    <div className="contenedor">
      <section className="portada">
        <FadeIn>
          <h1 className="titular t-72">
            <TituloPortada />
          </h1>
          <p className="lead">
            Sube tu exógena o cuéntale tus ingresos. Te arma el borrador y te guía para presentarlo en la DIAN.
          </p>
          <div className="acciones">
            <button className="boton" onClick={empezar}>Empezar</button>
            <button className="boton secundario" onClick={demo.iniciar}>
              <svg className="icono-boton" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.5v9l7-4.5z" /></svg>
              Ver la demo guiada
            </button>
          </div>
          {cuenta ? null : (
            <p className="nota-privacidad">
              <Candado />
              Tus datos personales nunca llegan a la IA. Las cifras las calcula el código.
            </p>
          )}
        </FadeIn>
        <RutaPortada ir={ir} hayResultado={!!resultado} />
      </section>

      <Revelar className="seccion-debo">
        <h2 id="titulo-debo" className="titular t-36">¿Tengo que declarar? Averígualo en 30 segundos.</h2>
        <p className="suave">Cuatro cifras y te digo si llegas a un tope.</p>
        <DeboDeclarar />
      </Revelar>


      <section className="agentes-portada" aria-labelledby="titulo-agentes">
        <Revelar>
          <h2 id="titulo-agentes" className="titular t-36">Diez agentes, una tarea cada uno.</h2>
          <p className="suave">
            El código hace los cálculos con las reglas de cada año. La IA conversa y explica, y cada cifra se verifica.
          </p>
        </Revelar>
        <Revelar>
          <ul className="rejilla-agentes">
            {AGENTES.map((a) => (
              <li key={a.nombre}>
                <SpotlightCard className="tarjeta-luz" theme={tema} spotlightColor={selloHex(tema)} intensity={tema === "dark" ? 0.18 : 0.1} spotlightSize={220}>
                  <div className="cabeza">
                    <strong>{a.nombre}</strong>
                    {a.ia ? <span className="etiqueta-ia">IA</span> : <span className="etiqueta-reglas">Reglas</span>}
                  </div>
                  <p>{a.tarea}</p>
                </SpotlightCard>
              </li>
            ))}
          </ul>
        </Revelar>
      </section>
    </div>
  );
}
