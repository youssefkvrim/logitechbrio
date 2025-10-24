import os
import platform
import shutil
import subprocess
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

if platform.system() == "Windows":
    # Prefer MSMF over DSHOW by index, can be overridden via env
    os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_MSMF", "1000")
    os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_DSHOW", "0")
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


def list_dshow_device_names_ffmpeg() -> list[str]:
    # Best-effort: use ffmpeg to list DirectShow video devices
    if platform.system() != "Windows":
        return []
    if shutil.which("ffmpeg") is None:
        return []
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=4,
        )
        out = proc.stdout or ""
        names: list[str] = []
        in_video = False
        for raw in out.splitlines():
            line = raw.strip()
            if "DirectShow video devices" in line:
                in_video = True
                continue
            if in_video and "DirectShow audio devices" in line:
                break
            if in_video and line.startswith("\"") and line.endswith("\""):
                names.append(line.strip('"'))
        return names
    except Exception:
        return []


_DEVICE_NAMES_CACHE: dict[str, object] = {"ts": 0.0, "names": []}
_INDICES_CACHE: dict[str, object] = {"ts": 0.0, "indices": []}
_INDICES_LOCK = threading.Lock()
_INDICES_REFRESHING = False


def get_device_names_cached() -> list[str]:
    now = time.time()
    ts = _DEVICE_NAMES_CACHE.get("ts") or 0.0
    if isinstance(ts, (int, float)) and (now - float(ts) < 10.0):
        cached = _DEVICE_NAMES_CACHE.get("names")
        return list(cached) if isinstance(cached, list) else []
    names = list_dshow_device_names_ffmpeg()
    if not names:
        # Provide sensible defaults if detection fails
        names = [
            "Logitech BRIO",
            "Logitech BRIO 4K",
            "Logitech BRIO 4K Stream Edition",
            "Logitech BRIO 500",
            "BRIO",
            "Logitech Webcam BRIO",
            "Integrated Camera",
            "USB Camera",
        ]
    _DEVICE_NAMES_CACHE["ts"] = now
    _DEVICE_NAMES_CACHE["names"] = names
    return names


def _refresh_indices_worker():
    global _INDICES_REFRESHING
    try:
        found: list[int] = []
        for i in range(16):
            if probe_camera_index(i):
                found.append(i)
        with _INDICES_LOCK:
            _INDICES_CACHE["ts"] = time.time()
            _INDICES_CACHE["indices"] = found
    finally:
        _INDICES_REFRESHING = False


def get_indices_cached() -> list[int]:
    now = time.time()
    with _INDICES_LOCK:
        ts = _INDICES_CACHE.get("ts") or 0.0
        if isinstance(ts, (int, float)) and (now - float(ts) < 5.0):
            cached = _INDICES_CACHE.get("indices")
            return list(cached) if isinstance(cached, list) else []
    # Quick first-fill: probe a small range synchronously
    quick_found: list[int] = []
    for i in range(4):
        if probe_camera_index(i):
            quick_found.append(i)
    with _INDICES_LOCK:
        _INDICES_CACHE["ts"] = now
        _INDICES_CACHE["indices"] = quick_found
        global _INDICES_REFRESHING
        if not _INDICES_REFRESHING:
            _INDICES_REFRESHING = True
            t = threading.Thread(target=_refresh_indices_worker, daemon=True)
            t.start()
    return quick_found


def open_camera_by_name(device_name: str):
    # Windows only: open by DirectShow device name for reliable BRIO selection
    if platform.system() != "Windows":
        return None
    # Try several likely device name variants
    base = device_name.strip()
    candidates = [
        base,
        f"{base} (Video)",
        f"{base} (video)",
    ]
    lower = base.lower()
    if "logi" in lower or "logitech" in lower or "brio" in lower:
        candidates.extend([
            "Logitech BRIO",
            "Logitech BRIO 4K",
            "Logitech BRIO 4K Stream Edition",
            "Logitech BRIO 500",
            "BRIO",
            "Logitech Webcam BRIO",
        ])
    tried = set()
    for name in candidates:
        if not name or name in tried:
            continue
        tried.add(name)
        source = f"video={name}"
        cap = cv2.VideoCapture(source, getattr(cv2, "CAP_DSHOW", 700))
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            continue
        # Configure and verify a frame
        try:
            try:
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                cap.set(cv2.CAP_PROP_FPS, 30)
            except Exception:
                pass
            for (w, h) in [(1920, 1080), (1280, 720), (640, 480)]:
                try:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                except Exception:
                    pass
                time.sleep(0.12)
                for _ in range(4):
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
    try:
        # Configure for stability
        try:
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            cap.set(cv2.CAP_PROP_FPS, 30)
        except Exception:
            pass
        for (w, h) in [(1920, 1080), (1280, 720), (640, 480)]:
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            except Exception:
                pass
            time.sleep(0.15)
            for _ in range(4):
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


class CameraManager:
    def __init__(self, index: int = 0, mode: str = "index", device_name: str | None = None) -> None:
        self.lock = threading.Lock()
        self.camera_index = index
        self.camera_mode = mode  # 'index' or 'name'
        self.camera_device_name = device_name or ""
        self.cap = None
        self.thread = None
        self.running = False
        self.last_frame = None

    def start(self, index: int | None = None, device_name: str | None = None, mode: str | None = None) -> bool:
        if index is not None:
            self.camera_index = int(index)
        if device_name is not None:
            self.camera_device_name = str(device_name)
        if mode in ("index", "name"):
            self.camera_mode = str(mode)
        self.stop()
        if self.camera_mode == "name" and self.camera_device_name:
            self.cap = open_camera_by_name(self.camera_device_name) or open_camera_by_index(self.camera_index)
        else:
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
        if self.running and self.camera_mode == "index" and index == self.camera_index:
            return True
        return self.start(index=index, mode="index")

    def switch_camera_name(self, device_name: str) -> bool:
        device_name = str(device_name)
        if self.running and self.camera_mode == "name" and device_name == self.camera_device_name:
            return True
        return self.start(device_name=device_name, mode="name")

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

    def get_property(self, prop_id: int):
        with self.lock:
            if self.cap is None:
                return None
            try:
                val = self.cap.get(prop_id)
            except Exception:
                return None
        return val

    def set_property(self, prop_id: int, value: float) -> bool:
        with self.lock:
            if self.cap is None:
                return False
            try:
                return bool(self.cap.set(prop_id, float(value)))
            except Exception:
                return False


app = Flask(__name__)

# Global runtime configuration
DEFAULT_SAVE_DIR, DEFAULT_FOR_WINDOWS = get_save_dir()
CURRENT_SAVE_DIR = DEFAULT_SAVE_DIR
CURRENT_FOR_WINDOWS = DEFAULT_FOR_WINDOWS

# Camera manager initialized at startup
CAMERA_MODE = os.environ.get("CAMERA_MODE", "index") if os.environ.get("CAMERA_MODE", "index") in ("index", "name") else "index"
CAMERA_DEVICE_NAME = os.environ.get("CAMERA_DEVICE_NAME", "")
CAMERA = CameraManager(index=int(os.environ.get("CAMERA_INDEX", "0")), mode=CAMERA_MODE, device_name=CAMERA_DEVICE_NAME)
CAMERA.start()


def _autoselect_brio_worker():
    # If running on Windows, try to switch to BRIO by name shortly after startup
    try:
        if platform.system() != "Windows":
            return
        time.sleep(0.6)
        names = get_device_names_cached()
        for name in names:
            if isinstance(name, str) and "brio" in name.lower():
                # Attempt switch by name; ignore result
                try:
                    CAMERA.switch_camera_name(name)
                except Exception:
                    pass
                break
    except Exception:
        pass


threading.Thread(target=_autoselect_brio_worker, daemon=True).start()


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
    available: list[int] = get_indices_cached()
    return jsonify({
        "ok": True,
        "camera_index": CAMERA.camera_index,
        "camera_mode": CAMERA.camera_mode,
        "camera_device_name": CAMERA.camera_device_name,
        "available_indices": available,
        "available_device_names": get_device_names_cached(),
        "save_dir": CURRENT_SAVE_DIR,
        "windows_target_present": is_dir(WINDOWS_TARGET_DIR),
    })


@app.post("/rescan_cameras")
def rescan_cameras():
    # Non-blocking rescan: trigger background refresh and return cached immediately
    try:
        with _INDICES_LOCK:
            global _INDICES_REFRESHING
            _INDICES_CACHE["ts"] = 0.0
            if not _INDICES_REFRESHING:
                _INDICES_REFRESHING = True
                t = threading.Thread(target=_refresh_indices_worker, daemon=True)
                t.start()
        indices = _INDICES_CACHE.get("indices") or []
        names = get_device_names_cached()
        return jsonify({"ok": True, "available_indices": list(indices), "available_device_names": names})
    except Exception:
        return jsonify({"ok": False, "error": "Rescan failed"}), 500


# Camera properties mapping
PROP_MAP: dict[str, int] = {}
try:
    PROP_MAP["brightness"] = int(cv2.CAP_PROP_BRIGHTNESS)
    PROP_MAP["contrast"] = int(cv2.CAP_PROP_CONTRAST)
    PROP_MAP["saturation"] = int(cv2.CAP_PROP_SATURATION)
    if hasattr(cv2, "CAP_PROP_SHARPNESS"):
        PROP_MAP["sharpness"] = int(cv2.CAP_PROP_SHARPNESS)
    if hasattr(cv2, "CAP_PROP_ZOOM"):
        PROP_MAP["zoom"] = int(getattr(cv2, "CAP_PROP_ZOOM"))
except Exception:
    pass


@app.get("/camera_props")
def get_camera_props():
    props: dict[str, object] = {}
    for name, pid in PROP_MAP.items():
        val = CAMERA.get_property(pid)
        if val is None:
            props[name] = None
        else:
            # Normalize to int if close to int
            try:
                ival = int(round(float(val)))
                props[name] = ival
            except Exception:
                props[name] = float(val)
    return jsonify({"ok": True, "props": props})


@app.post("/camera_props")
def set_camera_props():
    data = request.get_json(silent=True) or {}
    results: dict[str, bool] = {}
    for name, value in data.items():
        if name not in PROP_MAP:
            continue
        try:
            v = float(value)
        except Exception:
            results[name] = False
            continue
        ok = CAMERA.set_property(PROP_MAP[name], v)
        results[name] = bool(ok)
    return jsonify({"ok": True, "results": results})


@app.post("/config")
def set_config():
    global CURRENT_SAVE_DIR, CURRENT_FOR_WINDOWS
    data = request.get_json(silent=True) or {}
    errors: list[str] = []

    # Camera index
    if "camera_index" in data:
        try:
            cam_idx = int(data["camera_index"])
            # Apply only if mode is index or unspecified
            desired_mode = str(data.get("camera_mode") or CAMERA.camera_mode)
            if desired_mode == "index":
                if not CAMERA.switch_camera(cam_idx):
                    errors.append("Failed to switch camera")
        except Exception:
            errors.append("Invalid camera_index")

    # Camera mode
    if "camera_mode" in data:
        mode = str(data["camera_mode"])
        if mode in ("index", "name"):
            CAMERA.camera_mode = mode
        else:
            errors.append("Invalid camera_mode")

    # Camera device name (Windows DirectShow)
    if "camera_device_name" in data:
        name = str(data["camera_device_name"]).strip()
        if name:
            if not CAMERA.switch_camera_name(name):
                errors.append("Failed to switch camera by name")
        else:
            CAMERA.camera_device_name = ""

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

    return jsonify({
        "ok": len(errors) == 0,
        "errors": errors,
        "camera_index": CAMERA.camera_index,
        "camera_mode": CAMERA.camera_mode,
        "camera_device_name": CAMERA.camera_device_name,
        "save_dir": CURRENT_SAVE_DIR,
    })


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


