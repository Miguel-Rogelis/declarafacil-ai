import { motion } from "motion/react";
import type { ReactNode } from "react";
import AnimatedContent from "./reactbits/AnimatedContent";

const CURVA = [0.22, 1, 0.36, 1] as const;

/** Entrada al montar: sube 12 px y aparece (de la plantilla rbp-portfolio). */
export function FadeIn({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay, ease: CURVA }}>
      {children}
    </motion.div>
  );
}

/** Entrada al montar: crece desde 0.8 y se enfoca (de la plantilla rbp-portfolio). */
export function ScaleUnblur({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, scale: 0.8, filter: "blur(16px)" }}
      animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
      transition={{ duration: 1, delay, ease: CURVA }}
    >
      {children}
    </motion.div>
  );
}

/** Aparece al hacer scroll (AnimatedContent de React Bits con los valores de la casa). */
export function Revelar({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <AnimatedContent className={className} distance={36} duration={0.9} ease="power3.out" blur={8} threshold={0.15} delay={delay}>
      {children}
    </AnimatedContent>
  );
}
