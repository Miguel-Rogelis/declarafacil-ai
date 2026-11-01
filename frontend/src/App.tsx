import { MotionConfig } from "motion/react";
import Asistente from "./components/Asistente";
import { Marca } from "./components/piezas";
import { ProveedorSesion, useSesion, type Ruta } from "./lib/estado";
import Configuracion from "./pages/Configuracion";
import Declarar from "./pages/Declarar";
import Inicio from "./pages/Inicio";
import Resultado from "./pages/Resultado";

function Encabezado() {
  const { ruta, anio, setAnio, anios, extraccion } = useSesion();
  const enlace = (r: Ruta, texto: string) => (
    <a href={`#/${r}`} aria-current={ruta === r ? "page" : undefined}>{texto}</a>
  );
  return (
    <header className="encabezado">
      <div className="contenedor">
        <a className="marca" href="#/inicio"><Marca /> DeclaraFácil</a>
        <label className="selector-anio">
          Año gravable
          <select value={anio} onChange={(e) => setAnio(Number(e.target.value))} disabled={!!extraccion} title={extraccion ? "Empieza de nuevo para cambiar el año" : undefined}>
            {(anios.length ? anios : [{ anio_gravable: 2025, estado: "vigente" }]).map((a) => (
              <option key={a.anio_gravable} value={a.anio_gravable}>{a.anio_gravable}{a.estado === "borrador" ? " (borrador)" : ""}</option>
            ))}
          </select>
        </label>
        <nav className="nav" aria-label="Principal">
          {enlace("declarar", "Declarar")}
          {extraccion ? enlace("resultado", "Resultado") : null}
          {enlace("configuracion", "Reglas y agentes")}
        </nav>
      </div>
    </header>
  );
}

function Paginas() {
  const { ruta } = useSesion();
  return (
    <main>
      {ruta === "inicio" ? <Inicio /> : null}
      {ruta === "declarar" ? <Declarar /> : null}
      {ruta === "resultado" ? <Resultado /> : null}
      {ruta === "configuracion" ? <Configuracion /> : null}
      <footer className="pie contenedor">
        DeclaraFácil prepara un borrador con fines educativos. No reemplaza la asesoría de un contador ni presenta la declaración por ti.
        Proyecto del curso Problem Discovery &amp; Solution Design with AI, Universidad Católica de Colombia.
      </footer>
    </main>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorSesion>
        <Encabezado />
        <Paginas />
        <Asistente />
      </ProveedorSesion>
    </MotionConfig>
  );
}
