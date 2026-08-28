# Architecture

## Overview

WoundLens has a React Native / Expo client and a FastAPI backend. The backend owns image processing, persisted records, generated assets, model loading, and optional documentation-assistant calls. The client renders typed API results and never contains model logic or provider credentials.

```text
Expo UI
  |  src/screens + src/components
  |  typed calls through src/services/woundlensApi.ts
  v
FastAPI (backend/main.py)
  |-- current-scan image workflow
  |-- historical comparison workflow
  |-- patient, visit, plan, report, and AI-summary endpoints
  |-- SQLite persistence (backend/persistence.py)
  |-- local generated asset storage
  |-- pre-trained joblib artifacts (woundlens_trained_model/)
  `-- optional Groq documentation service (backend/services/groq_service.py)
```

## Current Scan Path

`POST /analyze-current` receives RGB, thermal, and depth files. It validates image types, preserves the originals, creates the visible wound ROI, produces relative-depth and 3D surface assets, calculates structural metrics, then persists the visit and assets. It does not invoke the longitudinal Isolation Forest.

## Longitudinal Path

`POST /analyze-followup` loads a baseline and current visit from the same dataset case. `WoundLensModel` loads the existing `joblib` artifacts at API startup and uses them only for inference. It returns the model change score and the RGB, thermal, and depth change indices.

## Data Boundaries

- `src/services/woundlensApi.ts` converts backend responses into frontend types.
- `backend/persistence.py` owns SQLite reads and writes.
- `backend/services/storage_service.py` owns saved generated image assets.
- `backend/report_service.py` renders persisted data into a PDF.
- `backend/services/groq_service.py` is server-only and validates AI JSON before it reaches the UI.

## AI Summary Behavior

The AI endpoint retrieves saved measurements, asset availability, clinician notes, and same-patient history on the backend. Provider output is treated as documentation assistance only. If the provider cannot respond, the API saves and returns a clearly labeled summary assembled from stored WoundLens measurements; image analysis and report generation remain available.
