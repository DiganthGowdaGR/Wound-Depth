# Safety and Data Handling

## Prototype Boundary

WoundLens is an academic/research prototype. It is not validated or cleared for clinical diagnosis, treatment selection, wound staging, physical depth measurement, infection detection, or assessment of muscle or other underlying tissue involvement.

## Measurement Language

The application reports **relative depth / surface geometry** from supplied depth imagery. These values are not physical millimetres unless a separately validated calibration and measurement workflow is implemented. The 3D view supports visual review of the reconstructed surface; it is not a claim about anatomy below the visible surface.

The longitudinal change model identifies patterns that are unusual relative to its development data. Its output is a review signal, not a diagnosis, prognosis, healing percentage, or probability of deterioration.

## Data Rules

- Use pseudonymous patient identifiers in development datasets and demonstrations.
- Keep raw scans, SQLite databases, generated PDFs, and secrets out of source control.
- Use the ignored `.env` file for API credentials and local paths only.
- Do not expose provider keys through `EXPO_PUBLIC_*` variables or client-side code.
- Review generated AI text before it is included in clinical documentation.

## Operational Considerations

Before any clinical or human-subject use, establish appropriate governance, consent, access control, storage encryption, audit logging, device calibration, validation procedures, and regulatory review. This repository does not provide those operational controls by itself.
