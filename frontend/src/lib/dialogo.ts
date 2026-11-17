import { useLayoutEffect, useRef, type RefObject } from "react";

/**
 * Abre un <dialog> nativo como modal mientras el componente está montado.
 * El navegador pone el resto de la página inerte, encierra el foco y lo devuelve al cerrar.
 * Escape y tocar fuera piden cerrar con onCerrar, para que la salida se anime antes de desmontar.
 */
export function useDialogoModal(ref: RefObject<HTMLDialogElement | null>, onCerrar: () => void) {
  const cerrar = useRef(onCerrar);
  cerrar.current = onCerrar;

  useLayoutEffect(() => {
    const d = ref.current;
    if (!d) return;
    const antes = document.activeElement as HTMLElement | null;
    if (!d.open) d.showModal();

    // Escape (y el gesto de atrás): en vez de cerrarse en seco, avisa para animar la salida
    const alCancelar = (e: Event) => {
      e.preventDefault();
      cerrar.current();
    };
    // Tocar fuera: se mira la posición del puntero, no el target (el <dialog> también es el target de su relleno)
    const fuera = (e: PointerEvent) => {
      const r = d.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    let empezoFuera = false;
    const abajo = (e: PointerEvent) => (empezoFuera = fuera(e));
    const arriba = (e: PointerEvent) => {
      if (empezoFuera && fuera(e)) cerrar.current();
      empezoFuera = false;
    };
    d.addEventListener("cancel", alCancelar);
    d.addEventListener("pointerdown", abajo);
    d.addEventListener("pointerup", arriba);
    return () => {
      d.removeEventListener("cancel", alCancelar);
      d.removeEventListener("pointerdown", abajo);
      d.removeEventListener("pointerup", arriba);
      if (d.open) d.close();
      // Al desmontar sin close() previo el navegador no siempre devuelve el foco: se devuelve a quien la abrió
      if (antes?.isConnected) antes.focus();
    };
  }, [ref]);
}
