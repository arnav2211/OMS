# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray with multi-role access (Admin, Telecaller, Packaging, Dispatch, Accounts), order/customer management, Proforma Invoice creation, PDF generation, and comprehensive workflow management.

## Tech Stack
- **Backend:** FastAPI, Motor (async MongoDB), Pydantic, JWT, Passlib, ReportLab, pdfplumber
- **Frontend:** React, React Router, Tailwind CSS, Shadcn/UI, Axios
- **Database:** MongoDB

## Amazon PDF Orders Module (Latest Updates - March 2026)
### Core
- Admin uploads Easy Ship / Self Ship PDF invoices
- System parses and creates orders in `amazon_orders` collection (separate from regular orders)
- AM-XXXX sequential numbering via `amazon_counter`
- Duplicate prevention by Amazon Order ID

### Upload
- Easy Ship: shipping=Amazon, no courier
- Self Ship: shipping=Courier, **courier NOT selected during upload** — set manually per order later

### Access Control
- Admin: upload + full access + delete
- Packaging: view + packing + dispatch + courier edit
- Dispatch: dispatch + courier edit + view
- Telecaller: NO access

### Pages
- `/amazon-orders` — List with status + ship type filters. Upload (admin), Delete (admin, non-dispatched)
- `/amazon-orders/:id` — Detail with packaging, dispatch
- `/amazon-packing` — Packing queue with image uploads
- `/amazon-dispatch` — Two tabs: Easy Ship (bulk multi-select dispatch), Self Ship (courier edit + mandatory LR dispatch)

### Dispatch Rules
- Easy Ship: bulk select + dispatch (no LR needed)
- Self Ship: must assign courier first, then dispatch with **mandatory** LR number
- PDF deleted from server after parsing

### API Endpoints
- `POST /api/amazon/upload-pdf` — Parse PDF, create orders
- `GET /api/amazon/orders` — List all
- `GET /api/amazon/orders/{id}` — Single order
- `PUT /api/amazon/orders/{id}/packaging` — Update packaging
- `PUT /api/amazon/orders/{id}/mark-packed` — Mark packed
- `PUT /api/amazon/orders/{id}/dispatch` — Dispatch (LR mandatory for self_ship)
- `POST /api/amazon/orders/bulk-dispatch` — Bulk dispatch easy_ship
- `PUT /api/amazon/orders/{id}/courier` — Update courier name
- `DELETE /api/amazon/orders/{id}` — Delete order (admin, non-dispatched)
- `DELETE /api/amazon/orders/{id}/images` — Delete images

## Invoice Upload Enhancement (March 2026)
- Upload modal with Tax Invoice (mandatory) + E-Way Bill (optional)
- PDFs merged server-side via PyPDF2 (Tax Invoice first, E-Way Bill second)
- Single combined PDF stored, used for viewing/download/sharing
- Endpoint: `POST /api/orders/{id}/invoice-upload` (multipart: tax_invoice, eway_bill)
- Applies to both Accounts Dashboard and Admin Accounts view

## Credentials
- Admin: admin / admin123
- Packaging: test_packaging_user / test123
- Dispatch: test_dispatch_user / test123
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
