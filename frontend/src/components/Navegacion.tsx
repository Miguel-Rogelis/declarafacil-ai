import { motion } from "motion/react";
import { useLayoutEffect, useRef, useState, useSyncExternalStore, type MouseEvent } from "react";
import { useSesion, type Ruta } from "../lib/estado";
import { LetraD } from "./piezas";

type Tema = "light" | "dark";

const leerTema = (): Tema => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
const suscribirTema = (avisar: () => void) => {
  const o = new MutationObserver(avisar);
  o.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => o.disconnect();
};

/** El tema vigente, para los componentes de React Bits que lo reciben como prop (Aurora, Stepper, SpotlightCard). */
export const useTemaActual = () => useSyncExternalStore(suscribirTema, leerTema);

/** El violeta del sello en hexadecimal (los componentes de React Bits no leen variables CSS). */
export const selloHex = (t: Tema) => (t === "dark" ? "#b3a2ff" : "#5a3bc0");

function useTema() {
  const [tema, setTema] = useState<Tema>(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
  const aplicar = (t: Tema) => {
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem("df-tema", t);
    } catch {
      /* almacenamiento no disponible */
    }
    setTema(t);
  };
  return [tema, aplicar] as const;
}

/** Sol y luna. El tema nuevo se abre en círculo desde el botón cuando el navegador lo permite. */
function BotonTema() {
  const [tema, aplicar] = useTema();
  const oscuro = tema === "dark";
  const cambiar = (e: MouseEvent<HTMLButtonElement>) => {
    const siguiente: Tema = oscuro ? "light" : "dark";
    const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducido || typeof document.startViewTransition !== "function") {
      aplicar(siguiente);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const raiz = document.documentElement;
    raiz.style.setProperty("--tema-x", `${x}px`);
    raiz.style.setProperty("--tema-y", `${y}px`);
    raiz.style.setProperty("--tema-r", `${Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))}px`);
    raiz.dataset.temaAnim = "1";
    document.startViewTransition(() => aplicar(siguiente)).finished.finally(() => delete raiz.dataset.temaAnim);
  };
  return (
    <button type="button" className="boton-tema" onClick={cambiar} aria-pressed={oscuro} aria-label={oscuro ? "Usar tema claro" : "Usar tema oscuro"}>
      <span aria-hidden="true" className={`icono-tema${oscuro ? "" : " visible"}`}>
        <svg viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" /></svg>
      </span>
      <span aria-hidden="true" className={`icono-tema${oscuro ? " visible" : ""}`}>
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" /></svg>
      </span>
    </button>
  );
}

/** Píldora flotante con un indicador que se desliza a la página activa, como en la plantilla rbp-portfolio. */
export function Encabezado() {
  const { ruta, anio, cambiarAnio, anios, resultado } = useSesion();
  const items: { ruta: Ruta; texto: string; corto?: string }[] = [
    { ruta: "inicio", texto: "Inicio" },
    { ruta: "declarar", texto: "Chat" },
    ...(resultado ? [{ ruta: "resultado" as Ruta, texto: "Resultado" }] : []),
    { ruta: "configuracion", texto: "Reglas y agentes", corto: "Reglas" },
  ];
  const lista = useRef<HTMLUListElement>(null);
  const [pastilla, setPastilla] = useState<{ x: number; ancho: number } | null>(null);
  const medido = useRef(false);

  useLayoutEffect(() => {
    const medir = () => {
      const activo = lista.current?.querySelector<HTMLElement>("[aria-current='page']")?.parentElement;
      if (!lista.current || !activo) return setPastilla(null);
      setPastilla({ x: activo.offsetLeft, ancho: activo.offsetWidth });
    };
    medir();
    window.addEventListener("resize", medir);
    void document.fonts?.ready.then(medir);
    return () => window.removeEventListener("resize", medir);
  }, [ruta, resultado]);

  const vigentes = anios.filter((a) => a.estado === "vigente");
  return (
    <header className="encabezado">
      <a className="saltar" href="#contenido" onClick={(e) => { e.preventDefault(); document.getElementById("contenido")?.focus(); }}>Saltar al contenido</a>
      <a className="marca" href="#/inicio" aria-label="DeclaraFácil, inicio"><LetraD /><span aria-hidden="true">eclaraFácil</span></a>
      <nav className="nav" aria-label="Principal">
        <ul ref={lista}>
          {pastilla ? (
            <motion.li
              role="presentation"
              aria-hidden="true"
              className="nav-indicador"
              initial={false}
              animate={{ x: pastilla.x, width: pastilla.ancho }}
              transition={medido.current ? { type: "spring", stiffness: 380, damping: 32 } : { duration: 0 }}
              onAnimationComplete={() => (medido.current = true)}
            />
          ) : null}
          {items.map((i) => (
            <li key={i.ruta} className={i.ruta === "inicio" ? "solo-ancho-item" : undefined}>
              <a href={`#/${i.ruta}`} aria-current={ruta === i.ruta ? "page" : undefined}>
                {i.corto ? <><span className="solo-ancho">{i.texto}</span><span className="solo-angosto">{i.corto}</span></> : i.texto}
              </a>
            </li>
          ))}
        </ul>
        <BotonTema />
      </nav>
      <label className="selector-anio">
        <span>Año</span>
        <select value={anio} onChange={(e) => cambiarAnio(Number(e.target.value))} aria-label="Año gravable">
          {(vigentes.length ? vigentes : [{ anio_gravable: 2025 }]).map((a) => (
            <option key={a.anio_gravable} value={a.anio_gravable}>{a.anio_gravable}</option>
          ))}
        </select>
      </label>
    </header>
  );
}
