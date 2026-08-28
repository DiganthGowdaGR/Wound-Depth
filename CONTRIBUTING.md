# Contributing to WoundLens

## Scope

WoundLens is a research prototype. Keep changes grounded in the implemented workflow and avoid representing prototype outputs as clinical diagnoses or calibrated physical measurements unless a validated capability is added with supporting evidence.

## Local Setup

Follow the [Quick Start](README.md#quick-start) instructions. Use the root `.env` only for local secrets and machine-specific configuration; it is ignored by Git.

## Development Conventions

- Keep frontend network calls inside `src/services/woundlensApi.ts`.
- Keep persistence and external-service work in backend boundaries rather than React components.
- Preserve the separation between computed measurements, AI-generated documentation, and clinician-entered plan data.
- Never add raw patient images, reports, SQLite databases, dataset archives, API keys, or credentials to Git.
- Do not modify the trained `joblib` artifacts as part of UI or API work.
- Use clear, small commits with an imperative subject line.

## Before Opening a Pull Request

```powershell
npm run lint
npm run typecheck
npx expo export --platform web --clear
.\.venv\Scripts\python.exe -m py_compile backend\main.py backend\persistence.py
```

Include the workflow exercised, screenshots for visual changes, and any limitations or manual verification in the pull request description.

## Branches and Reviews

Create focused branches from the current integration branch. A pull request should describe:

1. The user-facing behavior changed.
2. The validation performed.
3. Any data, security, or safety implications.
4. Any follow-up work deliberately left out of scope.

## Reporting Security Issues

Do not open public issues containing credentials, patient information, raw scan images, or report files. Remove or rotate accidentally exposed credentials immediately.
