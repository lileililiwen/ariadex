# Design: widget-ux-repair

## Decisions

### 1. Toggle order: collapsed → full → strip

`_cycle_display_mode` currently steps through `WIDGET_MODES` in
order, forcing collapsed → strip → full. The toggle-button path
(`_toggle_expanded`) steps collapsed → full → strip instead,
while the strip drag-handle click keeps its strip → full step.
Strip stays reachable and keeps its click-to-expand behavior; it
is simply no longer between the operator and the manual panel.
`_set_display_mode`, geometry, and clamping are untouched.

Traceability: proposal one-click expand; spec toggle requirement.

### 2. One log surface in the expanded view

Today `context_log` (managed-context projection, visible in
collapsed and full) and `status_text` (details-only, includes its
own `activity:` lines per `format_view_text`) overlap. The merged
surface keeps `context_log`'s follow-tail and scrollbar behavior
as the single expanded log; the context projection becomes its
labeled head section and the activity lines its body — no line
appears twice. `Copy log` / `Copy context` both address the
single surface (copy semantics unchanged, sources unified).
Collapsed keeps the latest-line status bar as today.

Traceability: proposal single log; spec log requirement.

### 3. Selector follows theme and layout

`refresh_manual_panel` re-applies the `optionmenu` role to the
button and the `menu` role to the popup on every refresh (not
only at build), so runtime theme switches restyle the open
options too. The button width tracks the longest current option
so names render untruncated. Row order puts the model row where
its popup cannot cover the message textarea (message row keeps
its position and stays fully visible and focusable while the
popup is open). Hub's `build_manual_panel` call site inherits
all three behaviors.

Traceability: proposal selector fix; spec selector requirement.

### 4. Verification strategy

Headless widget tests as the suite does today (fake Tk or
geometry stubs): one-click toggle lands in `full` with manual
refs packed; strip still reachable via its own affordance; merged
log contains no duplicated line across former surfaces; selector
refresh applies both theme roles and keeps the textarea mapped
and unobscured. Existing expand/collapse, copy, and hotkey tests
stay green.

## Unresolved

Exact merged-log section labels are set at implementation; the
spec pins single-surface and no-duplication only.
