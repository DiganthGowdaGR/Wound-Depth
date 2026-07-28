# WoundLens AI Intelligence Layer

WoundLens measures RGB, thermal, depth, ROI, and relative-surface outputs. The backend-only AI layer receives those saved measurements, clinician notes, data-quality status, and same-patient history to create validated, clinician-readable documentation. It does not calculate measurements, diagnose, prescribe, determine surgery, state healing probability, or report physical depth in millimetres.

Every AI summary is persisted with its model name and a clinician-review state. Real measurements and backend-generated data-quality facts remain separate from AI narrative text. If the provider is unavailable, analysis, storage, and report generation continue to work.
