# Project Overview — Logitech BRIO Minimal Capture App

Purpose: Minimal local web app to preview live video and capture a photo from a Logitech BRIO and save it with a deterministic filename.

## Structure

- `app.py`
  - Flask server entrypoint
  - Routes:
    - `GET /` → serves minimal UI
    - `GET /stream` → MJPEG stream of the current camera
    - `GET /config` → returns available camera indices, current selection, and save dir
    - `POST /config` → updates camera index and/or save dir
    - `POST /capture` → captures an image and saves it
  - Utilities:
    - `get_save_dir()` → chooses Windows target directory if present, else local fallback
    - `format_filename(user_base, for_windows)` → builds filename `image_<base>_pc<DDMMYY>T<HH:MM:SS><+HH>.jpg` (Windows replaces `:` with `-`)
    - `open_camera_by_index(index)` → opens camera with OS-appropriate backend
  - `CameraManager`
    - Background thread continuously reads frames from the selected camera
    - `switch_camera(index)` to change active camera
    - `get_jpeg()` for streaming, `capture_frame()` for instant capture

- `templates/index.html`
  - Minimal UI:
    - Live preview `<img src="/stream">`
    - Camera selection dropdown and save directory input
    - Preset name dropdown + custom name input
    - Apply settings and Capture buttons

- `requirements.txt`
  - Python dependencies (Flask, OpenCV)

- `README.md`
  - Setup and usage notes

## Responsibilities

- Filename semantics: prefix `image_`, then user-provided base, `_pc`, date `DDMMYY`, `T`, time `HH:MM:SS` (or `HH-MM-SS` on Windows), and timezone label `+HH`, with `.jpg` extension.
- Save destination precedence: Windows path `C:\\Users\\d649578\\Desktop\\test images pc logitech` if available, else project-local `captured_images/`. Overridable via UI.
- Camera: Uses index 0 by default; switch via UI. Stream and capture source update immediately.

## Non-goals

- No device-name-based selection (indices only).
- No authentication.
