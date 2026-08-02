---
name: dtdc-booking
description: DTDC Excel export/booking system and the plan to auto-book via DTDC API
metadata:
  type: project
---

DTDC booking in the OMS is driven by [DTDCExportDialog.js](frontend/src/components/DTDCExportDialog.js) (frontend, `xlsx` lib). Weight + destination pincode → `POST /api/dtdc/calculate` returns a series; the sheet is filled and downloaded, then manually uploaded to the DTDC portal.

Account routing (3 DTDC accounts, all "RL" client codes):
- **RL1386** → D-Series → GROUND EXPRESS
- **RL1423** → M-Series → STD EXP-A
- **RL1387** → carrier-risk orders (`carrier_risk_applicable`), handles BOTH service types with Risk Surcharge column = "1"; service type still auto-picked by weight/pincode. Added 2026-07 (frontend-only, zero-downtime). Export now emits up to 3 files partitioned by Client Code.

**Part 2 (planned, not built): auto-book on weight entry via the official DTDC API.** User chose the API path over portal RPA. DTDC offers a Softdata/Consignment-Booking API (books from your system, routes by account/weight, returns the AWB, ≤20 consignments/request). BLOCKED ON: user getting API credentials from their DTDC rep for RL1386/1387/1423. Once creds + API spec arrive, move booking to the backend, hook it on `PUT /orders/{id}/packaging` (weight save), store the returned AWB into courier_name/lr_no. Backend deploy → use blue-green for zero downtime (see [[vps-deploy]]). DTDC portal creds were shared in chat once (RL accounts) — user asked to rotate them; store only in backend `.env`, never in code.

**DTDC API integration (built 2026-08, replaces the Excel).** DTDC's customer API is Shipsy-hosted — base URL is **`https://app.shipsy.in`**, NOT customer.dtdc.in (the playground at customer.dtdc.in/api-playground documents it and shows "API Server https://app.shipsy.in"). Auth is an `api-key` header, one **per account**. Endpoints: book `POST /api/customer/integration/consignment/upload/softdata/v2`, track `GET .../consignment/track?reference_number=`, label `GET .../consignment/shippinglabel/stream?reference_number=`, cancel `POST .../consignment/cancel`. Keys live in backend `.env` as `DTDC_API_KEY_RL1386/RL1387/RL1423`. Service strings are env-overridable (`DTDC_SERVICE_GROUND`/`DTDC_SERVICE_STD`) because DTDC's API may want different codes than the Excel's "GROUND EXPRESS"/"STD EXP-A" — CONFIRM on the first real booking. `dtdc_quote_for()` is the shared series/rate helper used by both the calculator and booking so they route identically.

Do NOT build portal RPA (customer.dtdc.in) — fragile, breaks on UI changes, blocked by any CAPTCHA/OTP, ToS risk.

**Amazon Shipping serviceability (LIVE since 2026-07-31).** `GET /api/amazon/check/{pincode}` uses Amazon Shipping API v2 `POST {endpoint}/shipping/v2/shipments/rates` — serviceable iff `payload.rates` is non-empty. Credentials in backend `.env` as `AMAZON_SHIP_*` (endpoint = `https://sellingpartnerapi-eu.amazon.com`; India is served by the EU region). Hard-won payload requirements, each found by live 400s:
1. `packages[].items` is MANDATORY (else `InvalidInput ... packages.1.member.items must not be null`).
2. Root-level `taxDetails: [{taxType: "GST", taxRegistrationNumber: <GSTIN>}]` is MANDATORY for Indian accounts.
3. Destination `city`/`stateOrRegion` must be REAL — placeholders like "NA" return `NO_COVERAGE (A-306)` even for covered pincodes. Resolved via `_resolve_pincode_geo()` (local DTDC table → api.postalpincode.in, cached).
4. Amazon returns duplicate rate rows; dedupe by (serviceId, amount).
Verified live: 440025 Nagpur ₹40 (Express+Standard), 110001 ₹65, 560001 ₹65; 400001 Mumbai genuinely NO_COVERAGE. Rates are weight-dependent (110001: 1kg ₹65, 5kg ₹233).

**Amazon booking + label (LIVE, first real booking done 2026-07-31 — order CS-1183).** `POST /amazon/quote` (read-only) then `POST /amazon/book` (purchases — real money + pickup, so the UI always confirms first; never auto-book). Booking stores `order.amazon_shipment` {shipment_id, tracking_id, service, amount, label_base64 (PNG), ...} and writes tracking into `dispatch`. `GET /amazon/label/{order_id}` renders it.
Label gotcha: do NOT use SimpleDocTemplate — its Frame adds 6pt padding per side, so an image scaled to the margin box raises `LayoutError: too large on page`. Draw on a raw `pdfgen.Canvas` instead. Amazon returns portrait 4x6 labels (1216x1824 px); rotating them 90° onto landscape A5 prints 7.80x5.20in vs ~3.6x5.4in unrotated, keeping the barcode scannable.
