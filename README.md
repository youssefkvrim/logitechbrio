# Logitech BRIO Minimal Capture App

A minimal Flask + OpenCV app to capture a photo from a connected Logitech BRIO. Press Enter in the input to trigger a capture. The image is saved to the Windows directory `C:\Users\d649578\Desktop\test images pc logitech` when available, otherwise to a local `captured_images/` folder.

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

4. Open `http://127.0.0.1:5000` in a browser. Enter a name (e.g. `M7-3_006`) and press Enter or click Capture.

## File naming

- Pattern: `image_<USER_INPUT>_pc<DDMMYY>T<HH:MM:SS><+HH>.jpg`
- Example: `image_M7-3_006_pc251024T10:20:32+02.jpg`
- On Windows, `:` is not allowed in filenames, so times are saved as `HH-MM-SS` instead.
- The timezone label uses hours only (e.g., `+02`).

## Camera selection

- The app opens camera index `0` by default. Override with the environment variable `CAMERA_INDEX`, e.g. `CAMERA_INDEX=1 python app.py`.
- Attempts sensible backends per OS (MSMF/DSHOW on Windows, AVFoundation on macOS, V4L2 on Linux).

## Notes

- Ensure OpenCV has access to the camera (OS permission prompts may appear on first run).
- If the Windows target folder is unavailable, images are saved to `captured_images/` in the project directory.
