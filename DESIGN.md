# AirFed dashboard — design system

## Direction

**Operate.** This is an industrial control room, not a marketing dashboard.
Dense, quiet, and legible at a glance. One restrained accent (amber) marks live
and actionable state. Semantic colors (green / red / blue) are reserved for
health and protocol outcomes, never decoration.

Explicitly rejected: AI-purple gradients, glassmorphism, floating orbs,
oversized hero typography, card-within-card nesting, animated charts that
imply data that does not exist.

## Type

- UI: **Geist Variable** (self-hosted, `@fontsource-variable/geist`).
- Data / identifiers / timestamps: **JetBrains Mono Variable**
  (`@fontsource-variable/jetbrains-mono`), tabular numerals.
- Scale: 11 px labels (uppercase, 0.12em tracking), 12–13 px body, 20–28 px
  metric values. No display type larger than 32 px.

## Color

| Token | Value | Use |
| --- | --- | --- |
| `void` | `#08090a` | app background |
| `panel` | `#0e1012` | surfaces |
| `raise` | `#14171a` | nested rows, inputs |
| `line` | `#23272c` | hairline borders |
| `text` | `#eceef0` | primary text |
| `muted` | `#98a1a9` | secondary text |
| `faint` | `#606a73` | tertiary / metadata |
| `accent` | `#f5a524` | live session, primary action, selection |
| `ok` | `#7bd88f` | confirmed success |
| `warn` | `#e8b04b` | stale / waiting |
| `bad` | `#f07f72` | failed / rejected |

The background is flat `void` with a 1 px graph-paper grid at 3 % opacity. No
large gradients.

## Layout

- Fixed left rail (240 px) with seven destinations and a persistent system
  status footer; content max-width 1440 px.
- Every page opens with a title row and a thin status strip, then a 12-column
  grid. Panels are single-hairline containers, 16–20 px padding, 8 px radius.
- Numbers align right in monospace. Tables are the default for histories.
- Empty, loading, stale, and disconnected states are first-class designs.

## Motion

- 120–180 ms ease-out for state changes; no entrance animation for data.
- A single pulse on the live indicator; no looping decorative motion.
- `prefers-reduced-motion` disables all non-essential transitions.

## Honesty rules

- A stage is `pending` until the coordinator says otherwise; `skipped` and
  `failed` are displayed as such.
- "Single-client round" is surfaced wherever FedAvg would otherwise be implied.
- Every live panel reports its source and freshness. Retained/registry data is
  labelled, not passed off as live.
