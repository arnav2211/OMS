# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray Aroma Sciences with role-based access (Admin, Accounts, Telecaller, Packaging, Dispatch), Amazon PDF order parsing, advanced notification system, reporting/analytics dashboard, and comprehensive order lifecycle management.

## Core Architecture
- **Backend:** FastAPI + Motor (MongoDB) + Pydantic + JWT Auth
- **Frontend:** React + Tailwind CSS + Shadcn/UI
- **PDF Tools:** pdfplumber (parsing), ReportLab (generation), PyPDF2 (merging)
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
- GST/Non-GST and Invoice Upload Status columns

### Bug Fixes (Latest)
- [2026-04-02] Fixed Packaging "Pack" dialog not showing items/upload options (lean projection issue - openOrder now fetches full order detail)
- Fixed formulation data loss on order update (safe $set merging)
- Fixed executive report period filter (IST timezone)
- Fixed mobile print popup blocker issues

## Key API Endpoints
- `GET /api/orders` - Paginated, lean projection, server-side search
- `GET /api/orders/{id}` - Full order detail
- `PUT /api/orders/{id}` - Safe merge update (preserves formulations)
- `PUT /api/orders/{id}/packaging` - Packaging status update
- `POST /api/orders/{id}/request-edit` - Formulation lock edit request
- `PUT /api/admin/edit-permissions/{id}` - Admin approval
- `POST /api/orders/{id}/invoice-upload` - Tax + E-Way merge
- `GET /api/orders/{id}/print` - Packing slip PDF

## Key DB Collections
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
