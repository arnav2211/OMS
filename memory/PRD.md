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

## Phase 8 Features (Completed - March 2026)
1. Print Behavior Fix
2. Customer Deletion Restriction - Admin-only with two-step confirmation
3. Negative Value Restriction
4. Additional Charges System
5. Copyable Details
6. Shipping Method Column
7. Edit Shipping in Dispatch
8. Duplicate Order/PI
9. Mobile Camera Upload Fix
10. Camera in Edit Mode

## Phase 9 Features (Completed - March 2026)
1. Charges UI Restructured
2. Image Compression

## Phase 10 Features (Completed - March 2026)
1. Forward to Packaging (Admin toggle in All Orders)
2. Tax Invoice Filter (Accounts - Uploaded/Pending)
3. Remove Local Charges from all forms
4. Telecaller Payment Edit (own orders, even after dispatch)
5. Admin Full Edit Power (everything, even after dispatch)
6. Image Upload in Packaging Update dialog (Order Summary)

## Phase 10.1 - Accounts Dashboard Payment Check Fixes (Completed - March 2026)
1. **Date filter fix** — Now filters by order creation date (client-side). Works for Today, This Week, This Month, Custom range.
2. **New columns added** — Mode of Payment, Date of Order, GST/Non-GST badge, Payment Proof preview button.
3. **Payment screenshot preview** — Eye icon button with count opens a dialog showing all payment screenshots with clickable full-size images.

## Credentials
- Admin: admin / admin123
- Accounts: test_accounts / test123, accounts1

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
