"""
Valorant AI Triggerbot — Single-file script
Run this file → GUI opens → pick settings → press START

Requirements (install once):
    pip install ultralytics torch mss opencv-python numpy pandas keyboard

Place your YOLO .pt model files in the same folder as this script,
or they will be looked for in a "models/" subfolder next to the script.

NOTE: The included v1/v2.pt models are trained for Overwatch 2.
      For Valorant you need a Valorant-trained YOLO model.
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
    "v2.pt": "https://github.com/Jellomakker/aimbotow2/raw/main/ow-vision/models/v2.pt",
    "v1.1.pt": "https://github.com/Jellomakker/aimbotow2/raw/main/ow-vision/models/v1.1.pt",
    "v1.pt": "https://github.com/Jellomakker/aimbotow2/raw/main/ow-vision/models/v1.pt",
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
        self._mouse_held = False  # track if we're holding left click (rapid mode)
        self._last_target_time = 0  # last time we saw a valid target (for grace period)

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

        left = int(mw / 2 - mw / sc / 2)
        top = int(mh / 2 - mh / sc / 2)
        w = int(mw / sc)
        h = int(mh / sc)
        monitor = {"left": left, "top": top, "width": w, "height": h}
        center = [w // 2, h // 2]

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

        show_overlay = True  # always show detection window
        only_still = s.get("onlyWhenStill", False)
        aim_assist = s.get("aimAssist", False)
        aim_strength = s.get("aimStrength", 0.4)
        aim_input_mult = s.get("aimInputMultiplier", 0.5)
        stop_key = s.get("stopKey", "F6")
        trigger_min = s.get("triggerMinDelay", 0.0)
        trigger_max = s.get("triggerMaxDelay", 0.0)
        fire_mode = s.get("fireMode", "single")  # "single" or "rapid"
        burst_min = int(s.get("burstMin", 3))
        burst_max = int(s.get("burstMax", 7))
        proximity_enabled = s.get("proximityEnabled", False)
        proximity_px = s.get("proximityPx", 30)  # pixels from bbox edge

        frame_count = 0
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

                results = model.predict(
                    shot,
                    save=False,
                    classes=s["detect"],
                    conf=s["confidence"],
                    verbose=False,
                    device=device,
                    half=False,
                )

                boxes = results[0].boxes
                if boxes is not None and len(boxes):
                    df = pd.DataFrame(
                        boxes.data.cpu().numpy(),
                        columns=["xmin", "ymin", "xmax", "ymax", "conf", "class"],
                    )
                else:
                    df = pd.DataFrame(columns=["xmin", "ymin", "xmax", "ymax", "conf", "class"])

                for i, (_, row) in enumerate(df.iterrows()):
                    try:
                        x1, y1, x2, y2 = int(row.xmin), int(row.ymin), int(row.xmax), int(row.ymax)
                        cx = (x2 - x1) / 2 + x1
                        cy = (y2 - y1) / 2 + y1
                        d = math.dist([cx, cy], center)
                        if d < closest_dist:
                            closest_dist = d
                            closest_idx = i
                        if show_overlay:
                            cv2.rectangle(shot, (x1, y1), (x2, y2), (255, 0, 0), 2)
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
                    self._notify(f"TB: {tb} | Det: {n_det} | F: {frame_count}{aim_status}")

                if closest_idx != -1:
                    r = df.iloc[closest_idx]
                    x1, y1, x2, y2 = int(r.xmin), int(r.ymin), int(r.xmax), int(r.ymax)
                    target_cx = (x1 + x2) / 2
                    target_cy = (y1 + y2) / 2

                    # Aim assist — aims at upper 5th center of body bbox (head area)
                    if aim_assist:
                        aim_x = target_cx
                        aim_y = y1  # very top edge of body box

                        off_x = aim_x - center[0]
                        off_y = aim_y - center[1]
                        effective_str = aim_strength * aim_input_mult
                        move_x = off_x * effective_str
                        move_y = off_y * effective_str
                        if abs(move_x) > 0.5 or abs(move_y) > 0.5:
                            _move_mouse_relative(move_x, move_y)

                    # Check if crosshair is on or near target
                    # Pad bbox by 10px so small head boxes aren't impossible to hit
                    pad = 10
                    in_range = (x1 - pad) <= center[0] <= (x2 + pad) and (y1 - pad) <= center[1] <= (y2 + pad)
                    in_proximity = False
                    if proximity_enabled and not in_range:
                        px1 = x1 - proximity_px
                        py1 = y1 - proximity_px
                        px2 = x2 + proximity_px
                        py2 = y2 + proximity_px
                        in_proximity = px1 <= center[0] <= px2 and py1 <= center[1] <= py2

                    should_fire = in_range or in_proximity

                    if should_fire and self.triggerbot:
                        self._last_target_time = now

                        if only_still and _is_moving():
                            continue

                        if fire_mode == "rapid":
                            # Rapid: hold mouse down the entire time
                            if not self._mouse_held:
                                delay = random.uniform(trigger_min, trigger_max)
                                if delay > 0:
                                    time.sleep(delay)
                                _real_mouse_down()
                                self._mouse_held = True
                            # No cooldown — just keep holding
                        else:
                            # Single: tap once per cooldown
                            if now - self.last_click > s["cooldown"]:
                                delay = random.uniform(trigger_min, trigger_max)
                                if delay > 0:
                                    time.sleep(delay)
                                _real_click()
                                self.last_click = now

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
                    cv2.putText(shot, "valorant-vision", (25, 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                    cv2.imshow("valorant-vision", shot)
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
        self.title("Valorant Vision")
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
        tk.Label(hdr, text="VALORANT VISION", font=("Segoe UI", 20, "bold"),
                 fg=self.ACCENT2, bg=self.BG2).pack(anchor="w")
        tk.Label(hdr, text="AI Triggerbot  •  F6 = stop from anywhere", font=("Segoe UI", 10),
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

        # Model selector
        self._add_label(body, "MODEL")
        self._model_var = tk.StringVar(value=self._models[-1] if self._models else "")
        mf = tk.Frame(body, bg=self.BG)
        mf.pack(fill="x", pady=(0, 12))
        for m in self._models:
            tk.Radiobutton(
                mf, text=m.replace(".pt", ""), variable=self._model_var, value=m,
                bg=self.BG, fg=self.FG, selectcolor=self.BG2,
                activebackground=self.BG, activeforeground=self.ACCENT2,
                font=("Segoe UI", 10), indicatoron=0, padx=14, pady=5,
                bd=0, relief="flat", highlightthickness=0,
            ).pack(side="left", padx=(0, 6))
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
        self._head_var = tk.BooleanVar(value=False)
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
        self._conf_var = tk.StringVar(value="0.35")
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
        self._sc_var = tk.StringVar(value="5")
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
        aim_row.columnconfigure((0, 1), weight=1)

        fa_str = tk.Frame(aim_row, bg=self.BG)
        fa_str.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fa_str, "STRENGTH (0.1→1.0)")
        self._aim_str_var = tk.StringVar(value="0.4")
        self._make_entry(fa_str, self._aim_str_var)

        fa_mult = tk.Frame(aim_row, bg=self.BG)
        fa_mult.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._add_label(fa_mult, "INPUT MULT (0=you, 1=bot)")
        self._aim_mult_var = tk.StringVar(value="0.5")
        self._make_entry(fa_mult, self._aim_mult_var)

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

        # Spray hold setting
        hold_row = tk.Frame(body, bg=self.BG)
        hold_row.pack(fill="x", pady=(0, 12))
        hold_row.columnconfigure((0,), weight=1)

        fh_grace = tk.Frame(hold_row, bg=self.BG)
        fh_grace.grid(row=0, column=0, sticky="ew")
        self._add_label(fh_grace, "SPRAY HOLD (s) — keep firing after target lost")
        self._hold_grace_var = tk.StringVar(value="0.6")
        self._make_entry(fh_grace, self._hold_grace_var)

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
            body, text="Ready  —  press START then toggle key (`) in-game",
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

    def _start(self):
        # Build detect list from checkboxes
        detect = []
        if self._head_var.get():
            detect.append(1)
        if self._body_var.get():
            detect.append(0)
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
            "cooldown": float(self._cd_var.get() or 0.3),
            "confidence": float(self._conf_var.get() or 0.35),
            "triggerMinDelay": float(self._delay_min_var.get() or 0),
            "triggerMaxDelay": float(self._delay_max_var.get() or 0),
            "monitorWidth": int(self._w_var.get() or 1920),
            "monitorHeight": int(self._h_var.get() or 1080),
            "monitorScale": int(self._sc_var.get() or 5),
            "onlyWhenStill": self._still_var.get(),
            "showOverlay": self._overlay_var.get(),
            "autoFire": self._autofire_var.get(),
            "aimAssist": self._aim_var.get(),
            "aimStrength": max(0.01, min(1.0, float(self._aim_str_var.get() or 0.4))),
            "aimInputMultiplier": max(0.0, min(1.0, float(self._aim_mult_var.get() or 0.5))),
            "fireMode": self._fire_mode_var.get(),
            "burstMin": int(self._burst_min_var.get() or 3),
            "burstMax": int(self._burst_max_var.get() or 7),
            "proximityEnabled": self._prox_var.get(),
            "proximityPx": int(self._prox_px_var.get() or 30),
            "holdGrace": float(self._hold_grace_var.get() or 0.6),
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
