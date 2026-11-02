import { animate, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Candado } from "../components/piezas";
import { api } from "../lib/api";
import { useSesion } from "../lib/estado";
import { pesos } from "../lib/formato";

const RENGLONES = [
  { n: "R29", texto: "Patrimonio bruto", valor: 214_500_000 },
  { n: "R30", texto: "Deudas", valor: 98_200_000 },
  { n: "R32", texto: "Ingresos por rentas de trabajo", valor: 104_000_000 },
  { n: "R132", texto: "Retenciones del año", valor: 2_100_000 },
];

function Cifra({ valor, retraso }: { valor: number; retraso: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const reducido = useReducedMotion();
  useEffect(() => {
    if (!ref.current) return;
    if (reducido) {
      ref.current.textContent = pesos(valor);
      return;
    }
    const c = animate(0, valor, {
      duration: 0.9,
      delay: retraso,
      ease: [0.2, 0.7, 0.2, 1],
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = pesos(v);
      },
    });
    return () => c.stop();
  }, [valor, retraso, reducido]);
  return <span ref={ref}>$0</span>;
}

function FormularioMuestra() {
  return (
    <div className="formulario-muestra" aria-label="Ejemplo de borrador del formulario 210">
      <header>
        <strong>Formulario 210</strong>
        <span className="chico suave">Año gravable 2025</span>
      </header>
      {RENGLONES.map((r, i) => (
        <div className="renglon" key={r.n}>
          <span className="num">{r.n}</span>
          <span>{r.texto}</span>
          <span className="valor">
            <Cifra valor={r.valor} retraso={0.35 + i * 0.32} />
          </span>
        </div>
      ))}
      <motion.div
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
  { nombre: "Lector", tarea: "Lee el Excel o PDF de tu exógena.", ia: false },
  { nombre: "Anonimizador", tarea: "Quita tu cédula, nombre y cuentas antes de usar IA.", ia: false },
  { nombre: "Clasificador", tarea: "Confirma que el archivo es una exógena y de qué año.", ia: true },
  { nombre: "Intérprete", tarea: "Ubica cada concepto en la declaración y te lo explica. Nunca ve tus montos.", ia: true },
  { nombre: "Motor tributario", tarea: "Hace todos los cálculos con las reglas del año.", ia: false },
  { nombre: "Auditor", tarea: "Busca errores, datos faltantes y fechas vencidas.", ia: false },
  { nombre: "Explicador", tarea: "Resume el resultado en palabras simples, sin inventar cifras.", ia: true },
  { nombre: "Asistente", tarea: "Te responde y hace lo que le pides: anota tus datos, calcula o cambia de año. Tú llevas la conversación.", ia: true },
];

export default function Inicio() {
  const { ir, reiniciar, setArchivoPendiente, extraccion } = useSesion();
  const [cargandoEjemplo, setCargandoEjemplo] = useState(false);
  const [error, setError] = useState("");

  const empezar = () => ir("declarar");
  const probarEjemplo = async () => {
    setCargandoEjemplo(true);
    setError("");
    try {
      const archivo = await api.exogenaDemo();
      if (extraccion) reiniciar();
      setArchivoPendiente(archivo);
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
        <div>
          <h1 className="titular t-72">Tu declaración de renta, lista para revisar.</h1>
          <p className="lead">
            Un agente que te responde la renta sin enredos y arma el borrador del año gravable que elijas (2021 a 2025): adjunta tu
            exógena de la DIAN o cuéntale tus ingresos con tus palabras. Cada cifra queda explicada antes de que firmes.
          </p>
          <div className="acciones">
            <button className="boton" onClick={empezar}>Empezar</button>
            <button className="boton secundario" onClick={probarEjemplo} disabled={cargandoEjemplo}>
              {cargandoEjemplo ? "Cargando ejemplo…" : "Probar con un ejemplo ficticio"}
            </button>
          </div>
          {error ? <p className="mensaje-estado error">{error}</p> : null}
          <p className="nota-privacidad">
            <Candado />
            Tu archivo no se guarda. Antes de usar IA quitamos tu cédula, tu nombre y tus cuentas, y las cifras las calcula el código, no la IA.
          </p>
        </div>
        <FormularioMuestra />
      </section>

      <ol className="pasos" aria-label="Cómo funciona">
        <li className="paso">
          <span className="n">1</span>
          <h3>Pregunta lo que quieras</h3>
          <p>Qué es la DIAN, si te toca declarar, qué pasa si no lo haces. Ninguna pregunta es tonta.</p>
        </li>
        <li className="paso">
          <span className="n">2</span>
          <h3>Cuéntale tus datos</h3>
          <p>Adjunta tu exógena o escribe cosas como «gano 4 millones al mes» o «tengo dos hijos». El agente los anota y te muestra qué anotó.</p>
        </li>
        <li className="paso">
          <span className="n">3</span>
          <h3>Pídele el cálculo</h3>
          <p>Escribe «calcula» y ves cuánto pagas o te devuelven, por qué y qué revisar. La firma en la DIAN siempre es tuya.</p>
        </li>
      </ol>

      <section className="agentes-portada" aria-labelledby="titulo-agentes">
        <div>
          <h2 id="titulo-agentes" className="titular t-36">Ocho agentes, una tarea cada uno.</h2>
          <p className="suave">
            Los cálculos los hacen reglas del Estatuto Tributario de cada año, de 2021 a 2025. La IA conversa, interpreta y explica, y cada
            cifra que escribe o anota se verifica contra lo que dijiste y contra el cálculo.
          </p>
        </div>
        <ul className="lista-agentes">
          {AGENTES.map((a) => (
            <li key={a.nombre}>
              <strong>{a.nombre}</strong>
              <span>{a.tarea}</span>
              {a.ia ? <em className="etiqueta-ia">IA</em> : <em className="etiqueta-reglas">Reglas</em>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
