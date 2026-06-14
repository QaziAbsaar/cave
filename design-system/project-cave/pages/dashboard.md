# Dashboard Page Overrides

> **PROJECT:** Project Cave
> **Generated:** 2026-06-15
> **Page Type:** SaaS Dashboard / Agent Pipeline Monitor

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** Full-width (100vw) with 32px side padding
- **Grid:** 12-column responsive grid for data flexibility
- **Sections:**
  1. Top navbar — project selector + user menu
  2. Pipeline status — real-time DAG flow visualization (React Flow)
  3. Agent detail panel — current agent logs, artifacts
  4. Output viewer — generated code, test results
  5. Side panel — project settings, history

### Spacing Overrides

- **Content Density:** High — optimize for information display
- **Card padding:** 20px (p-5) instead of default 24px
- **Gap between panels:** 16px
- **Sidebar width:** 280px collapsed, 360px expanded

### Typography Overrides

- Use Master typography: **Plus Jakarta Sans** for headings + body
- Mono font: **JetBrains Mono** for code/terminal output
- Font sizes:
  - Page title: 24px (text-2xl) semibold
  - Section header: 16px (text-base) semibold
  - Body: 14px (text-sm)
  - Code: 13px (text-xs) monospace
  - Status badges: 12px (text-xs) semibold uppercase

### Color Overrides

- **Pipeline node colors:**
  - Pending: slate-600
  - Running: blue-500 (pulse animation)
  - Success: emerald-500
  - Failed: red-500
  - Intervention: amber-500
- **Log background:** slate-950 (`#020617`)
- **Code block background:** slate-900 (`#0F172A`)

### Component Overrides

- **Pipeline DAG:** Interactive React Flow graph with draggable nodes
- **Artifact viewer:** Tabbed interface (DB schema → Backend code → Frontend code)
- **Progress bar:** Animated indeterminate bar during agent runs
- **Status badges:** Small dot + text indicator (green/red/yellow/blue)
- **WebSocket status:** Connection indicator in top bar (green=connected, red=disconnected)
- **Avoid:** Light mode default (keep dark as primary)
- **Avoid:** Slow rendering on status updates (use virtualization for logs)

---

## Page-Specific Components

1. **PipelineDAG** — React Flow graph showing 4 agents + edges
2. **AgentLogPanel** — Scrollable terminal-style log viewer
3. **ArtifactTabs** — Tabbed code viewer with syntax highlighting
4. **ProjectStatusBar** — Top bar with status, step count, elapsed time
5. **EventStream** — Real-time event list from WebSocket

---

## Recommendations

- **Effects:** Real-time status pulse on running nodes, smooth edge animations, terminal-style log fade-in
- **Loading:** Skeleton screens for initial load, spinner for refresh
- **Feedback:** Toast notifications for agent completion/errors
- **Responsive:** Down to 1024px keep full layout; below 1024px collapse sidebar to drawer
