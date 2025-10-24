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

## Usage

- Live preview appears at the top of the page, with a live clock at top-right.
- Choose the camera index from the dropdown, set a save directory, then click "Apply settings".
- Select a predefined name or type a custom name in the input.
- Click "Capture" (or press Enter in the custom input) to save instantly.

## File naming

- Pattern: `image_<USER_INPUT>_pc<DDMMYY>T<HHMMSS><+HH>.jpg`
- Example: `image_M7-3_006_pc251024T102032+02.jpg`
- The timezone label uses hours only (e.g., `+02`).

## Camera selection

- The app opens camera index `0` at startup.
- Use the "Camera" dropdown and "Apply settings" to switch cameras. This updates the live stream and capture source immediately.
- If your Logitech BRIO is not index 0, select the appropriate index.

## Save location

- Default: `C:\Users\d649578\Desktop\test images pc logitech` if it exists; otherwise `captured_images/` under the project.
- You can override the save directory in the UI. The app will create it if missing.

## Notes

- Ensure OpenCV has camera permissions on your OS.
- Optional: set `CAMERA_INDEX` env var before launch to choose startup camera.
