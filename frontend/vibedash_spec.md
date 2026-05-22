# VibeDash — Meta-Vibecoding Health Analytics Dashboard
## Product Specification v0.1

---

## 1. Concept Summary

A health analytics dashboard where users can extend the UI by chatting with an embedded agent. The agent interprets natural language prompts, generates a compute function + widget descriptor, and renders a new chart into the dashboard. Widgets are persisted and reloaded on return. The frontend is fully deterministic; the LLM only authors data transformation logic and selects from a fixed chart vocabulary.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                            │
│                                                                     │
│  ┌─────────────────────────────┐   ┌──────────────────────────────┐ │
│  │  Dashboard Grid             │   │  Chat Panel                  │ │
│  │  [Widget] [Widget] [Widget] │   │  > "Show 7-day HRV trend"    │ │
│  │  [Widget] [+ Add via chat]  │   │  < generating...             │ │
│  └────────────┬────────────────┘   └────────────┬─────────────────┘ │
│               │                                 │                   │
└───────────────┼─────────────────────────────────┼───────────────────┘
                │                                 │
        render widgets                     POST /api/agent
                │                                 │
┌───────────────▼─────────────────────────────────▼───────────────────┐
│  Backend                                                            │
│                                                                     │
│  GET /api/health/raw     POST /api/agent      GET/POST /api/widgets │
│  (static data layer)     (LLM orchestrator)   (widget persistence)  │
│                                                                     │
│                          ┌─────────────┐                            │
│                          │  LLM API    │                            │
│                          │  (Claude /  │                            │
│                          │   OpenAI)   │                            │
│                          └─────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Layer

### 3.1 Raw Data Contract

The backend exposes a single endpoint returning all raw health data the frontend is allowed to compute against. This schema is also injected verbatim into the LLM system prompt.

```
GET /api/health/raw
```

Response shape (example — adapt to actual data source):

```ts
type RawHealthData = {
  records: HealthRecord[]
}

type HealthRecord = {
  date: string            // ISO 8601, e.g. "2024-03-15"
  hrv_ms: number          // Heart rate variability, milliseconds
  resting_hr: number      // BPM
  sleep_duration_h: number
  sleep_score: number     // 0–100
  deep_sleep_h: number
  rem_sleep_h: number
  steps: number
  active_calories: number
  workout_minutes: number
  spo2_pct: number        // Blood oxygen
  stress_score: number    // 0–100
  weight_kg?: number
}
```

Rules:
- All fields must be documented with units and range in a schema constant shared with the LLM
- Missing values represented as `null`, never omitted
- The frontend fetches this once on load and caches it in memory for the session

### 3.2 Data Source Adapters

The raw endpoint is backed by an adapter layer. Supported sources:

| Source | Adapter |
|---|---|
| Garmin Connect | `GarminAdapter` via Garmin Health API |
| Apple Health | `AppleAdapter` via exported XML or HealthKit bridge |
| Oura Ring | `OuraAdapter` via Oura REST API |
| CSV upload | `CSVAdapter` (manual import fallback) |

All adapters map to the canonical `HealthRecord` schema. No frontend code is aware of the source.

---

## 4. Widget System

### 4.1 Widget Schema

The atomic persisted unit:

```ts
type Widget = {
  id: string              // UUID
  title: string
  description: string     // shown as subtitle
  dataFields: string[]    // which HealthRecord fields this uses (for docs/hints)
  computeFn: string       // JS function body string: (data: HealthRecord[]) => ComputeResult
  vizType: VizType
  vizConfig: VizConfig
  createdAt: string
  updatedAt: string
}

type VizType =
  | 'single_value'
  | 'line'
  | 'bar'
  | 'stacked_bar'
  | 'heatmap'
  | 'scatter'

type ComputeResult =
  | SingleValueResult
  | SeriesResult

type SingleValueResult = {
  kind: 'single_value'
  value: number
  unit: string
  label: string
  trend?: 'up' | 'down' | 'flat'
  trendValue?: number     // e.g. +3.2 (relative to previous period)
}

type SeriesResult = {
  kind: 'series'
  series: Array<{ x: string | number; y: number; [key: string]: any }>
  xLabel?: string
  yLabel?: string
  unit?: string
}
```

### 4.2 Chart Registry

Fixed registry. No new chart types added at runtime.

```ts
import { LineWidget } from './widgets/LineWidget'
import { BarWidget } from './widgets/BarWidget'
import { StackedBarWidget } from './widgets/StackedBarWidget'
import { SingleValueWidget } from './widgets/SingleValueWidget'
import { HeatmapWidget } from './widgets/HeatmapWidget'
import { ScatterWidget } from './widgets/ScatterWidget'

const CHART_REGISTRY: Record<VizType, React.FC<WidgetProps>> = {
  single_value: SingleValueWidget,
  line:         LineWidget,
  bar:          BarWidget,
  stacked_bar:  StackedBarWidget,
  heatmap:      HeatmapWidget,
  scatter:      ScatterWidget,
}
```

Charting library: **Recharts** (Tremor is an acceptable alternative for faster prototyping).

### 4.3 Widget Execution

```ts
function executeWidget(widget: Widget, rawData: HealthRecord[]): ComputeResult {
  const fn = new Function('data', widget.computeFn)
  const result = fn(rawData)
  validateComputeResult(result)   // throws if shape is wrong
  return result
}
```

All widget execution is sandboxed via `new Function()`. No `eval()` with direct scope access. Future: iframe sandbox for stronger isolation.

---

## 5. Agent System

### 5.1 Agent Endpoint

```
POST /api/agent
Body: { prompt: string, existingWidgets?: Widget[] }
Returns: { widget: Widget } | { error: string, attempts: number }
```

### 5.2 System Prompt

The system prompt injected on every agent call:

```
You are a health dashboard widget builder.

The user has health data with the following schema:
<SCHEMA>
{{DATA_SCHEMA_JSON}}
</SCHEMA>

When the user describes a metric or visualization they want, respond ONLY with a
valid JSON object matching the Widget type below. No prose, no markdown fences.

Widget JSON schema:
{{WIDGET_SCHEMA_JSON}}

Rules:
- computeFn must be a valid JS function body string taking (data: HealthRecord[])
  and returning a ComputeResult object
- vizType must be one of: single_value | line | bar | stacked_bar | heatmap | scatter
- Choose vizType based on what makes sense for the metric — trends → line,
  comparisons → bar, single KPIs → single_value
- Handle null values in data gracefully (filter them out before computing)
- title should be concise (≤ 5 words)
- description should explain what the metric means (1 sentence)
```

### 5.3 Retry Loop

Max 5 attempts total across two error classes:

```
Attempt budget:
  Structural errors (invalid JSON, bad vizType, missing fields): max 2 retries
  Runtime errors (computeFn throws on actual data):              max 3 retries
  Total hard cap:                                                5 attempts
```

Error feedback injected as user message into conversation history:

```ts
function buildRetryMessage(error: ValidationError, attempt: number): string {
  return `
Attempt ${attempt} failed.

Error class: ${error.class}   // 'structural' | 'runtime' | 'shape'
Error type:  ${error.type}    // e.g. TypeError
Message:     ${error.message}

Your computeFn:
\`\`\`js
${error.failedFn}
\`\`\`

Sample of actual data (2 records):
${JSON.stringify(error.dataSample, null, 2)}

Fix the issue and return the complete Widget JSON again.
  `.trim()
}
```

### 5.4 Validation Pipeline

In order:

1. **JSON parse** — is the LLM output valid JSON?
2. **Schema validation** — all required Widget fields present and correctly typed?
3. **vizType check** — is vizType in the CHART_REGISTRY?
4. **Syntax check** — `new Function('data', widget.computeFn)` without error?
5. **Runtime check** — execute against full rawData without throwing?
6. **Shape check** — does the result match `ComputeResult` schema?

Each failure class routes to the appropriate retry message.

---

## 6. Persistence

### 6.1 Widget Storage

```
GET    /api/widgets          → Widget[]           (load dashboard)
POST   /api/widgets          → Widget             (save new widget)
PUT    /api/widgets/:id      → Widget             (update existing)
DELETE /api/widgets/:id      → { ok: true }       (remove widget)
```

Backend storage: PostgreSQL table `widgets` with columns matching Widget schema. `computeFn` stored as text.

### 6.2 Dashboard Layout

Widget grid positions stored separately:

```ts
type LayoutConfig = {
  userId: string
  layout: Array<{
    widgetId: string
    gridX: number     // column index
    gridY: number     // row index
    w: number         // width in grid units
    h: number         // height in grid units
  }>
}
```

Library: **react-grid-layout** for drag-and-drop repositioning.

---

## 7. Frontend UI

### 7.1 Dashboard Grid

- Default grid: 12 columns, rows auto-sized to content
- Default widget sizes: `single_value` → 2×1, `line`/`bar` → 4×2, `heatmap` → 6×2
- Widgets draggable and resizable by user
- Layout persisted to `POST /api/layout` on drop/resize

### 7.2 Chat Panel

- Collapsible sidebar, default width 340px
- Displays conversation history between user and agent
- Shows per-attempt status: "Generating...", "Retrying (2/5)...", "Failed after 5 attempts"
- On success: renders widget preview inline in chat before adding to dashboard
- User confirms ("Add to dashboard") or discards

### 7.3 Widget Card UI

Each widget card:
- Title + description header
- Chart area (Recharts component from registry)
- Last updated timestamp
- Three-dot menu: Edit (re-prompt agent), Delete, Move

### 7.4 Widget Edit Flow

"Edit" opens chat panel pre-filled with the widget's current title + description as context, allowing the user to describe a modification. Agent receives the existing Widget object and the new prompt.

---

## 8. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | React + TypeScript | Typed widget schemas, component ecosystem |
| Charts | Recharts | Composable, well-documented, Recharts is React-native |
| Grid layout | react-grid-layout | De-facto standard for draggable dashboards |
| Backend | FastAPI (Python) or Next.js API routes | Fast to stand up, easy LLM integration |
| LLM | Claude via Anthropic API (or OpenAI) | Strong JSON instruction-following |
| DB | PostgreSQL | Reliable, widget JSON stored as text column |
| Auth | Clerk or NextAuth | Not core, plug in later |

---

## 9. Security & Safety

- `computeFn` executed via `new Function()`, never `eval()` — no closure scope leak
- `computeFn` string stored as-is in DB; re-validated on load before execution
- Compute result size capped at 10,000 data points before rendering
- LLM API key never exposed to frontend; all agent calls proxied through backend
- Rate limit `/api/agent`: 20 calls/user/hour to prevent abuse

---

## 10. MVP Scope

**In scope for v0.1:**

- Raw data endpoint with mock/CSV data
- Agent endpoint with retry loop
- 4 chart types: `single_value`, `line`, `bar`, `scatter`
- Widget persistence (save/delete)
- Fixed 2-column grid layout (no drag-and-drop yet)
- Chat panel with generation status

**Deferred to v0.2+:**

- Drag-and-drop grid layout
- Widget edit flow (re-prompting)
- Multi-user / auth
- Real data source adapters (Garmin, Oura)
- Iframe sandbox for stronger compute isolation
- Backend computation registry (Option C)

---

## 11. Open Questions

| Question | Options | Recommendation |
|---|---|---|
| LLM provider | Claude vs OpenAI | Claude — better instruction following for structured JSON |
| Compute isolation | `new Function()` vs iframe sandbox | `new Function()` for MVP, iframe in v0.2 |
| Data freshness | Fetch on load vs polling | Fetch on load + manual refresh button for MVP |
| Widget sharing | Per-user vs shared library | Per-user for MVP |
| computeFn timeout | None vs enforced | Add 2s timeout via `Promise.race` before v0.1 ships |
