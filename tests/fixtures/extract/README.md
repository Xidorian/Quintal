# extract.js fixtures

Saved search-results markup that `tests/extract_harness.mjs` replays through the real
`src/quintal/collect/extract.js`, so a selector or blob-shape change fails `pytest` instead of
silently corrupting a pull. Asserted in `tests/test_extract_js.py`.

| file | provenance | what it pins |
|---|---|---|
| `imovirtual-search.html` | captured live **2026-09-26** | 3 real organic cards + the matching trimmed `__NEXT_DATA__`. Two cards are in the blob (so they exercise the `reverseGeocoding` path, one with freguesia ≠ concelho — `São Gonçalo de Lagos, Lagos, Faro`), one is a promoted tile absent from the blob (so it exercises the address-`<p>` fallback). Captured *after* imovirtual nulled `address.city`/`address.province`, so it reproduces the QT-050 shape. One card carries the real `680 €12,36 €/m²` concatenation. |
| `idealista-search.html` | captured live **2026-09-26** | 2 real cards — one private, one agency-branded — pinning `is_private` (which decides the canonical winner in `dedup.py`) and the title-derived concelho. |
| `imovirtual-selector-moved.html` | **derived**, not captured as-is | `imovirtual-search.html` with only the two card selectors renamed, listing links untouched. The selector-drift alarm: zero cards while the page plainly shows 3 listings → `suspect="no-cards"`. |
| `idealista-end-of-results.html` | hand-written | A results page past the last page: no cards **and** no listing links → `expected=0`, `suspect="none"`. Pins the no-false-alarm side, which paging-to-plateau depends on. |
| `imovirtual-price-css-incident.html` | **derived**, not captured as-is | Card 1 of `imovirtual-search.html` with the styled-components `<style>` that imovirtual's SSR emitted *inside* the price cell re-injected verbatim (QT-049). Only the price cell differs from the real capture. |

## Why two fixtures are derived rather than captured

**`imovirtual-price-css-incident.html`** — the QT-049 markup is *intermittent*. It was present
on 2026-09-04, where a raw `.textContent` read the rent out of a colour and a font-size and
priced thirteen Faro listings at €0.63/month. It was **absent** from the live page on 2026-09-26
— verified directly (`priceHasStyle: false` on all 40 cards) — so a freshly captured fixture
does not reproduce it. Hence the reconstruction.

**`imovirtual-selector-moved.html`** — you cannot capture a portal breaking its own markup on
demand, so the break is simulated by renaming the card selectors on a real capture. That is
exactly the shape the alarm must catch: the listing links are untouched, so the page still
plainly shows 3 listings while the card selector finds none.

## What these fixtures do NOT do

They are a **snapshot**. They pin the parsing contract and the two known regression classes;
they cannot detect future production drift on their own. If a portal moves its markup next
month, the real pull breaks while these tests stay green. The gate protects against *our* code
regressing, not against *their* markup changing.

So: when a pull looks wrong — zero cards, junk concelhos, absurd prices — **re-capture before
debugging**, then run the suite. If the tests now fail, the fixture caught up with reality and
the extractor needs fixing.

## Re-capturing

Collection is browser-session based, so this is a manual capture from a logged-in page (same
flow as `RECOLLECT.md` step 1). In the results tab, build a minimal document from real cards:

```js
// imovirtual — 2 cards that ARE in __NEXT_DATA__ + 1 that is not, with a trimmed blob.
const cs=[...document.querySelectorAll('[data-cy="search.listing.organic"] article, article[data-cy="listing-item"]')];
const idOf=h=>{const m=(h||'').split('?')[0].match(/-ID([A-Za-z0-9]+)$/);return m?m[1]:null;};
const hid=c=>c.querySelector('a[data-cy="listing-item-link"]').getAttribute('href');
const all=JSON.parse(document.getElementById('__NEXT_DATA__').textContent)
           .props.pageProps.data.searchAds.items;
const ids=new Set(all.map(it=>idOf(it.href)));
const small=a=>a.sort((x,y)=>x.outerHTML.length-y.outerHTML.length);
const picked=[...small(cs.filter(c=>ids.has(idOf(hid(c))))).slice(0,2),
              ...small(cs.filter(c=>!ids.has(idOf(hid(c))))).slice(0,1)];
const keep=picked.map(c=>idOf(hid(c)));
const blob={props:{pageProps:{data:{searchAds:{items:all.filter(it=>keep.includes(idOf(it.href)))}}}}};
window.__fx='<!doctype html>\n<html lang="pt"><head><meta charset="utf-8"><title>imovirtual search fixture</title></head>\n<body>\n<div data-cy="search.listing.organic">\n'
  + picked.map(c=>c.outerHTML).join('\n')
  + '\n</div>\n<script id="__NEXT_DATA__" type="application/json">'
  + JSON.stringify(blob).replace(/</g,'\\u003c') + '</'+'script>\n</body></html>\n';
```

```js
// idealista — one private card and one agency-branded card.
const cs=[...document.querySelectorAll('article.item')];
const isAg=c=>!!c.querySelector('[class*="branding"], .logo-branding');
const small=a=>a.sort((x,y)=>x.outerHTML.length-y.outerHTML.length);
const picked=[small(cs.filter(c=>!isAg(c)))[0], small(cs.filter(isAg))[0]];
window.__fx='<!doctype html>\n<html lang="pt"><head><meta charset="utf-8"><title>idealista search fixture</title></head>\n<body>\n<main>\n'
  + picked.map(c=>c.outerHTML).join('\n') + '\n</main>\n</body></html>\n';
```

Then download it (**fresh tab per download**, and `rm ~/Downloads/quintal_*` first — see
`RECOLLECT.md` step 2):

```js
const a=document.createElement('a');
a.href=URL.createObjectURL(new Blob([window.__fx],{type:'text/html'}));
a.download='quintal_fx.html'; document.body.appendChild(a); a.click(); a.remove();
```

Move it into this directory, update the expected ids/values in `tests/test_extract_js.py`
(they are asserted by listing id, e.g. `ID1iUGn`), and update the capture dates in the table
above. Then regenerate **both** derived fixtures from the new capture:

```python
# imovirtual-selector-moved.html — rename only the card selectors, leave the links alone.
src = open("imovirtual-search.html").read()
moved = (src.replace('data-cy="search.listing.organic"', 'data-cy="search.listing.organic-RENAMED"')
            .replace('data-cy="listing-item"', 'data-cy="listing-item-RENAMED"'))
```

For `imovirtual-price-css-incident.html`, take card 1 of the new capture and re-inject the
`<style>` block immediately after the `listing-item-price` opening tag (keep the `__NEXT_DATA__`
blob so the location path still resolves). Preserve the provenance comment at the top of each —
it is the only thing telling a future reader they are not raw captures.

**Check for PII before committing** — these are public search-results cards (no account data),
but the capture is raw markup, so skim it rather than trusting that.
