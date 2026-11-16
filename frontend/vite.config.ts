import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  plugins: [react()],
  // En desarrollo /api va al backend local; DF_API cambia el puerto si el 8000 está ocupado
  server: { proxy: { "/api": process.env.DF_API ?? "http://127.0.0.1:8000" } },
});
