import os
from mss import mss
import cv2
import numpy as np
import time
import pandas as pd
from ultralytics import YOLO
import pyautogui
import keyboard
import threading
import math
import torch

# Resolve model path relative to this file so it works from any working directory
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_SCRIPT_DIR, os.pardir, os.pardir, "models")


class Detection:
    def __init__(self, settings=None):
        self.running = False
        self._thread = None

        # Defaults (can be overridden via the settings dict)
        self.settings = {
            "toggleKey": "`",        # key to toggle triggerbot (` works on all keyboards)
            "cooldown": 1.1,         # seconds between auto-clicks
            "detect": [1],           # 0=enemy body, 1=enemy head, [0,1]=both
            "triggerDelay": 0,       # extra delay before click (seconds)
            "monitorWidth": 1920,
            "monitorHeight": 1080,
            "monitorScale": 5,
            "confidence": 0.70,
            "model": "v2.pt",
        }
        if settings:
            self.settings.update(settings)

        self.triggerbot = False
        self.lastClick = 0
        self.status_callback = None   # GUI can set this to receive status text

    # ---------- public API ----------
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

    # ---------- internals ----------
    def _notify(self, text):
        if self.status_callback:
            self.status_callback(text)

    def _loop(self):
        s = self.settings
        mw, mh, sc = s["monitorWidth"], s["monitorHeight"], s["monitorScale"]

        left = int(mw / 2 - mw / sc / 2)
        top  = int(mh / 2 - mh / sc / 2)
        w    = int(mw / sc)
        h    = int(mh / sc)
        # mss expects a dict, not a tuple
        monitor = {"left": left, "top": top, "width": w, "height": h}
        screenshotCenter = [w // 2, h // 2]

        model_path = os.path.normpath(os.path.join(_MODELS_DIR, s["model"]))
        self._notify(f"Loading model {s['model']}...")
        model = YOLO(model_path)

        # Use GPU if available, otherwise CPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        self._notify(f"Running on {device.upper()}")

        with mss() as stc:
            while self.running:
                closestPartDistance = 100000
                closestPart = -1
                currentTime = time.time()

                screenshot = np.array(stc.grab(monitor))
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

                results = model.predict(
                    screenshot, save=False,
                    classes=s["detect"],
                    conf=s["confidence"],
                    verbose=False,
                    device=device,
                    half=False,
                )

                boxes = results[0].boxes
                if boxes is not None and len(boxes):
                    positionsFrame = pd.DataFrame(
                        boxes.data.cpu().numpy(),
                        columns=["xmin", "ymin", "xmax", "ymax", "conf", "class"],
                    )
                else:
                    positionsFrame = pd.DataFrame(
                        columns=["xmin", "ymin", "xmax", "ymax", "conf", "class"]
                    )

                for i, (_, row) in enumerate(positionsFrame.iterrows()):
                    try:
                        xmin, ymin, xmax, ymax = int(row.xmin), int(row.ymin), int(row.xmax), int(row.ymax)
                        centerX = (xmax - xmin) / 2 + xmin
                        centerY = (ymax - ymin) / 2 + ymin
                        distance = math.dist([centerX, centerY], screenshotCenter)

                        if distance < closestPartDistance:
                            closestPartDistance = distance
                            closestPart = i

                        cv2.rectangle(screenshot, (xmin, ymin), (xmax, ymax), (255, 0, 0), 2)
                    except Exception:
                        pass

                # Toggle triggerbot with hotkey
                try:
                    if keyboard.is_pressed(s["toggleKey"]) and currentTime - self.lastClick > 0.2:
                        self.triggerbot = not self.triggerbot
                        self.lastClick = currentTime
                        self._notify("Triggerbot ON" if self.triggerbot else "Triggerbot OFF")
                except Exception:
                    pass

                if closestPart != -1:
                    xmin = int(positionsFrame.iloc[closestPart, 0])
                    ymin = int(positionsFrame.iloc[closestPart, 1])
                    xmax = int(positionsFrame.iloc[closestPart, 2])
                    ymax = int(positionsFrame.iloc[closestPart, 3])
                    inRange = (xmin <= screenshotCenter[0] <= xmax and
                               ymin <= screenshotCenter[1] <= ymax)
                    if currentTime - self.lastClick > s["cooldown"] and self.triggerbot and inRange:
                        time.sleep(s["triggerDelay"])
                        pyautogui.click()
                        self.lastClick = currentTime

                # Draw overlay
                color = (0, 255, 0) if self.triggerbot else (0, 0, 255)
                cv2.rectangle(screenshot, (0, 0), (20, 20), color, -1)
                cv2.putText(screenshot, "ow-vision", (25, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                cv2.imshow("ow-vision", screenshot)
                if cv2.waitKey(1) == ord("l"):
                    break

        cv2.destroyAllWindows()
        self.running = False
        self._notify("Stopped")