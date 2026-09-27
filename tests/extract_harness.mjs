/*
 * Node/jsdom harness for src/quintal/collect/extract.js.
 *
 * WHY THIS EXISTS: extract.js is injected into a live logged-in browser, so nothing about it
 * was covered by `pytest`. Both bugs it has produced were data corruptions found in the
 * collected pool rather than in a test — QT-049 (imovirtual's SSR'd styled-components rule
 * sat inside the price cell, so textContent read the rent out of a colour and font-size:
 * thirteen listings at 0.63 EUR/month) and QT-050 (imovirtual nulled address.city, so every
 * card lost its freguesia and geocoded to a concelho centroid, quietly wrecking the beach
 * axis). This harness loads a saved fixture into jsdom, evaluates the *real* extract.js in
 * that window, and prints the rows it produces as JSON — so tests/test_extract_js.py can
 * assert on them, and the Python adapters can be run over the same rows.
 *
 * Usage:  node tests/extract_harness.mjs <fixture.html> <idealista|imovirtual> [originUrl]
 * Output: {"rows": [...], "counts": {...}} on stdout. Exit non-zero on failure.
 *
 * It deliberately calls quintalReset/quintalExtract — the same entry points a collection run
 * calls — rather than reaching for the internals, so the selectors and the localStorage
 * accumulation are exercised too. window.quintalInternals is available for finer assertions.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXTRACT_JS = resolve(HERE, "../src/quintal/collect/extract.js");

const DEFAULT_ORIGIN = {
  idealista: "https://www.idealista.pt/arrendar-casas/faro-distrito/com-preco-max_1500,t2,t3,t4-t5/",
  imovirtual: "https://www.imovirtual.com/pt/resultados/arrendar/apartamento/faro?page=1",
};

const [fixturePath, site, originArg] = process.argv.slice(2);
if (!fixturePath || !site) {
  console.error("usage: node tests/extract_harness.mjs <fixture.html> <idealista|imovirtual> [originUrl]");
  process.exit(2);
}
if (!DEFAULT_ORIGIN[site]) {
  console.error(`unknown site '${site}' (idealista|imovirtual)`);
  process.exit(2);
}

const html = readFileSync(resolve(fixturePath), "utf-8");
// A real page URL matters: relative hrefs resolve against it (idealista cards are relative),
// and jsdom only provides localStorage for an http(s) origin.
const url = originArg || DEFAULT_ORIGIN[site];

// runScripts "outside-only" gives window.eval a real script context (so extract.js sees
// `window`, `document`, `localStorage`) while leaving the fixture's own captured <script>
// tags inert — __NEXT_DATA__ must be read as text, never executed.
const dom = new JSDOM(html, { url, pretendToBeVisual: true, runScripts: "outside-only" });
const { window } = dom;

// Evaluate extract.js inside the fixture's window, exactly as the browser injection does.
const source = readFileSync(EXTRACT_JS, "utf-8");
try {
  window.eval(source);
} catch (err) {
  console.error("extract.js threw while being evaluated:\n" + (err && err.stack ? err.stack : err));
  process.exit(1);
}

for (const fn of ["quintalExtract", "quintalReset", "quintalInternals"]) {
  if (!window[fn]) {
    console.error(`extract.js did not define window.${fn} — the test seam or a helper is missing.`);
    process.exit(1);
  }
}

window.quintalReset(site);
const counts = window.quintalExtract(site);
const key = window.quintalInternals.SITES[site].key;
const rows = JSON.parse(window.localStorage.getItem(key) || "[]");

process.stdout.write(JSON.stringify({ rows, counts, url }, null, 2));
