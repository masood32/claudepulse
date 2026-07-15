# Corner-Resize Compact Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user resize the compact floating pill (`FloatingWidget._build_compact` in `floating_widget.py`) by dragging any of its four corners, freeform, with no persistence across restarts.

**Architecture:** Add pure, unit-testable helper functions for corner hit-testing, resize math, and font scaling. Wire them into `FloatingWidget` by replacing the compact canvas's existing move-only drag binding with a corner-aware one that either resizes (in a corner zone) or falls back to the existing move/click behavior (elsewhere on the bar). The canvas is resized/redrawn in place during a drag — never destroyed and rebuilt — so its event bindings survive the drag.

**Tech Stack:** Python, Tkinter (existing), pytest (already installed — `pytest 8.2.0` confirmed via `python -m pytest --version`).

## Global Constraints

- Applies only to the compact pill view — the expanded panel (`_build_expanded`) is untouched.
- Resized dimensions are never written to `config.json` — every app launch resets to the default `BAR_W`/`BAR_H` (160×10).
- Corner grab margin: 6px, invisible (no drawn handles).
- Resize is fully unconstrained (no user-facing min/max) except an internal `MIN_DIM = 1` px floor to prevent invalid Tk canvas sizes.
- Font size for the `%` label scales with bar height: `max(6, round(height * 0.7))` — reproduces today's 7pt at the default 10px height.
- Cursor: `size_nw_se` over NW/SE corners, `size_ne_sw` over NE/SW corners, default cursor elsewhere.
- No new runtime dependencies. pytest is a dev-only dependency for the new pure-function tests (not added to `requirements.txt`, which lists runtime deps only).

---

### Task 1: Pure resize/cursor helper functions

**Files:**
- Modify: `floating_widget.py` (add module-level functions near existing `_pct_color`, floating_widget.py:38-41)
- Create: `tests/conftest.py`
- Create: `tests/test_floating_widget_resize.py`

**Interfaces:**
- Produces (consumed by Task 2):
  - `_corner_at(x: int, y: int, w: int, h: int, margin: int = CORNER_MARGIN) -> str | None` — returns `"nw"`, `"ne"`, `"sw"`, `"se"`, or `None`.
  - `_resize_dims(corner: str, sw: int, sh: int, swx: int, swy: int, dx: int, dy: int) -> tuple[int, int, int, int]` — returns `(new_w, new_h, new_x, new_y)`.
  - `_font_pt_for_height(h: int) -> int`.
  - `CORNER_MARGIN = 6`, `MIN_DIM = 1` module constants.
  - `_CORNER_CURSOR: dict[str, str]` mapping corner name to Tk cursor name (`"nw"`/`"se"` → `"size_nw_se"`, `"ne"`/`"sw"` → `"size_ne_sw"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

Create `tests/test_floating_widget_resize.py`:

```python
from floating_widget import _corner_at, _resize_dims, _font_pt_for_height, MIN_DIM


# ── _corner_at ──────────────────────────────────────────────────────────────

def test_corner_at_top_left():
    assert _corner_at(0, 0, 160, 10) == "nw"


def test_corner_at_top_right():
    assert _corner_at(159, 0, 160, 10) == "ne"


def test_corner_at_bottom_left():
    assert _corner_at(0, 9, 160, 10) == "sw"


def test_corner_at_bottom_right():
    assert _corner_at(159, 9, 160, 10) == "se"


def test_corner_at_middle_returns_none():
    assert _corner_at(80, 5, 160, 10) is None


def test_corner_at_respects_margin():
    # 7px from the left edge, with a 6px margin, is outside the zone.
    assert _corner_at(7, 0, 160, 10, margin=6) is None
    # 5px from the left edge is inside the zone.
    assert _corner_at(5, 0, 160, 10, margin=6) == "nw"


# ── _resize_dims ────────────────────────────────────────────────────────────

def test_resize_se_grows_in_place():
    w, h, x, y = _resize_dims("se", sw=160, sh=10, swx=500, swy=800, dx=20, dy=5)
    assert (w, h, x, y) == (180, 15, 500, 800)


def test_resize_se_shrinks_in_place():
    w, h, x, y = _resize_dims("se", sw=160, sh=10, swx=500, swy=800, dx=-20, dy=-4)
    assert (w, h, x, y) == (140, 6, 500, 800)


def test_resize_nw_grows_and_moves_position():
    w, h, x, y = _resize_dims("nw", sw=160, sh=10, swx=500, swy=800, dx=-20, dy=-5)
    assert (w, h, x, y) == (180, 15, 480, 795)


def test_resize_ne_changes_height_and_y_only():
    w, h, x, y = _resize_dims("ne", sw=160, sh=10, swx=500, swy=800, dx=20, dy=-4)
    assert (w, h, x, y) == (180, 14, 500, 796)


def test_resize_sw_changes_width_and_x_only():
    w, h, x, y = _resize_dims("sw", sw=160, sh=10, swx=500, swy=800, dx=-20, dy=5)
    assert (w, h, x, y) == (180, 15, 480, 800)


def test_resize_se_floors_at_min_dim():
    w, h, x, y = _resize_dims("se", sw=160, sh=10, swx=500, swy=800, dx=-1000, dy=-1000)
    assert (w, h, x, y) == (MIN_DIM, MIN_DIM, 500, 800)


def test_resize_nw_keeps_opposite_corner_anchored_past_floor():
    # Dragging NW far past the opposite (SE) corner (positive dx/dy = dragging
    # the top-left corner down-and-right, past center) must not let the
    # window drift beyond where SE actually sits — position follows the
    # clamped width/height, not the raw mouse delta.
    sw, sh, swx, swy = 160, 10, 500, 800
    dx, dy = 1000, 1000
    w, h, x, y = _resize_dims("nw", sw, sh, swx, swy, dx, dy)
    assert (w, h) == (MIN_DIM, MIN_DIM)
    # The SE corner (fixed point) is at swx+sw, swy+sh. The new NW-anchored
    # window's opposite corner (x+w, y+h) must equal that same fixed point.
    assert (x + w, y + h) == (swx + sw, swy + sh)


# ── _font_pt_for_height ──────────────────────────────────────────────────────

def test_font_pt_matches_current_default_at_default_height():
    assert _font_pt_for_height(10) == 7


def test_font_pt_scales_up_with_height():
    assert _font_pt_for_height(20) == 14


def test_font_pt_floors_at_six():
    assert _font_pt_for_height(1) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_floating_widget_resize.py -v`
Expected: FAIL — `ImportError: cannot import name '_corner_at' from 'floating_widget'`

- [ ] **Step 3: Implement the helper functions**

In `floating_widget.py`, add after the existing `_pct_color` function (floating_widget.py:38-41):

```python
CORNER_MARGIN = 6
MIN_DIM       = 1

_CORNER_CURSOR = {
    "nw": "size_nw_se",
    "se": "size_nw_se",
    "ne": "size_ne_sw",
    "sw": "size_ne_sw",
}


def _corner_at(x, y, w, h, margin=CORNER_MARGIN):
    """Which corner ('nw'/'ne'/'sw'/'se') the point (x, y) is within `margin`
    px of, inside a (w, h)-sized canvas. None if not near any corner."""
    near_left   = x <= margin
    near_right  = x >= w - margin
    near_top    = y <= margin
    near_bottom = y >= h - margin
    if near_top and near_left:
        return "nw"
    if near_top and near_right:
        return "ne"
    if near_bottom and near_left:
        return "sw"
    if near_bottom and near_right:
        return "se"
    return None


def _resize_dims(corner, sw, sh, swx, swy, dx, dy):
    """New (width, height, x, y) for dragging `corner` by (dx, dy), starting
    from bar size (sw, sh) at window position (swx, swy). Clamps each
    dimension to MIN_DIM while keeping the corner opposite `corner` fixed in
    place, so the window never drifts once a dimension bottoms out."""
    if corner == "se":
        new_w = max(MIN_DIM, sw + dx)
        new_h = max(MIN_DIM, sh + dy)
        return new_w, new_h, swx, swy
    if corner == "ne":
        new_w = max(MIN_DIM, sw + dx)
        new_h = max(MIN_DIM, sh - dy)
        return new_w, new_h, swx, swy + (sh - new_h)
    if corner == "sw":
        new_w = max(MIN_DIM, sw - dx)
        new_h = max(MIN_DIM, sh + dy)
        return new_w, new_h, swx + (sw - new_w), swy
    if corner == "nw":
        new_w = max(MIN_DIM, sw - dx)
        new_h = max(MIN_DIM, sh - dy)
        return new_w, new_h, swx + (sw - new_w), swy + (sh - new_h)
    raise ValueError(f"unknown corner: {corner!r}")


def _font_pt_for_height(h):
    return max(6, round(h * 0.7))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_floating_widget_resize.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add floating_widget.py tests/conftest.py tests/test_floating_widget_resize.py
git commit -m "feat: add pure corner-resize math and font-scaling helpers"
```

---

### Task 2: Wire corner-resize into the compact widget

**Files:**
- Modify: `floating_widget.py:44-59` (`__init__`)
- Modify: `floating_widget.py:104-135` (`_build_compact`)

**Interfaces:**
- Consumes: `_corner_at`, `_resize_dims`, `_font_pt_for_height`, `_CORNER_CURSOR`, `CORNER_MARGIN`, `MIN_DIM` from Task 1.
- Produces: `FloatingWidget._bar_w`, `FloatingWidget._bar_h` (instance state read by any future compact-view code); no new public interface consumed by other files.

- [ ] **Step 1: Add resize state to `__init__`**

In `floating_widget.py`, in `FloatingWidget.__init__` (floating_widget.py:44-59), replace:

```python
        self.expanded   = False
        self.win        = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x  = 0
        self._win_start_y  = 0
        self._dragging     = False
        self._pos_x        = None   # remembered position
        self._pos_y        = None
```

with:

```python
        self.expanded   = False
        self.win        = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x  = 0
        self._win_start_y  = 0
        self._dragging     = False
        self._pos_x        = None   # remembered position
        self._pos_y        = None

        # Compact-pill corner resize (never persisted — resets every launch)
        self._bar_w             = BAR_W
        self._bar_h             = BAR_H
        self._compact_canvas    = None
        self._resizing          = False
        self._resize_corner     = None
        self._resize_start_dims = (BAR_W, BAR_H)
        self._resize_start_pos  = (0, 0)
```

- [ ] **Step 2: Split `_build_compact` into a redrawable draw step + build step**

In `floating_widget.py`, replace the existing `_build_compact` method (floating_widget.py:104-135):

```python
    def _build_compact(self):
        cfg  = self.get_config()
        data = self.get_data()
        warn = cfg.get("warning_threshold", 70)
        crit = cfg.get("critical_threshold", 85)

        pct = 0
        if data and data.get("session"):
            pct = data["session"]["used_pct"]
        elif data and data.get("weekly"):
            pct = data["weekly"][0]["used_pct"]

        color = _pct_color(pct, warn, crit)

        # Thin rectangular bar
        canvas = tk.Canvas(self.win, width=BAR_W, height=BAR_H,
                           bg="#111111", highlightthickness=0)
        canvas.pack()

        # Track (dark background)
        canvas.create_rectangle(0, 0, BAR_W, BAR_H, fill="#222222", outline="")

        # Filled portion
        fill_w = max(2, int(pct / 100 * BAR_W))
        canvas.create_rectangle(0, 0, fill_w, BAR_H, fill=color, outline="")

        # % label on the right side of the bar
        canvas.create_text(BAR_W - 3, BAR_H // 2, text=f"{pct}%",
                           anchor="e", fill=color,
                           font=("Segoe UI", 7, "bold"))

        self._bind_drag(canvas)
```

with:

```python
    def _build_compact(self):
        canvas = tk.Canvas(self.win, bg="#111111", highlightthickness=0)
        canvas.pack()
        self._compact_canvas = canvas
        self._draw_compact_canvas(canvas)
        self._bind_resizable_drag(canvas)

    def _draw_compact_canvas(self, canvas):
        """(Re)draw the compact bar at its current self._bar_w/self._bar_h.
        Resizes the existing canvas in place rather than recreating it, so
        this is safe to call mid-drag without losing event bindings."""
        cfg  = self.get_config()
        data = self.get_data()
        warn = cfg.get("warning_threshold", 70)
        crit = cfg.get("critical_threshold", 85)

        pct = 0
        if data and data.get("session"):
            pct = data["session"]["used_pct"]
        elif data and data.get("weekly"):
            pct = data["weekly"][0]["used_pct"]

        color = _pct_color(pct, warn, crit)
        w, h = self._bar_w, self._bar_h

        canvas.configure(width=w, height=h)
        canvas.delete("all")

        # Track (dark background)
        canvas.create_rectangle(0, 0, w, h, fill="#222222", outline="")

        # Filled portion
        fill_w = max(2, int(pct / 100 * w))
        canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

        # % label on the right side of the bar
        canvas.create_text(w - 3, h // 2, text=f"{pct}%",
                           anchor="e", fill=color,
                           font=("Segoe UI", _font_pt_for_height(h), "bold"))
```

- [ ] **Step 3: Add corner-aware binding and handlers**

In `floating_widget.py`, in the "Drag" section (floating_widget.py:382-390, right before `_bind_drag`), add:

```python
    def _bind_resizable_drag(self, canvas):
        """Like _bind_drag, but corner zones resize the compact bar instead
        of moving the window. Used only by the compact canvas."""
        canvas.bind("<Motion>",          self._compact_motion)
        canvas.bind("<ButtonPress-1>",   self._compact_press)
        canvas.bind("<B1-Motion>",       self._compact_drag)
        canvas.bind("<ButtonRelease-1>", self._compact_release)
        canvas.bind("<Button-3>",        self._show_menu)

    def _compact_motion(self, e):
        corner = _corner_at(e.x, e.y, self._bar_w, self._bar_h)
        e.widget.configure(cursor=_CORNER_CURSOR.get(corner, ""))

    def _compact_press(self, e):
        self._drag_start_x = e.x_root
        self._drag_start_y = e.y_root
        self._win_start_x  = self._pos_x
        self._win_start_y  = self._pos_y
        self._dragging      = False

        corner = _corner_at(e.x, e.y, self._bar_w, self._bar_h)
        self._resize_corner = corner
        self._resizing       = corner is not None
        if self._resizing:
            self._resize_start_dims = (self._bar_w, self._bar_h)
            self._resize_start_pos  = (self._pos_x, self._pos_y)

    def _compact_drag(self, e):
        dx = e.x_root - self._drag_start_x
        dy = e.y_root - self._drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._dragging = True
        if not self._dragging:
            return

        if self._resizing:
            sw, sh = self._resize_start_dims
            swx, swy = self._resize_start_pos
            self._bar_w, self._bar_h, self._pos_x, self._pos_y = _resize_dims(
                self._resize_corner, sw, sh, swx, swy, dx, dy)
            self._draw_compact_canvas(self._compact_canvas)
            self.win.geometry(
                f"{self._bar_w}x{self._bar_h}+{self._pos_x}+{self._pos_y}")
        else:
            self._pos_x = self._win_start_x + dx
            self._pos_y = self._win_start_y + dy
            self.win.geometry(f"+{self._pos_x}+{self._pos_y}")

    def _compact_release(self, e):
        if not self._dragging:
            self._toggle()
        elif not self._resizing:
            # Moved (not resized) — persist position, same as before.
            cfg = self.get_config()
            cfg["widget_x"] = self._pos_x
            cfg["widget_y"] = self._pos_y
            from config import save_config
            save_config(cfg)
        self._dragging = False
        self._resizing  = False
        self._resize_corner = None
```

- [ ] **Step 4: Manual verification**

Run: `python main.py`

Check each of the following against the compact pill:
1. Hover each of the four corners — cursor changes to a diagonal resize cursor; hovering the middle of the bar shows the normal cursor.
2. Drag the bottom-right (SE) corner outward — bar grows, top-left corner of the window stays fixed.
3. Drag the top-left (NW) corner outward — bar grows, bottom-right corner of the window stays fixed (window position shifts up-left).
4. Drag the NE and SW corners — confirm each only moves one axis of position (NE: y moves, x fixed; SW: x moves, y fixed) while both width and height change.
5. Drag a corner far past the opposite corner — bar shrinks to a minimum visible size and does not disappear, error, or crash.
6. Click a corner without dragging — expanded view toggles open, same as clicking anywhere else on the bar.
7. Resize the bar larger — confirm the `%` text grows proportionally; resize smaller — confirm it shrinks, floored at a legible size.
8. Drag from the middle of the bar (not a corner) — window still moves, unchanged from current behavior.
9. Quit and relaunch the app — compact bar is back to the default 160×10 size regardless of how it was left.

- [ ] **Step 5: Commit**

```bash
git add floating_widget.py
git commit -m "feat: resize compact widget by dragging its corners"
```

---

## Self-Review Notes

- **Spec coverage:** compact-only scope (Task 2 leaves `_build_expanded`/`_bind_drag` untouched), all four corners (Task 1 + 2 handle nw/ne/sw/se), unconstrained resize with crash-only floor (`MIN_DIM = 1`), no persistence (`_bar_w`/`_bar_h` only ever seeded from constants in `__init__`, never read from or written to config), font scaling (`_font_pt_for_height`, wired into `_draw_compact_canvas`), 6px invisible margin (`CORNER_MARGIN`) — all covered.
- **Placeholder scan:** none found.
- **Type/signature consistency:** `_corner_at`, `_resize_dims`, `_font_pt_for_height` signatures match between Task 1's definitions and Task 2's call sites. `self._compact_canvas` set in `_build_compact`, read in `_compact_drag`.
