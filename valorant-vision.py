"""
Valorant AI Triggerbot — Single-file script
Run this file → GUI opens → pick settings → press START

Requirements (install once):
    pip install ultralytics torch mss opencv-python numpy pandas pyautogui keyboard

Place your YOLO .pt model files in the same folder as this script,
or they will be looked for in a "models/" subfolder next to the script.
"""

import os
import sys
import math
import time
import threading
import tkinter as tk
from tkinter import ttk

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
    for d in [_SCRIPT_DIR, _MODELS_DIR]:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return os.path.join(_MODELS_DIR, name)


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
            import pyautogui
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
        self._notify(f"Loading model {s['model']}…")
        try:
            model = YOLO(model_path)
        except Exception as e:
            self._notify(f"Model error: {e}")
            self.running = False
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        self._notify(f"Running on {device.upper()}")

        with mss() as stc:
            while self.running:
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
                        cv2.rectangle(shot, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    except Exception:
                        pass

                # Toggle hotkey
                try:
                    if keyboard.is_pressed(s["toggleKey"]) and now - self.last_click > 0.2:
                        self.triggerbot = not self.triggerbot
                        self.last_click = now
                        self._notify("Triggerbot ON" if self.triggerbot else "Triggerbot OFF")
                except Exception:
                    pass

                if closest_idx != -1:
                    r = df.iloc[closest_idx]
                    x1, y1, x2, y2 = int(r.xmin), int(r.ymin), int(r.xmax), int(r.ymax)
                    in_range = x1 <= center[0] <= x2 and y1 <= center[1] <= y2
                    if in_range and self.triggerbot and now - self.last_click > s["cooldown"]:
                        time.sleep(s["triggerDelay"])
                        pyautogui.click()
                        self.last_click = now

                # Overlay
                color = (0, 255, 0) if self.triggerbot else (0, 0, 255)
                cv2.rectangle(shot, (0, 0), (20, 20), color, -1)
                cv2.putText(shot, "valorant-vision", (25, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                cv2.imshow("valorant-vision", shot)
                if cv2.waitKey(1) == ord("l"):
                    break

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
        self.geometry("420x520")

        self._detection = None
        self._models = _find_models()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── build ──
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=self.BG2, padx=24, pady=18)
        hdr.pack(fill="x")
        tk.Label(hdr, text="VALORANT VISION", font=("Segoe UI", 20, "bold"),
                 fg=self.ACCENT2, bg=self.BG2).pack(anchor="w")
        tk.Label(hdr, text="AI Triggerbot", font=("Segoe UI", 10),
                 fg=self.DIM, bg=self.BG2).pack(anchor="w")

        # Body
        body = tk.Frame(self, bg=self.BG, padx=24, pady=16)
        body.pack(fill="both", expand=True)

        # Model selector
        self._add_label(body, "MODEL")
        self._model_var = tk.StringVar(value=self._models[-1] if self._models else "v2.pt")
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

        # Target selector
        self._add_label(body, "TARGET")
        self._target_var = tk.StringVar(value="head")
        tf = tk.Frame(body, bg=self.BG)
        tf.pack(fill="x", pady=(0, 12))
        for txt, val in [("Head", "head"), ("Body", "body"), ("Both", "both")]:
            tk.Radiobutton(
                tf, text=txt, variable=self._target_var, value=val,
                bg=self.BG, fg=self.FG, selectcolor=self.BG2,
                activebackground=self.BG, activeforeground=self.ACCENT2,
                font=("Segoe UI", 10), indicatoron=0, padx=14, pady=5,
                bd=0, relief="flat", highlightthickness=0,
            ).pack(side="left", padx=(0, 6))

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

        # Resolution row
        row2 = tk.Frame(body, bg=self.BG)
        row2.pack(fill="x", pady=(0, 14))
        row2.columnconfigure((0, 1, 2), weight=1)

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

        fs = tk.Frame(row2, bg=self.BG)
        fs.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self._add_label(fs, "SCALE")
        self._sc_var = tk.StringVar(value="5")
        self._make_entry(fs, self._sc_var)

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
            body, text="Ready", font=("Segoe UI", 10),
            fg=self.DIM, bg=self.BG,
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
    def _toggle(self):
        if self._detection and self._detection.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        target_map = {"head": [1], "body": [0], "both": [0, 1]}
        settings = {
            "model": self._model_var.get(),
            "detect": target_map.get(self._target_var.get(), [1]),
            "toggleKey": self._key_var.get() or "`",
            "cooldown": float(self._cd_var.get() or 1.1),
            "confidence": float(self._conf_var.get() or 0.70),
            "triggerDelay": 0,
            "monitorWidth": int(self._w_var.get() or 1920),
            "monitorHeight": int(self._h_var.get() or 1080),
            "monitorScale": int(self._sc_var.get() or 5),
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
