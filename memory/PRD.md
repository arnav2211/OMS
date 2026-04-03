# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray Aroma Sciences with role-based access (Admin, Accounts, Telecaller, Packaging, Dispatch), Amazon PDF order parsing, advanced notification system, reporting/analytics dashboard, and comprehensive order lifecycle management.

## Core Architecture
- **Backend:** FastAPI + Motor (MongoDB) + Pydantic + JWT Auth
- **Frontend:** React + Tailwind CSS + Shadcn/UI
- **PDF Tools:** pdfplumber (parsing), ReportLab (generation), PyPDF2 (merging)
- **Barcode:** pyzbar + Pillow (server-side), html5-qrcode (client-side camera scan)
- **Key Pattern:** Lean projections with server-side pagination for list endpoints

## What's Been Implemented

### Phase 1 - Core System
- Role-based authentication and routing
- Customer management with Alias field
- Order CRUD with full lifecycle (new -> packaging -> packed -> dispatched)
- Amazon PDF order parsing
- Persistent notification system

### Phase 2 - Invoicing & Documents
- Invoice upload modal with PyPDF2 merging (Tax + E-Way Bill)
- Packing slip PDF generation with compressed logo
- Address label printing with multiple copies
- Mobile print via Web Share API

### Phase 3 - Data Integrity & UX
- Formulation Lock system with Admin edit permission flow
- Customer master data live-sync (no stale snapshots)
- Inline address editing in Create/Edit Order and PI flows
- Address Name field for dispatch clarity
- State/UT dropdown validation (INDIAN_STATES)
- Free sample formulation support

### Phase 4 - Performance Optimization
- Backend pagination & server-side search for all major lists
- Lean projections excluding heavy nested data from list views
- Compressed logo_pdf.png for PDF generation

### Phase 5 - Dispatch Enhancements (Latest)
- **Courier/Transport Slip Upload:** Admin, Packaging, Dispatch can upload slip images during dispatch
- **Barcode Auto-Fill:** Uploaded slip images scanned for barcodes; LR No. auto-filled if detected
- **Camera Barcode Scan:** Manual camera scan option to read barcodes directly
- **Packaging Dispatch Access:** Packaging role can dispatch from Order Detail page
- **Slip images stored** in `dispatch.dispatch_slip_images` array and displayed in order detail

### Bug Fixes (Latest Session)
- [2026-04-03] Fixed Packaging "Pack" dialog not showing items/upload options (lean projection)
- [2026-04-03] Fixed PI edit form loading empty (lean projection - now fetches full PI)
- [2026-04-03] Fixed duplicate item name image collision (composite key product_name__idx)
- [2026-04-03] Fixed /all-orders alias search (pre-lookup customers by alias)
- [2026-04-03] Fixed payment proof not visible in Accounts dashboard (removed from lean exclusion)

## Key API Endpoints
- `GET /api/orders` - Paginated, lean projection, server-side search (incl. alias)
- `GET /api/orders/{id}` - Full order detail
- `PUT /api/orders/{id}` - Safe merge update (preserves formulations)
- `PUT /api/orders/{id}/dispatch` - Dispatch with slip images support
- `POST /api/scan-barcode` - Barcode detection from uploaded image (pyzbar)
- `PUT /api/orders/{id}/packaging` - Packaging status update
- `POST /api/orders/{id}/request-edit` - Formulation lock edit request
- `POST /api/orders/{id}/invoice-upload` - Tax + E-Way merge
- `GET /api/orders/{id}/print` - Packing slip PDF

## Key DB Schema
- **orders.dispatch:** `{ courier_name, transporter_name, lr_no, dispatch_slip_images: [], dispatched_by, dispatched_at }`
- **orders:** `{ formulation_locked, extra_shipping_details, items[].formulation, ... }`
- **customers:** `{ alias, phone_numbers, gst_no, ... }`
- **addresses:** `{ address_name, ... }`
- **edit_permissions:** `{ order_id, requested_by, status, remark, ... }`

## Mocked APIs
- GST verification (`/api/gst-verify`)
- Pincode lookup (`/api/pincode`)

## Prioritized Backlog
### P1
- Refactor `server.py` monolith (>3400 lines) into modular FastAPI routers

### P3
- Export to CSV/Excel functionality
- WhatsApp integration for dispatch notifications
- Comprehensive Audit Log
- Customer payment history ledger
