# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray with multi-role access (Admin, Telecaller, Packaging, Dispatch, Accounts), order/customer management, Proforma Invoice creation, PDF generation, and comprehensive workflow management.

## Tech Stack
- **Backend:** FastAPI, Motor (async MongoDB), Pydantic, JWT, Passlib, ReportLab
- **Frontend:** React, React Router, Tailwind CSS, Shadcn/UI, Axios
- **Database:** MongoDB

## Core Features (Implemented)
- JWT authentication with role-based access
- Customer management with addresses
- Order creation, editing, status workflow (new -> packaging -> packed -> dispatched)
- Proforma Invoice (PI) creation, editing, PDF generation, PI-to-order conversion
- Payment tracking with screenshots
- Packaging dashboard with image uploads
- Dispatch management
- PDF generation (order prints, address labels, PI PDFs)
- Tax invoice generation with UPI QR codes
- Formulation management
- Item analytics

## Phase 10 Features (Completed - March 2026)
1. Forward to Packaging (Admin toggle in All Orders)
2. Tax Invoice Filter (Accounts - Uploaded/Pending)
3. Remove Local Charges from all forms
4. Telecaller Payment Edit (own orders, even after dispatch)
5. Admin Full Edit Power (everything, even after dispatch)
6. Image Upload in Packaging Update dialog (Order Summary)

## Phase 10.1 - Accounts Dashboard Payment Check Fixes (Completed - March 2026)
1. Date filter fix — filters by order creation date (client-side)
2. New columns: Mode of Payment, Date of Order, GST/Non-GST badge, Payment Proof preview
3. Payment screenshot preview dialog

## Phase 11 - Notifications & Share Features (Completed - March 2026)
1. **Share Packed Box Images** — Renamed "Share Images" to "Share All Images". Added new "Share Packed Box Images" button that shares only packed box images (not item/order images).
2. **Persistent Notification System** — New `notifications` MongoDB collection. Backend endpoints: POST /api/notifications (create, idempotent), GET /api/notifications (unacknowledged), PUT /api/notifications/{id}/acknowledge. Notifications persist until manually acknowledged.
3. **Notification Box on Dashboard** — Fixed-height scrollable box at top of telecaller dashboard. Shows Packed/Dispatched badge, clickable order ID (navigates to order summary), customer name, thumbs-up acknowledge button.
4. **Notification Sound & Mobile Popup** — Sound plays on new notifications (desktop & mobile). Toast popups appear immediately. Bell icon in header shows count and navigates to dashboard.
5. **Trigger Logic Unchanged** — Porter/Self Arranged/Office Collection → notifies on Packed. Courier/Transport → notifies on Dispatched.

## Credentials
- Admin: admin / admin123
- Accounts: test_accounts / test123
- Telecaller: test_tc_payment / test123

## Upcoming Tasks
- **P1:** Pagination on all major data tables
- **P2:** Refactor server.py into modular FastAPI routers

## Future/Backlog
- P3: Export to CSV/Excel
- P3: WhatsApp integration for dispatch notifications
- P3: Comprehensive Audit Log
- P3: Customer payment history ledger

## Known Mocked APIs
- GST verification (`/api/gst-verify/{gst_no}`)
- Pincode lookup (`/api/pincode`)
