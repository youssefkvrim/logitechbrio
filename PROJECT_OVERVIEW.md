# Project Overview — Logitech BRIO Minimal Capture App

Purpose: Minimal local web app to capture a single photo from a Logitech BRIO and save it with a deterministic filename.

## Structure

- `app.py`
  - Flask server entrypoint
  - Routes:
    - `GET /` → serves minimal UI
    - `POST /capture` → captures an image and saves it
  - Utilities:
    - `get_save_dir()` → chooses Windows target directory if present, else local fallback
    - `format_filename(user_base, for_windows)` → builds filename `image_<base>_pc<DDMMYY>T<HH:MM:SS><+HH>.jpg` (Windows replaces `:` with `-`)
    - `open_camera()` → opens camera index (default 0) with OS-appropriate backend

- `templates/index.html`
  - Minimal UI with a single input and a Capture button
  - Pressing Enter triggers a POST to `/capture`
  - Displays the saved path or error

- `requirements.txt`
  - Python dependencies (Flask, OpenCV)

- `README.md`
  - Setup and usage notes

## Responsibilities

- Filename semantics: prefix `image_`, then user-provided base, `_pc`, date `DDMMYY`, `T`, time `HH:MM:SS` (or `HH-MM-SS` on Windows), and timezone label `+HH`, with `.jpg` extension.
- Save destination precedence: Windows path `C:\\Users\\d649578\\Desktop\\test images pc logitech` if available, else project-local `captured_images/`.
- Camera: Uses index 0 by default; overridable via `CAMERA_INDEX`.

## Non-goals

- No multi-camera enumeration or device name matching.
- No video streaming; single-shot captures only.
- No authentication.
