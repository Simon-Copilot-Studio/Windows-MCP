"""Persistent on-screen indicator shown while an AI agent is controlling the desktop.

Renders a breathing Claude-terracotta glow around every monitor plus a banner
at the top of the primary monitor ("CLAUDE CODE 正在控制桌面") for the whole
duration of tool activity, so the human at the machine always knows whether it
is safe to touch the mouse/keyboard. The overlay lights up on the first tool
call, stays lit while calls are in flight, and fades out after the server has
been idle for ``WINDOWS_MCP_INDICATOR_TIMEOUT`` seconds (default 5).

A global emergency-stop hotkey (Ctrl+Alt+End) is registered while the overlay
is visible: pressing it terminates the MCP server process immediately, which
aborts the controlling agent's tool calls.

The overlay window is excluded from screen capture (WDA_EXCLUDEFROMCAPTURE)
so it never contaminates the agent's own Screenshot/Snapshot results.

Reuses the Win32 layered-window plumbing from desktop.flash_overlay.

Env:
    WINDOWS_MCP_DISABLE_INDICATOR   truthy to disable entirely
    WINDOWS_MCP_INDICATOR_TIMEOUT   idle seconds before hiding (default 5)
"""

import ctypes
import logging
import os
import threading
import time

from fastmcp.server.middleware import Middleware, MiddlewareContext

from windows_mcp.desktop.flash_overlay import (
    _create_layered_window,
    _push_bitmap,
    _user32,
)

logger = logging.getLogger(__name__)

_GLOW_RGB = (0xD9, 0x77, 0x57)  # Claude brand terracotta — matches Claude in Chrome
_BANNER_BG = (24, 24, 24, 235)
_BANNER_TEXT = "CLAUDE CODE 正在控制桌面    Ctrl+Alt+End 強制停止"
_GLOW_THICKNESS = 6
_GLOW_BLUR_RADIUS = 12
_BREATH_PERIOD_S = 3.2
_BREATH_MIN = 0.22
_BREATH_GAMMA = 1.8  # LED-style eased breathing (slow dwell at the dim end)
_FRAME_INTERVAL_S = 0.05
_INTENSITY_QUANT = 24
_HOTKEY_ID = 0xC1AD
_WM_HOTKEY = 0x0312
_MOD_ALT, _MOD_CONTROL, _MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
_VK_END = 0x23
_WDA_EXCLUDEFROMCAPTURE = 0x11
_PM_REMOVE = 0x0001

_lock = threading.Lock()
_active_calls = 0
_last_activity = 0.0
_thread: threading.Thread | None = None


def _disabled() -> bool:
    return os.getenv("WINDOWS_MCP_DISABLE_INDICATOR", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _idle_timeout() -> float:
    try:
        return max(1.0, float(os.getenv("WINDOWS_MCP_INDICATOR_TIMEOUT", "5")))
    except ValueError:
        return 5.0


def notify_begin() -> None:
    """Mark a tool call as started; light the overlay if not already lit."""
    global _active_calls, _last_activity, _thread
    if _disabled():
        return
    with _lock:
        _active_calls += 1
        _last_activity = time.monotonic()
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(
                target=_run_indicator, name="windows-mcp-indicator", daemon=True
            )
            _thread.start()


def notify_end() -> None:
    global _active_calls, _last_activity
    if _disabled():
        return
    with _lock:
        _active_calls = max(0, _active_calls - 1)
        _last_activity = time.monotonic()


class ControlIndicatorMiddleware(Middleware):
    """Lights the desktop-control indicator around every tool call."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        notify_begin()
        try:
            return await call_next(context)
        finally:
            notify_end()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _load_font(size: int):
    from PIL import ImageFont

    for name in ("msjh.ttc", "msjhbd.ttc", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_glow(width: int, height: int, local_rects):
    """Breathing layer: soft terracotta halo along every monitor edge.

    Same look as the Claude-in-Chrome tab glow — a sharp inner ring
    gaussian-blurred into a halo, composited back so the edge stays crisp.
    """
    from PIL import Image, ImageDraw, ImageFilter

    sharp = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sharp)
    color = (*_GLOW_RGB, 255)
    for x1, y1, x2, y2 in local_rects:
        for i in range(_GLOW_THICKNESS):
            draw.rectangle([x1 + i, y1 + i, x2 - 1 - i, y2 - 1 - i], outline=color, width=1)
    blurred = sharp.filter(ImageFilter.GaussianBlur(radius=_GLOW_BLUR_RADIUS))
    return Image.alpha_composite(blurred, sharp)


def _render_banner(width: int, height: int, banner_rect):
    """Static layer: dark pill banner with terracotta dot and white text."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bx, by, bw, bh = banner_rect
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=_BANNER_BG)
    font = _load_font(int(bh * 0.48))
    tb = draw.textbbox((0, 0), _BANNER_TEXT, font=font)
    th = tb[3] - tb[1]
    dot_r = int(bh * 0.18)
    pad = int(bh * 0.42)
    text_x = bx + pad + dot_r * 2 + int(bh * 0.28)
    draw.text((text_x, by + (bh - th) / 2 - tb[1]), _BANNER_TEXT, font=font, fill=(255, 255, 255, 255))
    dot_cx, dot_cy = bx + pad + dot_r, by + bh // 2
    draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
                 fill=(*_GLOW_RGB, 255))
    return img


def _pulsed_bgra(glow_img, banner_img, intensity: float) -> bytes:
    """Premultiplied BGRA: glow layer breathing at ``intensity``, banner constant."""
    import numpy as np

    # uint32: the compositing terms multiply three 8-bit values (~255^3),
    # which overflows uint16 and silently blanks the glow layer.
    glow = np.array(glow_img, dtype=np.uint32)
    glow[:, :, 3] = (glow[:, :, 3] * int(intensity * 255)) // 255

    banner = np.array(banner_img, dtype=np.uint32)
    ba = banner[:, :, 3:4]
    ga = glow[:, :, 3:4]
    out_a = ba + (ga * (255 - ba)) // 255
    safe_a = np.maximum(out_a, 1)
    out_rgb = (banner[:, :, :3] * ba + (glow[:, :, :3] * ga * (255 - ba)) // 255) // safe_a
    # premultiply for UpdateLayeredWindow
    pre = (out_rgb * out_a) // 255
    bgra = np.concatenate([pre[:, :, [2, 1, 0]], out_a], axis=2).astype(np.uint8)
    return bgra.tobytes()


# ---------------------------------------------------------------------------
# Overlay thread
# ---------------------------------------------------------------------------


def _pump_thread_messages() -> bool:
    """Pump window + thread messages. Returns False if emergency stop fired."""
    from ctypes import wintypes

    msg = wintypes.MSG()
    while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_REMOVE):
        if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
            return False
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))
    return True


def _breath_intensity(now: float) -> float:
    """LED-style breathing curve: eased cosine with a dwell at the dim end."""
    import math

    phase = (now % _BREATH_PERIOD_S) / _BREATH_PERIOD_S
    wave = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)  # 0→1→0, smooth
    return _BREATH_MIN + (1 - _BREATH_MIN) * (wave**_BREATH_GAMMA)


def _should_stay_visible() -> bool:
    with _lock:
        return _active_calls > 0 or (time.monotonic() - _last_activity) < _idle_timeout()


def _run_indicator() -> None:
    hwnd = None
    h_instance = None
    hotkey_ok = False
    class_name = f"WindowsMCPIndicator_{threading.get_ident():x}"
    try:
        import windows_mcp.uia as uia

        monitors = uia.GetMonitorsRect()
        rects = [(m.left, m.top, m.right, m.bottom) for m in monitors]
        if not rects:
            return
        union_left = min(r[0] for r in rects)
        union_top = min(r[1] for r in rects)
        width = max(r[2] for r in rects) - union_left
        height = max(r[3] for r in rects) - union_top
        local_rects = [
            (l - union_left, t - union_top, r - union_left, b - union_top)
            for l, t, r, b in rects
        ]
        # Banner goes top-center of the primary monitor (contains virtual origin).
        primary = next((r for r in rects if r[0] <= 0 <= r[2] and r[1] <= 0 <= r[3]), rects[0])
        bh = 46
        bw = 620
        bx = primary[0] - union_left + ((primary[2] - primary[0]) - bw) // 2
        by = primary[1] - union_top + 10
        glow = _render_glow(width, height, local_rects)
        banner = _render_banner(width, height, (bx, by, bw, bh))

        hwnd, h_instance = _create_layered_window(class_name, union_left, union_top, width, height)
        capturable = os.getenv("WINDOWS_MCP_INDICATOR_CAPTURABLE", "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if not capturable:
            try:
                _user32.SetWindowDisplayAffinity(hwnd, _WDA_EXCLUDEFROMCAPTURE)
            except Exception:
                pass
        _user32.ShowWindow(hwnd, 8)  # SW_SHOWNA
        hotkey_ok = bool(
            _user32.RegisterHotKey(None, _HOTKEY_ID, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, _VK_END)
        )
        logger.info("control indicator shown (%dx%d, hotkey=%s)", width, height, hotkey_ok)

        last_q = -1
        while _should_stay_visible():
            if not _pump_thread_messages():
                logger.warning("emergency stop hotkey pressed — terminating server")
                os._exit(43)
            intensity = _breath_intensity(time.monotonic())
            q = round(intensity * _INTENSITY_QUANT)
            if q != last_q:
                _push_bitmap(hwnd, union_left, union_top, width, height, _pulsed_bgra(glow, banner, intensity))
                last_q = q
            time.sleep(_FRAME_INTERVAL_S)
    except Exception:
        logger.debug("control indicator failed", exc_info=True)
    finally:
        try:
            if hotkey_ok:
                _user32.UnregisterHotKey(None, _HOTKEY_ID)
        except Exception:
            pass
        try:
            if hwnd:
                _user32.DestroyWindow(hwnd)
        except Exception:
            pass
        try:
            if h_instance:
                _user32.UnregisterClassW(class_name, h_instance)
        except Exception:
            pass
        logger.info("control indicator hidden")
