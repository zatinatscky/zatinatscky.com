# Handoff: IVAN Index Terminal

## Overview
IVAN is a browsable terminal for 22 daily-updated market indexes (crypto, equities, commodities, macro, FX). Users land on a full-screen welcome page, enter a filterable grid/table of indexes, open an index detail view with a 90-day chart, save indexes to a local watchlist, set threshold alerts, and overlay up to 3 indexes on a normalized comparison chart.

## About the Design Files
The files in this bundle are **design references created in HTML** — a working prototype showing intended look and behavior, not production code to copy directly. The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, SwiftUI, etc.) using its established patterns, component library, and data layer. If no environment exists yet, pick the most appropriate framework and implement there. All data in the prototype is deterministically generated mock data — replace with real feeds.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, radii, animation timings and interaction states are all specified below and present in the prototype. Recreate pixel-accurately using the codebase's own primitives.

---

## Screens / Views

### 1. Welcome (full-screen modal page)
**Purpose:** One-question entry gate that conveys "there's a lot of data behind this."

**Layout:** `position:fixed; inset:0`, background `--bg`, content centered, `max-width:920px`, `padding:0 32px`.

- **Background field:** absolutely positioned grid, `inset:20px 40px -60px`, `grid-template-columns:repeat(4,1fr)`, `gap:0 56px`. One row per index: name (left, 11px IBM Plex Mono, `--text-dim`) and 24h change (right, green/red), `padding:9px 0`, `border-bottom:1px solid --hairline`. Container `opacity:.2`, masked with `radial-gradient(115% 78% at 50% 50%, transparent 26%, #000 72%)` intersected with a vertical fade (`transparent → #000 130px → #000 calc(100% - 70px) → transparent`). Slow drift animation: `translateY(18px) → translateY(-46px)`, 26s, `cubic-bezier(.4,0,.6,1)`, infinite alternate.
- **Top chrome:** 9px pulsing accent dot + wordmark `IVAN` (600 10px mono, `.22em`, uppercase) left; `22 indexes · daily · open data` right (500 10px mono, `.2em`, `--text-faint`). Padding `30px 40px`.
- **Eyebrow:** centered `INDEX TERMINAL` (600 9.5px mono, `.24em`) flanked by 1px hairline rules that scale in from the outside (`scaleX(0)→1`, 1.1s, `cubic-bezier(.16,1,.3,1)`, delay .35s).
- **Headline:** `Ready for the bigger picture?` — Newsreader 500, `clamp(46px,7vw,96px)`, `line-height:1.02`, `letter-spacing:-.025em`. "bigger picture" is italic with a highlight bar: `background:linear-gradient(--tone-soft,--tone-soft) 0 66% / 100% .34em no-repeat`. Each word sits in an `overflow:hidden` wrapper and rises in (`translateY(115%) rotate(3deg) → none`, 1s, `cubic-bezier(.16,1,.3,1)`) with staggered delays .45 / .56 / .64 / .72 / .80s.
- **Primary button:** `Yes, I'm ready →`, height 60px, padding `0 40px`, `border-radius:999px`, `background:--accent`, `color:--on-accent`, Archivo 600 16px, `box-shadow:0 18px 44px --shadow`. Hover: `border-radius:18px 18px 18px 6px`, `translateY(-2px)`, padding `0 46px`. Entrance: `opacity 0 / translateY(30px) scale(.94) → none`, .95s, delay 1.05s.
- **Checkbox:** `Don't show again` — 18px square, `border-radius:6px`, hairline border; checked = `--accent` fill with `✓` in `--on-accent`. Writes `ivan_welcome_dismissed=1` to localStorage on enter.
- **Bottom marquee:** all 22 names duplicated, `translateX(0 → -50%)`, 46s linear infinite, 10.5px mono uppercase `--text-faint`, separated by 3px dots; `border-top:1px solid --hairline`.

**Exit → grid transition (the key moment):** on click, center block animates out (`translateY(-28px) scale(.95) blur(5px)`, .38s), chrome and marquee fade (.3s), the background field simultaneously goes `opacity .2 → .9`, drops its mask and scales to `1.14` (.75s `cubic-bezier(.16,1,.3,1)`) — the data "comes forward". The whole overlay then lifts (`opacity → 0, scale 1.05`, .68s, delay .12s) and unmounts at 700ms. The terminal content enters with `translateY(16px) scale(.992) → none` (.8s) and grid cards stagger in (`translateY(26px) scale(.965) → none`, .72s, delay `0.12 + i*0.055s`, capped at i=11).

### 2. Home — index grid / table
**Layout:** fixed left sidebar (248px expanded / 64px collapsed, `transition:margin-left .25s` on content), then a top band and the content area.

**Sidebar (top → bottom):**
- Brand row + collapse toggle.
- Vertical carousel of all 22 indexes rotating every ~2.8s, paused on hover, `height:116px`, `border-left:1px solid --band-line`.
- **`YOURS` section header** — a `<button>` row: label (600 9px mono, `.18em`, uppercase, `--text`), flexible hairline rule, chevron `›` rotating `0deg → 90deg` (.25s `cubic-bezier(.16,1,.3,1)`) when open. Collapsible.
  - **Watchlist:** count label + `ONLY →` link (600 10px mono, `--accent-strong`). Rows: name (11.5px Archivo, ellipsis) over value + 24h change (10.5px mono), `×` remove button, `border-top:1px solid --hairline`, `padding:8px 0`. Empty state: "Tap ☆ on any index to keep it here."
  - **Alerts:** rows with name, condition (`< 25`), status pill (`ARMED` = `--layer`/`--text-faint`, `TRIGGERED` = `--down`/`--bg2`, 600 8.5px mono, `.1em`, `border-radius:999px`, `padding:3px 7px`), `×` remove.
- **`BROWSE` section header** — same collapsible pattern.
  - **Filter by tag:** wrapping chips — `All`, `★ Saved`, then domains, sub-tags and countries, each with a count in 9.5px mono at 65% opacity. Active chip = `--accent` fill; hover = same.
  - **View:** segmented pill (`Cards` / `Table`) inside `--bg2`, `border-radius:999px`, `padding:4px`.
- **`Shortcuts`** (always visible): `/ · search`, `↑↓ · navigate · ⏎ open`, `s · save · w · watchlist · esc · back` — 500 10px mono, `--text-faint`.

**Top band:** triple ticker carousel of the first 3 indexes of the current filter, plus a fixed index counter.

**Header row:** search input (`ref` focusable with `/`), active-filter breadcrumb with clear (`×`), and sort control: `Featured`, `Name`, `24h`, `Range`.

**Grid:** responsive card grid. The **first card is always featured** (`grid-column:span 2`) regardless of filter or sort. Card: `background:--bg2`, `border-radius:24px 24px 24px 6px`, `padding:20px 21px`. Contents: name, tag chips (clickable, they filter and must `stopPropagation`), current value (IBM Plex Mono, large), 24h and range deltas, sparkline. Top-right controls: **☆/★ watchlist toggle** and **+/− compare toggle** — both 24px circles, `border-radius:50%`, `border:1px solid --hairline`; active state fills with `--accent` and `--on-accent`. Keyboard-selected card gets `outline:2px solid --accent; outline-offset:3px`. Hovering a card (but not its tags) shows a cursor-following pill reading `Open index →`.

**Table view:** same data as rows; star and compare buttons live in the last cell.

**Last card:** always a `Request an index` card opening a modal form (name, rationale, email) with a styled confirmation state.

**Compare tray:** slides up from the bottom, holds up to 3 indexes, renders a normalized 90-day overlay chart; fixed `Close` button pinned to the tray's top edge.

**Floating watchlist button** (bottom-right, above the tray): 44px circle, `--accent`, showing `★` when the list is non-empty and `☆` otherwise. On hover the label `Watchlist · N` expands: the label span animates `max-width 0 → 150px`, `opacity 0 → 1`, `margin-left 0 → 9px` (.32s `cubic-bezier(.16,1,.3,1)`). Clicking opens a 308px panel (`--bg2`, `border-radius:24px 24px 4px 24px`, `box-shadow:0 24px 60px --shadow`) listing saved indexes with `Show saved only` (filled) and `Compare saved · N` (outline, shown when ≥2 saved) buttons.

### 3. Index detail
**Layout:** `max-width:1120px`, centered. Back row: `← All indexes` pill + `☆ Save to watchlist` / `★ Saved` pill (filled `--accent` when saved).

- **Chart:** full-width 90-day line, `--accent` stroke 2px, left axis labelled in the index's own units, gridlines, hover crosshair + tooltip (index value, optional comparison value, volume), range selector (`30d / 90d / 1y`).
- **Comparison control** (in the chart legend): an autocomplete, **not** a select. 200px pill input (`height:28px`, `border-radius:999px`, `padding:0 26px 0 12px`, border `--hairline`, `--accent` while open) with placeholder `Add comparison…`, a `×` clear button when a value is set, and a dropdown (262px, `max-height:264px`, `--bg2`, `border-radius:16px 16px 16px 4px`, `box-shadow:0 20px 48px --shadow`, `padding:6px`). Options: `BTC price` plus every other index; each row shows the label left and its domain tag right (500 9px mono, uppercase). Filtering matches label + tag substring. Keyboard: `↑↓` move, `⏎` pick, `Esc` close; hover also sets the highlighted row (`background:--layer`, `border-radius:10px`). **Default is empty — no comparison series.** When a comparison is chosen, a dashed `--text-faint` line renders against a right-hand axis in that series' own units and the tooltip grows to include it.
- **Alert card:** `--bg2`, `border-radius:24px 24px 24px 6px`, `padding:22px 24px`. Title `Alert` + status pill (`ARMED · WAITING` = `--up-soft`/`--up`, `TRIGGERED NOW` = `--down`/`--bg2`). Segmented `Below` / `Above` pill, then a threshold input (42px, mono 600 14px, prefilled with the current value), then `Set alert` / `Update alert` (filled) and a 40px `×` remove button. The active threshold draws on the chart as a 1.5px dashed line with a 150×17 rounded label reading `ALERT < 25` (or `> …`), coloured `--text-dim` when armed and `--down` when triggered.
- **Stats row:** 52w high/low, 90d average, volatility, current volume.
- **Methodology block:** source, cadence, formula description.
- **Related indexes:** up to 3 cards from the same domain at the bottom.

---

## Interactions & Behavior

**Navigation:** welcome → home → detail. Home scroll position is captured on navigating away and restored on return.

**Keyboard (global listener on `window`):**
| Key | Action |
|---|---|
| `/` | focus search (switches to home) |
| `↑` `↓` | move card selection, auto-scrolls if the card is out of view (`scrollTo` with smooth behavior, offset −190px) |
| `⏎` | open selected index |
| `s` | toggle watchlist for the selected/current index |
| `w` | toggle watchlist panel |
| `Esc` | blur input → close comparison dropdown → close watchlist → close request modal → back to home |

Shortcuts are ignored while typing in an input/textarea or with a modifier key held.

**Animation inventory:** `ivpulse` (2.4s dot), `ivwRise`, `ivwUp`, `ivwFade`, `ivwLine`, `ivwMarq`, `ivwDrift`, `ivwSweep`, `ivwLift`, `ivwCenterOut`, `ivwEnter`, `ivwCard`. Standard easings: entrances `cubic-bezier(.16,1,.3,1)`, exits `cubic-bezier(.5,0,.9,.2)`. Corner-morph on primary buttons: `border-radius 999px → 12–18px` over .25–.3s.

## State Management
```
page          'home' | 'detail'          current view
indexId       string                     open index on detail
range         '30d' | '90d' | '1y'
q             string                     search query
cat           'all' | 'saved' | <tag>    active filter
sort          'featured' | 'name' | 'chg' | 'range'
layout        'grid' | 'table'
hover         number | null              chart hover position
compare       string[]  (max 3)          compare tray
collapsed     boolean                    sidebar
yoursOpen     boolean                    sidebar section
browseOpen    boolean                    sidebar section
watch         string[]                   → localStorage 'ivan_watchlist'
watchOpen     boolean
alerts        { [id]: {op:'below'|'above', value:number} } → localStorage 'ivan_alerts'
alertOp       'below' | 'above'          detail form
alertVal      string                     detail form
selIdx        number                     keyboard cursor, -1 = none
cmpWith       'none' | 'btc' | <indexId> detail comparison series
cmpQuery      string                     autocomplete text
cmpOpen       boolean
cmpSel        number                     highlighted autocomplete row
welcomeOpen / welcomeExit / entering     transition orchestration
reqOpen       boolean                    request-an-index modal
```
Persistence: `ivan_welcome_dismissed`, `ivan_watchlist`, `ivan_alerts` in localStorage. In production, watchlist and alerts should sync to an account; the prototype deliberately requires no sign-in.

**Data:** each index has `{ id, name, domain, tags, source, unit, dec, series[], … }`; the app also holds a shared `dates[]`, `vol[]` and `btc[]` series. Real implementation needs a daily time-series endpoint per index plus 24h/range deltas.

## Design Tokens
| Token | Value | Use |
|---|---|---|
| `--bg` | `#EBEBEB` | page background |
| `--bg2` | `#F5F5F5` | cards, panels |
| `--band` / `--band-line` | `#D0D8DF` / rgba tint | tonal bands, dividers |
| `--text` | `#013547` | primary text |
| `--text-dim` | ~62% of `--text` | secondary |
| `--text-faint` | ~42% of `--text` | labels, axes |
| `--accent` | `#DDBA9B` | primary actions |
| `--accent-strong` | darker accent | links |
| `--on-accent` | `#013547` | text on accent |
| `--up` / `--up-soft` | green / tint | positive change |
| `--down` | red-brown | negative change, triggered |
| `--hairline` | 1px low-contrast border | dividers, inputs |
| `--border-s` | stronger 1px border | outline buttons |
| `--layer` | subtle state layer | hover fills |
| `--tone-soft` | soft tone | headline highlight |
| `--shadow` | ambient shadow colour | elevation |

**Radii:** asymmetric `24px 24px 24px 6px` (cards), `28px 28px 6px 28px` (bands), `16px 16px 16px 4px` (dropdown), `999px` (pills), `12px` (inputs), `10px` (list rows).
**Spacing:** 4 / 6 / 8 / 10 / 14 / 16 / 20 / 22 / 24 / 26 / 32 / 40px.
**Shadows:** `0 12px 30px --shadow` (floating button), `0 18px 44px --shadow` (welcome CTA), `0 20px 48px --shadow` (dropdown), `0 24px 60px --shadow` (panel).

**Typography**
- **Newsreader** (serif, 500) — headlines, card/section titles. `letter-spacing:-.015 … -.025em`.
- **Archivo** (500/600) — all UI text, buttons, labels.
- **IBM Plex Mono** (500/600) — every number, axis label, eyebrow, status pill, shortcut legend. Uppercase eyebrows use `.1 – .24em` tracking.

Scale: 9 / 9.5 / 10 / 10.5 / 11 / 11.5 / 12 / 12.5 / 13 / 14 / 16 / 19 / 38 / `clamp(46px,7vw,96px)`.

## Assets
None — no images or icon files. All glyphs are text characters (`★ ☆ × › → ← ✓ ⏎`) and all charts are inline SVG generated from the data. Fonts load from Google Fonts (Newsreader, Archivo, IBM Plex Mono).

## Files
- `IVAN Terminal v5.dc.html` — the complete prototype (markup + logic in one file).
- `support.js` — the prototype runtime that renders the file; **not** part of the design, do not port it.

Open the HTML file directly in a browser to interact with the prototype.
