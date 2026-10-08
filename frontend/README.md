# Frontend — Dashboard

A small single-page dashboard for the Factory Traffic Management backend.

The dashboard is **read-mostly** — it polls the backend every second and
renders the result. It also exposes a few buttons / forms to send events
back to the backend for demo purposes (manual overrides, vehicle
simulation, controller ACK).

## Files

| File         | Purpose                                                |
| ------------ | ------------------------------------------------------ |
| `index.html` | Single-page HTML — header, intersection SVG, status, manual controls, simulation form, history feed |
| `style.css`  | Dark theme, responsive grid layout, signal color tokens |
| `app.js`     | Polling (1 Hz status, 0.2 Hz pending cmd, 0.2 Hz history), DOM rendering, form submissions |

## Stack

Plain HTML + CSS + JavaScript. No build step, no npm. The FastAPI
backend serves these files via `StaticFiles` mount at `/`, so the
dashboard and API share the same origin (no CORS issues).

## How to run

The dashboard is served automatically by the backend. Start the backend
the usual way:

```bash
cd backend
source venv/bin/activate
alembic upgrade head
python -m scripts.seed_junction_a
uvicorn app.main:app --reload --port 8001
```

Then open **<http://127.0.0.1:8001/>** in your browser.

(The Swagger UI is still available at <http://127.0.0.1:8001/docs> for
exploring the API directly.)

## What it shows

- **Alerts panel** — a top banner that classifies the current state
  into red / yellow / green rows. Covers every failure type from the
  spec (§14.6): controller offline, signal/sensor failure,
  desired/actual mismatch, command timeout, unknown device state, and
  "DEGRADED mode" (when the backend is in degraded mode for any
  reason). Empty state shows a green "All clear" pill. The card itself
  gets a red border whenever a critical alert is active.
- **Visual intersection** — cross-shaped SVG with NORTH/SOUTH/EAST/WEST
  signal heads. The light currently showing GREEN/YELLOW/RED on the
  controller is rendered with the matching colour. Lights update every 1s.
- **Status panel** — current mode (AUTOMATIC / MANUAL / EMERGENCY /
  DEGRADED), phase, controller status, queue size per direction,
  pending command id, manual-override / emergency flags.
- **Signals table** — desired vs actual per direction (catches
  situations where the controller is lagging or the backend is in
  transition).
- **Manual control** — four buttons to force a direction green, plus
  a "Return to AUTOMATIC" button. Each sends a `POST` to
  `/api/junctions/{id}/commands`.
- **Simulation form** — send a vehicle event (arrived / cleared, any
  type, any direction, custom vehicle id and sequence number), send a
  device event (controller online/offline/degraded), or send a
  controller ACK for the most recent pending command. Useful for demoing
  the full event flow without curl.
- **Recent activity** — last 20 audit events polled from
  `/api/junctions/{id}/history` every 5 seconds. Shows timestamp,
  event type, direction, and payload.

## Hard rule (still applies)

The frontend must never decide traffic sequencing on its own. Every
signal change comes from the backend; the UI only reflects backend
state. The buttons in the manual-control and simulation panels are
just thin wrappers around the public REST API — they don't mutate
state locally.

## Customising

- **Theme:** change the colour tokens in `style.css` (`--bg`, `--fg`,
  `--green`, etc.).
- **Poll frequency:** change the `setInterval` calls at the bottom of
  `app.js`. (Status is 1s, history is 5s, pending-command is 2s by
  default.)
- **Default junction:** change the `value` of the `<input id="junction-id">`
  in `index.html`. (You can also change it at runtime using the input
  in the header — it triggers a refresh on Enter or blur.)