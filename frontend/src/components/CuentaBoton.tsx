import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useDialogoModal } from "../lib/dialogo";
import { useSesion } from "../lib/estado";
import { botonGoogle, entrarConCorreo, entrarConGoogle, googleDirecto, salir } from "../lib/nube";

const CURVA = [0.23, 1, 0.32, 1] as const;

/** La «G» de Google con sus colores (la marca oficial, para el botón de iniciar sesión). */
function LogoGoogle() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" className="logo-google">
      <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.6-.4-3.9z" />
    </svg>
  );
}

function VentanaEntrar({ onCerrar }: { onCerrar: () => void }) {
  const [correo, setCorreo] = useState("");
  const [estado, setEstado] = useState<"" | "google" | "enviando" | "enviado">("");
  const [error, setError] = useState("");
  const ventana = useRef<HTMLDialogElement>(null);
  useDialogoModal(ventana, onCerrar);
  // Con el ID de Google configurado va su botón oficial; si no carga, el de siempre (redirige por Supabase)
  const cajaGoogle = useRef<HTMLDivElement>(null);
  const [oficial, setOficial] = useState<"cargando" | "listo" | "no">(googleDirecto() ? "cargando" : "no");
  useEffect(() => {
    if (oficial !== "cargando" || !cajaGoogle.current) return;
    const oscuro = document.documentElement.dataset.theme === "dark" || (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
    void botonGoogle(cajaGoogle.current, { oscuro, alFallar: setError }).then((ok) => setOficial(ok ? "listo" : "no"));
  }, [oficial]);


  const google = async () => {
    setError("");
    setEstado("google");
    try {
      await entrarConGoogle(); // la página se va a Google y vuelve con la sesión
    } catch (e) {
      setEstado("");
      setError((e as Error).message);
    }
  };
  const porCorreo = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setEstado("enviando");
    try {
      await entrarConCorreo(correo.trim());
      setEstado("enviado");
    } catch (ex) {
      setEstado("");
      setError("No pude enviar el enlace. Revisa el correo y vuelve a intentar.");
      console.warn(ex);
    }
  };

  return (
    <>
      <motion.dialog
        ref={ventana}
        className="ventana-entrar"
        aria-labelledby="titulo-entrar"
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 4 }}
        transition={{ duration: 0.22, ease: CURVA }}
      >
        <button type="button" className="ventana-cerrar" onClick={onCerrar} aria-label="Cerrar">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" /></svg>
        </button>
        <h2 id="titulo-entrar" className="titular t-24">Guarda tu declaración</h2>
        <p className="suave ventana-texto">Entra para seguirla desde cualquier dispositivo, guardar tus documentos y tener tu propio cupo de respuestas con IA.</p>

        <AnimatePresence mode="popLayout" initial={false}>
          {estado === "enviado" ? (
            <motion.div key="enviado" className="enlace-enviado" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, ease: CURVA }} role="status">
              <span className="sobre" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M3.5 6.5h17v11h-17z M3.5 7l8.5 6.5L20.5 7" /></svg>
              </span>
              <strong>Revisa tu correo</strong>
              <p className="suave">Te mandé un enlace a {correo}. Ábrelo en este mismo navegador y quedas adentro.</p>
              <button type="button" className="boton-texto chico" onClick={() => setEstado("")}>Usar otro correo</button>
            </motion.div>
          ) : (
            <motion.div key="opciones" className="opciones-entrar" initial={false} exit={{ opacity: 0 }}>
              {oficial !== "no" ? (
                <div className={`google-oficial${oficial === "cargando" ? " cargando" : ""}`} ref={cajaGoogle} aria-busy={oficial === "cargando"} />
              ) : (
                <button type="button" className="boton-google" onClick={() => void google()} disabled={estado !== ""}>
                  <LogoGoogle />
                  {estado === "google" ? "Abriendo Google…" : "Continuar con Google"}
                </button>
              )}
              <div className="separador" role="separator"><span>o con tu correo</span></div>
              <form className="entrar-correo" onSubmit={(e) => void porCorreo(e)}>
                <label htmlFor="correo-entrar" className="visualmente-oculto">Tu correo</label>
                <input id="correo-entrar" name="email" className="entrada" type="email" required autoComplete="email" autoCorrect="off" autoCapitalize="none" spellCheck={false} enterKeyHint="send" placeholder="tucorreo@ejemplo.com" value={correo} onChange={(e) => setCorreo(e.target.value)} />
                <button className="boton" disabled={!correo.includes("@") || estado !== ""}>{estado === "enviando" ? "Enviando…" : "Enviarme el enlace"}</button>
              </form>
            </motion.div>
          )}
        </AnimatePresence>
        {error ? <p className="mensaje-estado error" role="alert">{error}</p> : null}
        <p className="nota-ventana">Guardamos tu borrador de cada año y los documentos que subas, en privado: solo tú los ves. Puedes borrarlos cuando quieras.</p>
      </motion.dialog>
    </>
  );
}

/** En el encabezado: «Entrar» sin sesión; con sesión, la foto o la inicial y un menú corto. */
export function CuentaBoton() {
  const { nubeActiva, cuenta, sincronizando } = useSesion();
  const [abierta, setAbierta] = useState(false);
  const [menu, setMenu] = useState(false);
  const caja = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const fuera = (e: PointerEvent) => !caja.current?.contains(e.target as Node) && setMenu(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    document.addEventListener("pointerdown", fuera);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", fuera);
      document.removeEventListener("keydown", esc);
    };
  }, [menu]);
  useEffect(() => {
    if (cuenta) setAbierta(false);
  }, [cuenta]);

  if (!nubeActiva) return null;

  if (!cuenta) {
    return (
      <>
        <button type="button" className="boton-entrar" onClick={() => setAbierta(true)}>Entrar</button>
        <AnimatePresence>{abierta ? <VentanaEntrar onCerrar={() => setAbierta(false)} /> : null}</AnimatePresence>
      </>
    );
  }

  return (
    <div className="cuenta" ref={caja}>
      <button type="button" className={`avatar${sincronizando ? " sincronizando" : ""}`} onClick={() => setMenu((m) => !m)} aria-expanded={menu} aria-haspopup="menu" aria-label={`Tu cuenta: ${cuenta.nombre}`}>
        {cuenta.foto ? <img src={cuenta.foto} alt="" referrerPolicy="no-referrer" /> : <span aria-hidden="true">{cuenta.nombre.slice(0, 1).toUpperCase()}</span>}
      </button>
      <AnimatePresence>
        {menu ? (
          <motion.div
            className="menu-cuenta"
            role="menu"
            initial={{ opacity: 0, scale: 0.96, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.16, ease: CURVA }}
          >
            <div className="menu-quien">
              <strong>{cuenta.nombre}</strong>
              <span className="suave">{cuenta.correo}</span>
            </div>
            <p className="menu-nota">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 8.5l2.6 2.6L12 5.5" /></svg>
              {sincronizando ? "Sincronizando…" : "Tu declaración se guarda en tu cuenta"}
            </p>
            <button type="button" role="menuitem" className="menu-item" onClick={() => { setMenu(false); void salir(); }}>Cerrar sesión</button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
