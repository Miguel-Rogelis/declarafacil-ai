import { useEffect, useRef, useState } from "react";
import { guardarConsentimiento, registrarDialogo } from "../lib/consentimiento";

/** Pide la autorización de tratamiento de datos (Ley 1581) antes del primer documento real. */
export function DialogoConsentimiento() {
  const [responder, setResponder] = useState<((acepta: boolean) => void) | null>(null);
  const [marcado, setMarcado] = useState(false);
  const boton = useRef<HTMLButtonElement>(null);

  useEffect(() => registrarDialogo((r) => setResponder(() => r)), []);
  useEffect(() => {
    if (responder) boton.current?.focus();
  }, [responder]);

  if (!responder) return null;
  const cerrar = (acepta: boolean) => {
    if (acepta) guardarConsentimiento();
    responder(acepta);
    setResponder(null);
    setMarcado(false);
  };
  return (
    <>
      <div className="velo" aria-hidden="true" />
      <div className="dialogo-consentimiento" role="dialog" aria-modal="true" aria-labelledby="titulo-consentimiento"
        onKeyDown={(e) => e.key === "Escape" && cerrar(false)}>
        <h2 id="titulo-consentimiento" className="titular t-21">Antes de leer tus documentos</h2>
        <p>
          DeclaraFácil va a leer tu exógena y tus certificados solo para armar el borrador de tu declaración. Sin cuenta, los archivos se leen en
          memoria y no se guardan. Antes de usar IA quitamos tu cédula, tu nombre, tu dirección y tus números de cuenta; a los modelos solo llegan
          conceptos y cifras, nunca tu identidad.
        </p>
        <p className="chico suave">
          Puedes conocer, actualizar, rectificar o borrar tus datos cuando quieras (botón «Borrar mis datos»). Detalles en la{" "}
          <a href={`${import.meta.env.BASE_URL}privacidad.html`} target="_blank" rel="noreferrer">política de privacidad</a>.
        </p>
        <label className="casilla">
          <input type="checkbox" checked={marcado} onChange={(e) => setMarcado(e.target.checked)} />
          <span>Autorizo el tratamiento de mis datos personales para esta finalidad, según la Ley 1581 de 2012.</span>
        </label>
        <div className="opciones mt-2">
          <button ref={boton} className="boton" disabled={!marcado} onClick={() => cerrar(true)}>Autorizo y sigo</button>
          <button className="boton-texto" onClick={() => cerrar(false)}>Ahora no</button>
        </div>
      </div>
    </>
  );
}
