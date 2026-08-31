import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the PDF Extractor upload experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>PDF Extractor<\/title>/i);
  assert.match(html, /LEITURA INTELIGENTE DE DOCUMENTOS/);
  assert.match(html, /Envie um documento e transforme todas as páginas em texto\./);
  assert.match(html, /Arraste seu PDF para cá/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
  assert.doesNotMatch(html, /Seu PDF, em texto|editável|Sem cadastro|processados com segurança|Resultado em segundos/);
});

test("keeps the production UI and API contract wired", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /NEXT_PUBLIC_API_URL/);
  assert.match(page, /\$\{API_URL\}\/api\/extract/);
  assert.match(page, /\$\{API_URL\}\/api\/export\/\$\{format\}/);
  assert.match(page, /accept="application\/pdf,\.pdf"/);
  assert.match(page, /readOnly aria-label="Texto extraído do PDF"/);
  assert.match(layout, /lang="pt-BR"/);
  assert.doesNotMatch(layout, /openGraph|twitter|\/og\.png/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await assert.rejects(access(new URL("../app/_sites-preview/", import.meta.url)));
});
