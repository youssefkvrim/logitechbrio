import os
import platform
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

try:
    import cv2  # type: ignore
except Exception as e:  # pragma: no cover
    raise RuntimeError("OpenCV (opencv-python) is required to run this app.") from e


APP_DIR = os.path.dirname(os.path.abspath(__file__))
FALLBACK_DIR = os.path.join(APP_DIR, "captured_images")
WINDOWS_TARGET_DIR = r"C:\\Users\\d649578\\Desktop\\test images pc logitech"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def is_dir(path: str) -> bool:
    try:
        return os.path.isdir(path)
    except Exception:
        return False


def get_save_dir() -> tuple[str, bool]:
    # Prefer the requested Windows path when present and usable
    is_windows = platform.system().lower().startswith("win")
    if is_dir(WINDOWS_TARGET_DIR):
        try:
            ensure_dir(WINDOWS_TARGET_DIR)
            return WINDOWS_TARGET_DIR, is_windows
        except Exception:
            pass

    # Fallback locally
    ensure_dir(FALLBACK_DIR)
    return FALLBACK_DIR, False


def sanitize_filename(name: str, for_windows: bool) -> str:
    # Allow alnum and a small safe charset; strip trailing dots
    safe = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_", "+", "."))
    if for_windows:
        safe = safe.replace(":", "-")
    return safe.strip(".") or "image"


def format_filename(user_base: str, for_windows: bool) -> str:
    now = datetime.now().astimezone()
    date_part = now.strftime("%d%m%y")
    time_part = now.strftime("%H%M%S")

    # Build timezone label as +HH (hours only), matching the example style
    offset = now.utcoffset() or now.tzinfo.utcoffset(now)  # type: ignore[arg-type]
    total_seconds = int(offset.total_seconds()) if offset else 0
    sign = "+" if total_seconds >= 0 else "-"
    hours = abs(total_seconds) // 3600
    tz_label = f"{sign}{hours:02d}"

    base = sanitize_filename(user_base, for_windows)
    return f"image_{base}_pc{date_part}T{time_part}{tz_label}.jpg"


def open_camera_by_index(index: int):
    # Try likely backends per OS (prefer Media Foundation on Windows for index capture)
    system = platform.system()
    backends: list[int] = []
    if system == "Windows":
        backends = [getattr(cv2, "CAP_MSMF", 1400), getattr(cv2, "CAP_DSHOW", 700), cv2.CAP_ANY]
    elif system == "Darwin":
        backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_V4L2, cv2.CAP_ANY]

    # Candidate resolutions from high to low
    resolutions = [(1920, 1080), (1280, 720), (640, 480)]

    for backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            continue
        try:
            # Set codec/fps if supported
            try:
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                cap.set(cv2.CAP_PROP_FPS, 30)
            except Exception:
                pass

            # Try resolutions with warmup and verify a readable frame
            for (w, h) in resolutions:
                try:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                except Exception:
                    pass
                # small settle time
                time.sleep(0.2)
                # warm-up reads
                for _ in range(5):
                    cap.read()
                ok, frame = cap.read()
                if ok and frame is not None:
                    return cap
        except Exception:
            pass
        try:
            cap.release()
        except Exception:
            pass
    return None


def probe_camera_index(index: int) -> bool:
    # Minimal probing without heavy config to avoid backend warnings where possible
    system = platform.system()
    if system == "Windows":
        candidates = [getattr(cv2, "CAP_MSMF", 1400), cv2.CAP_ANY]
    elif system == "Darwin":
        candidates = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    else:
        candidates = [cv2.CAP_V4L2, cv2.CAP_ANY]
    for backend in candidates:
        cap = None
        try:
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                return True
        except Exception:
            pass
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
    return False


class CameraManager:
    def __init__(self, index: int = 0) -> None:
        self.lock = threading.Lock()
        self.camera_index = index
        self.cap = None
        self.thread = None
        self.running = False
        self.last_frame = None

    def start(self, index: int | None = None) -> bool:
        if index is not None:
            self.camera_index = int(index)
        self.stop()
        self.cap = open_camera_by_index(self.camera_index)
        if self.cap is None:
            return False
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()
        return True

    def _reader(self) -> None:
        # Warm-up reads
        try:
            for _ in range(5):
                if self.cap is None:
                    break
                self.cap.read()
        except Exception:
            pass
        while self.running:
            try:
                if self.cap is None:
                    time.sleep(0.02)
                    continue
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    with self.lock:
                        self.last_frame = frame
                else:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.02)

    def stop(self) -> None:
        self.running = False
        if self.thread is not None:
            try:
                self.thread.join(timeout=0.5)
            except Exception:
                pass
        self.thread = None
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None

    def switch_camera(self, index: int) -> bool:
        index = int(index)
        if self.running and index == self.camera_index:
            return True
        return self.start(index)

    def get_jpeg(self) -> bytes | None:
        frame = None
        with self.lock:
            if self.last_frame is not None:
                frame = self.last_frame.copy()
        if frame is None:
            return None
        ok, buf = cv2.imencode('.jpg', frame)
        if not ok:
            return None
        return bytes(buf)

    def capture_frame(self):
        with self.lock:
            if self.last_frame is None:
                return None
            return self.last_frame.copy()


app = Flask(__name__)

# Global runtime configuration
DEFAULT_SAVE_DIR, DEFAULT_FOR_WINDOWS = get_save_dir()
CURRENT_SAVE_DIR = DEFAULT_SAVE_DIR
CURRENT_FOR_WINDOWS = DEFAULT_FOR_WINDOWS

# Camera manager initialized at startup
CAMERA = CameraManager(index=int(os.environ.get("CAMERA_INDEX", "0")))
CAMERA.start()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/stream")
def stream():
    def generate():
        while True:
            frame_bytes = CAMERA.get_jpeg()
            if frame_bytes is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            time.sleep(0.03)  # ~30 fps
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/config")
def get_config():
    # Scan a wider index range without forcing a frame grab
    available: list[int] = []
    for i in range(16):
        if probe_camera_index(i):
            available.append(i)
    return jsonify({
        "ok": True,
        "camera_index": CAMERA.camera_index,
        "available_indices": available,
        "save_dir": CURRENT_SAVE_DIR,
        "windows_target_present": is_dir(WINDOWS_TARGET_DIR),
    })


@app.post("/config")
def set_config():
    global CURRENT_SAVE_DIR, CURRENT_FOR_WINDOWS
    data = request.get_json(silent=True) or {}
    errors: list[str] = []

    # Camera index
    if "camera_index" in data:
        try:
            cam_idx = int(data["camera_index"])
            if not CAMERA.switch_camera(cam_idx):
                errors.append("Failed to switch camera")
        except Exception:
            errors.append("Invalid camera_index")

    # Save dir
    if "save_dir" in data:
        new_dir = str(data["save_dir"]).strip()
        try:
            ensure_dir(new_dir)
            CURRENT_SAVE_DIR = new_dir
            # Recompute Windows filename compatibility based on host OS
            CURRENT_FOR_WINDOWS = platform.system().lower().startswith("win")
        except Exception:
            errors.append("Failed to use save_dir")

    return jsonify({"ok": len(errors) == 0, "errors": errors, "camera_index": CAMERA.camera_index, "save_dir": CURRENT_SAVE_DIR})


@app.post("/choose_dir")
def choose_dir():
    # Open a native directory selection dialog on the server machine
    try:
        import tkinter as tk  # type: ignore
        from tkinter import filedialog  # type: ignore
    except Exception:
        return jsonify({"ok": False, "error": "Folder dialog not available (tkinter missing)"}), 500

    selected: str | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=CURRENT_SAVE_DIR or APP_DIR, mustexist=False, title="Choose save directory")
        root.destroy()
    except Exception:
        return jsonify({"ok": False, "error": "Failed to open folder dialog"}), 500

    if not selected:
        return jsonify({"ok": False, "error": "No folder selected"}), 200

    try:
        ensure_dir(selected)
    except Exception:
        return jsonify({"ok": False, "error": "Cannot create/access selected folder"}), 400

    return jsonify({"ok": True, "selected": selected})


@app.post("/capture")
def capture():
    data = request.get_json(silent=True) or {}
    base = (data.get("user_base_name") or "").strip()

    # Allow per-request override for save_dir (optional)
    save_dir = str(data.get("save_dir") or CURRENT_SAVE_DIR)
    try:
        ensure_dir(save_dir)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid save directory"}), 400

    filename = format_filename(base, for_windows=CURRENT_FOR_WINDOWS)
    out_path = os.path.join(save_dir, filename)

    frame = CAMERA.capture_frame()
    if frame is None:
        return jsonify({"ok": False, "error": "No frame available from camera"}), 500

    if not cv2.imwrite(out_path, frame):
        return jsonify({"ok": False, "error": "Failed to write image"}), 500

    return jsonify({"ok": True, "saved_path": out_path, "filename": filename})


if __name__ == "__main__":
    app.run(host="localhost", port=8000, debug=False)


