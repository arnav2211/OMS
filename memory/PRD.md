# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray Aroma Sciences with role-based access (Admin, Accounts, Telecaller, Packaging, Dispatch), Amazon PDF order parsing, advanced notification system, reporting/analytics dashboard, and comprehensive order lifecycle management.

## Core Architecture
- **Backend:** FastAPI + Motor (MongoDB) + Pydantic + JWT Auth
- **Frontend:** React + Tailwind CSS + Shadcn/UI
- **PDF Tools:** pdfplumber, ReportLab, PyPDF2
- **Barcode:** pyzbar + Pillow (server-side), react-image-crop (client-side crop)
- **External APIs:** Shree Anjani Courier serviceability API
- **Real-time Alerts:** Polling-based (3s interval) with Web Audio API alarm

## What's Been Implemented

### Phase 1-4 - Core System through Performance
- Role-based auth, Customer management, Order CRUD, Amazon parsing, Notifications
- Invoice upload with PDF merging, Packing slips, Address labels, Mobile print
- Formulation Lock, Customer data sync, Inline address editing, State dropdown
- Backend pagination, lean projections, compressed PDF logos

### Phase 5 - Dispatch Enhancements
- Courier/Transport slip upload with barcode auto-fill (pyzbar)
- Camera barcode scan, image crop before upload (react-image-crop)
- Packaging role dispatch access, edit dispatch after dispatching
- Copy dispatch details, share dispatch slip

### Phase 6 - Shipping Utilities
- **DTDC Rate Calculator** (`/dtdc`): 28K+ pincode serviceability, rate calculation
- **Shree Anjani Checker** (`/anjani`): Live API serviceability with center/hub/area details

### Phase 7 - Admin Alert System (Latest)
- **Admin Alert Panel** (`/admin-alerts`): Compose alerts with team/individual targeting
- **Real-time Popup**: Full-screen overlay with continuous alarm sound (Web Audio API)
- **Acknowledgement Flow**: Users must click "Acknowledge" to dismiss; sound stops only on ack
- **Alert History**: Admin can track sent alerts, per-user acknowledgement status with timestamps
- **Targeting**: Send to specific users, entire roles, or multiple roles at once
- **Order Context**: Optionally link alerts to specific orders

### Bug Fixes (This Session)
- Fixed Packaging "Pack" dialog (lean projection)
- Fixed PI edit form loading empty
- Fixed duplicate item name image collision
- Fixed /all-orders alias search
- Fixed payment proof visibility in Accounts
- Fixed barcode scanner (libzbar0 system library)
- Removed number input spinners globally
- Added mandatory address selection in all order/PI forms

## Key DB Collections
- **admin_alerts** (NEW): `{ id, title, message, sent_by, recipient_ids[], recipient_roles[], acknowledgements{}, order_id, customer_name, created_at }`

## Mocked APIs
- GST verification (`/api/gst-verify`), Pincode lookup (`/api/pincode`)

## Prioritized Backlog
### P1
- Refactor `server.py` monolith (>3600 lines) into modular FastAPI routers

### P3
- Export to CSV/Excel, WhatsApp dispatch notifications, Audit Log, Payment ledger
