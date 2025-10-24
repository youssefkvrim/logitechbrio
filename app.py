import os
import platform
from datetime import datetime

from flask import Flask, jsonify, render_template, request

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
    time_part = now.strftime("%H:%M:%S")

    # Build timezone label as +HH (hours only), matching the example style
    offset = now.utcoffset() or now.tzinfo.utcoffset(now)  # type: ignore[arg-type]
    total_seconds = int(offset.total_seconds()) if offset else 0
    sign = "+" if total_seconds >= 0 else "-"
    hours = abs(total_seconds) // 3600
    tz_label = f"{sign}{hours:02d}"

    if for_windows:
        time_part = time_part.replace(":", "-")  # Windows forbids ':' in filenames

    base = sanitize_filename(user_base, for_windows)
    return f"image_{base}_pc{date_part}T{time_part}{tz_label}.jpg"


def open_camera():
    # Try likely backends per OS
    system = platform.system()
    backends: list[int] = []
    if system == "Windows":
        backends = [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
    elif system == "Darwin":
        backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
    else:
        backends = [cv2.CAP_V4L2, cv2.CAP_ANY]

    index = int(os.environ.get("CAMERA_INDEX", "0"))

    for backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            # Try to set a sensible resolution; ignore if not supported
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            return cap
        try:
            cap.release()
        except Exception:
            pass
    return None


app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/capture")
def capture():
    data = request.get_json(silent=True) or {}
    base = (data.get("user_base_name") or "").strip()

    save_dir, use_windows_format = get_save_dir()
    filename = format_filename(base, for_windows=use_windows_format)
    out_path = os.path.join(save_dir, filename)

    cap = open_camera()
    if cap is None:
        return jsonify({"ok": False, "error": "Camera not available"}), 500

    try:
        # Warm-up reads improve first-frame quality
        for _ in range(3):
            cap.read()
        ok, frame = cap.read()
        if not ok or frame is None:
            return jsonify({"ok": False, "error": "Failed to capture frame"}), 500

        if not cv2.imwrite(out_path, frame):
            return jsonify({"ok": False, "error": "Failed to write image"}), 500
    finally:
        try:
            cap.release()
        except Exception:
            pass

    return jsonify({"ok": True, "saved_path": out_path, "filename": filename})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)


