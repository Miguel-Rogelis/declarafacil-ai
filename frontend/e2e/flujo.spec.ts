import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => localStorage.clear());
});

test("el chat anota los datos, los guarda en el navegador y se pueden borrar", async ({ page }) => {
  await page.goto("/#/declarar");
  await page.locator("#mensaje").fill("gano 4 millones al mes, me retienen 150 mil cada mes y tengo 2 hijos");
  await page.locator("#mensaje").press("Enter");
  await expect(page.getByText("Salarios del año")).toBeVisible();
  await expect(page.locator(".anotado").getByText("$1.800.000", { exact: true })).toBeVisible();
  await expect(page.locator(".ficha-item.tengo")).toHaveCount(3);

  await page.reload();
  await expect(page.getByText("me retienen 150 mil cada mes")).toBeVisible();
  await expect(page.locator(".ficha-item.tengo")).toHaveCount(3);

  await page.getByRole("button", { name: "Borrar mis datos" }).click();
  await page.getByRole("button", { name: "Sí, borrar todo" }).click();
  await expect(page.getByRole("heading", { name: /En qué te ayudo/ })).toBeVisible();
});

test("la demo guiada llega sola hasta el borrador y se puede pausar", async ({ page }) => {
  await page.goto("/#/inicio");
  await page.getByRole("button", { name: "Ver la demo guiada" }).click();
  await expect(page.getByText("Demo · paso 1 de 8")).toBeVisible();
  await page.getByRole("button", { name: "Pausar la demo" }).click();
  const escrito = await page.locator("#mensaje").inputValue();
  await page.waitForTimeout(1500);
  expect(await page.locator("#mensaje").inputValue()).toBe(escrito);
  await page.getByRole("button", { name: "Seguir la demo" }).click();
  await expect(page).toHaveURL(/#\/resultado/, { timeout: 120_000 });
  await expect(page.getByText(/saldo a favor|Te toca pagar/).first()).toBeVisible();
  await expect(page.getByText("Ya viste el caso completo")).toBeVisible();

  // Del resultado a la guía para presentar en la DIAN: cada casilla se copia y queda marcada
  await page.getByRole("button", { name: "Seguir yo" }).click();
  await page.goto("/#/resultado");
  await page.getByRole("button", { name: "Presentar en la DIAN, paso a paso" }).click();
  await expect(page.getByRole("heading", { name: "Presenta tu declaración en la DIAN." })).toBeVisible();
  await page.getByRole("button", { name: /Copiar el valor de la casilla/ }).first().click();
  await expect(page.getByText(/^1 de \d+ casillas listas$/)).toBeVisible();
});

test("«¿Tengo que declarar?» responde con los topes del año", async ({ page }) => {
  await page.goto("/#/inicio");
  const debo = page.locator(".debo-declarar");
  await debo.getByLabel(/Cuánto recibiste en/).fill("85000000");
  await expect(debo.getByText("Sí, tienes que declarar")).toBeVisible();
  await debo.getByLabel(/Cuánto recibiste en/).fill("20000000");
  await expect(debo.getByText(/No tienes que declarar/)).toBeVisible();
});

test("la guía de la DIAN se ve siempre en el menú, aunque no haya borrador", async ({ page }) => {
  await page.goto("/#/inicio");
  await page.locator(".nav").getByRole("link", { name: /DIAN/ }).click();
  await expect(page.getByRole("heading", { name: "Presenta tu declaración en la DIAN." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Armar mi borrador" })).toBeVisible();
});
