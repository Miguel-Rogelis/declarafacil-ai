import { motion } from "motion/react";
import { Fragment, useState, type CSSProperties } from "react";
import { Candado, LetraD } from "../components/piezas";
import { FadeIn, Revelar, ScaleUnblur } from "../components/Movimiento";
import { selloHex, useTemaActual } from "../components/Navegacion";
import SpotlightCard from "../components/reactbits/SpotlightCard";
import Stepper, { Step } from "../components/reactbits/Stepper";
import CountUp from "../components/reactbits/CountUp";
import { api } from "../lib/api";
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
  { nombre: "Lector", tarea: "Lee el Excel o PDF de tu exógena y de tus certificados, varios a la vez.", ia: false },
  { nombre: "Anonimizador", tarea: "Quita tu cédula, nombre y cuentas antes de usar IA.", ia: false },
  { nombre: "Clasificador", tarea: "Reconoce cada documento (exógena, certificado del empleador, del banco, de vivienda…) y de qué año es.", ia: true },
  { nombre: "Intérprete", tarea: "Ubica cada concepto de la exógena en la declaración y te lo explica. Nunca ve tus montos.", ia: true },
  { nombre: "Extractor", tarea: "Saca las cifras de tus certificados con reglas, sin IA.", ia: false },
  { nombre: "Conciliador", tarea: "Cruza tus documentos para no contar nada dos veces y te avisa si no coinciden.", ia: false },
  { nombre: "Motor tributario", tarea: "Hace todos los cálculos con las reglas del año.", ia: false },
  { nombre: "Auditor", tarea: "Busca errores, datos faltantes y fechas vencidas.", ia: false },
  { nombre: "Explicador", tarea: "Resume el resultado en palabras simples, sin inventar cifras.", ia: true },
  { nombre: "Asistente", tarea: "Te responde y hace lo que le pides: anota tus datos, calcula o cambia de año. Tú llevas la conversación.", ia: true },
];

const PASOS = [
  { titulo: "Pregunta lo que quieras", texto: "Qué es la DIAN, si te toca declarar, qué pasa si no lo haces. Ninguna pregunta es tonta." },
  { titulo: "Cuéntale tus datos", texto: "Adjunta tu exógena y tus certificados, o escribe cosas como «gano 4 millones al mes» o «tengo dos hijos». El agente los anota y te muestra qué anotó." },
  { titulo: "Pídele el cálculo", texto: "Escribe «calcula» y ves cuánto pagas o te devuelven, por qué y qué revisar. La firma en la DIAN siempre es tuya." },
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
  const { ir, reiniciar, setArchivoPendiente, extraccion } = useSesion();
  const tema = useTemaActual();
  const [cargandoEjemplo, setCargandoEjemplo] = useState(false);
  const [error, setError] = useState("");

  const empezar = () => ir("declarar");
  const probarEjemplo = async () => {
    setCargandoEjemplo(true);
    setError("");
    try {
      const archivos = await api.documentosDemo();
      if (extraccion) reiniciar();
      setArchivoPendiente(archivos);
      ir("declarar");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargandoEjemplo(false);
    }
  };

  return (
    <div className="contenedor">
      <section className="portada">
        <FadeIn>
          <h1 className="titular t-72">
            <TituloPortada />
          </h1>
          <p className="lead">
            Pregúntale lo que quieras sobre la renta y arma contigo el borrador del año que elijas (2021 a 2025). Adjunta tu exógena de la
            DIAN y tus certificados, o cuéntale tus ingresos con tus palabras: cada cifra queda explicada antes de que firmes.
          </p>
          <div className="acciones">
            <button className="boton" onClick={empezar}>Empezar</button>
            <button className="boton secundario" onClick={probarEjemplo} disabled={cargandoEjemplo}>
              {cargandoEjemplo ? "Cargando ejemplo…" : "Probar con un ejemplo ficticio"}
            </button>
          </div>
          {error ? <p className="mensaje-estado error" role="alert">No pude cargar el ejemplo: {error}</p> : null}
          <p className="nota-privacidad">
            <Candado />
            Tus archivos no se guardan. Antes de usar IA quitamos tu cédula, tu nombre y tus cuentas, y las cifras las calcula el código, no la IA.
          </p>
        </FadeIn>
        <ScaleUnblur delay={0.15}>
          <FormularioMuestra />
        </ScaleUnblur>
      </section>

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
            Los cálculos los hacen reglas del Estatuto Tributario de cada año, de 2021 a 2025. La IA conversa, interpreta y explica, y cada
            cifra que escribe o anota se verifica contra lo que dijiste y contra el cálculo.
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
