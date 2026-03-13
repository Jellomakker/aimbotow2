"""
ow-vision — Desktop App
Double-click ow-vision.bat → browser opens → pick settings → press START.
"""
import sys
import os
import threading
import webbrowser
import logging
import socket

# Suppress Flask request logs so no console window noise
logging.getLogger("werkzeug").setLevel(logging.ERROR)

from flask import Flask, render_template_string, request, jsonify

# ---------------------------------------------------------------------------
# Paths — work as both a script and a frozen PyInstaller .exe
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_MODELS_DIR = os.path.join(_BASE_DIR, "models")
sys.path.insert(0, os.path.join(_BASE_DIR, "scripts"))

# ---------------------------------------------------------------------------
# Global detection state
# ---------------------------------------------------------------------------
_detection = None
_status = "Ready"

# ---------------------------------------------------------------------------
# Available models
# ---------------------------------------------------------------------------
def _get_models():
    if os.path.isdir(_MODELS_DIR):
        pts = sorted(f for f in os.listdir(_MODELS_DIR) if f.endswith(".pt"))
        if pts:
            return pts
    return ["v2.pt"]

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ow-vision</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background: #0d0d1a;
    color: #e2e2f0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .app {
    width: 440px;
    background: linear-gradient(145deg, #13132b 0%, #1a1a3e 100%);
    border-radius: 20px;
    border: 1px solid rgba(233,69,96,0.15);
    box-shadow: 0 20px 60px rgba(0,0,0,0.6), 0 0 40px rgba(233,69,96,0.08);
    overflow: hidden;
  }

  /* ── header ── */
  .header {
    background: linear-gradient(135deg, #1e1e4a 0%, #16163a 100%);
    padding: 24px 28px 18px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }
  .header h1 {
    font-size: 26px; font-weight: 800;
    background: linear-gradient(135deg, #e94560, #ff6b81);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
  }
  .header p { font-size: 13px; color: #7a7a9e; margin-top: 2px; }

  /* ── body ── */
  .body { padding: 22px 28px 28px; }

  /* ── field groups ── */
  .field { margin-bottom: 18px; }
  .field label {
    display: block; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1.2px;
    color: #7a7a9e; margin-bottom: 8px;
  }

  /* radio pills */
  .pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pills input[type="radio"] { display: none; }
  .pills label.pill {
    font-size: 13px; font-weight: 500;
    padding: 7px 16px; border-radius: 8px;
    background: #1e1e3e; color: #9e9ec0;
    cursor: pointer; transition: all .15s;
    border: 1px solid transparent;
    text-transform: none; letter-spacing: 0;
  }
  .pills input:checked + label.pill {
    background: rgba(233,69,96,0.15); color: #ff6b81;
    border-color: rgba(233,69,96,0.4);
  }
  .pills label.pill:hover { background: #252550; }

  /* text inputs */
  .row { display: flex; gap: 12px; }
  .row .field { flex: 1; }
  input[type="text"], input[type="number"] {
    width: 100%; padding: 10px 14px;
    background: #111128; border: 1px solid #2a2a50;
    border-radius: 10px; color: #e2e2f0;
    font-size: 14px; font-family: inherit;
    outline: none; transition: border .15s;
  }
  input:focus { border-color: #e94560; }

  /* ── start/stop button ── */
  .btn-start {
    width: 100%; padding: 14px 0; margin-top: 6px;
    font-size: 15px; font-weight: 700; letter-spacing: 1px;
    border: none; border-radius: 12px; cursor: pointer;
    color: #fff; transition: all .2s;
    background: linear-gradient(135deg, #e94560, #c0392b);
    box-shadow: 0 4px 20px rgba(233,69,96,0.3);
  }
  .btn-start:hover { transform: translateY(-1px); box-shadow: 0 6px 28px rgba(233,69,96,0.45); }
  .btn-start.running {
    background: linear-gradient(135deg, #27ae60, #2ecc71);
    box-shadow: 0 4px 20px rgba(46,204,113,0.3);
  }
  .btn-start.running:hover { box-shadow: 0 6px 28px rgba(46,204,113,0.45); }

  /* ── status bar ── */
  .status {
    text-align: center; margin-top: 14px;
    font-size: 13px; color: #7a7a9e;
    min-height: 20px;
  }
  .status.active { color: #2ecc71; }

  /* ── footer ── */
  .footer {
    text-align: center; padding: 12px;
    font-size: 11px; color: #3a3a5e;
    border-top: 1px solid rgba(255,255,255,0.03);
  }
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <h1>ow-vision</h1>
    <p>Overwatch 2 AI Detection</p>
  </div>
  <div class="body">

    <!-- Model -->
    <div class="field">
      <label>Model</label>
      <div class="pills" id="model-pills">
        {% for m in models %}
        <input type="radio" name="model" id="m-{{m}}" value="{{m}}" {{'checked' if m == 'v2.pt' else ''}}>
        <label class="pill" for="m-{{m}}">{{ m | replace('.pt','') }}</label>
        {% endfor %}
      </div>
    </div>

    <!-- Target -->
    <div class="field">
      <label>Target</label>
      <div class="pills">
        <input type="radio" name="target" id="t-head" value="head" checked>
        <label class="pill" for="t-head">Head only</label>
        <input type="radio" name="target" id="t-body" value="body">
        <label class="pill" for="t-body">Body only</label>
        <input type="radio" name="target" id="t-both" value="both">
        <label class="pill" for="t-both">Both</label>
      </div>
    </div>

    <!-- Row: Toggle key + Cooldown + Confidence -->
    <div class="row">
      <div class="field">
        <label>Toggle Key</label>
        <input type="text" id="key" value="`" maxlength="10">
      </div>
      <div class="field">
        <label>Cooldown (s)</label>
        <input type="number" id="cooldown" value="1.1" step="0.1" min="0">
      </div>
      <div class="field">
        <label>Confidence</label>
        <input type="number" id="confidence" value="0.70" step="0.05" min="0.1" max="1.0">
      </div>
    </div>

    <button class="btn-start" id="btn" onclick="toggle()">START</button>
    <div class="status" id="status">Ready</div>
  </div>
  <div class="footer">ow-vision v2.0 &middot; AI powered by YOLOv8</div>
</div>

<script>
let running = false;

function getSettings() {
  const model = document.querySelector('input[name="model"]:checked').value;
  const target = document.querySelector('input[name="target"]:checked').value;
  const detectMap = {head: [1], body: [0], both: [0,1]};
  return {
    model: model,
    detect: detectMap[target] || [1],
    toggleKey: document.getElementById('key').value || '`',
    cooldown: parseFloat(document.getElementById('cooldown').value) || 1.1,
    confidence: parseFloat(document.getElementById('confidence').value) || 0.70,
    triggerDelay: 0
  };
}

async function toggle() {
  const btn = document.getElementById('btn');
  const st  = document.getElementById('status');
  if (!running) {
    btn.textContent = 'Loading...';
    const resp = await fetch('/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(getSettings())
    });
    const data = await resp.json();
    if (data.ok) {
      running = true;
      btn.textContent = 'STOP';
      btn.classList.add('running');
      st.textContent = 'Running...';
      st.classList.add('active');
      pollStatus();
    } else {
      btn.textContent = 'START';
      st.textContent = 'Error: ' + (data.error || 'unknown');
    }
  } else {
    await fetch('/stop', {method: 'POST'});
    running = false;
    btn.textContent = 'START';
    btn.classList.remove('running');
    st.textContent = 'Stopped';
    st.classList.remove('active');
  }
}

async function pollStatus() {
  while (running) {
    try {
      const resp = await fetch('/status');
      const data = await resp.json();
      document.getElementById('status').textContent = data.status;
      if (!data.running) {
        running = false;
        document.getElementById('btn').textContent = 'START';
        document.getElementById('btn').classList.remove('running');
        document.getElementById('status').classList.remove('active');
        break;
      }
    } catch(e) {}
    await new Promise(r => setTimeout(r, 1000));
  }
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE, models=_get_models())

@app.route("/start", methods=["POST"])
def start_detection():
    global _detection, _status
    if _detection and _detection.running:
        return jsonify(ok=False, error="Already running")

    data = request.get_json(force=True)
    settings = {
        "model":       str(data.get("model", "v2.pt")),
        "detect":      list(data.get("detect", [1])),
        "toggleKey":   str(data.get("toggleKey", "`")),
        "cooldown":    float(data.get("cooldown", 1.1)),
        "confidence":  float(data.get("confidence", 0.70)),
        "triggerDelay": float(data.get("triggerDelay", 0)),
    }

    try:
        from ai.Detection import Detection
        _detection = Detection(settings)
        _detection.status_callback = _on_status
        _detection.start()
        _status = "Starting..."
        return jsonify(ok=True)
    except Exception as e:
        _status = f"Error: {e}"
        return jsonify(ok=False, error=str(e))

@app.route("/stop", methods=["POST"])
def stop_detection():
    global _detection, _status
    if _detection:
        _detection.stop()
        _detection = None
    _status = "Stopped"
    return jsonify(ok=True)

@app.route("/status")
def get_status():
    running = _detection.running if _detection else False
    return jsonify(status=_status, running=running)

@app.route("/quit", methods=["POST"])
def quit_app():
    """Gracefully stop detection and shut down the server."""
    global _detection, _status
    if _detection:
        _detection.stop()
        _detection = None
    _status = "Shutting down..."
    shutdown = request.environ.get("werkzeug.server.shutdown")
    if shutdown:
        shutdown()
    else:
        os._exit(0)
    return jsonify(ok=True)

def _on_status(text):
    global _status
    _status = text

def _port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

# ---------------------------------------------------------------------------
# Main — start server and open browser automatically
# ---------------------------------------------------------------------------
def main():
    port = 18729
    url = f"http://127.0.0.1:{port}"

    # If already running, just open browser to existing instance
    if _port_in_use(port):
        webbrowser.open(url)
        return

    # Open browser after a short delay
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
