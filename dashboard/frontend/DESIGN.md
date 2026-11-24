# AirFed Dashboard — Design System & Motion Specification

## 1. Design Philosophy

**Fluid, interruptible, velocity-aware motion** — following Apple's *Designing Fluid Interfaces* principles. Every interaction starts on pointer-down, tracks 1:1, projects momentum on release, and can be grabbed mid-flight.

**Cohesion over decoration** — Motion serves wayfinding, hierarchy, and state clarity. No gratuitous animation.

**Respects accessibility** — `prefers-reduced-motion` downgrades springs to 150ms cross-fades; `prefers-reduced-transparency` solidifies glass layers; `prefers-contrast: more` enforces visible borders.

---

## 2. Color System (CSS Custom Properties)

All values use `hsl()` format for reliable light/dark switching.

```css
:root {
  /* Base semantic tokens — both themes */
  --background: hsl(0 0% 100%);
  --foreground: hsl(0 0% 9%);
  --muted: hsl(0 0% 96%);
  --muted-foreground: hsl(0 0% 45%);
  --border: hsl(0 0% 90%);
  --ring: hsl(217 91% 60%);

  /* AirFed Brand — Electric Blue */
  --accent: hsl(199 89% 48%);
  --accent-foreground: hsl(0 0% 100%);
  --accent-soft: hsl(199 89% 48% / 0.12);
  --accent-dim: hsl(199 89% 48% / 0.08);

  /* Semantic status — both themes */
  --ok: hsl(142 76% 36%);
  --ok-text: hsl(142 76% 36%);
  --ok-soft: hsl(142 76% 36% / 0.12);
  --warn: hsl(38 92% 50%);
  --warn-text: hsl(38 92% 50%);
  --warn-soft: hsl(38 92% 50% / 0.12);
  --bad: hsl(0 84% 60%);
  --bad-text: hsl(0 84% 60%);
  --bad-soft: hsl(0 84% 60% / 0.12);
  --info: hsl(217 91% 60%);
  --info-text: hsl(217 91% 60%);
  --info-soft: hsl(217 91% 60% / 0.12);

  /* Glass materials */
  --glass-bg: hsl(0 0% 100% / 0.72);
  --glass-border: hsl(0 0% 100% / 0.3);
  --glass-blur: blur(20px);

  /* Elevation shadows */
  --shadow-1: 0 1px 2px hsl(0 0% 0% / 0.04), 0 1px 3px hsl(0 0% 0% / 0.06);
  --shadow-2: 0 4px 8px hsl(0 0% 0% / 0.05), 0 8px 16px hsl(0 0% 0% / 0.06);
  --shadow-3: 0 8px 24px hsl(0 0% 0% / 0.06), 0 16px 32px hsl(0 0% 0% / 0.08);

  /* Radius */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 18px;
  --radius-full: 9999px;

  /* Spacing scale (4px base) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;

  /* Typography */
  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;

  /* Motion tokens */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1); /* slight overshoot for momentum */

  --duration-instant: 80ms;
  --duration-fast: 120ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;
  --duration-page: 400ms;

  /* Spring configs (Motion/Framer) */
  --spring-critical: 0.4;     /* damping 1.0, response ~0.4s */
  --spring-momentum: 0.3;     /* damping 0.8, response ~0.3s */

  /* Z-index scale */
  --z-base: 1;
  --z-dropdown: 100;
  --z-sticky: 200;
  --z-modal: 300;
  --z-toast: 400;
  --z-tooltip: 500;
}

/* Dark theme — .dark class on <html> (next-themes default) */
.dark {
  --background: hsl(222 47% 6%);
  --foreground: hsl(0 0% 90%);
  --muted: hsl(222 47% 11%);
  --muted-foreground: hsl(215 20% 65%);
  --border: hsl(222 47% 18%);
  --ring: hsl(199 89% 55%);

  --accent: hsl(199 89% 55%);
  --accent-soft: hsl(199 89% 55% / 0.18);
  --accent-dim: hsl(199 89% 55% / 0.12);

  --ok: hsl(142 71% 45%);
  --ok-text: hsl(142 71% 45%);
  --ok-soft: hsl(142 71% 45% / 0.18);
  --warn: hsl(38 92% 55%);
  --warn-text: hsl(38 92% 55%);
  --warn-soft: hsl(38 92% 55% / 0.18);
  --bad: hsl(0 75% 65%);
  --bad-text: hsl(0 75% 65%);
  --bad-soft: hsl(0 75% 65% / 0.18);
  --info: hsl(199 89% 55%);
  --info-text: hsl(199 89% 55%);
  --info-soft: hsl(199 89% 55% / 0.18);

  --glass-bg: hsl(222 47% 8% / 0.72);
  --glass-border: hsl(0 0% 100% / 0.12);

  --shadow-1: 0 1px 2px hsl(0 0% 0% / 0.2), 0 1px 3px hsl(0 0% 0% / 0.3);
  --shadow-2: 0 4px 8px hsl(0 0% 0% / 0.25), 0 8px 16px hsl(0 0% 0% / 0.3);
  --shadow-3: 0 8px 24px hsl(0 0% 0% / 0.3), 0 16px 32px hsl(0 0% 0% / 0.35);
}
```

---

## 3. Typography Scale

```css
:root {
  /* Display — tight leading, negative tracking */
  --text-display: clamp(2.25rem, 4vw, 3.5rem);
  --leading-display: 1.05;
  --tracking-display: -0.02em;

  /* Page title */
  --text-page-title: clamp(1.5rem, 2.5vw, 2rem);
  --leading-page-title: 1.15;
  --tracking-page-title: -0.01em;

  /* Section heading */
  --text-section: 1.125rem;
  --leading-section: 1.3;
  --tracking-section: -0.005em;

  /* Body */
  --text-body: 0.9375rem;    /* 15px */
  --leading-body: 1.6;
  --tracking-body: 0;

  /* Small / UI */
  --text-sm: 0.8125rem;      /* 13px */
  --leading-sm: 1.5;
  --tracking-sm: 0.005em;

  /* Micro */
  --text-xs: 0.6875rem;      /* 11px */
  --leading-xs: 1.45;
  --tracking-xs: 0.02em;

  /* Mono */
  --text-mono: 0.8125rem;
  --leading-mono: 1.55;
  --tracking-mono: 0;
}
```

---

## 4. Motion System

### 4.1 Spring Configurations (for Motion/Framer Motion)

| Interaction | Type | Damping | Response | Use Case |
|-------------|------|---------|----------|----------|
| **Default UI** | `spring` | 1.0 (critically damped) | 0.35s | Modals, panels, dropdowns, tabs, hover lifts |
| **Momentum** | `spring` | 0.8 | 0.3s | Drawer/sheet, flicked cards, scroll-driven reveals |
| **Reposition** | `spring` | 1.0 | 0.4s | Drag-to-reorder, live position updates |
| **Scale press** | `spring` | 1.0 | 0.15s | Button `:active`, card press |
| **Page enter** | `spring` | 1.0 | 0.5s | Initial page mount, route transitions |

### 4.2 CSS Transition Tokens (for non-gesture UI)

```css
:root {
  --transition-instant: transform var(--duration-instant) var(--ease-out),
                        opacity var(--duration-instant) var(--ease-out);
  --transition-fast: transform var(--duration-fast) var(--ease-out),
                     opacity var(--duration-fast) var(--ease-out),
                     background var(--duration-fast) var(--ease-out);
  --transition-normal: transform var(--duration-normal) var(--ease-out),
                       opacity var(--duration-normal) var(--ease-out),
                       background var(--duration-normal) var(--ease-out),
                       border-color var(--duration-normal) var(--ease-out),
                       box-shadow var(--duration-normal) var(--ease-out);
  --transition-slow: transform var(--duration-slow) var(--ease-out),
                     opacity var(--duration-slow) var(--ease-out);
  --transition-page: transform var(--duration-page) var(--ease-out),
                     opacity var(--duration-page) var(--ease-out);
}
```

### 4.3 Entrance/Exit Choreography

**Page Mount (staggered, 60ms per element):**
1. Page header (title + actions) — `opacity 0 → 1`, `translateY(8px) → 0`
2. Primary metric cards — `opacity 0 → 1`, `translateY(12px) → 0`, stagger 60ms
3. Secondary panels — `opacity 0 → 1`, `translateY(16px) → 0`, stagger 80ms
4. Charts/visualizations — `opacity 0 → 1`, `scale(0.98) → 1`, stagger 100ms

**Route Transition:**
- Outgoing page: `opacity 1 → 0`, `translateX(-16px)` (200ms, ease-in-out)
- Incoming page: `opacity 0 → 1`, `translateX(16px) → 0` (300ms, spring)
- Cross-fade overlap: 80ms

**Panel/Section Expand:**
- Height: `spring(damping: 1.0, response: 0.35)`
- Content opacity: cross-fade 150ms (delayed 60ms after height starts)

---

## 5. Component Motion Specifications

### 5.1 Layout Shell

| Component | Enter | Exit | Interaction |
|-----------|-------|------|-------------|
| **Sidebar** | `translateX(-100%) → 0` (spring, 0.4s) | `0 → -100%` (spring, 0.3s) | Mobile: swipe from edge; Desktop: hamburger click |
| **Header** | `translateY(-100%) → 0` (spring, 0.35s) | N/A (sticky) | Glass blur fades in with scroll (0 → 1 over 100px) |
| **Mobile overlay** | `opacity 0 → 1` (150ms) | `1 → 0` (150ms) | Tap outside to dismiss |

### 5.2 Navigation

| Element | Hover | Active (Press) | Focus-visible | Active Route |
|---------|-------|----------------|---------------|--------------|
| **Nav item** | `background: var(--muted)` (120ms) | `scale(0.98)` (spring, 0.15s) | Ring `var(--ring)` | `background: var(--accent-soft)`, text `var(--accent)`, left border 3px `var(--accent)` |
| **Logo/brand** | `opacity 0.8` (120ms) | `scale(0.96)` (spring) | Ring | — |

### 5.3 Data Display

| Component | Mount | Data Update | Hover | Interaction |
|-----------|-------|-------------|-------|-------------|
| **Metric card** | Staggered entrance (see 4.3) | Number: `spring(count)` 800ms; Trend: color cross-fade 300ms | `translateY(-2px)`, `shadow-2` (200ms) | Click → navigate (page transition) |
| **Panel/Card** | `opacity 0→1`, `translateY(12px)→0` (spring, 0.4s) | Content cross-fade 200ms | `shadow-1 → shadow-2` (200ms) | — |
| **Table row** | Stagger 30ms/row (max 200ms total) | Row highlight pulse 800ms | `background: var(--muted)` (100ms) | Click → select (checkbox) |
| **Badge/StatusPill** | `scale(0.8)→1` (spring, 0.25s) | Color cross-fade 300ms | `scale(1.02)` (150ms) | — |
| **StageRail** | Stagger 80ms/stage | Status: icon spin + color cross-fade 400ms | — | Click stage → detail drawer |

### 5.4 Charts & Visualizations

| Component | Mount | Data Refresh | Hover/Interaction |
|-----------|-------|--------------|-------------------|
| **Line/Area chart** | Path `stroke-dashoffset` 800ms spring; Axes fade 400ms | Path morph `spring(damping: 1.0, response: 0.6)` | Tooltip spring from point (120ms); Highlight series (opacity others 0.3) |
| **Bar chart** | Bars `scaleY(0)→1` stagger 40ms (spring) | Bar height spring 500ms | Bar `scaleX(1.04)` 150ms; Tooltip |
| **Network topology** | Nodes `scale(0)→1` stagger 50ms; Edges `stroke-dashoffset` | Node position spring 600ms; Edge reroute | Drag node (1:1); Hover node → highlight connected (150ms) |
| **Gauge/Radial** | Needle rotation spring 1.2s; Arc draw 800ms | Needle spring 500ms | — |

### 5.5 Forms & Controls

| Component | Hover | Active/Press | Focus | Disabled | Error |
|-----------|-------|--------------|-------|----------|-------|
| **Button** | `background: darker 5%` (120ms) | `scale(0.97)` (spring, 0.12s) | Ring `var(--ring)` | `opacity 0.5`, `cursor: not-allowed` | Shake X 3 (100ms each), border `var(--bad)` |
| **Input** | `border: var(--ring)` (120ms) | — | Ring `var(--ring)`, `border: var(--ring)` | `background: var(--muted)` | Border `var(--bad)`, shake on submit |
| **Select/Dropdown** | — | — | Ring | — | — |
| **Switch/Toggle** | Track `background: var(--accent-soft)` | Thumb `scale(0.9)` (spring) | Ring | `opacity 0.5` | — |
| **Checkbox/Radio** | `border: var(--ring)` | `scale(0.9)` (spring) | Ring | `opacity 0.5` | — |

### 5.6 Feedback & Overlays

| Component | Enter | Exit | Dismiss |
|-----------|-------|------|---------|
| **Modal/Dialog** | Backdrop `opacity 0→1` (200ms); Panel `scale(0.96)→1`, `opacity 0→1` (spring, 0.35s) | Reverse (250ms) | Esc, backdrop click, close button |
| **Drawer/Sheet** | `translateX(100%)→0` (spring, 0.35s) | `0→100%` (spring, 0.3s) | Swipe, Esc, backdrop |
| **Toast** | `translateY(100%)→0`, `opacity 0→1` (spring, 0.4s) | `opacity 1→0`, `translateY(-16px)` (200ms) | Auto (5s), swipe, close |
| **Tooltip** | `opacity 0→1`, `scale(0.9)→1` (120ms) | `opacity 1→0`, `scale(0.9)` (100ms) | Pointer leave (100ms delay) |
| **Popover/Menu** | `opacity 0→1`, `scale(0.95)→1` (spring, 0.2s, origin=trigger) | Reverse (150ms) | Outside click, Esc |

### 5.7 Real-time / Live Indicators

| Indicator | Behavior |
|-----------|----------|
| **Live dot (pulse)** | `scale(1)→1.3`, `opacity 1→0` (1500ms, ease-out, infinite) |
| **WebSocket status** | Connected: green dot + pulse; Connecting: amber spin; Disconnected: red dot |
| **Data freshness** | Text updates: brief highlight flash (300ms, `var(--accent-soft)` bg) |
| **MQTT ActivityFeed** | New item: `translateX(-20px)→0`, `opacity 0→1` (spring, 0.4s); Older items push down |

---

## 6. Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  /* Preserve meaning — cross-fade instead of slide */
  .page-enter,
  .page-exit,
  .panel-enter,
  .panel-exit,
  .modal-enter,
  .modal-exit,
  .drawer-enter,
  .drawer-exit,
  .toast-enter,
  .toast-exit {
    animation: none !important;
    transition: opacity 150ms ease !important;
    transform: none !important;
  }

  /* Springs → instant */
  .spring {
    transition: none !important;
  }

  /* Live pulse → static */
  .live-pulse {
    animation: none !important;
    opacity: 1;
    transform: none;
  }
}

@media (prefers-reduced-transparency: reduce) {
  .glass {
    background: var(--background) !important;
    backdrop-filter: none !important;
    border: 1px solid var(--border) !important;
  }
}

@media (prefers-contrast: more) {
  :root {
    --border: hsl(0 0% 60%);
    --ring: hsl(0 0% 20%);
  }
  .dark {
    --border: hsl(0 0% 40%);
    --ring: hsl(0 0% 80%);
  }
  .glass {
    border-width: 2px !important;
  }
  .focus-visible {
    outline: 3px solid var(--ring) !important;
    outline-offset: 2px !important;
  }
}
```

---

## 7. Implementation Architecture

### 7.1 Animation Primitives (React Components)

```
src/components/motion/
├── Spring.tsx           # Motion/Framer spring wrapper with config presets
├── Stagger.tsx          # Staggered children entrance
├── PageTransition.tsx   # Route-level transitions
├── Presence.tsx         # AnimatePresence wrapper with exit animations
├── ReducedMotion.tsx    # Hook + context for prefers-reduced-motion
├── useSpring.ts         # Hook for spring values (drag, scroll)
├── useStagger.ts        # Hook for staggered delays
└── index.ts             # Exports
```

### 7.2 Enhanced UI Components

All existing UI components in `src/components/ui.tsx` get motion enhancements:
- `Button` — press spring, loading spinner
- `Panel/Card` — entrance stagger, hover lift
- `Badge/StatusPill` — mount spring, status change cross-fade
- `Metric` — number count-up spring, trend animation
- `DataRow/Table` — row stagger, hover, selection
- `DropdownMenu` — origin-aware spring from trigger
- `Tooltip` — instant show, delayed hide
- `Skeleton` — shimmer animation

### 7.3 Page-Level Animation

Each page wraps content in `<PageEnter>` for consistent mount choreography.
Route transitions via `<PageTransition>` in `App.tsx`.

---

## 8. Accessibility Checklist

- [ ] All motion respects `prefers-reduced-motion`
- [ ] Focus indicators visible in all themes
- [ ] Color contrast ≥ 4.5:1 (AA) for text, 3:1 for UI
- [ ] Touch targets ≥ 44×44px
- [ ] Keyboard navigation for all interactive elements
- [ ] ARIA labels for icon-only buttons
- [ ] Live regions for dynamic updates (WebSocket data)
- [ ] Skip link for main content
- [ ] No flashing > 3Hz

---

## 9. Performance Budgets

| Metric | Target |
|--------|--------|
| Animation frame time | ≤ 16.67ms (60fps) |
| Interaction to Next Paint (INP) | ≤ 200ms |
| Initial page JS (gzipped) | ≤ 120KB |
| Largest Contentful Paint | ≤ 2.5s |
| Cumulative Layout Shift | ≤ 0.1 |

**GPU-only properties:** `transform`, `opacity`, `filter` (backdrop-filter on glass)
**Avoid animating:** `width`, `height`, `top/left`, `margin`, `padding`, `background-color` (use opacity cross-fade instead)

---

## 10. Token Reference (CSS Variables)

All design tokens are defined as CSS custom properties in `:root` and `.dark`. Components reference tokens via `var(--token-name)` — never hardcode values.

**Naming convention:** `--{category}-{variant}-{state?}`  
Categories: `color`, `space`, `radius`, `shadow`, `font`, `text`, `leading`, `tracking`, `duration`, `ease`, `spring`, `z`

Example: `--color-accent-soft`, `--duration-normal`, `--spring-critical`