---
name: BraggFlow
description: Processing, valley tracking and publication figures for optical fibre sensor data
colors:
  azul-tinta-de-caneta: "#1a4e8a"
  azul-tinta-profunda: "#143d6d"
  azul-tinta-lavada: "#e9f1fa"
  nevoa-de-laboratorio: "#eef1f5"
  superficie: "#ffffff"
  borda: "#e2e7ee"
  borda-firme: "#c9d3e0"
  borda-campo: "#8593a6"
  tinta: "#16212e"
  tinta-apagada: "#5b6779"
  perigo: "#b3261e"
  perigo-fundo: "#fdecea"
  aviso: "#8a5a00"
  aviso-fundo: "#fff4d6"
  aviso-borda: "#f1d58a"
  laranja-referencia: "#e67e22"
typography:
  brand:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 600
  section-label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 700
  panel-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 600
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  card-title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "13px"
    fontWeight: 600
  field-label:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  hint:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  data:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "tnum"
  meta:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, Roboto, sans-serif"
    fontSize: "11.5px"
    fontWeight: 400
rounded:
  key: "4px"
  input: "7px"
  button: "8px"
  row: "9px"
  card: "10px"
  panel: "12px"
  dialog: "14px"
  pill: "99px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.azul-tinta-de-caneta}"
    textColor: "{colors.superficie}"
    rounded: "{rounded.button}"
    padding: "10px 12px"
  button-primary-hover:
    backgroundColor: "{colors.azul-tinta-profunda}"
  button-secondary:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.azul-tinta-de-caneta}"
    rounded: "{rounded.button}"
    padding: "10px 12px"
  button-secondary-hover:
    backgroundColor: "{colors.azul-tinta-lavada}"
  button-dashed:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.azul-tinta-de-caneta}"
    rounded: "{rounded.input}"
    padding: "7px 8px"
  input:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta}"
    rounded: "{rounded.input}"
    padding: "4px 8px"
    height: "30px"
  tab:
    textColor: "{colors.tinta-apagada}"
    rounded: "{rounded.input}"
    padding: "6px 18px"
  tab-active:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.azul-tinta-de-caneta}"
  card:
    backgroundColor: "{colors.superficie}"
    rounded: "{rounded.card}"
    padding: "11px 13px"
  switch-on:
    backgroundColor: "{colors.azul-tinta-de-caneta}"
    rounded: "{rounded.pill}"
    width: "34px"
    height: "19px"
  switch-off:
    backgroundColor: "{colors.borda-firme}"
  status-chip:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.azul-tinta-de-caneta}"
    rounded: "{rounded.pill}"
    padding: "3px 9px"
  status-chip-warn:
    backgroundColor: "{colors.aviso-fundo}"
    textColor: "{colors.aviso}"
  field-error:
    textColor: "{colors.perigo}"
    typography: "{typography.field-label}"
  stale-badge:
    backgroundColor: "{colors.aviso-fundo}"
    textColor: "{colors.aviso}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  key-cap:
    backgroundColor: "{colors.superficie}"
    textColor: "{colors.tinta-apagada}"
    rounded: "{rounded.key}"
  button-icon:
    textColor: "{colors.tinta}"
    rounded: "{rounded.button}"
    size: "32px"
  button-ghost:
    textColor: "{colors.tinta-apagada}"
    rounded: "{rounded.button}"
    padding: "6px 10px"
  readout-state-ok:
    backgroundColor: "{colors.azul-tinta-lavada}"
    textColor: "{colors.azul-tinta-de-caneta}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  readout-state-warn:
    backgroundColor: "{colors.aviso-fundo}"
    textColor: "{colors.aviso}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
---

<!-- Captured from the implementation on 2026-11-03, refreshed after the critique refinement and the visual pass: ruled sidebar, header with the project crumb, drawn icons, status as an instrument readout. -->

# Design System: BraggFlow

## Overview

**Creative North Star: "A Bancada Organizada"** (the tidy bench)

BraggFlow is a working bench for one test at a time. Everything sits where the
work needs it:

- a white sidebar of numbered sections follows the order of the job (files,
  sensors, processing steps). It is one surface divided by hairlines, not a
  stack of boxes;
- the plot takes the rest of the screen;
- the results sit in panels stacked under the plot.

Nothing floats free. Each card has a header that says its state even when it
is closed, and a small blue dot marks every option that differs from the
default.

The mood is soft and orderly. Cool neutrals form the room: a pale blue-grey
ground behind white surfaces, with dark blue-black ink. One pen-ink blue does
every job that needs attention:

- the active tab;
- the primary button;
- a switch that is on;
- the focus ring.

Density is high but calm:

- body text is 13px;
- labels and hints are 12px;
- the sidebar is 350px wide;
- figures are tabular everywhere, so numbers line up.

Long explanations fold into a "Como funciona ›" disclosure, so the hint you
see is one line long. Shortcuts sit where they act, as small key caps.

Icons are drawn in one stroke (24 × 24, 2px, round caps) from a sprite in the
page, never text glyphs. The header reads like a path, **BraggFlow / LMR
demo**, with the project switcher beside the name. The status bar reads like an
instrument: values in ink with their unit in faded ink, and the CSV's state in
a pill at the end.

The character comes from the plots, not the chrome. The plots carry the
domain's own marks:

- the reference wavelength as a dashed orange line;
- the search window as a pale orange band;
- the tracked valley as an orange ring;
- the FWHM as dashed level lines;
- events as dashed vertical lines.

Trouble is never hidden. A refused value is marked at its field, with the
reason under it. A plot that no longer matches the options carries a
"Desatualizado" badge instead of disappearing.

**Key Characteristics:**
- Cool neutral room (Névoa de Laboratório ground, white surfaces) with one blue
  accent.
- Numbered sidebar sections in the order of the work, separated by hairlines,
  each block reporting its own state.
- Soft cards that rest on the ground with a hairline shadow and gently rounded
  corners (10px).
- Plots fill the main area; results stack under the plot.
- Text keeps its case: λ, nm and σ stay λ, nm and σ.
- Errors at the field, stale plots marked, shortcuts visible.
- Drawn icons in one stroke; the status bar as an instrument readout.

## Colors

A restrained, cool palette: neutrals tinted toward blue, one pen-ink accent,
and state colours used only where they carry meaning.

### Primary
- **Azul Tinta de Caneta** (pen-ink blue): the one accent. Used for the active
  tab, primary buttons, switches that are on, links, disclosure summaries and
  focus rings. It also marks changed options (the small dot) and the hover
  outline of rows.
- **Azul Tinta Profunda** (deep pen-ink blue): hover and pressed state of
  primary buttons.
- **Azul Tinta Lavada** (washed pen-ink blue): the tint behind hovered rows,
  selected files and a dropzone being dragged over, and the focus ring of text
  fields.

### Tertiary
- **Laranja Referência** (reference orange): plot annotations only. It marks
  the λ ref line, the search window band, the tracked valley's ring, the point
  in focus on the evolution plot, and the "Marcar no gráfico" button while it
  is armed.

### Neutral
- **Névoa de Laboratório** (laboratory mist): the page ground behind the
  sidebar cards and the main area. It is also the tab track, the dropzone fill
  and the background of disabled fields.
- **Superfície** (surface, white): cards, sidebar, header, plots, tables,
  inputs and dialogs.
- **Borda** (border): hairline borders of cards, tables and the header.
- **Borda Firme** (firm border): secondary button outlines, table header rules,
  the off state of switches, key caps and scrollbar thumbs.
- **Borda de Campo** (field border): the outline of inputs and selects. It
  reaches 3:1 on white, so a field reads as a field.
- **Tinta** (ink): all primary text, section labels, plot font colour and
  headings.
- **Tinta Apagada** (faded ink): labels, hints, inactive tabs, file metadata
  and table headers. It is dark enough for small text on both grounds: 5:1 on
  the Névoa ground and 5.7:1 on white.

### State
- **Perigo** (danger) on **Perigo Fundo** (danger ground). Used for:
  - the error notice;
  - field error messages and the red outline of an invalid field;
  - the status line when a run fails;
  - destructive confirmations ("Confirmar exclusão", "Descartar").
- **Aviso** (warning) on **Aviso Fundo** with **Aviso Borda**. Used for:
  - the "não salvo" badge;
  - the "Desatualizado" badge on plots;
  - status chips that need attention.

### Named Rules
**The One Ink Rule.** Pen-ink blue is the only colour the chrome uses for
emphasis. If something needs to stand out and it is not an error or a warning,
it is blue or it is bold.

**The Orange Is Data Rule.** Reference orange belongs to the plot: what the
evolution follows and where it looked. Never use it for chrome, buttons or
decoration.

## Typography

**Body Font:** Segoe UI Variable Text, with Segoe UI, system-ui, -apple-system
and Roboto as fallbacks.

**Character:** a single system sans for everything. It is the platform's own
voice, legible at small sizes, and the plots use it too (`--font`), so a plot's
labels match the interface around it. Figures are tabular across the whole
page.

### Hierarchy
- **Brand** (700, 16px, line-height 1.15, -0.01em): the BraggFlow wordmark in
  the header and the project dialog. The project name follows in the header at
  15px 600.
- **Title** (600, 14px): the project name in the header; empty-state headings
  go up to 17px.
- **Section label** (700, 15px, ink, sentence case): the numbered step labels
  ("1 Arquivos", "3 Etapas · de cima para baixo"), 22px above and 4px below.
  Sub-section labels and the evolution's group titles are 12px 700 ink.
- **Panel title** (600, 14px): the headers of the panels in the main area
  ("Evolução entre arquivos", "Estatísticas por intervalo").
- **Body** (400, 13px): controls, buttons, status text, and file names (12px
  in lists).
- **Card title** (600, 13px): the block headers in the sidebar ("Limpeza e
  amostragem", "Transmissão").
- **Field label** (400, 12px, faded ink): the label above every input. Field
  error messages use the same size in Perigo.
- **Hint** (400, 12px, line-height 1.4, faded ink): explanations under groups
  of fields.
- **Data** (400, 12px, tabular figures): table cells. Headers are 12px
  semibold faded ink, in the case they are written.
- **Meta** (400, 11.5px): file metadata, badges and key caps. This is the floor
  for any functional text.

### Named Rules
**The One Voice Rule.** One family carries brand, labels, data and plots. Size
and weight make the hierarchy; a second typeface is never needed.

**The Case Is Meaning Rule.** Text keeps the case it was written in. λ, Δλ, σ,
t, nm and s change meaning in capitals. No label, header or summary is ever
transformed to uppercase; hierarchy comes from weight, size and ink.

## Layout

The page is a full-height app shell:

- a 56px header in three columns:
  - left: the wordmark and the project crumb (name and "Projetos");
  - centre: the three tabs as a segmented control;
  - right: the save state, autosave, undo, redo and save;
- under it, a fixed 350px sidebar that scrolls on its own;
- a main area that fills the rest.

Each tab has its own sidebar and main area, and they swap in place.

- **Sidebar.** Numbered sections in the order of the work. Within a section,
  blocks are separated by 1px hairlines with 12–14px of padding, never boxed.
  Block bodies use a two-column grid.
- **Main area.** 14px padding, 10px gaps. A status bar sits on top, the plot
  fills the space, and result panels stack under it. The Espectros main area
  scrolls as a whole, with the spectrum plot at 44vh. The evolution card groups
  its controls into "Acompanhar" and "Mostrar", with the actions right-aligned
  and one primary ("Fazer figura").
- **Responsive.**
  - Below 1100px, the project name narrows and the autosave label hides.
  - Below 1180px, the sidebar narrows to 300px.
  - Below 900px (a narrow window, or 200% zoom on a laptop), the sidebar moves
    above the work area, the page scrolls, and plots keep at least 340px of
    height.

Spacing follows a small scale: 4, 8, 10, 14 and 24px. Groups get the larger
step; controls within a group get the smaller.

### Named Rules
**The Ruled Sidebar Rule.** The sidebar is one surface divided by hairlines.
Boxes, with border, radius and shadow, belong to the panels of the main area.
A box inside the sidebar is a box inside a box.

## Elevation & Depth

Surfaces rest on the ground; they do not float. Cards, plots, status bars and
panels carry a hairline ambient shadow that only separates white from the
Névoa ground. Depth is otherwise tonal: white surfaces on a blue-grey room.
Only overlays are lifted:

- the project dialog, which also blurs and dims the app behind it;
- the leave dialog;
- the error notice fixed under the header;
- dropdown-like panels.

### Shadow Vocabulary
- **Pousada** (`box-shadow: 0 1px 2px rgba(16, 24, 40, .06)`): every card,
  plot frame, status bar, panel, and the active tab pill.
- **Elevada** (`box-shadow: 0 4px 16px rgba(16, 24, 40, .09)`): dialogs, the
  error notice and floating panels.
- **Barra de ação** (`box-shadow: 0 -6px 12px -10px rgba(16, 24, 40, .35)`):
  the sticky action footer of the Séries sidebar.

### Named Rules
**The Rest, Don't Float Rule.** A surface in the flow of the page gets the
Pousada shadow at most. Lift is reserved for things that sit above the page:
dialogs, the error notice and floating panels.

## Shapes

Gently rounded throughout, growing with the size of the surface:

| Element | Radius |
|---|---|
| Key caps | 4px |
| Inputs, tabs, dashed buttons | 7px |
| Buttons and segmented controls | 8px |
| Project rows | 9px |
| Cards and the error notice | 10px |
| Plot frames, panels and the empty state | 12px |
| The project dialog | 14px |
| Switches, status chips, badges and the stale badge | pill |

Borders are 1px hairlines. The dropzone uses a 2px dashed border and "add"
buttons a 1px dashed one, so dashes mean "put something here".

## Components

### Buttons
Soft and orderly: rounded, filled or outlined, never shouting.
- **Shape:** gently rounded (8px).
- **Primary:** filled pen-ink blue with white 13px semibold text, padding
  10px 12px, and the Pousada shadow. One per area: "Processar ▶",
  "Atualizar ▶", "Fazer figura".
- **Hover / Focus:**
  - hover deepens to Azul Tinta Profunda in 150ms;
  - keyboard focus draws a 2px pen-ink outline, 2px offset;
  - disabled buttons drop to 55% opacity.
- **Secondary:** white, firm border, blue text; on hover, the washed tint and a
  blue border. "Descartar" uses the Perigo text colour.
- **Dashed:** white with a 1px dashed firm border and blue 12px semibold text.
  For "+ Adicionar …" and "Aplicar …", anything that adds or copies.
- **Link:** blue text that underlines on hover; also the disclosure summaries
  ("Adicionar arquivos ao projeto ›").
- **File import:** a secondary button with the upload icon that opens the file
  picker, never the browser's native file control.
- **Icon-only:** 32px square, transparent, ink icon at 18px. On hover, the
  washed tint and blue. Used for undo, redo and save in the header; each has an
  `aria-label` and a tooltip with its shortcut.
- **Ghost:** transparent, faded ink, 12.5px semibold, with an icon. Used for
  "Projetos" beside the project name.
- **Icons:** drawn from the page's sprite (`<use href="#i-…">`): play,
  refresh, download, upload, copy, arrow, chevrons, x, plus, check, folder,
  undo, redo, save, layers. They are 16px in buttons, 14px in small buttons
  and 13px in remove buttons. Disclosures use a drawn chevron, rotated when
  closed.

### Chips
- **Status chip:** a white pill with a firm border and blue 11.5px semibold
  text, used for "detalhes" and "Abrir na Figura →".
- **Warning chip:** the same pill in the warning colours.
- **Badge:** "não salvo", an 11.5px bold warning pill.

### Cards / Containers
Only the panels of the main area are cards. The sidebar's blocks are not (see
The Ruled Sidebar Rule).
- **Corner Style:** 10px.
- **Background:** white on the Névoa ground.
- **Shadow Strategy:** Pousada (see Elevation & Depth).
- **Border:** 1px, turning faint blue (`rgba(26, 78, 138, .35)`) when the
  card's step is on.
- **Internal Padding:** 11px 13px.
- **Header:** a 12.5px semibold title, a 12px summary of the card's state on
  the right, and an optional switch. The switch is labelled by the title for
  screen readers.

### Inputs / Fields
- **Style:** white, 1px Borda de Campo, 7px radius, 30px tall, 12.5px text. The
  label sits above in 12px faded ink.
- **Focus:** the border turns blue with a 3px washed-blue ring
  (`0 0 0 3px rgba(26, 78, 138, .14)`).
- **Invalid:** a value the processing would refuse is caught before any
  request:
  - the field takes a Perigo border with a faint red ring
    (`0 0 0 3px rgba(179, 38, 30, .12)`);
  - the reason sits right under it in 12px Perigo ("Use um número ímpar a
    partir de 3.");
  - the status bar names the field;
  - the plot is marked stale.

  The message leaves as soon as the value is fixed.
- **Switches:** 34 × 19px pills. Firm-border grey when off, pen-ink blue when
  on, with a white knob that slides in 180ms. Keyboard focus shows a 3px blue
  ring.

### Navigation
- **Tabs:** a segmented control with ARIA tab semantics.
  - The track is Névoa with a 9px radius and 3px padding.
  - Tabs are 12.5px semibold in faded ink; the active tab is a white pill with
    blue text and the Pousada shadow.
  - The arrow keys move between tabs.
- **Sidebar:** each tab's sidebar is a numbered sequence of section labels and
  cards. Nothing is hidden behind a menu.
- **Project dialog:** a modal dialog that keeps focus inside it. Esc returns to
  the current project.

### Status readout
The status bar of each tab reads like an instrument:

- values in ink 600 with their unit in faded ink ("**9.001** amostras",
  "**900** s", "**648** pontos");
- notes in faded ink ("gravado 2026-03-02 09:30:15");
- the state in a pill at the end.

The pill is pen-ink blue with a check for "CSV salvo", the warning colours for
"CSV ainda não gravado", and neutral for a CSV written earlier. Messages
("Processando…", "Corrija o campo destacado…") replace the readout while they
apply.

### Feedback
- **Error notice:** fixed under the header and centred, Perigo on Perigo Fundo,
  with the Elevada shadow and a close button (Esc also closes it). It is
  announced to screen readers.
- **Stale badge:** a warning pill centred at the top of a plot ("Desatualizado:
  o último processamento falhou"). It stays while the plot shows the last good
  result and leaves on the next success.
- **Key caps:** shortcuts shown where they act (Zoom Z, Medir trecho M, Marcar
  A, Ctrl+S in the project dialog). 11.5px faded ink in a white cap with a
  4px radius.

### Plot annotations (signature)
The plots are where the product's own language lives:

- the reference wavelength is a dashed orange line labelled "λ ref";
- the search window is a pale orange band;
- the tracked valley gets an orange open ring;
- the point in focus on the evolution plot gets the same ring;
- events are coloured dashed vertical lines with their labels on top;
- markers on the series plot are dashed lines, each a new colour.

Interactive modes (marking λ ref, marking events, measuring a stretch) switch
the cursor to a crosshair and arm a button that shows the mode. In Espectros,
← and → step through the spectra in evolution order.

## Do's and Don'ts

### Do:
- **Do** keep pen-ink blue as the only emphasis colour in the chrome. Errors
  and warnings use their own state colours.
- **Do** order sidebar sections as the work happens, numbered, and let every
  card header summarise its own state.
- **Do** give in-flow surfaces the Pousada shadow at most. Keep the Elevada
  shadow for dialogs, the error notice and floating panels.
- **Do** keep orange for what the evolution tracks and where it looked, on the
  plot.
- **Do** use tabular figures for every number, so columns line up.
- **Do** mark a refused value at its field with the reason under it, and badge
  the plot as stale instead of blanking it.

### Don't:
- **Don't** uppercase text that can carry a symbol or unit (The Case Is Meaning
  Rule).
- **Don't** put essential information only in a `title` tooltip. Shortcuts,
  what a mode does, and what a delete keeps must be visible or reachable by
  keyboard.
- **Don't** add a second accent colour to the chrome. New emphasis is blue,
  bold, or a state colour.
- **Don't** set functional text below 11.5px, or labels and hints below 12px.
- **Don't** leave a control without an accessible name. Fields in tables and
  repeated rows get one through `aria-label`.
- **Don't** use text glyphs (▶ × ↶ ⭳ ›) as icons. Draw them from the sprite.
- **Don't** box a block inside the sidebar (The Ruled Sidebar Rule).
