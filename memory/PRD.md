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

## UI/UX Enhancements (March 2026 - Batch 2)
- Customer GST number displayed in Order Summary with copy button
- Addresses formatted in multi-line readable format with copy buttons (billing + shipping)
- Customer edit option added to Create Order, Edit Order, Create PI, Edit PI forms
- Free samples now support formulation (same role-based visibility rules)
- Extra Shipping Details optional field in order creation/editing, shown in Order Summary
- GST/Non-GST column in All Orders for Accounts role
- GST Invoice Upload Status column (Uploaded/Pending/Not Required) in All Orders for non-Accounts roles
- Mobile print fix: improved popup handling and iframe fallback for Android

## Phase 16 Enhancements (March 2026 - Batch 3)
- Executive Reports period filter fixed (uses IST timezone for Today/Yesterday/Week/Month)
- Pincode auto-fill removed; replaced with searchable Indian States/UTs dropdown
- Customer Alias field added (searchable alongside name, phone, GST)
- Dispatch page Order IDs now clickable (link to Order Summary)
- Packing role can update dispatch fields from Order Summary
- Admin + Packing can Mark Packed / Undo Packed from Order Summary
- Packing role gets Share Images (all + packed box) in Order Summary
- New endpoints: `PUT /api/orders/{id}/mark-packed`, `PUT /api/orders/{id}/undo-packed`

## Credentials
- Admin: admin / admin123
- Packaging: test_packaging_user / test123
- Dispatch: test_dispatch_user / test123
- Telecaller: test_tc_payment / test123
- Accounts: test_accounts / test123

## Edit Formulation Enhancement (March 2026)
- Item description now displayed alongside product name in Edit Formulation dialog
- Format: "Product Name — Description  Qty: X unit  Amt: ₹Y"
- Description shown only when available, hidden gracefully when empty

## Alias Unification (March 2026)
- Alias is stored centrally on the customer document (single source of truth)
- `PUT /api/customers/{id}` propagates `customer_name` to all orders & PIs when customer is updated
- All detail and list endpoints enrich with latest customer data (name, alias, phone, GST, email)
- Alias shown in: Order Detail, All Orders table, PI list, Packaging table, Dispatch table
- All Orders search expanded: order #, customer name, alias, phone, GST

## Customer Master Data Sync (March 2026)
- All customer-linked data (name, alias, phone, GST, email) stays synced across the system
- `PUT /api/customers/{id}` propagates `customer_name` to all orders & PIs documents
- `GET /api/orders/{id}` and `GET /api/proforma-invoices/{id}` enrich with full live customer data
- Order/PI list endpoints enrich phone, GST, alias from customer at query time
- Duplicate order/PI and Convert PI endpoints fetch live customer name
- PDF generation always fetches fresh customer data from DB
- OrderDetail.js uses enriched order response (no separate customer API call needed)

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
