# WoundLens

WoundLens is an Expo/React Native clinician-facing prototype with a FastAPI backend for multimodal wound analysis. The current-scan workflow accepts RGB, thermal, and depth images, generates an automatically localized wound ROI, relative-depth visualization, and 3D surface visualization.

## Requirements

- Node.js 18+
- Python 3.12+

## Install

```powershell
npm install
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Configure

Set the dataset directory only when using the dataset visit screens:

```powershell
$env:WOUNDLENS_DATASET_DIR="C:\path\to\results"
```

Gemini is optional and is used only by the FastAPI documentation-assistant endpoints. Do not add API keys to source files. Set one key or a comma-separated failover list before launching the backend:

```powershell
$env:GEMINI_API_KEY="your-key"
# Or: $env:GEMINI_API_KEYS="primary-key,secondary-key"
```

## Run

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8011 --reload
```

Start the Expo web app in a second terminal:

```powershell
npx expo start --web --clear
```

The frontend expects the backend at `http://127.0.0.1:8011`.

## Quality Checks

```powershell
npm run lint
npm run typecheck
npx expo export --platform web --clear
```

## Safety Notes

- Relative-depth results describe visible surface geometry and are not calibrated physical depth in millimetres.
- WoundLens does not determine muscle involvement from uploaded images.
- Gemini text summarizes measured data and clinician-entered notes only. It is not an autonomous diagnosis or prescription.
