import { motion } from "motion/react";
import { Fragment, type CSSProperties } from "react";
import { Candado, LetraD } from "../components/piezas";
import { DeboDeclarar } from "../components/DeboDeclarar";
import { FadeIn, Revelar, ScaleUnblur } from "../components/Movimiento";
import { selloHex, useTemaActual } from "../components/Navegacion";
import SpotlightCard from "../components/reactbits/SpotlightCard";
import Stepper, { Step } from "../components/reactbits/Stepper";
import CountUp from "../components/reactbits/CountUp";
import { useDemo } from "../lib/demo";
import { useSesion } from "../lib/estado";

const RENGLONES = [
  { n: "R29", texto: "Patrimonio bruto", valor: 214_500_000 },
  { n: "R30", texto: "Deudas", valor: 98_200_000 },
  { n: "R32", texto: "Ingresos por rentas de trabajo", valor: 104_000_000 },
  { n: "R132", texto: "Retenciones del año", valor: 2_100_000 },
];

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

function FormularioMuestra() {
  return (
    <div className="formulario-muestra" role="figure" aria-label="Ejemplo de borrador del formulario 210">
      <header>
        <strong>Formulario 210</strong>
        <span className="chico suave">Año gravable 2025</span>
      </header>
      {RENGLONES.map((r, i) => (
        <div className="renglon" key={r.n}>
          <span className="num"><span className="visualmente-oculto">Casilla </span>{r.n.slice(1)}</span>
          <span>{r.texto}</span>
          <span className="valor">
            <CountUp to={r.valor} prefix="$" separator="." duration={0.9} delay={0.35 + i * 0.32} trigger="load" />
          </span>
        </div>
      ))}
      <motion.div
        aria-hidden="true"
        className="sello-borrador"
        initial={{ opacity: 0, scale: 2.2, rotate: -20 }}
        animate={{ opacity: 1, scale: 1, rotate: -7 }}
        transition={{ delay: 0.35 + RENGLONES.length * 0.32 + 0.6, type: "spring", stiffness: 480, damping: 17 }}
      >
        BORRADOR
      </motion.div>
    </div>
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

const PASOS = [
  { titulo: "Cuéntale tus datos", texto: "Sube tu exógena o escribe «gano 4 millones al mes»." },
  { titulo: "Pide el cálculo", texto: "Escribe «calcula» y ves cuánto pagas o te devuelven." },
  { titulo: "Preséntala en la DIAN", texto: "Te guiamos en MUISCA, casilla por casilla." },
];

/** El Stepper trae su propia paleta gris; la reemplazamos por los tokens de la casa (sirven en claro y en oscuro). */
const COLORES_STEPPER = {
  "--stepper-frame": "var(--papel-hondo)",
  "--stepper-frame-edge": "var(--marco)",
  "--stepper-frame-shadow": "var(--sombra-elevada)",
  "--stepper-tile": "var(--hoja)",
  "--stepper-tile-edge": "var(--marco)",
  "--stepper-ink": "var(--tinta)",
  "--stepper-muted": "var(--tinta-suave)",
} as CSSProperties;

export default function Inicio() {
  const { ir, cuenta } = useSesion();
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
        <ScaleUnblur delay={0.15}>
          <FormularioMuestra />
        </ScaleUnblur>
      </section>

      <Revelar className="seccion-debo">
        <h2 id="titulo-debo" className="titular t-36">¿Tengo que declarar? Averígualo en 30 segundos.</h2>
        <p className="suave">Cuatro cifras y te digo si llegas a un tope.</p>
        <DeboDeclarar />
      </Revelar>

      <Revelar className="pasos-stepper">
        <h2 id="titulo-pasos" className="titular t-36">Cómo funciona</h2>
        <Stepper
          theme={tema}
          accentColor={selloHex(tema)}
          width="100%"
          radius={28}
          backButtonText="Anterior"
          nextButtonText="Siguiente"
          completeButtonText="Listo"
          onFinalStepCompleted={empezar}
          aria-label="Cómo funciona, en tres pasos"
          style={COLORES_STEPPER}
        >
          {PASOS.map((p) => (
            <Step key={p.titulo} title={p.titulo}>
              <div className="paso-contenido">
                <h3>{p.titulo}</h3>
                <p>{p.texto}</p>
              </div>
            </Step>
          ))}
        </Stepper>
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
