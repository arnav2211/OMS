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

## Phase 10 Features (Completed)
1. Forward to Packaging (Admin toggle in All Orders)
2. Tax Invoice Filter (Accounts - Uploaded/Pending)
3. Remove Local Charges from all forms
4. Telecaller Payment Edit (own orders, even after dispatch)
5. Admin Full Edit Power (everything, even after dispatch)
6. Image Upload in Packaging Update dialog (Order Summary)

## Phase 10.1 - Accounts Dashboard Fixes (Completed)
1. Date filter fix — filters by order creation date
2. New columns: Mode of Payment, Date, GST/Non-GST, Payment Proof preview

## Phase 11 - Notifications & Share (Completed)
1. Share Packed Box Images — separate button for packed box images only
2. Persistent Notification System — DB-backed, acknowledge to dismiss
3. Notification Box on Dashboard — fixed height, scrollable
4. Sound & Mobile Popup on new notifications

## Phase 12 - Latest Changes (Completed - March 2026)
1. **Shipping Details in Order Summary** — New card between Customer Info and Items showing shipping method and courier/transport name. Visible to all roles.
2. **Shipping Column in Packaging Queue** — Added Shipping column showing method and name (same format as All Orders page).
3. **Executive Performance Date Filter** — Independent date filter (Today default, Yesterday, This Week, This Month, Custom) for the Executive Performance table in Analytics. Shows order count and revenue per executive for the selected period. Backend updated with "yesterday" period support.

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
