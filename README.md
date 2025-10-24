# Logitech BRIO Minimal Capture App

A minimal Flask + OpenCV app to preview a live video stream and capture a photo from a connected Logitech BRIO.

## Quick start

1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the server:

```bash
python app.py
```

4. Open `http://localhost:8000` in a browser.

## Improving camera detection on Windows

For more reliable device discovery and switching to Logitech BRIO:

- Install FFmpeg (to enumerate DirectShow devices):
  - winget: `winget install --id=Gyan.FFmpeg -e`
  - or Chocolatey: `choco install ffmpeg`
  - or download from `https://ffmpeg.org` and add to PATH
- Optional: pygrabber (already in requirements) provides DirectShow device names without FFmpeg.

Environment knobs:
- `BACKEND_PREF` (Windows): `msmf` (default), `dshow`, or `auto`
- `PREFER_BRIO`: `1` (default) to try switching to BRIO by name if index fails
- `CAMERA_MODE`: `index` (default) or `name`
- `CAMERA_INDEX` / `CAMERA_DEVICE_NAME`: initial selection

Examples (PowerShell):
```powershell
$env:BACKEND_PREF='msmf'; $env:PREFER_BRIO='1'; python app.py
$env:CAMERA_MODE='index'; $env:CAMERA_INDEX='1'; python app.py
$env:CAMERA_MODE='name'; $env:CAMERA_DEVICE_NAME='Logitech BRIO'; python app.py
```

## Usage

- Live preview appears at the top of the page, with a live clock at top-right.
- Click the gear to open settings. Choose the camera index, rescan if needed, and set a save directory (Browse…).
- Adjust camera settings (brightness, contrast, saturation, sharpness, zoom; availability depends on the driver).
- Select a predefined name or type a custom name in the input.
- Click "Capture" (or press Enter in the custom input) to save instantly.

## File naming

- Pattern: `image_<USER_INPUT>_pc<DDMMYY>T<HHMMSS><+HH>.jpg`
- Example: `image_M7-3_006_pc251024T102032+02.jpg`
- The timezone label uses hours only (e.g., `+02`).

## Save location

- Default: `C:\Users\d649578\Desktop\test images pc logitech` if it exists; otherwise `captured_images/` under the project.
- You can override the save directory in the UI. The app will create it if missing.

## Notes

- Ensure OpenCV has camera permissions on your OS.
- Some properties are not supported by all cameras/drivers.
