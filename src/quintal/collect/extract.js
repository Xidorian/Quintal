/*
 * Quintal — in-browser card extraction (QT-033).
 *
 * The single source of truth for the DOM scraping done during a browser-session collection,
 * so a pull is inject-this-file → call the helpers, instead of re-pasting an ad-hoc snippet
 * per page (and so a selector change is a one-file fix). Site selectors were validated live
 * 2026-07-19; re-verify against the page on first run if a portal has moved them.
 *
 * Flow (per site, in the logged-in results tab):
 *   1. Paste this file's contents once per page load (navigation clears `window`).
 *   2. quintalReset('idealista')            // page 1 only — start a fresh accumulation
 *   3. quintalExtract('idealista')          // each page — appends cards to localStorage
 *   4. quintalDownload('idealista')         // once, FROM A FRESH TAB — Blob → ~/Downloads
 *      (Chrome blocks a 2nd auto-download in the SAME tab; open a new same-origin tab.)
 *   5. python -m quintal.collect.run --site idealista --ingest ~/Downloads/quintal_idealista.json
 *
 * Notes: Imovirtual's price cell concatenates rent + €/m²; captured raw here and cleaned in
 * the adapter (`imovirtual._rent_only`). Idealista embeds location in the title; the shared
 * `row_to_raw` takes the last comma-token as the concelho.
 */
(function () {
  const SITES = {
    idealista: {
      key: "q_ide",
      cards: () => [...document.querySelectorAll("article.item")],
      row: (c) => {
        const link = c.querySelector("a.item-link");
        if (!link || !/\/imovel\//.test(link.href)) return null; // skip ads / new-dev blocks
        const details = [...c.querySelectorAll(".item-detail")].map((e) => e.textContent.trim());
        const img = c.querySelector("img");
        const src =
          img?.getAttribute("src") ||
          img?.getAttribute("data-ondemand-img") ||
          img?.getAttribute("data-src") ||
          "";
        return {
          url: link.href.split("?")[0],
          title: link.textContent.trim(),
          price_text: c.querySelector(".item-price")?.textContent?.trim() || "",
          typology: details.find((d) => /^T\d/.test(d)) || "",
          area_text: details.find((d) => /m²|m2/.test(d)) || "",
          rooms_text: details.join(", "),
          location: link.textContent.trim(), // title → concelho = last comma token
          description: c.querySelector(".item-description")?.textContent?.trim() || "",
          is_private: !c.querySelector('[class*="branding"], .logo-branding'),
          image_url: /placeholder|data:image/.test(src) ? "" : src,
        };
      },
    },
    imovirtual: {
      key: "q_imv",
      cards: () => [
        ...document.querySelectorAll(
          '[data-cy="search.listing.organic"] article, article[data-cy="listing-item"]'
        ),
      ],
      row: (c) => {
        const a = c.querySelector('a[data-cy="listing-item-link"]');
        if (!a) return null;
        const dd = [...c.querySelectorAll("dl dd")].map((e) => e.textContent.trim());
        const ps = [...c.querySelectorAll("p")].map((e) => e.textContent.trim());
        const src = c.querySelector("img")?.getAttribute("src") || "";
        return {
          url: location.origin + a.getAttribute("href").split("?")[0],
          title: c.querySelector('[data-cy="listing-item-title"]')?.textContent?.trim() || "",
          price_text:
            c.querySelector('[data-cy="listing-item-price"]')?.textContent?.trim() ||
            [...c.querySelectorAll("span,p")]
              .map((e) => e.textContent.trim())
              .find((t) => /€/.test(t)) ||
            "", // rent + €/m² concatenated; imovirtual._rent_only strips it
          typology: dd.find((d) => /^T\d/.test(d)) || "",
          area_text: dd.find((d) => /m²/.test(d)) || "",
          rooms_text: dd.join(", "),
          // Prefer the structured address from __NEXT_DATA__ (reliable, has the concelho).
          // Fall back to the address <p> — "freguesia, concelho, <District>" ending in any
          // mainland district — for the few cards not in the blob (promoted/ad tiles).
          location:
            imvLocation(imvIndex()[imvId(a.getAttribute("href"))]) ||
            ps.find((t) =>
              /(?:Aveiro|Beja|Braga|Bragança|Castelo Branco|Coimbra|Évora|Faro|Guarda|Leiria|Lisboa|Portalegre|Porto|Santarém|Setúbal|Viana do Castelo|Vila Real|Viseu)$/.test(
                t
              )
            ) ||
            "",
          description: "", // cards carry none — enriched later via quintal.descriptions
          is_private: /oferta privada/i.test(c.innerText),
          image_url: /^data:|placeholder/.test(src) ? "" : src,
        };
      },
    },
  };

  function cfg(site) {
    const c = SITES[site];
    if (!c) throw new Error("quintal: unknown site '" + site + "' (idealista|imovirtual)");
    return c;
  }

  // --- Imovirtual structured location (from Next.js __NEXT_DATA__) --------------------
  // The card address <p> is fragile — some cards omit it, so those listings lost their
  // location and their concelho collapsed to the title. The Next.js blob carries every
  // organic card's structured address, incl. the authoritative concelho at
  // reverseGeocoding.locations[locationLevel="council"]. Index it once per page (navigation
  // reloads the page, so window state is fresh each time) and match cards by the "-ID<code>"
  // href suffix (the blob's href is a "[lang]/ad/…" template; only the ID suffix is shared).
  function imvId(href) {
    const m = (href || "").split("?")[0].match(/-ID([A-Za-z0-9]+)$/);
    return m ? m[1] : null;
  }
  function imvIndex() {
    if (window.__qImvIndex) return window.__qImvIndex;
    const idx = {};
    try {
      const nd = JSON.parse(document.getElementById("__NEXT_DATA__").textContent);
      const items = ((((nd.props || {}).pageProps || {}).data || {}).searchAds || {}).items || [];
      items.forEach((it) => {
        const id = imvId(it.href);
        if (id) idx[id] = it;
      });
    } catch (e) {
      /* no blob / shape moved → callers fall back to the <p> scan */
    }
    window.__qImvIndex = idx;
    return idx;
  }
  function imvLocation(item) {
    const loc = item && item.location;
    if (!loc) return "";
    const addr = loc.address || {};
    const freguesia = addr.city && addr.city.name;
    const district = addr.province && addr.province.name;
    let concelho = null;
    const levels = (loc.reverseGeocoding && loc.reverseGeocoding.locations) || [];
    for (const l of levels)
      if (l.locationLevel === "council") {
        concelho = l.name;
        break;
      }
    // "freguesia, concelho, District" — imovirtual._parse_location strips the trailing
    // district and takes the concelho as the token before it, so a comma-containing
    // freguesia union still parses to the right concelho.
    return [freguesia, concelho, district].filter(Boolean).join(", ");
  }

  // Extract the current page's cards and merge (dedup by url) into localStorage.
  window.quintalExtract = function (site) {
    const c = cfg(site);
    const rows = c.cards().map(c.row).filter(Boolean);
    const byUrl = new Map(JSON.parse(localStorage.getItem(c.key) || "[]").map((r) => [r.url, r]));
    rows.forEach((r) => byUrl.set(r.url, r));
    const all = [...byUrl.values()];
    localStorage.setItem(c.key, JSON.stringify(all));
    return { page: rows.length, total: all.length, with_image: all.filter((r) => r.image_url).length };
  };

  // Start a fresh accumulation (call on page 1).
  window.quintalReset = function (site) {
    localStorage.removeItem(cfg(site).key);
    return "reset " + site;
  };

  // Blob-download the accumulated cards. Run FROM A FRESH same-origin TAB (2nd download in
  // the same tab is Chrome-blocked).
  window.quintalDownload = function (site) {
    const c = cfg(site);
    const data = localStorage.getItem(c.key) || "[]";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([data], { type: "application/json" }));
    a.download = "quintal_" + site + ".json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    return JSON.parse(data).length;
  };
})();
