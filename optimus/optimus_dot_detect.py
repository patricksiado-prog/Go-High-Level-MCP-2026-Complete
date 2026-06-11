#!/usr/bin/env python3
"""
OPTIMUS DOT DETECT v1.0 -- the ONE place dot-color thresholds + dot detection live.
=============================================================================
Both map scanners import from here so the thresholds can never drift apart
again:
  - fiber_precise_pipeline.py  (signal -> ZIP -> capture/click -> exact address)
  - precise_fiber_hunter.py    (grid snake scan, click every dot)

WHY THIS FILE EXISTS (threshold unification):
  precise_fiber_hunter v0.2 detected dots in HSV with OpenCV hue 70-95.
  OpenCV hue is 0-179 (degrees/2), so 70-95 is 140-190 REAL degrees -- that is
  teal/cyan, NOT the vivid green of AT&T's dots.
  fiber_precise_pipeline used an RGB box (30,130,30)-(100,210,80) whose hue is
  roughly 100-140 real degrees (OpenCV 50-70). The two windows barely touch:
  on a screen where the RGB box is right, the HSV window can return 0 dots.
  The pipeline's comment "same thresholds as fiber_hunter -- DO NOT retune"
  was wrong about them being equivalent.

  CANONICAL = the RGB box below. It was confirmed against a live 77070
  session (2026-05-31 screenshots). Tune HERE only, never in the scanners.

Dependencies: numpy, pillow, scipy (no OpenCV needed).
"""

import numpy as np

# ---------------------------------------------------------------------------
# CANONICAL color windows (RGB, inclusive). Confirmed live 77070 2026-05-31.
# ---------------------------------------------------------------------------
GREEN_MIN = (30, 130, 30)
GREEN_MAX = (100, 210, 80)
GOLD_MIN = (220, 160, 0)      # copper-upgrade dots (existing copper customer)
GOLD_MAX = (255, 200, 60)
GRAY_MIN = (150, 150, 150)    # existing fiber customer dots
GRAY_MAX = (205, 205, 205)

# ---------------------------------------------------------------------------
# LEGEND -- confirmed from the map's own on-screen key (west Houston /
# Ashford neighborhood, 2026-06). The dot COLOR is the customer status and
# is more reliable than parsing "Subscriber BAN" out of a popup:
#   GREEN = fiber eligible / non-customer      -> LEAD (door/call)
#   GRAY  = fiber customer (already on fiber)   -> existing customer, SKIP
#   GOLD  = fiber eligible / copper customer    -> UPGRADE target (existing
#           AT&T copper/DSL customer who can move to fiber)
# ---------------------------------------------------------------------------
STATUS_LEAD = "lead"
STATUS_CUSTOMER = "customer"
STATUS_COPPER_UPGRADE = "copper_upgrade"

COLOR_STATUS = {
    "GREEN": STATUS_LEAD,
    "GRAY": STATUS_CUSTOMER,
    "GOLD": STATUS_COPPER_UPGRADE,
}


def classify_status(text=None, ban=None, color=None):
    """Decide LEAD / CUSTOMER / COPPER_UPGRADE for one dot.

    Priority: explicit dot color (the legend) > a status string from the
    backend JSON > BAN presence. Defaults to LEAD only when nothing says
    otherwise.
    """
    if color and color.upper() in COLOR_STATUS:
        return COLOR_STATUS[color.upper()]
    low = (text or "").lower()
    if "copper" in low:
        return STATUS_COPPER_UPGRADE
    if "non-customer" in low or "noncustomer" in low or "eligible" in low:
        return STATUS_LEAD
    if "customer" in low or "subscriber" in low:
        return STATUS_CUSTOMER
    if ban:
        return STATUS_CUSTOMER
    return STATUS_LEAD

# ---------------------------------------------------------------------------
# Shape filters: keep blobs that look like a round map dot, drop terrain
# patches, lines and speckle. (Lifted from fiber_precise_pipeline v0.3.)
# ---------------------------------------------------------------------------
MIN_DOT_PIXELS = 3
MAX_DOT_PIXELS = 800
MAX_DOT_BBOX_AREA = 1500
MIN_DOT_COMPACTNESS = 0.45    # filled px / bbox px
MAX_DOT_ASPECT = 2.5

# ---------------------------------------------------------------------------
# Popup parsing (canonical regexes; address may wrap onto two lines --
# confirmed live, 77070, 2026-05-31 -- so capture to the next field marker
# and collapse whitespace).
# ---------------------------------------------------------------------------
ADDRESS_REGEX = r"Address:\s*(.+?)\s*(?:CREATE\s*REFERRAL|Subscriber\s*BAN|Status:|$)"
STATUS_REGEX = r"Status:\s*(.+?)(?:\s*Subscriber|\s*CREATE|$)"
BAN_REGEX = r"Subscriber\s+BAN:\s*([*\d]+)"
ELIGIBLE_REGEX = r"FIBER\s+ELIGIBLE"
POPUP_READY_HINTS = ["Address:", "Subscriber BAN", "CREATE REFERRAL", "FIBER ELIGIBLE"]


def _is_dot_shape(size, ys, xs):
    if size < MIN_DOT_PIXELS or size > MAX_DOT_PIXELS:
        return False
    h = int(ys.max()) - int(ys.min()) + 1
    w = int(xs.max()) - int(xs.min()) + 1
    if h * w > MAX_DOT_BBOX_AREA:
        return False
    if float(size) / float(h * w) < MIN_DOT_COMPACTNESS:
        return False
    short = max(min(h, w), 1)
    if float(max(h, w)) / float(short) > MAX_DOT_ASPECT:
        return False
    return True


def find_dots_in_array(arr_rgb, cmin=GREEN_MIN, cmax=GREEN_MAX,
                       region=None):
    """Find dot centers in an HxWx3 RGB array.

    region: optional (top, bottom, left, right) pixel bounds to search within
    (e.g. to exclude the search bar). Returned coordinates are in FULL-image
    pixels either way.

    Returns: list of (x, y, blob_size) sorted in reading order.
    """
    from scipy import ndimage

    off_y = off_x = 0
    if region:
        top, bottom, left, right = region
        arr_rgb = arr_rgb[top:bottom, left:right]
        off_y, off_x = top, left

    r, g, b = arr_rgb[:, :, 0], arr_rgb[:, :, 1], arr_rgb[:, :, 2]
    mask = ((r >= cmin[0]) & (r <= cmax[0]) &
            (g >= cmin[1]) & (g <= cmax[1]) &
            (b >= cmin[2]) & (b <= cmax[2]))
    labeled, num = ndimage.label(mask)
    dots = []
    for i in range(1, num + 1):
        ys, xs = np.where(labeled == i)
        if _is_dot_shape(len(ys), ys, xs):
            dots.append((int(xs.mean()) + off_x, int(ys.mean()) + off_y, int(len(ys))))
    dots.sort(key=lambda p: (p[1] // 40, p[0]))  # reading order
    return dots


def find_dots_in_png(path, cmin=GREEN_MIN, cmax=GREEN_MAX, region=None):
    """Same as find_dots_in_array but from a PNG file.

    Returns: (dots, (img_w, img_h)) -- the image dims are needed by callers
    to compute the screenshot-px -> click-px scale (the HiDPI fix).
    """
    from PIL import Image
    try:
        arr = np.array(Image.open(path).convert("RGB"))
    except Exception:
        return [], (0, 0)
    img_h, img_w = arr.shape[0], arr.shape[1]
    return find_dots_in_array(arr, cmin, cmax, region), (img_w, img_h)


def find_dots_in_png_bytes(raw, cmin=GREEN_MIN, cmax=GREEN_MAX, region=None):
    """Same as find_dots_in_png but from in-memory PNG bytes
    (page.screenshot(type='png') without a temp file)."""
    import io
    from PIL import Image
    try:
        arr = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    except Exception:
        return [], (0, 0)
    img_h, img_w = arr.shape[0], arr.shape[1]
    return find_dots_in_array(arr, cmin, cmax, region), (img_w, img_h)
