# Architecture

## Stack

| Layer | Technology |
|---|---|
| Framework | SvelteKit 5 (runes mode) |
| Rendering | Static SPA — `@sveltejs/adapter-static`, `fallback: index.html` |
| PWA | `@vite-pwa/sveltekit` + Workbox (offline-first, app shell precache) |
| Styling | Scoped `<style>` blocks + global CSS custom properties |
| Language | TypeScript throughout |

---

## Directory Layout

```
src/
  app.html              HTML shell — viewport, PWA meta tags, Google Fonts preconnect
  app.css               Global design tokens (:root CSS vars), reset, @keyframes

  lib/
    api.ts                Typed fetch client for Flask backend endpoints
                          (getStatus, getLatest, getDaily, getSeries, getEvents)
    data/
      vitals.ts           Typed interfaces + mock data constants — types still
                          in use by all pages; mock values no longer used
                          by the dashboard (it pulls live data)

    components/
      StatusBar.svelte      Clock + signal/wifi/battery icons
      AppHeader.svelte      Date label, serif title, subtitle, optional avatar
      BottomNav.svelte      Fixed 3-tab nav — Dashboard / Build / Agent
                            Active state driven by $page.url.pathname
      Card.svelte           Base card wrapper; hero=true flips to green bg
      Sparkline.svelte      SVG polyline + area fill; accepts SparkPoint[]
      InsightStrip.svelte   Left-bordered callout; renders @html for bold text
      SleepStagesBar.svelte Proportional flex bar + legend from SleepStage[]
      WeeklyBars.svelte     7-bar chart; today prop dims + recolors label
      MetricRow.svelte      Label / serif-value / unit row with bottom border
      SectionLabel.svelte   Full-grid-width section divider
      ChatBubble.svelte     agent | user bubble with role label
      ChatInput.svelte      Input + send button; fires onSend callback
      SavedWidgetCard.svelte Icon tile + name/type; color driven by string key

  routes/
    +layout.svelte      Imports app.css; renders StatusBar → <main> → BottomNav
    +page.svelte        Dashboard — full metric grid
    builder/
      +page.svelte      Widget builder — saved widget list + conversational card
    agent/
      +page.svelte      Health agent chat — message list + suggestions + input

static/
  icons/                SVG placeholder icons (192, 512) for PWA manifest
  robots.txt

reference/
  health-app.html       Original single-file prototype (source of truth for design)

vite.config.ts          SvelteKitPWA plugin config — manifest, Workbox glob patterns,
                        Google Fonts runtime cache (CacheFirst, 1yr TTL)
svelte.config.js        adapter-static + runes: true enforced project-wide
vibedash_spec.md        Product spec — describes LLM-powered widget builder vision
```

---

## Data Flow

**Dashboard** pulls live data from the Flask backend on mount (see
"Backend Integration" below). Types from `vitals.ts` are still used for
component props, but the actual values come from the API.

**Builder & Agent pages** still use static mock data from `vitals.ts`
(`savedWidgets`, `agentMessages`, `agentSuggestions`, etc.). They have
not yet been connected to a backend.

State that exists: `$state` on message arrays in `/builder` and `/agent`
pages — append-only, local to the page, reset on navigation. The
dashboard uses `$state` for all loaded metric values.

---

## Routing

Three routes, no nested layouts beyond the root. Navigation is SvelteKit `<a href>` links inside `BottomNav`. The static adapter emits a single `index.html` fallback so all routes resolve client-side.

```
/          → Dashboard
/builder   → Widget Builder
/agent     → Health Agent
```

---

## PWA Configuration

- **Precache:** all `.js`, `.css`, `.html`, `.svg`, `.png`, `.woff2` at build time
- **Runtime cache:** Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) — CacheFirst, 1 year, max 10 entries
- **Register mode:** `autoUpdate` (silent SW update on new deploy)
- **Dev:** PWA enabled in dev mode (`devOptions.enabled: true`) to avoid 404 on `manifest.webmanifest`
- **Icons:** SVG placeholders — need real 192×512 PNGs for full iOS installability

---

## Backend Integration (Dashboard)

The Dashboard page (`/routes/+page.svelte`) now pulls live data from the Flask backend
(`backend/backend/backend.py`) instead of using the static mock module.

### API Client (`src/lib/api.ts`)

Typed fetch wrappers around the backend endpoints. Base URL defaults to
`http://127.0.0.1:5000` and can be overridden via `VITE_API_BASE` env var.
The backend enables CORS globally so the static SPA can call it directly
from any origin.

| Function | Backend endpoint | Returns |
|---|---|---|
| `getStatus()` | `GET /api/status` | dataset metadata (rows, start/end, columns) |
| `getLatest(columns?)` | `GET /api/latest` | most recent row for requested columns |
| `getDaily(day)` | `GET /api/daily?day=YYYY-MM-DD` | daily aggregates for one day |
| `getSeries(column, opts)` | `GET /api/series/<column>` | time-series with optional `step`, `dropNull` |
| `getEvents(opts)` | `GET /api/events` | discrete events (workouts, weigh-ins, BP) |

### Loading Strategy

On mount, the dashboard calls `onMount` and fires a cascade of parallel
fetch requests:

1. **`/api/status`** → determines the dataset date range; the last date
   in the dataset is treated as "today" for all queries.

2. **Dense real-time metrics** — `getLatest('spo2,heart_rate,calories,steps')`.
   These columns exist per-second so the latest row is always meaningful.

3. **Sparse morning-only metrics (HRV, RHR)** — `getSeries('hrv', …)` and
   `getSeries('rhr', …)` for the current day with `dropNull: true`,
   then the **last value** in each series is taken as the daily reading.
   *Why not `getLatest`?* The CSV only contains HRV/RHR once per day
   (recorded around 07:00). At dataset end (23:59:59) these columns are
   `NaN`, so `/api/latest` returns unusable values. The series approach
   filters nulls and picks the last real observation.

4. **Daily aggregates** — `getDaily(todayStr)` provides steps, calories,
   workout seconds, sleep score, resting HR, HRV, SpO₂ mean, weight,
   blood pressure.

5. **Sleep stages** — `getSeries('sleep_phase', …)` with `step: 300`
   (5-minute intervals) and `dropNull: true` over the last night
   (18:00 yesterday → 12:00 today). Second-count × 300s = sleep
   duration. Stage proportions are aggregated by type
   (`deep`, `REM`, `light`) and fed into `<SleepStagesBar>`.

6. **Weekly bars + 7-day summary** — 7 parallel `getDaily()` calls
   for the last 7 dataset days. Daily strain is computed from
   `workout_seconds` (or from `steps` as a fallback) for each day
   and mapped to bar heights.

7. **Sparklines** — `getSeries('hrv', …)` and `getSeries('rhr', …)`
   over the full week with `dropNull: true`. The returned timestamps
   and values are mapped into `<Sparkline>`'s coordinate space
   (0–140 x, 0–40 y viewBox). If a series is empty, a static
   8-point fallback shape is used.

### Computed & Fallback Values

| Dashboard card | Source | Fallback if data missing |
|---|---|---|
| **Recovery %** | Computed formula: `100 − (RHR−35)×1.2 + (HRV−50)×0.25`, clamped 0–100 | 78 |
| **Recovery zone** | `≥80` → Green, `≥60` → Yellow, else Red | "Green zone — ready" |
| **HRV / Resting HR** | Last value from `/api/series` with `dropNull` | 68 ms / 52 bpm |
| **HRV/RHR sparklines** | Weekly series mapped to SVG coords | 8-point mock shape |
| **Sleep duration** | `sleep_phase` count × step (300s) for last night | 0h 0m |
| **Sleep score** | `daily.sleep_score` | 85 |
| **Sleep stages bar** | Stage counts aggregated from downsampled series | 8-segment mock bar |
| **Strain** | `workout_seconds / 3600 × 8`, capped at 21. If no workout: `steps / 12000 × 8`, capped at 8 | 6.0 |
| **Calories active/basal** | Split 28% / 72% of `daily.calories_total` (rough estimate) | 2100 total |
| **SpO₂** | `daily.spo2_mean` | 97 |
| **Resp. Rate** | *Not in CSV* | 14.8 rpm (static) |
| **Skin Temp** | *Not in CSV* | +0.2 °C (static) |
| **Weekly strain bars** | 7× `getDaily()` → strain computed per day → bar height | bars at 8% min height |
| **7-day summary** | Averaged from the 7 daily calls | static mock row values |
| **Insight text** | Dynamic message keyed to recovery zone | generic loading text |

### Timezone Handling

The CSV timestamps are **tz-naive** (no timezone, assumed local wall-clock
hours). The frontend must **not** send ISO strings with a `Z` suffix
(because `toISOString()` converts to UTC). A helper `fmtNaiveISO(d)`
produces `YYYY-MM-DDTHH:mm:ss` in the local timezone. Sending `Z`-suffixed
timestamps causes a `TypeError` inside pandas: *Cannot compare tz-naive and
tz-aware datetime-like objects*.

### State Management

All loaded data lives in `$state` variables inside `+page.svelte` (no global
stores, no SvelteKit load functions — the app is a static SPA so server-side
`load` does not run). Data is fetched once on mount; there is no polling or
reactive refresh. Navigation away and back re-fetches.

### Error Handling

If any fetch fails, an error banner is rendered above the grid. Sparkline
and sleep-stage arrays fall back to static shapes so the cards remain
visually stable.

---

## What Is Not Implemented

- Backend API endpoints for `/api/agent` and `/api/widgets` (described in `vibedash_spec.md`)
- Actual LLM widget generation
- Widget persistence
- Real health data ingestion
- Dashboard polling / live refresh
- Per-night sleep duration in the weekly average (currently reuses today's sleep as proxy)
