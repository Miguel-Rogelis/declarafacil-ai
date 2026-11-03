import { MotionConfig } from "motion/react";
import { Encabezado } from "./components/Navegacion";
import Noise from "./components/reactbits/Noise";
import { ShaderFlow } from "./components/ShaderFlow";
import { ProveedorSesion, useSesion, type Ruta } from "./lib/estado";
import Configuracion from "./pages/Configuracion";
import Declarar from "./pages/Declarar";
import Inicio from "./pages/Inicio";
import Resultado from "./pages/Resultado";

/** Fondo animado detrás de la parte de arriba (el shader de la plantilla rbp-portfolio con la tinta y el sello).
 *  En la portada va más vivo; en el chat, quieto y suave para no distraer. */
function Fondo({ ruta }: { ruta: Ruta }) {
  const portada = ruta === "inicio";
  return (
    <div className={`fondo-animado${ruta === "declarar" ? " suave" : ""}${portada ? " vivo" : ""}`} aria-hidden="true">
      <ShaderFlow
        className="shader-flow"
        brightness={portada ? 1.35 : 1.15}
        iterations={portada ? 12 : 10}
        flowSpeed={portada ? [0.05, 0.12] : [0, 0.1]}
        colorLowA={[0.07, 0.23, 0.2]}
        colorHighA={[0.42, 0.33, 0.85]}
      />
    </div>
  );
}

function Marco() {
  const { ruta } = useSesion();
  return (
    <div className={`app${ruta === "declarar" ? " app-chat" : ""}`}>
      <Noise fixed fps={0} opacity={0.04} size={1.2} blendMode="multiply" contrast={0.5} zIndex={60} />
      <Fondo ruta={ruta} />
      <Encabezado />
      <Paginas />
    </div>
  );
}

function Paginas() {
  const { ruta } = useSesion();
  return (
    <main className="principal" id="contenido" tabIndex={-1}>
      {ruta === "inicio" ? <Inicio /> : null}
      {ruta === "declarar" ? <Declarar /> : null}
      {ruta === "resultado" ? <Resultado /> : null}
      {ruta === "configuracion" ? <Configuracion /> : null}
      {ruta === "declarar" ? null : <footer className="pie contenedor">
        DeclaraFácil prepara un borrador con fines educativos. No reemplaza la asesoría de un contador ni presenta la declaración por ti.
        Proyecto del curso Problem Discovery &amp; Solution Design with AI, Universidad Católica de Colombia.
      </footer>}
    </main>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorSesion>
        <Marco />
      </ProveedorSesion>
    </MotionConfig>
  );
}
