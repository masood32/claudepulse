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
