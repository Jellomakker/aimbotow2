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
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_SCRIPT_DIR, "models")


def _find_models():
    """Return list of .pt files available."""
    dirs = [_SCRIPT_DIR, _MODELS_DIR]
    found = set()
    for d in dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".pt"):
                    found.add(f)
    return sorted(found) if found else ["v2.pt"]


def _resolve_model(name):
    """Return absolute path to a model file."""
    # If it's already a full path (e.g. from file picker), use directly
    if os.path.isabs(name) and os.path.isfile(name):
        return name
    for d in [_SCRIPT_DIR, _MODELS_DIR]:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return os.path.join(_MODELS_DIR, name)


# ---------------------------------------------------------------------------
# Real mouse click via Windows SendInput (works in games)
# ---------------------------------------------------------------------------
def _real_click():
    """Send a hardware-level left mouse click using Win32 SendInput."""
    if sys.platform != "win32":
        # Fallback for non-Windows (won't work in games but won't crash)
        try:
            import pyautogui
            pyautogui.click()
        except Exception:
            pass
        return

    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    INPUT_MOUSE = 0

    # MOUSEINPUT struct: dx, dy, mouseData, dwFlags, time, dwExtraInfo
    # INPUT struct: type, union(MOUSEINPUT)
    # On 64-bit Windows, INPUT is 40 bytes
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

    def _send(flags):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.ii.mi.dwFlags = flags
        inp.ii.mi.dwExtraInfo = extra
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    _send(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.02)
    _send(MOUSEEVENTF_LEFTUP)


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


# ---------------------------------------------------------------------------
# Detection engine (runs in a background thread)
# ---------------------------------------------------------------------------
class Detection:
    def __init__(self, settings, status_cb=None):
        self.settings = settings
        self.status_cb = status_cb
        self.running = False
        self.triggerbot = False
        self.last_click = 0
        self._toggle_cooldown = 0
        self._thread = None

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
            self._notify(f"Model not found: {model_path}")
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

        show_overlay = s.get("showOverlay", False)
        only_still = s.get("onlyWhenStill", True)
        stop_key = s.get("stopKey", "F6")

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

                if closest_idx != -1:
                    r = df.iloc[closest_idx]
                    x1, y1, x2, y2 = int(r.xmin), int(r.ymin), int(r.xmax), int(r.ymax)
                    in_range = x1 <= center[0] <= x2 and y1 <= center[1] <= y2

                    can_click = (
                        in_range
                        and self.triggerbot
                        and now - self.last_click > s["cooldown"]
                        and (not only_still or not _is_moving())
                    )

                    if can_click:
                        time.sleep(s["triggerDelay"])
                        _real_click()
                        self.last_click = now

                # Optional debug overlay window
                if show_overlay:
                    color = (0, 255, 0) if self.triggerbot else (0, 0, 255)
                    cv2.rectangle(shot, (0, 0), (20, 20), color, -1)
                    cv2.putText(shot, "valorant-vision", (25, 18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                    cv2.imshow("valorant-vision", shot)
                    if cv2.waitKey(1) == ord("l"):
                        break

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
        self.resizable(False, False)
        self.geometry("420x680")

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

        # Body
        body = tk.Frame(self, bg=self.BG, padx=24, pady=16)
        body.pack(fill="both", expand=True)

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
        self._head_var = tk.BooleanVar(value=True)
        self._body_var = tk.BooleanVar(value=False)
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
        self._cd_var = tk.StringVar(value="1.1")
        self._make_entry(f2, self._cd_var)

        # Confidence
        f3 = tk.Frame(row, bg=self.BG)
        f3.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self._add_label(f3, "CONFIDENCE")
        self._conf_var = tk.StringVar(value="0.70")
        self._make_entry(f3, self._conf_var)

        # Trigger delay row
        row_delay = tk.Frame(body, bg=self.BG)
        row_delay.pack(fill="x", pady=(0, 12))
        row_delay.columnconfigure((0, 1), weight=1)

        fd = tk.Frame(row_delay, bg=self.BG)
        fd.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._add_label(fd, "TRIGGER DELAY (s)")
        self._delay_var = tk.StringVar(value="0.0")
        self._make_entry(fd, self._delay_var)

        fd2 = tk.Frame(row_delay, bg=self.BG)
        fd2.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._add_label(fd2, "SCALE")
        self._sc_var = tk.StringVar(value="5")
        self._make_entry(fd2, self._sc_var)

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

        self._still_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            chk_frame, text="Only click when standing still",
            variable=self._still_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

        self._overlay_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            chk_frame, text="Show debug overlay window",
            variable=self._overlay_var,
            bg=self.BG, fg=self.FG, selectcolor=self.BG2,
            activebackground=self.BG, activeforeground=self.FG,
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
        ).pack(anchor="w")

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
            "cooldown": float(self._cd_var.get() or 1.1),
            "confidence": float(self._conf_var.get() or 0.70),
            "triggerDelay": float(self._delay_var.get() or 0),
            "monitorWidth": int(self._w_var.get() or 1920),
            "monitorHeight": int(self._h_var.get() or 1080),
            "monitorScale": int(self._sc_var.get() or 5),
            "onlyWhenStill": self._still_var.get(),
            "showOverlay": self._overlay_var.get(),
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
