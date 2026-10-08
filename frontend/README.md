# Frontend (Dashboard) — placeholder

This folder is intentionally **blank** during the assessment.

The focus is on the backend (see `../backend/`). The frontend will be added here
later as a thin dashboard that consumes the backend REST API.

## What will go here (when started)

- A simple web dashboard that polls `GET /api/junctions/{id}/status`
  and shows: signal states, queue sizes, junction/controller status,
  current mode, current phase, emergency and failure indicators.
- Junction detail view (desired vs actual, queues, alerts, pending command).
- Visual intersection (a basic cross-shaped diagram with coloured lights).
- Manual traffic control buttons (sends `MANUAL_GREEN_REQUEST` /
  `RETURN_TO_AUTOMATIC` to the backend).
- Emergency / failure banners.
- Traffic-simulation form (vehicle arrival, clearance, controller status,
  emergency vehicle, controller ACK).
- A "Recent activity" list pulled from `GET /api/junctions/{id}/history`.

## Suggested stack (pick later)

- Plain HTML + CSS + JavaScript with `fetch` polling every 1s
  (simplest, matches the spec's "polishing is secondary" guidance)
- or React + Vite (more structure, slower setup)

## Hard rule

The frontend must never decide traffic sequencing on its own.
Every signal change must come from the backend, and the UI must reflect
backend state — never write signal states directly.
