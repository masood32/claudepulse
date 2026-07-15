# Corner-resize the compact floating widget

## Problem

The compact pill (`FloatingWidget._build_compact`, see `floating_widget.py`) is a
fixed-size 160×10px bar (`BAR_W`/`BAR_H` module constants). The user wants to be
able to freely resize it by dragging any of its four corners, the way a normal
window can be resized, without adding visual clutter to the minimal pill design.

## Scope

- Applies **only** to the compact pill view. The expanded panel is unaffected.
- Applies **only** to this session — resized dimensions are never persisted to
  `config.json`. Every app launch starts at the default 160×10 size.

## Design

### Why manual hit-testing

The widget window is created with `overrideredirect(True)` (no title bar, no
OS-drawn border) so it can float borderless and always-on-top. That means there
is no OS-native resize border to rely on — resizing has to be implemented by
hand, same as the existing move-drag (`_drag_start` / `_drag_motion` /
`_drag_end`) is implemented by hand today.

Two alternatives were considered and rejected:
- **Visible corner grip icons** — adds visual clutter to a widget whose whole
  point is a minimal, borderless pill.
- **Native OS resize** (drop `overrideredirect`) — reintroduces a title
  bar/border, breaking the compact aesthetic entirely.

### Corner hit-zone & cursor

On `<Motion>` over the compact canvas, compute distance from the cursor to each
of the four corners. If within a 6px margin of a corner, set the window cursor
to the matching diagonal-resize cursor:
- NW / SE corners → `size_nw_se`
- NE / SW corners → `size_ne_sw`

Outside all four margins, cursor reverts to the default and the canvas behaves
exactly as it does today (click-to-toggle-expand, drag-to-move via
`_bind_drag`).

### Starting a resize vs. a move vs. a click

`<ButtonPress-1>` on the compact canvas checks whether the press point falls in
a corner zone:
- **Inside a corner zone** → begin resize tracking: record which corner,
  the starting mouse position (`x_root`, `y_root`), the starting bar
  width/height, and the starting window position.
- **Outside all corner zones** → existing move-drag / click-to-expand logic
  applies unchanged.

`<B1-Motion>` during a resize recomputes width/height/position live (every
motion event triggers a re-render), using the same 3px motion threshold the
existing move-drag uses to distinguish "was this an actual drag" from "was
this just a click." If the total motion never exceeds the threshold,
`<ButtonRelease-1>` treats it as a plain click and toggles the expanded view —
identical to clicking anywhere else on the bar today.

### Resize math per corner

Let `(sx, sy)` be the mouse position at press, `(sw, sh)` the starting bar
width/height, `(swx, swy)` the starting window position, and `(dx, dy)` the
mouse delta at the current motion event.

| Corner | new width | new height | new window x | new window y |
|--------|-----------|------------|---------------|---------------|
| SE | `sw + dx` | `sh + dy` | `swx` (unchanged) | `swy` (unchanged) |
| NW | `sw - dx` | `sh - dy` | `swx + dx` | `swy + dy` |
| NE | `sw + dx` | `sh - dy` | `swx` (unchanged) | `swy + dy` |
| SW | `sw - dx` | `sh + dy` | `swx + dx` | `swy` (unchanged) |

No user-facing minimum or maximum — resizing is fully unconstrained per the
user's explicit choice. The only floor is an internal `max(1, ...)` clamp on
width/height so Tk never receives a zero or negative canvas size (a crash
guard, not a UX limit).

### Text scaling

The `%` label's font size scales with the bar's current height:

```
font_pt = max(6, round(bar_height * 0.7))
```

At the default height (10px) this yields 7pt — identical to today's hardcoded
`("Segoe UI", 7, "bold")`, so default appearance is unchanged. The floor of
6pt exists purely for legibility at very small heights.

### State

Two new instance attributes on `FloatingWidget`, seeded from the existing
`BAR_W`/`BAR_H` module constants in `__init__`:

```python
self._bar_w = BAR_W
self._bar_h = BAR_H
```

`_build_compact` uses `self._bar_w` / `self._bar_h` instead of the module
constants directly. Nothing is written to `config.json` — this is deliberate
per scope above.

## Testing

- Manual verification: run the widget, drag each of the four corners in both
  directions, confirm the bar grows/shrinks and the window anchors correctly
  (opposite corner stays fixed).
- Confirm a plain click on/near a corner (no drag) still toggles the expanded
  view.
- Confirm cursor changes to a resize cursor only within the 6px corner margins.
- Confirm font size scales visibly as height changes, and matches current
  default (7pt) at the default 10px height.
- Confirm restarting the app resets the bar to 160×10 regardless of how it was
  last resized.
