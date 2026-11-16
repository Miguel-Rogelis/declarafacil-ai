import { defineConfig, devices } from "@playwright/test";

// La prueba de punta a punta corre contra el sitio construido (npm run build), servido por el backend
// en modo simulado: sin llave ni IA, siempre igual. PYTHON apunta al intérprete con las dependencias del backend.
const PUERTO = 8090;
const dist = new URL("./dist", import.meta.url).pathname;

export default defineConfig({
  testDir: "e2e",
  timeout: 150_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: `http://127.0.0.1:${PUERTO}`, trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  projects: [
    { name: "escritorio", use: { ...devices["Desktop Chrome"] } },
    { name: "celular", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `${process.env.PYTHON ?? "python"} -m uvicorn app.main:app --app-dir ../backend --port ${PUERTO}`,
    url: `http://127.0.0.1:${PUERTO}/api/salud`,
    env: { LLM_MODE: "simulado", FRONTEND_DIR: dist },
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
