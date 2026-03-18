"""
OW Vision v5 — AI Triggerbot + Aim Assist + Counter-Strafe (Overwatch 2)
Run this file → GUI opens → pick settings → press START

Requirements (install once):
    pip install ultralytics torch mss opencv-python numpy pandas keyboard

Place your YOLO .pt model files in the same folder as this script,
or they will be looked for in a "models/" subfolder next to the script.

v5 model: 1 class — enemy (0)
       Only shoots enemies, never allies/friends.
"""

import os
import sys
import math
import time
import random
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_SCRIPT_DIR, "models")

_MODEL_URLS = {
    "v5-ow2.pt": "https://github.com/Jellomakker/aimbotow2/raw/main/ow-vision/models/v5-ow2.pt",
    "v4-valorant.pt": "https://github.com/Jellomakker/aimbotow2/raw/main/ow-vision/models/v4-valorant.pt",
    "v3-roboflow.pt": "https://github.com/Jellomakker/aimbotow2/raw/main/ow-vision/models/v3-roboflow.pt",
}


def _download_model(name, status_cb=None):
    """Download a model from GitHub if available."""
    url = _MODEL_URLS.get(name)
    if not url:
        return None
    os.makedirs(_MODELS_DIR, exist_ok=True)
    dest = os.path.join(_MODELS_DIR, name)
    if os.path.isfile(dest):
        return dest
    if status_cb:
        status_cb(f"Downloading {name}…")
    try:
        import urllib.request
        urllib.request.urlretrieve(url, dest)
        if status_cb:
            status_cb(f"Downloaded {name}")
        return dest
    except Exception as e:
        if status_cb:
            status_cb(f"Download failed: {e}")
        return None


def _model_search_dirs():
    """All directories where .pt models might live."""
    dirs = [_SCRIPT_DIR, _MODELS_DIR]
    # Also check common relative locations
    for sub in ["ow-vision/models", "ow-vision", "..", "../models"]:
        d = os.path.normpath(os.path.join(_SCRIPT_DIR, sub))
        if d not in dirs:
            dirs.append(d)
    # Also check user's Downloads folder
    home = os.path.expanduser("~")
    for sub in ["Downloads", "Desktop", "Documents"]:
        d = os.path.join(home, sub)
        if d not in dirs:
            dirs.append(d)
    return dirs


def _find_models():
    """Return list of .pt files available (local + downloadable)."""
    found = set()
    for d in _model_search_dirs():
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".pt"):
                    found.add(f)
    # Always show downloadable models as options
    for name in _MODEL_URLS:
        found.add(name)
    return sorted(found) if found else ["v2.pt"]


def _resolve_model(name):
    """Return absolute path to a model file."""
    # If it's already a full path (e.g. from file picker), use directly
    if os.path.isabs(name) and os.path.isfile(name):
        return name
    for d in _model_search_dirs():
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return name  # return as-is so error message is clear


# ---------------------------------------------------------------------------
# Real mouse click via Windows SendInput (works in games)
# ---------------------------------------------------------------------------
# ---- Win32 mouse helpers ----
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_INPUT_MOUSE = 0


def _send_mouse_event(flags):
    """Low-level SendInput for mouse flags."""
    if sys.platform != "win32":
        return
    extra = ctypes.POINTER(ctypes.c_ulong)()

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ii", _INPUT),
        ]

    inp = INPUT()
    inp.type = _INPUT_MOUSE
    inp.ii.mi.dwFlags = flags
    inp.ii.mi.dwExtraInfo = extra
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _real_click():
    """Send a single hardware-level left click."""
    if sys.platform != "win32":
        try:
            import pyautogui
            pyautogui.click()
        except Exception:
            pass
        return
    _send_mouse_event(_MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.02)
    _send_mouse_event(_MOUSEEVENTF_LEFTUP)


def _real_mouse_down():
    """Hold left mouse button down."""
    _send_mouse_event(_MOUSEEVENTF_LEFTDOWN)


def _real_mouse_up():
    """Release left mouse button."""
    _send_mouse_event(_MOUSEEVENTF_LEFTUP)



# ---------------------------------------------------------------------------
# Check if player is moving (WASD held)
# ---------------------------------------------------------------------------
def _is_moving():
    """Return True if any movement key is pressed."""
    try:
        import keyboard
        for key in ("w", "a", "s", "d"):
            if keyboard.is_pressed(key):
                return True
    except Exception:
        pass
    return False


def _move_mouse_relative(dx, dy):
    """Move the mouse by (dx, dy) pixels using Win32 SendInput."""
    if sys.platform != "win32":
        return

    MOUSEEVENTF_MOVE = 0x0001
    INPUT_MOUSE = 0

    extra = ctypes.POINTER(ctypes.c_ulong)()

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ii", _INPUT),
        ]

    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.ii.mi.dx = int(dx)
    inp.ii.mi.dy = int(dy)
    inp.ii.mi.dwFlags = MOUSEEVENTF_MOVE
    inp.ii.mi.dwExtraInfo = extra
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# ---------------------------------------------------------------------------
# Counter-strafe via SendInput (game-compatible keyboard input)
# ---------------------------------------------------------------------------
_INPUT_KEYBOARD = 1
_KEYEVENTF_SCANCODE = 0x0008
_KEYEVENTF_KEYUP = 0x0002

# DirectInput scancodes for WASD
_DI_SCAN = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20}
_OPPOSITE = {"w": "s", "s": "w", "a": "d", "d": "a"}


def _send_key(scancode, key_up=False):
    """Send a single key event via SendInput (DirectInput scancode)."""
    if sys.platform != "win32":
        return

    extra = ctypes.POINTER(ctypes.c_ulong)()

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ii", _INPUT),
        ]

    flags = _KEYEVENTF_SCANCODE
    if key_up:
        flags |= _KEYEVENTF_KEYUP

    inp = INPUT()
    inp.type = _INPUT_KEYBOARD
    inp.ii.ki.wVk = 0
    inp.ii.ki.wScan = scancode
    inp.ii.ki.dwFlags = flags
    inp.ii.ki.dwExtraInfo = extra
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _counter_strafe(duration=0.03):
    """Tap opposite movement key briefly to stop momentum before shooting."""
    try:
        import keyboard as kb
        for key, opp in _OPPOSITE.items():
            if kb.is_pressed(key):
                sc = _DI_SCAN.get(opp)
                if sc:
                    _send_key(sc, key_up=False)
                    time.sleep(duration)
                    _send_key(sc, key_up=True)
                return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Detection engine (runs in a background thread)
# ---------------------------------------------------------------------------
class Detection:
    def __init__(self, settings, status_cb=None):
        self.settings = settings
        self.status_cb = status_cb
        self.running = False
        self.triggerbot = settings.get("autoFire", True)
        self.last_click = 0
        self._toggle_cooldown = 0
        self._thread = None
        self._mouse_held = False
        self._last_target_time = 0
        self._counter_strafe = settings.get("counterStrafe", False)
        self._cs_min = settings.get("counterStrafeMin", 0.02)
        self._cs_max = settings.get("counterStrafeMax", 0.05)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _notify(self, txt):
        if self.status_cb:
            self.status_cb(txt)

    def _loop(self):
        # Late imports so the GUI still opens fast even if libs are missing
        try:
            import torch
            from mss import mss
            import cv2
            import numpy as np
            import pandas as pd
            from ultralytics import YOLO
            import keyboard
        except ImportError as e:
            self._notify(f"Missing package: {e.name}  —  pip install {e.name}")
            self.running = False
            return

        s = self.settings
        mw, mh = s["monitorWidth"], s["monitorHeight"]
        sc = s["monitorScale"]

        # Capture a centered region of the screen
        cap_w = int(mw / sc)
        cap_h = int(mh / sc)
        left = int((mw - cap_w) / 2)
        top = int((mh - cap_h) / 2)
        monitor = {"left": left, "top": top, "width": cap_w, "height": cap_h}
        center = [cap_w // 2, cap_h // 2]

        model_path = _resolve_model(s["model"])
        if not os.path.isfile(model_path):
            # Try to auto-download
            downloaded = _download_model(
                os.path.basename(s["model"]),
                status_cb=self._notify,
            )
            if downloaded and os.path.isfile(downloaded):
                model_path = downloaded
            else:
                self._notify(f"Model not found: {s['model']} — use Browse to pick your .pt file")
                self.running = False
                return
        self._notify(f"Loading model {os.path.basename(model_path)}\u2026")
        try:
            model = YOLO(model_path)
        except Exception as e:
            self._notify(f"Model error: {e}")
            self.running = False
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        self._notify(f"Running on {device.upper()} — press {s['toggleKey']} to activate")

        # Depth estimation model (optional)
        depth_pipe = None
        use_depth = s.get("depthEnabled", False)
        if use_depth:
            self._notify("Loading depth model (Depth-Anything-V2)…")
            try:
                from transformers import pipeline as hf_pipeline
                from PIL import Image as PILImage
                _depth_model_id = "depth-anything/Depth-Anything-V2-Small-hf"
                depth_pipe = hf_pipeline("depth-estimation", model=_depth_model_id, device=device)
                self._notify("Depth model loaded!")
            except Exception as e:
                self._notify(f"Depth model failed: {e} — continuing without depth")
                use_depth = False
        depth_map = None
        depth_frame_interval = max(1, int(s.get("depthInterval", 3)))

        show_overlay = True  # always show detection window
        only_still = s.get("onlyWhenStill", False)
        aim_assist = s.get("aimAssist", False)
        aim_strength = s.get("aimStrength", 0.4)
        aim_input_mult = s.get("aimInputMultiplier", 0.5)
        aim_head_pos = s.get("aimHeadPos", 0.10)
        aim_smoothness = s.get("aimSmoothness", 3.0)
        aim_deadzone = s.get("aimDeadzone", 5.0)
        mouse_override = s.get("mouseOverride", 0.5)  # 0=your mouse only, 1=bot only
        _prev_move_x, _prev_move_y = 0.0, 0.0  # for smoothing
        stop_key = s.get("stopKey", "F6")
        trigger_min = s.get("triggerMinDelay", 0.0)
        trigger_max = s.get("triggerMaxDelay", 0.0)
        recoil_enabled = s.get("recoilEnabled", False)
        recoil_min = s.get("recoilMin", 0.5)
        recoil_max = s.get("recoilMax", 2.0)
        fire_mode = s.get("fireMode", "single")  # "single" or "rapid"
        burst_min = int(s.get("burstMin", 3))
        burst_max = int(s.get("burstMax", 7))
        proximity_enabled = s.get("proximityEnabled", False)
        hitbox_pct = s.get("hitboxPct", 100) / 100.0  # 1.0 = full box, 0.5 = center half
        proximity_px = s.get("proximityPx", 30)  # pixels from bbox edge

        frame_count = 0
        fire_count = 0
        last_status_time = 0
        hold_grace = s.get("holdGrace", 0.6)  # seconds to keep holding after losing target

        with mss() as stc:
            while self.running:
                # Global stop hotkey (F6 by default)
                try:
                    if keyboard.is_pressed(stop_key):
                        self._notify("Stopped (hotkey)")
                        break
                except Exception:
                    pass

                closest_dist = 1e9
                closest_idx = -1
                now = time.time()
                frame_count += 1

                shot = np.array(stc.grab(monitor))
                shot = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)

                # --- SAHI-style tiled + multi-zoom detection ---
                fh, fw = shot.shape[:2]
                all_dets = []
                # Always use 640 for inference (better detection even for v5 trained at 416)
                _imgsz = 640
                _pa = dict(save=False, classes=s["detect"], iou=0.45,
                           imgsz=_imgsz, verbose=False, device=device, half=False)

                # Pass 1: full frame at normal confidence
                r1 = model.predict(shot, conf=s["confidence"], **_pa)
                if r1[0].boxes is not None and len(r1[0].boxes):
                    all_dets.extend(r1[0].boxes.data.cpu().numpy().tolist())

                # Pass 2-5: 2x2 overlapping tiles (each ~60% of frame)
                # Small targets appear ~1.7x bigger in each tile
                tile_conf = max(0.08, s["confidence"] - 0.15)
                tw = int(fw * 0.6)
                th = int(fh * 0.6)
                step_x = max(1, (fw - tw) // 1)  # 2 positions: 0 and step_x
                step_y = max(1, (fh - th) // 1)
                for ty in [0, step_y]:
                    for tx in [0, step_x]:
                        tile = shot[ty:ty+th, tx:tx+tw]
                        tile_up = cv2.resize(tile, (fw, fh),
                                             interpolation=cv2.INTER_LINEAR)
                        rt = model.predict(tile_up, conf=tile_conf, **_pa)
                        if rt[0].boxes is not None and len(rt[0].boxes):
                            sx, sy = tw / fw, th / fh
                            for det in rt[0].boxes.data.cpu().numpy().tolist():
                                all_dets.append([
                                    det[0]*sx + tx, det[1]*sy + ty,
                                    det[2]*sx + tx, det[3]*sy + ty,
                                    det[4], det[5]])

                # Pass 6: deep center 4x zoom (very far targets)
                cw4, ch4 = fw // 4, fh // 4
                cx0 = fw // 2 - cw4 // 2
                cy0 = fh // 2 - ch4 // 2
                deep = cv2.resize(shot[cy0:cy0+ch4, cx0:cx0+cw4],
                                  (fw, fh), interpolation=cv2.INTER_LINEAR)
                rd = model.predict(deep, conf=tile_conf, **_pa)
                if rd[0].boxes is not None and len(rd[0].boxes):
                    sx4, sy4 = cw4 / fw, ch4 / fh
                    for det in rd[0].boxes.data.cpu().numpy().tolist():
                        all_dets.append([
                            det[0]*sx4 + cx0, det[1]*sy4 + cy0,
                            det[2]*sx4 + cx0, det[3]*sy4 + cy0,
                            det[4], det[5]])

                # NMS deduplication
                if all_dets:
                    all_dets.sort(key=lambda d: -d[4])
                    keep = []
                    for d in all_dets:
                        dup = False
                        for k in keep:
                            ix1, iy1 = max(d[0],k[0]), max(d[1],k[1])
                            ix2, iy2 = min(d[2],k[2]), min(d[3],k[3])
                            inter = max(0,ix2-ix1)*max(0,iy2-iy1)
                            union = (d[2]-d[0])*(d[3]-d[1])+(k[2]-k[0])*(k[3]-k[1])-inter
                            if union > 0 and inter/union > 0.3:
                                dup = True; break
                        if not dup:
                            keep.append(d)
                    df = pd.DataFrame(keep, columns=["xmin","ymin","xmax","ymax","conf","class"])
                else:
                    df = pd.DataFrame(columns=["xmin","ymin","xmax","ymax","conf","class"])

                # Depth estimation (run every N frames)
                if use_depth and depth_pipe and frame_count % depth_frame_interval == 0:
                    try:
                        from PIL import Image as PILImage
                        pil_img = PILImage.fromarray(cv2.cvtColor(shot, cv2.COLOR_BGR2RGB))
                        depth_result = depth_pipe(pil_img)
                        import numpy as _np
                        depth_map = _np.array(depth_result["depth"], dtype=_np.float32)
                    except Exception:
                        pass

                target_classes = s.get('targetClasses', s['detect'])
                for i, (_, row) in enumerate(df.iterrows()):
                    try:
                        x1, y1, x2, y2 = int(row.xmin), int(row.ymin), int(row.xmax), int(row.ymax)
                        bw = x2 - x1
                        bh = y2 - y1
                        # Filter out tiny detections (noise) and huge ones (background)
                        if bw < 2 or bh < 3 or bw > cap_w * 0.7 or bh > cap_h * 0.85:
                            continue
                        cx = (x2 - x1) / 2 + x1
                        cy = (y2 - y1) / 2 + y1
                        d = math.dist([cx, cy], center)
                        # Depth-weighted scoring: closer targets get priority
                        score = d
                        det_depth = 0.0
                        if use_depth and depth_map is not None:
                            dcx, dcy = int(cx), int(cy)
                            dh, dw = depth_map.shape[:2]
                            if 0 <= dcx < dw and 0 <= dcy < dh:
                                det_depth = depth_map[dcy, dcx] / 255.0
                                # Lower depth = closer = lower score = higher priority
                                score = d * (0.3 + 0.7 * det_depth)
                        is_target = int(row['class']) in target_classes
                        if is_target and score < closest_dist:
                            closest_dist = score
                            closest_idx = i
                        if show_overlay:
                            conf_pct = int(row.conf * 100)
                            # Green for headshot_splash (class 1), blue for enemy (class 0)
                            box_color = (0, 255, 0) if int(row['class']) == 1 else (255, 0, 0)
                            cv2.rectangle(shot, (x1, y1), (x2, y2), box_color, 2)
                            depth_txt = ""
                            if use_depth and depth_map is not None:
                                _dcx, _dcy = int(cx), int(cy)
                                _dh, _dw = depth_map.shape[:2]
                                if 0 <= _dcx < _dw and 0 <= _dcy < _dh:
                                    depth_txt = f" D:{depth_map[_dcy,_dcx]:.0f}"
                            label = f"HS {conf_pct}%" if int(row['class']) == 1 else f"{conf_pct}%"
                            cv2.putText(shot, f"{label}{depth_txt}", (x1, y1 - 5),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                    except Exception:
                        pass

                # Toggle triggerbot hotkey
                try:
                    if keyboard.is_pressed(s["toggleKey"]) and now - self._toggle_cooldown > 0.3:
                        self.triggerbot = not self.triggerbot
                        self._toggle_cooldown = now
                        self._notify("Triggerbot ON" if self.triggerbot else "Triggerbot OFF")
                except Exception:
                    pass

                # Live status update every 0.5s
                n_det = len(df)
                if now - last_status_time > 0.5:
                    last_status_time = now
                    tb = "ON" if self.triggerbot else "OFF"
                    aim_status = ""
                    if closest_idx != -1:
                        r2 = df.iloc[closest_idx]
                        bx1, by1, bx2, by2 = int(r2.xmin), int(r2.ymin), int(r2.xmax), int(r2.ymax)
                        on_target = bx1 <= center[0] <= bx2 and by1 <= center[1] <= by2
                        if on_target:
                            aim_status = " | AIM: ON TARGET"
                        else:
                            aim_status = " | AIM: off target"
                    self._notify(f"TB: {tb} | Det: {n_det} | F: {frame_count} | Shots: {fire_count}{aim_status}")

                if closest_idx != -1:
                    r = df.iloc[closest_idx]
                    x1, y1, x2, y2 = int(r.xmin), int(r.ymin), int(r.xmax), int(r.ymax)
                    target_cx = (x1 + x2) / 2
                    target_cy = (y1 + y2) / 2

                    # Check if v4 model detected a headshot_splash (class 1)
                    # overlapping this enemy — if so, use its bbox as head region
                    hs_box = None
                    if len(df) > 0 and 'class' in df.columns:
                        hs_rows = df[df['class'] == 1]
                        for _, hsr in hs_rows.iterrows():
                            hx1_, hy1_, hx2_, hy2_ = int(hsr.xmin), int(hsr.ymin), int(hsr.xmax), int(hsr.ymax)
                            ox1_ = max(x1, hx1_)
                            oy1_ = max(y1, hy1_)
                            ox2_ = min(x2, hx2_)
                            oy2_ = min(y2, hy2_)
                            if ox1_ < ox2_ and oy1_ < oy2_:
                                hs_box = (hx1_, hy1_, hx2_, hy2_)
                                break

                    # Aim assist — aims at headshot splash if available, else head position
                    if aim_assist:
                        if hs_box:
                            aim_x = (hs_box[0] + hs_box[2]) / 2
                            aim_y = (hs_box[1] + hs_box[3]) / 2
                        else:
                            aim_x = target_cx
                            aim_y = y1 + (y2 - y1) * aim_head_pos  # configurable head position

                        off_x = aim_x - center[0]
                        off_y = aim_y - center[1]
                        dist = math.hypot(off_x, off_y)
                        # Deadzone — don't move if offset is tiny
                        if dist < aim_deadzone:
                            _prev_move_x, _prev_move_y = 0.0, 0.0
                        else:
                            effective_str = aim_strength * aim_input_mult
                            target_mx = off_x * effective_str
                            target_my = off_y * effective_str
                            # Smoothing — lerp toward target (higher = smoother)
                            alpha = 1.0 / aim_smoothness
                            move_x = _prev_move_x + (target_mx - _prev_move_x) * alpha
                            move_y = _prev_move_y + (target_my - _prev_move_y) * alpha
                            _prev_move_x, _prev_move_y = move_x, move_y
                            move_x *= mouse_override
                            move_y *= mouse_override
                            if abs(move_x) > 0.3 or abs(move_y) > 0.3:
                                _move_mouse_relative(move_x, move_y)

                    # Check if crosshair is on or near target
                    pad = 10
                    if hs_box:
                        in_range = ((hs_box[0] - pad) <= center[0] <= (hs_box[2] + pad) and
                                    (hs_box[1] - pad) <= center[1] <= (hs_box[3] + pad))
                    else:
                        # Full bbox fire zone — model already detects enemies only
                        bw = x2 - x1
                        bh = y2 - y1
                        shrink_x = bw * (1.0 - hitbox_pct) / 2
                        shrink_y = bh * (1.0 - hitbox_pct) / 2
                        hx1 = x1 + shrink_x - pad
                        hy1 = y1 + shrink_y - pad
                        hx2 = x2 - shrink_x + pad
                        hy2 = y2 - shrink_y + pad
                        in_range = hx1 <= center[0] <= hx2 and hy1 <= center[1] <= hy2
                    in_proximity = False
                    if proximity_enabled and not in_range:
                        px1 = x1 - proximity_px
                        py1 = y1 - proximity_px
                        px2 = x2 + proximity_px
                        py2 = y2 + proximity_px
                        in_proximity = px1 <= center[0] <= px2 and py1 <= center[1] <= py2

                    should_fire = in_range or in_proximity

                    # Draw fire status on overlay
                    if show_overlay:
                        if should_fire:
                            cv2.putText(shot, "FIRE", (center[0]-20, center[1]-20),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                        elif closest_idx != -1:
                            cv2.putText(shot, "NO FIRE", (center[0]-30, center[1]-20),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)

                    if should_fire and self.triggerbot:
                        self._last_target_time = now

                        if only_still and _is_moving():
                            continue

                        # Counter-strafe: tap opposite key to stop momentum
                        if self._counter_strafe and _is_moving():
                            _counter_strafe(random.uniform(self._cs_min, self._cs_max))

                        if fire_mode == "rapid":
                            # Rapid: hold mouse down the entire time
                            if not self._mouse_held:
                                delay = random.uniform(trigger_min, trigger_max)
                                if delay > 0:
                                    time.sleep(delay)
                                _real_mouse_down()
                                fire_count += 1
                                self._mouse_held = True
                            # Apply horizontal recoil control while holding
                            if recoil_enabled and self._mouse_held:
                                h_recoil = random.uniform(recoil_min, recoil_max) * random.choice([-1, 1])
                                _move_mouse_relative(h_recoil, 0)
                        else:
                            # Single: tap once per cooldown
                            if now - self.last_click > s["cooldown"]:
                                delay = random.uniform(trigger_min, trigger_max)
                                if delay > 0:
                                    time.sleep(delay)
                                _real_click()
                                fire_count += 1
                                self.last_click = now
                                if recoil_enabled:
                                    h_recoil = random.uniform(recoil_min, recoil_max) * random.choice([-1, 1])
                                    _move_mouse_relative(h_recoil, 0)

                    elif not should_fire and self._mouse_held:
                        # Off target but still have detection — use grace period
                        if now - self._last_target_time > hold_grace:
                            _real_mouse_up()
                            self._mouse_held = False

                elif self._mouse_held:
                    # No detection at all — grace period before releasing
                    if now - self._last_target_time > hold_grace:
                        _real_mouse_up()
                        self._mouse_held = False

                # Optional debug overlay window
                if show_overlay:
                    color = (0, 255, 0) if self.triggerbot else (0, 0, 255)
                    cv2.rectangle(shot, (0, 0), (20, 20), color, -1)
                    # Draw fire zone box for closest target
                    if closest_idx != -1:
                        _r = df.iloc[closest_idx]
                        _fx1, _fy1, _fx2, _fy2 = int(_r.xmin), int(_r.ymin), int(_r.xmax), int(_r.ymax)
                        _fbw = _fx2 - _fx1
                        _fbh = _fy2 - _fy1
                        _fsx = _fbw * (1.0 - hitbox_pct) / 2
                        _fsy = _fbh * (1.0 - hitbox_pct) / 2
                        _fpad = 10
                        _fhx1 = int(_fx1 + _fsx - _fpad)
                        _fhy1 = int(_fy1 + _fsy - _fpad)
                        _fhx2 = int(_fx2 - _fsx + _fpad)
                        _fhy2 = int(_fy2 - _fsy + _fpad)
                        cv2.rectangle(shot, (_fhx1, _fhy1), (_fhx2, _fhy2), (0, 255, 255), 1)
                    # Crosshair marker
                    cv2.drawMarker(shot, (center[0], center[1]), (0, 0, 255), cv2.MARKER_CROSS, 10, 1)
                    cv2.putText(shot, "ow-vision v5", (25, 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                    disp = cv2.resize(shot, (384, 216))
                    cv2.imshow("ow-vision", disp)
                    if cv2.waitKey(1) == ord("l"):
                        break

        # Make sure mouse is released when stopping
        if self._mouse_held:
            _real_mouse_up()
            self._mouse_held = False
        if show_overlay:
            cv2.destroyAllWindows()
        self.running = False
        self._notify("Stopped")


# ---------------------------------------------------------------------------
# GUI (tkinter)
# ---------------------------------------------------------------------------
class App(tk.Tk):
    BG = "#0d0d1a"
    BG2 = "#13132b"
    FG = "#e2e2f0"
    ACCENT = "#e94560"
    ACCENT2 = "#ff6b81"
    DIM = "#7a7a9e"
    INPUT_BG = "#111128"
    INPUT_BD = "#2a2a50"
    BTN_GREEN = "#27ae60"

    def __init__(self):
        super().__init__()
        self.title("OW Vision v5")
        self.configure(bg=self.BG)
        self.resizable(False, True)
        self.geometry("440x900")

        self._detection = None
        self._models = _find_models()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Global stop hotkey listener
        self._poll_stop()

    # ── build ──
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=self.BG2, padx=24, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="OW VISION v5", font=("Segoe UI", 20, "bold"),
                 fg=self.ACCENT2, bg=self.BG2).pack(anchor="w")
        tk.Label(hdr, text="AI Triggerbot  •  Enemy-only  •  Counter-strafe  •  Overwatch 2  •  F6 = stop", font=("Segoe UI", 10),
                 fg=self.DIM, bg=self.BG2).pack(anchor="w")

        # Scrollable body
        container = tk.Frame(self, bg=self.BG)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=self.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=self.BG, padx=24, pady=16)
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        body.bind("<Configure>", _on_body_configure)

        def _on_canvas_configure(event):
            canvas.itemconfig(body_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _on_mousewheel_linux(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
        self.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind_all("<Button-4>", _on_mousewheel_linux)
        self.bind_all("<Button-5>", _on_mousewheel_linux)

        # Model selector (dropdown so all models are scrollable)
        self._add_label(body, "MODEL")
        # Default to v5-ow2 if available
        _default_model = "v5-ow2.pt" if "v5-ow2.pt" in self._models else (self._models[-1] if self._models else "")
        self._model_var = tk.StringVar(value=_default_model)
        mf = tk.Frame(body, bg=self.BG)
        mf.pack(fill="x", pady=(0, 12))
        _model_options = self._models if self._models else ["v5-ow2.pt"]
        om = tk.OptionMenu(mf, self._model_var, *_model_options)
        om.config(bg=self.INPUT_BG, fg=self.FG, font=("Segoe UI", 10),
                  activebackground=self.BG2, activeforeground=self.FG,
                  highlightthickness=0, bd=0, relief="flat", width=20)
        om["menu"].config(bg=self.INPUT_BG, fg=self.FG, font=("Segoe UI", 10),
                          activebackground=self.ACCENT, activeforeground="#fff")
        om.pack(side="left", padx=(0, 6))
        tk.Button(
            mf, text="Browse .pt", font=("Segoe UI", 9),
            bg=self.INPUT_BG, fg=self.DIM, bd=0, relief="flat",
            activebackground=self.BG2, activeforeground=self.FG,
            command=self._browse_model,
        ).pack(side="left", padx=(10, 0))

        # Target — individual on/off checkboxes
        self._add_label(body, "TARGET")
        tf = tk.Frame(body, bg=self.BG)
        tf.pack(fill="x", pady=(0, 12))
        self._head_var = tk.BooleanVar(value=True)
        self._body_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            tf, text="Head", variable=self._head_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(side="left", padx=(0, 12))
        tk.Checkbutton(
            tf, text="Body", variable=self._body_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(side="left")

        # Settings row
        row = tk.Frame(body, bg=self.BG)
        row.pack(fill="x", pady=(0, 12))
        row.columnconfigure((0, 1, 2), weight=1)

        # Toggle key
        f1 = tk.Frame(row, bg=self.BG)
        f1.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(f1, "TOGGLE KEY")
        self._key_var = tk.StringVar(value="`")
        self._make_entry(f1, self._key_var)

        # Cooldown
        f2 = tk.Frame(row, bg=self.BG)
        f2.grid(row=0, column=1, sticky="ew", padx=3)
        self._add_label(f2, "COOLDOWN (s)")
        self._cd_var = tk.StringVar(value="0.3")
        self._make_entry(f2, self._cd_var)

        # Confidence
        f3 = tk.Frame(row, bg=self.BG)
        f3.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self._add_label(f3, "CONFIDENCE")
        self._conf_var = tk.StringVar(value="0.25")
        self._make_entry(f3, self._conf_var)

        # Trigger delay row (min / max)
        self._add_label(body, "TRIGGER DELAY (s)")
        row_delay = tk.Frame(body, bg=self.BG)
        row_delay.pack(fill="x", pady=(0, 12))
        row_delay.columnconfigure((0, 1, 2), weight=1)

        fd_min = tk.Frame(row_delay, bg=self.BG)
        fd_min.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fd_min, "MIN")
        self._delay_min_var = tk.StringVar(value="0.0")
        self._make_entry(fd_min, self._delay_min_var)

        fd_max = tk.Frame(row_delay, bg=self.BG)
        fd_max.grid(row=0, column=1, sticky="ew", padx=3)
        self._add_label(fd_max, "MAX")
        self._delay_max_var = tk.StringVar(value="0.05")
        self._make_entry(fd_max, self._delay_max_var)

        fd_sc = tk.Frame(row_delay, bg=self.BG)
        fd_sc.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self._add_label(fd_sc, "SCALE")
        self._sc_var = tk.StringVar(value="1.5")
        self._make_entry(fd_sc, self._sc_var)

        # Resolution row
        row2 = tk.Frame(body, bg=self.BG)
        row2.pack(fill="x", pady=(0, 12))
        row2.columnconfigure((0, 1), weight=1)

        fw = tk.Frame(row2, bg=self.BG)
        fw.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fw, "WIDTH")
        self._w_var = tk.StringVar(value="1920")
        self._make_entry(fw, self._w_var)

        fh = tk.Frame(row2, bg=self.BG)
        fh.grid(row=0, column=1, sticky="ew", padx=3)
        self._add_label(fh, "HEIGHT")
        self._h_var = tk.StringVar(value="1080")
        self._make_entry(fh, self._h_var)

        # Checkboxes row
        chk_frame = tk.Frame(body, bg=self.BG)
        chk_frame.pack(fill="x", pady=(0, 12))

        self._autofire_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            chk_frame, text="Auto-fire on start (no toggle key needed)",
            variable=self._autofire_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        self._still_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            chk_frame, text="Only click when standing still",
            variable=self._still_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        self._overlay_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            chk_frame, text="Show debug overlay window",
            variable=self._overlay_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        # Aim assist section
        self._add_label(body, "AIM ASSIST")
        aim_frame = tk.Frame(body, bg=self.BG)
        aim_frame.pack(fill="x", pady=(0, 4))

        self._aim_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            aim_frame, text="Enable aim assist (always aims at head)",
            variable=self._aim_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        aim_row = tk.Frame(body, bg=self.BG)
        aim_row.pack(fill="x", pady=(0, 12))
        aim_row.columnconfigure((0, 1, 2), weight=1)

        fa_str = tk.Frame(aim_row, bg=self.BG)
        fa_str.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fa_str, "STRENGTH (0.1→1.0)")
        self._aim_str_var = tk.StringVar(value="0.4")
        self._make_entry(fa_str, self._aim_str_var)

        fa_mult = tk.Frame(aim_row, bg=self.BG)
        fa_mult.grid(row=0, column=1, sticky="ew", padx=3)
        self._add_label(fa_mult, "INPUT MULT (0=you, 1=bot)")
        self._aim_mult_var = tk.StringVar(value="0.5")
        self._make_entry(fa_mult, self._aim_mult_var)

        aim_row2 = tk.Frame(body, bg=self.BG)
        aim_row2.pack(fill="x", pady=(0, 12))
        aim_row2.columnconfigure((0,), weight=1)

        fa_override = tk.Frame(aim_row2, bg=self.BG)
        fa_override.grid(row=0, column=0, sticky="ew")
        self._add_label(fa_override, "MOUSE OVERRIDE (0=your mouse, 1=full bot control)")
        self._mouse_override_var = tk.StringVar(value="0.5")
        self._make_entry(fa_override, self._mouse_override_var)

        fa_head = tk.Frame(aim_row, bg=self.BG)
        fa_head.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self._add_label(fa_head, "HEAD POS (0=top, 1=bot)")
        self._aim_head_var = tk.StringVar(value="0.10")
        self._make_entry(fa_head, self._aim_head_var)

        aim_row2 = tk.Frame(body, bg=self.BG)
        aim_row2.pack(fill="x", pady=(0, 12))
        aim_row2.columnconfigure((0, 1), weight=1)

        fa_smooth = tk.Frame(aim_row2, bg=self.BG)
        fa_smooth.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fa_smooth, "SMOOTHNESS (1=instant, 5=smooth, 10=very)")
        self._aim_smooth_var = tk.StringVar(value="3")
        self._make_entry(fa_smooth, self._aim_smooth_var)

        fa_dz = tk.Frame(aim_row2, bg=self.BG)
        fa_dz.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._add_label(fa_dz, "DEADZONE (px, no move if closer)")
        self._aim_dz_var = tk.StringVar(value="5")
        self._make_entry(fa_dz, self._aim_dz_var)

        # Horizontal recoil control
        recoil_frame = tk.Frame(body, bg=self.BG)
        recoil_frame.pack(fill="x", pady=(0, 4))

        self._recoil_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            recoil_frame, text="Horizontal recoil control (counter spray drift)",
            variable=self._recoil_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        recoil_row = tk.Frame(body, bg=self.BG)
        recoil_row.pack(fill="x", pady=(0, 12))
        recoil_row.columnconfigure((0, 1), weight=1)

        fr_min = tk.Frame(recoil_row, bg=self.BG)
        fr_min.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fr_min, "H-RECOIL MIN (px per frame)")
        self._recoil_min_var = tk.StringVar(value="0.5")
        self._make_entry(fr_min, self._recoil_min_var)

        fr_max = tk.Frame(recoil_row, bg=self.BG)
        fr_max.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._add_label(fr_max, "H-RECOIL MAX (px per frame)")
        self._recoil_max_var = tk.StringVar(value="2.0")
        self._make_entry(fr_max, self._recoil_max_var)

        # Fire mode section
        self._add_label(body, "FIRE MODE")
        fire_frame = tk.Frame(body, bg=self.BG)
        fire_frame.pack(fill="x", pady=(0, 4))

        self._fire_mode_var = tk.StringVar(value="single")
        tk.Radiobutton(
            fire_frame, text="Single (tap)", variable=self._fire_mode_var, value="single",
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.ACCENT2,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(side="left", padx=(0, 12))
        tk.Radiobutton(
            fire_frame, text="Rapid (hold & spray)", variable=self._fire_mode_var, value="rapid",
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.ACCENT2,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(side="left")

        # Burst settings for rapid mode
        burst_row = tk.Frame(body, bg=self.BG)
        burst_row.pack(fill="x", pady=(0, 12))
        burst_row.columnconfigure((0, 1), weight=1)

        fb_min = tk.Frame(burst_row, bg=self.BG)
        fb_min.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fb_min, "BURST MIN (shots)")
        self._burst_min_var = tk.StringVar(value="3")
        self._make_entry(fb_min, self._burst_min_var)

        fb_max = tk.Frame(burst_row, bg=self.BG)
        fb_max.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._add_label(fb_max, "BURST MAX (shots)")
        self._burst_max_var = tk.StringVar(value="7")
        self._make_entry(fb_max, self._burst_max_var)

        # Proximity trigger
        prox_frame = tk.Frame(body, bg=self.BG)
        prox_frame.pack(fill="x", pady=(0, 4))

        self._prox_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            prox_frame, text="Proximity fire (shoot when close, not just on target)",
            variable=self._prox_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        prox_row = tk.Frame(body, bg=self.BG)
        prox_row.pack(fill="x", pady=(0, 12))
        prox_row.columnconfigure((0,), weight=1)

        fp_px = tk.Frame(prox_row, bg=self.BG)
        fp_px.grid(row=0, column=0, sticky="ew")
        self._add_label(fp_px, "PROXIMITY DISTANCE (px)")
        self._prox_px_var = tk.StringVar(value="30")
        self._make_entry(fp_px, self._prox_px_var)

        # Hitbox threshold
        hb_row = tk.Frame(body, bg=self.BG)
        hb_row.pack(fill="x", pady=(0, 12))
        hb_row.columnconfigure((0,), weight=1)
        fhb = tk.Frame(hb_row, bg=self.BG)
        fhb.grid(row=0, column=0, sticky="ew")
        self._add_label(fhb, "HITBOX % (100=edge, 50=halfway in, 1=dead center)")
        self._hitbox_var = tk.StringVar(value="100")
        self._make_entry(fhb, self._hitbox_var)

        # Depth estimation
        depth_frame = tk.Frame(body, bg=self.BG)
        depth_frame.pack(fill="x", pady=(0, 4))

        self._depth_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            depth_frame, text="Depth priority (closer targets first — needs GPU)",
            variable=self._depth_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        depth_row = tk.Frame(body, bg=self.BG)
        depth_row.pack(fill="x", pady=(0, 12))
        depth_row.columnconfigure((0,), weight=1)

        fd_int = tk.Frame(depth_row, bg=self.BG)
        fd_int.grid(row=0, column=0, sticky="ew")
        self._add_label(fd_int, "DEPTH EVERY N FRAMES (1=every, 3=default)")
        self._depth_int_var = tk.StringVar(value="3")
        self._make_entry(fd_int, self._depth_int_var)

        # Spray hold setting
        hold_row = tk.Frame(body, bg=self.BG)
        hold_row.pack(fill="x", pady=(0, 12))
        hold_row.columnconfigure((0,), weight=1)

        fh_grace = tk.Frame(hold_row, bg=self.BG)
        fh_grace.grid(row=0, column=0, sticky="ew")
        self._add_label(fh_grace, "SPRAY HOLD (s) — keep firing after target lost")
        self._hold_grace_var = tk.StringVar(value="0.6")
        self._make_entry(fh_grace, self._hold_grace_var)

        # Counter-strafe section
        self._add_label(body, "COUNTER-STRAFE")
        cs_frame = tk.Frame(body, bg=self.BG)
        cs_frame.pack(fill="x", pady=(0, 4))

        self._cs_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            cs_frame, text="Auto counter-strafe before firing (tap opposite key)",
            variable=self._cs_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        cs_row = tk.Frame(body, bg=self.BG)
        cs_row.pack(fill="x", pady=(0, 12))
        cs_row.columnconfigure((0, 1), weight=1)

        fcs_min = tk.Frame(cs_row, bg=self.BG)
        fcs_min.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fcs_min, "TAP MIN (s)")
        self._cs_min_var = tk.StringVar(value="0.02")
        self._make_entry(fcs_min, self._cs_min_var)

        fcs_max = tk.Frame(cs_row, bg=self.BG)
        fcs_max.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._add_label(fcs_max, "TAP MAX (s)")
        self._cs_max_var = tk.StringVar(value="0.05")
        self._make_entry(fcs_max, self._cs_max_var)

        # Start / Stop button
        self._btn = tk.Button(
            body, text="START", font=("Segoe UI", 13, "bold"),
            bg=self.ACCENT, fg="white", activebackground="#c0392b",
            activeforeground="white", bd=0, relief="flat",
            cursor="hand2", padx=10, pady=10,
            command=self._toggle,
        )
        self._btn.pack(fill="x", pady=(4, 0), ipady=2)

        # Status
        self._status_lbl = tk.Label(
            body, text="Ready  —  press START then toggle key (`) in-game • v5",
            font=("Segoe UI", 10), fg=self.DIM, bg=self.BG, wraplength=380,
        )
        self._status_lbl.pack(pady=(10, 0))

    # ── helpers ──
    def _add_label(self, parent, text):
        tk.Label(
            parent, text=text, font=("Segoe UI", 9, "bold"),
            fg=self.DIM, bg=self.BG,
        ).pack(anchor="w", pady=(0, 4))

    def _make_entry(self, parent, var):
        e = tk.Entry(
            parent, textvariable=var, font=("Segoe UI", 11),
            bg=self.INPUT_BG, fg=self.FG, insertbackground=self.FG,
            bd=0, relief="flat", highlightthickness=1,
            highlightbackground=self.INPUT_BD, highlightcolor=self.ACCENT,
        )
        e.pack(fill="x", ipady=4)
        return e

    # ── actions ──
    def _browse_model(self):
        path = filedialog.askopenfilename(
            title="Select YOLO model",
            filetypes=[("YOLO model", "*.pt"), ("All files", "*.*")],
        )
        if path:
            self._model_var.set(path)

    def _toggle(self):
        if self._detection and self._detection.running:
            self._stop()
        else:
            self._start()

    @staticmethod
    def _sf(val, default):
        """Safe float parse — returns default on bad input."""
        try:
            return float(val)
        except (ValueError, TypeError):
            return float(default)

    @staticmethod
    def _si(val, default):
        """Safe int parse — returns default on bad input."""
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return int(default)

    def _start(self):
        # Build detect list from checkboxes
        model_name = self._model_var.get().split("/")[-1].split("\\")[-1]
        if "v5" in model_name.lower():
            # v5 model: enemy only (1 class)
            detect = [0]
            target_classes = [0]
        elif "v4" in model_name.lower():
            # v4 model — always detect both classes; only fire at enemy (0)
            detect = [0, 1]
            target_classes = [0]  # only fire at enemies
        elif model_name == "v3-roboflow.pt":
            # v3 model: single class 0 = player (body+head combined)
            detect = [0]
            target_classes = [0]
        else:
            # Legacy models
            detect = []
            if self._head_var.get():
                detect.append(1)
            if self._body_var.get():
                detect.append(0)
            target_classes = detect[:]
        if not detect:
            messagebox.showwarning("No target", "Turn on at least Head or Body.")
            return

        model_val = self._model_var.get()
        if not model_val:
            messagebox.showwarning("No model", "Select a .pt model file.")
            return

        # If user browsed to a full path, use it directly
        if os.path.isfile(model_val):
            model_key = model_val
        else:
            model_key = model_val

        settings = {
            "model": model_key,
            "detect": detect,
            "toggleKey": self._key_var.get() or "`",
            "cooldown": self._sf(self._cd_var.get(), 0.3),
            "confidence": self._sf(self._conf_var.get(), 0.25),
            "triggerMinDelay": self._sf(self._delay_min_var.get(), 0),
            "triggerMaxDelay": self._sf(self._delay_max_var.get(), 0),
            "monitorWidth": self._si(self._w_var.get(), 1920),
            "monitorHeight": self._si(self._h_var.get(), 1080),
            "monitorScale": self._sf(self._sc_var.get(), 5),
            "onlyWhenStill": self._still_var.get(),
            "showOverlay": self._overlay_var.get(),
            "autoFire": self._autofire_var.get(),
            "aimAssist": self._aim_var.get(),
            "aimStrength": max(0.01, min(1.0, self._sf(self._aim_str_var.get(), 0.4))),
            "aimInputMultiplier": max(0.0, min(1.0, self._sf(self._aim_mult_var.get(), 0.5))),
            "mouseOverride": max(0.0, min(1.0, self._sf(self._mouse_override_var.get(), 0.5))),
            "aimHeadPos": max(0.0, min(1.0, self._sf(self._aim_head_var.get(), 0.10))),
            "aimSmoothness": max(1.0, self._sf(self._aim_smooth_var.get(), 3)),
            "aimDeadzone": max(0.0, self._sf(self._aim_dz_var.get(), 5)),
            "depthEnabled": self._depth_var.get(),
            "depthInterval": self._si(self._depth_int_var.get(), 3),
            "recoilEnabled": self._recoil_var.get(),
            "recoilMin": self._sf(self._recoil_min_var.get(), 0.5),
            "recoilMax": self._sf(self._recoil_max_var.get(), 2.0),
            "fireMode": self._fire_mode_var.get(),
            "burstMin": self._si(self._burst_min_var.get(), 3),
            "burstMax": self._si(self._burst_max_var.get(), 7),
            "proximityEnabled": self._prox_var.get(),
            "hitboxPct": max(1, min(100, self._si(self._hitbox_var.get(), 100))),
            "proximityPx": self._si(self._prox_px_var.get(), 30),
            "holdGrace": self._sf(self._hold_grace_var.get(), 0.6),
            "counterStrafe": self._cs_var.get(),
            "counterStrafeMin": max(0.005, self._sf(self._cs_min_var.get(), 0.02)),
            "counterStrafeMax": max(0.005, self._sf(self._cs_max_var.get(), 0.05)),
            "targetClasses": target_classes,
            "stopKey": "F6",
        }

        self._detection = Detection(settings, status_cb=self._set_status_threadsafe)
        self._detection.start()

        self._btn.configure(text="STOP", bg=self.BTN_GREEN)
        self._set_status("Starting…")

    def _stop(self):
        if self._detection:
            self._detection.stop()
            self._detection = None
        self._btn.configure(text="START", bg=self.ACCENT)
        self._set_status("Stopped")

    def _set_status(self, txt):
        self._status_lbl.configure(text=txt)

    def _set_status_threadsafe(self, txt):
        self.after(0, self._set_status, txt)

    def _poll_stop(self):
        """Check if detection stopped itself (e.g. via F6 hotkey) and update GUI."""
        if self._detection and not self._detection.running:
            self._detection = None
            self._btn.configure(text="START", bg=self.ACCENT)
        self.after(500, self._poll_stop)

    def _on_close(self):
        if self._detection:
            self._detection.stop()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.mainloop()
