# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray with multi-role access (Admin, Telecaller, Packaging, Dispatch, Accounts), order/customer management, Proforma Invoice creation, PDF generation, and comprehensive workflow management.

## Tech Stack
- **Backend:** FastAPI, Motor (async MongoDB), Pydantic, JWT, Passlib, ReportLab, pdfplumber
- **Frontend:** React, React Router, Tailwind CSS, Shadcn/UI, Axios
- **Database:** MongoDB

## Core Features (Implemented)
- JWT authentication with role-based access
- Customer management with addresses
- Order creation, editing, status workflow
- Proforma Invoice management
- Payment tracking with screenshots
- Packaging dashboard with image uploads
- Dispatch management
- PDF generation
- Tax invoice generation with UPI QR codes
- Formulation management
- Item analytics
- Persistent notification system
- Forward to Packaging (admin)
- Admin full edit power post-dispatch
- Telecaller payment edit post-dispatch

## Amazon PDF Orders Module (Completed - March 2026)
### Overview
Separate module for processing Amazon invoices. Admin uploads PDF → system auto-creates structured orders → packing team processes them.

### Features
- **PDF Upload:** Easy Ship (shipping=Amazon, no courier) and Self Ship (shipping=Courier, select from DTDC/Anjani/Professional/India Post)
- **PDF Parsing:** Extracts customer name, address, phone (self-ship), Amazon Order ID, items (name, qty, price), grand total
- **Separate Collection:** `amazon_orders` — does NOT mix with regular orders
- **AM Numbering:** Sequential AM-0001, AM-0002... via `amazon_counter` collection
- **Duplicate Prevention:** By Amazon Order ID
- **Access Control:** Admin (upload + full), Packaging (view + process), Telecaller (NO access)
- **Packing:** Same logic as /packaging — staff selection, item/order/packed box images, mark packed
- **Dispatch:** Easy Ship = just mark dispatched. Self Ship = optional LR number
- **Admin Override:** Can edit packaging even after dispatch

### Pages
- `/amazon-orders` — Order list with filters, Upload PDF button (admin)
- `/amazon-orders/:id` — Order detail with packaging, dispatch
- `/amazon-packing` — Packing queue for packaging team

### API Endpoints
- `POST /api/amazon/upload-pdf` — Parse PDF, create orders
- `GET /api/amazon/orders` — List all amazon orders
- `GET /api/amazon/orders/{id}` — Single order
- `PUT /api/amazon/orders/{id}/packaging` — Update packaging
- `PUT /api/amazon/orders/{id}/mark-packed` — Mark as packed
- `PUT /api/amazon/orders/{id}/dispatch` — Dispatch order
- `DELETE /api/amazon/orders/{id}/images` — Delete images

## Credentials
- Admin: admin / admin123
- Packaging: test_packaging_user / test123
- Telecaller: test_tc_payment / test123
- Accounts: test_accounts / test123

## Upcoming Tasks
- **P1:** Pagination on all major data tables
- **P2:** Refactor server.py into modular FastAPI routers

## Future/Backlog
- P3: Export to CSV/Excel
- P3: WhatsApp integration
- P3: Audit Log
- P3: Customer payment history ledger

## Known Mocked APIs
- GST verification (`/api/gst-verify/{gst_no}`)
- Pincode lookup (`/api/pincode`)
