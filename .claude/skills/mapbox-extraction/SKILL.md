---
name: mapbox-extraction
description: Techniques for extracting dot/feature data from a Mapbox GL map that HIDES its instance (no mapboxgl/maplibregl global, bundled build) — recover the hidden map object via an injected constructor hook or a canvas-getContext + React-fiber walk, then queryRenderedFeatures/querySourceFeatures; plus the network-capture and vector-tile-decode fallbacks. Use when the precise hunter captures 0, the map object "can't be reached," or you're deciding between reading the map object vs the wire on the AT&T fiber map (or any Mapbox site).
---

# Getting data off a Mapbox map that hides its instance

The AT&T dealer map (`youachieve.att.com/yourefer/fiber`) renders Mapbox dots +
basemap tiles but exposes **no `mapboxgl`/`maplibregl` global and no reachable
instance** (verified 2026-06-15: `hookedMaps:0, mapboxgl=false, maplibregl=false`
in both frames). The brain called the map-object read "IMPOSSIBLE." It is NOT —
it just needs one of the recovery hooks below, injected BEFORE the page's scripts
run. This skill is the menu of ways to pull the data, cheapest/most-robust first.

## Decision order (try in this order)

1. **Network capture** (already the hunter's default, most robust) — read the
   dots off the wire, never touch the map object.
2. **Constructor hook** — if a `mapboxgl`/`maplibregl` global exists at any point,
   wrap `Map` so every instance self-registers. Then `queryRenderedFeatures`.
3. **Canvas / React-fiber recovery** — for a BUNDLED build with no global (AT&T's
   case): catch the WebGL canvas as it's created, then walk the DOM/React fiber to
   the live map object.
4. **Vector-tile decode** — if the dots ship as `.pbf`/protobuf tiles, decode them
   to lng/lat + properties.

---

## 1. Network capture (the proven path — prefer this)

The dots come from a server call; you don't need the map object at all. Attach a
response listener BEFORE navigating, then trigger the fetch (search box / pan /
"Search this area") while it listens.

```python
page.on("response", cap.handle)          # passive: catch every response
page.goto(MAP_URL)
# deterministic trigger for a known endpoint:
with page.expect_response(lambda r: "serviceability" in r.url) as got:
    click_search_this_area(page)
data = got.value.json()
```

- AT&T's dot/address feed = the **`serviceability` JSON** endpoint (decoded by
  `optimus_api_capture.extract_features`). If a normal run captures 0, the fetch
  isn't firing during capture → force it by typing the area into the search box.
- Run with the endpoint dumper on (the hunter's `--net-debug` / `dump_debug`) to
  pin a RENAMED feed; it lists every URL biggest-first + writes `net_responses.log`.
- The **Backend Capture** sheet tab (hunter's `dump_backend`) is how you read this
  remotely without F12.

## 2. Constructor hook (when a global exists)

Inject before any page script so you wrap `Map` the instant the library loads.
Every map created then registers itself — no matter what scope it lives in.

```python
page.add_init_script("""
(() => {
  const reg = (Ctor) => new Proxy(Ctor, {
    construct(target, args) {
      const m = new target(...args);
      (window.__optimusMaps ||= []).push(m);
      return m;
    }
  });
  const hook = () => {
    for (const g of ['mapboxgl','maplibregl']) {
      if (window[g] && window[g].Map && !window[g].__hooked) {
        window[g].Map = reg(window[g].Map);
        window[g].__hooked = true;
      }
    }
  };
  hook();
  // library may load late (bundled/async) — re-check for a while
  const t = setInterval(hook, 250);
  setTimeout(() => clearInterval(t), 30000);
})();
""")
```

Then read features (see §5). NOTE this only works if `mapboxgl`/`maplibregl` is
ever assigned to `window`. AT&T's bundle does NOT do this → use §3.

## 3. Canvas / React-fiber recovery (bundled build, NO global — the AT&T unlock)

When the library is webpack-bundled with no global, you can't wrap `Map` by name.
Two escape hatches, both injected via `page.add_init_script` BEFORE navigation:

**(a) Catch the WebGL canvas as Mapbox creates it.** Mapbox calls
`canvas.getContext('webgl'|'webgl2')`. Hook it, keep the canvas, and its
container chain leads to the map.

```python
page.add_init_script("""
(() => {
  const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
      (window.__glCanvases ||= []).push(this);   // Mapbox's map canvas
    }
    return orig.call(this, type, ...rest);
  };
})();
""")
```

**(b) From the canvas, walk to the live map object.** Mapbox's canvas sits inside
`.mapboxgl-canvas-container` → `.mapboxgl-map`. The map instance is reachable via
the React fiber on/near that node, or a stored back-reference. Search for an object
that has `queryRenderedFeatures` + `getStyle`:

```python
MAP_FROM_DOM_JS = """
() => {
  const isMap = (o) => o && typeof o.queryRenderedFeatures === 'function'
                    && typeof o.getStyle === 'function';
  // 1) any canvas we caught -> climb its ancestors, scan React fiber props/state
  const nodes = new Set();
  for (const c of (window.__glCanvases || [])) {
    let n = c;
    for (let i = 0; i < 6 && n; i++) { nodes.add(n); n = n.parentElement; }
  }
  document.querySelectorAll('.mapboxgl-map, .maplibregl-map, canvas')
          .forEach(n => nodes.add(n));
  const seen = new Set(); const q = [];
  for (const n of nodes) {
    for (const k in n) {                      // React fiber keys: __reactFiber$...
      if (k.startsWith('__react')) q.push(n[k]);
    }
    // some builds stash the map on the container element directly
    for (const k of Object.keys(n)) { try { if (isMap(n[k])) return tag(n[k]); } catch(e){} }
  }
  // 2) BFS the fiber tree for memoizedProps/State/stateNode holding the map
  let steps = 0;
  while (q.length && steps++ < 5000) {
    const f = q.shift();
    if (!f || seen.has(f)) continue; seen.add(f);
    for (const key of ['memoizedProps','memoizedState','stateNode','pendingProps']) {
      const v = f && f[key];
      if (isMap(v)) return tag(v);
      if (v && typeof v === 'object') {
        for (const kk in v) { try { if (isMap(v[kk])) return tag(v[kk]); } catch(e){} }
      }
    }
    for (const key of ['child','sibling','return']) if (f && f[key]) q.push(f[key]);
  }
  function tag(m){ (window.__optimusMaps ||= []).push(m); return true; }
  return false;
}
"""
found = page.evaluate(MAP_FROM_DOM_JS)   # True => window.__optimusMaps[0] is live
```

Give the map a moment to instantiate after load before calling this. Once
`window.__optimusMaps[0]` exists you read features exactly like §5. If BOTH the
global hook and this fiber walk fail, the map genuinely isn't a standard
mapbox/maplibre object → fall back to network capture (§1) / tiles (§4).

## 4. Vector-tile decode (dots ship as protobuf tiles)

If the dot layer is `.pbf`/`x-protobuf` tiles (confirmed for AT&T 2026-06-14), the
JSON path returns 0 — decode the tiles instead.

- Lib: **`mapbox-vector-tile`** (tilezen, maintained pure-Python) — `pip install
  mapbox-vector-tile`; `mapbox_vector_tile.decode(body)` → layers/features/props.
- Each feature geom is tile-local (0..extent, extent=4096). Convert to lng/lat with
  the tile's z/x/y + web-mercator:
  ```
  n = 2**z
  lon = (x + gx/extent) / n * 360 - 180
  lat = degrees(atan(sinh(pi * (1 - 2*(y + gy/extent)/n))))
  ```
- If a tile carries only geometry (no address text in props), you still get the
  dot's lng/lat + color-by-pixel; the address then needs the JSON feed or a click.

## 5. Reading features once you HAVE the map object

```python
FEATURES_JS = """
() => {
  const m = (window.__optimusMaps || [])[0];
  if (!m) return null;
  // querySourceFeatures returns ALL features in loaded viewport tiles (even ones
  // not painted) -> more complete than queryRenderedFeatures for a full dot pull.
  const style = m.getStyle();
  const layerIds = style.layers.map(l => l.id);
  const out = [];
  for (const f of m.queryRenderedFeatures()) {   // or querySourceFeatures(srcId,{sourceLayer})
    const c = f.geometry && f.geometry.coordinates;
    out.push({ layer: f.layer.id, props: f.properties,
               lng: Array.isArray(c) ? c[0] : null,
               lat: Array.isArray(c) ? c[1] : null,
               // exact screen pixel so you can sample the dot's own colour:
               px: (c && m.project) ? m.project(c) : null });
  }
  return { layers: layerIds, dots: out, rect: m.getCanvas().getBoundingClientRect() };
}
"""
```

- `queryRenderedFeatures()` = only what's painted in the viewport; `querySourceFeatures(source, {sourceLayer})` = everything in the loaded viewport tiles (better coverage, needs the source/source-layer id — get them from `getStyle().layers`).
- `m.project([lng,lat])` gives the exact on-screen pixel → sample THAT pixel to
  colour the dot (GREEN/GOLD/GREY) instead of guessing on whole-screen pixels
  (which mis-reads portal buttons). This is `classify_pixel` in the hunter.
- Filter out the basemap layers by id/source; keep only the AT&T dot layer(s).

## Hard-won gotchas (from this repo)

- **Inject hooks BEFORE `page.goto`** (`add_init_script`), not after — the map is
  built during load; a late hook misses the constructor.
- **The map can be in a frame** — run recovery in each `page.frames` context, and
  when dragging fall back to the viewport map-region (`page.mouse`) since a frame
  canvas isn't reachable from the top page.
- **Don't trust whole-screen pixel detection** — it reads the portal's blue nav as
  "dots" and clicking them flips the view. Always anchor to a real dot's `project`
  pixel or a decoded feature coordinate.
- **querySourceFeatures only sees loaded tiles** — pan across the area to load more;
  it is NOT a dataset search.
- If everything object-side fails, **network capture is the floor** and always
  works — the dots crossed the wire to get drawn.

## Sources
- Mapbox GL JS API (Map, project/unproject, queryRenderedFeatures, querySourceFeatures): https://docs.mapbox.com/mapbox-gl-js/api/map/
- queryRenderedFeatures example: https://docs.mapbox.com/mapbox-gl-js/example/queryrenderedfeatures/
- queryRenderedFeatures vs querySourceFeatures: https://github.com/mapbox/mapbox-gl-js/issues/3751
- Reaching the map's window via `map._container.ownerDocument.defaultView`: https://github.com/mapbox/mapbox-gl-js/issues/4116
- Vector tile decode (tilezen/mapbox-vector-tile): https://github.com/tilezen/mapbox-vector-tile
- Vector tile standards / extent + coords: https://docs.mapbox.com/data/tilesets/guides/vector-tiles-standards/
