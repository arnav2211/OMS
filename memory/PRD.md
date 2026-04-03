# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray Aroma Sciences with role-based access (Admin, Accounts, Telecaller, Packaging, Dispatch), Amazon PDF order parsing, advanced notification system, reporting/analytics dashboard, and comprehensive order lifecycle management.

## Core Architecture
- **Backend:** FastAPI + Motor (MongoDB) + Pydantic + JWT Auth
- **Frontend:** React + Tailwind CSS + Shadcn/UI
- **PDF Tools:** pdfplumber (parsing), ReportLab (generation), PyPDF2 (merging)
- **Barcode:** pyzbar + Pillow (server-side), html5-qrcode (client-side camera scan)
- **External APIs:** Shree Anjani Courier serviceability API
- **Key Pattern:** Lean projections with server-side pagination for list endpoints

## What's Been Implemented

### Phase 1-4 - Core System through Performance
- Role-based auth, Customer management, Order CRUD, Amazon parsing, Notifications
- Invoice upload with PDF merging, Packing slips, Address labels, Mobile print
- Formulation Lock, Customer data sync, Inline address editing, State dropdown
- Backend pagination, lean projections, compressed PDF logos

### Phase 5 - Dispatch Enhancements
- Courier/Transport slip upload with barcode auto-fill (pyzbar)
- Camera barcode scan (html5-qrcode)
- Packaging role dispatch access from Order Detail
- Edit dispatch details after dispatching (admin, packaging, dispatch)
- Copy dispatch details (courier + LR No.)
- Share dispatch slip option

### Phase 6 - Shipping Utilities (Latest)
- **DTDC Rate Calculator** (`/dtdc`): Pincode serviceability check against 28K+ pincodes, weight-based rate calculation with Ground Express vs Standard comparison, series selection (D/M), CEILING to nearest ₹10
- **Shree Anjani Serviceability** (`/anjani`): Live API-based pincode serviceability check showing center details, hub info, serviceable areas with delivery type labels

## Key API Endpoints
- `GET /api/orders`, `GET /api/orders/{id}`, `PUT /api/orders/{id}`
- `PUT /api/orders/{id}/dispatch` - Dispatch with slip images
- `POST /api/scan-barcode` - Barcode detection from image
- `POST /api/dtdc/calculate` - DTDC rate calculation
- `GET /api/dtdc/check/{pincode}` - DTDC serviceability
- `GET /api/anjani/check/{pincode}` - Anjani serviceability (proxied API)

## Mocked APIs
- GST verification (`/api/gst-verify`)
- Pincode lookup (`/api/pincode`)

## Prioritized Backlog
### P1
- Refactor `server.py` monolith (>3500 lines) into modular FastAPI routers

### P3
- Export to CSV/Excel functionality
- WhatsApp integration for dispatch notifications
- Comprehensive Audit Log
- Customer payment history ledger
