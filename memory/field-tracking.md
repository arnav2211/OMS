---
name: field-tracking
description: How field-executive location tracking is built in the CitSpray OMS
metadata:
  type: project
---

The OMS (CitSpray / Mangalam Agro, FastAPI + React + MongoDB) has a field-executive location tracking feature.

- Role `field_executive` is locked down at the API layer: `get_current_user` in [backend/server.py](backend/server.py) rejects that role for any path outside `FIELD_EXECUTIVE_ALLOWED_PREFIXES` (`/api/auth/`, `/api/location/`). So the account can log in and report location but cannot read orders/customers/PIs even with a valid token.
- Location endpoints: `POST /api/location/ping`, `POST /api/location/batch` (offline buffering supported), admin-only `GET /api/location/executives|history/{id}|staypoints/{id}`. Stay-point clustering groups consecutive fixes within 60m lasting ≥5min. Days are bucketed by IST.
- Frontend: admin page `/tracking` ([FieldTracking.js](frontend/src/pages/admin/FieldTracking.js)) uses Leaflet via CDN (OpenStreetMap, no API key). Field role sees only [FieldHome.js](frontend/src/pages/field/FieldHome.js) — web geolocation foreground fallback.
- Native Android app in [android-app/](android-app/): WebView + Fused Location foreground service for true 24/7 background tracking. Set `OMS_BASE_URL` in `app/build.gradle` before building.

**Why:** Owner wanted 24/7 tracking of field staff on company-owned Android phones. I declined the covert/no-off-switch framing (stalkerware + Android surfaces it anyway via mandatory foreground-service notification); built the disclosed company-device version instead.
