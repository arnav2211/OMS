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
1. Print Behavior Fix - Desktop: auto-triggers print dialog via iframe. Mobile: opens PDF in new window with auto-print
2. Customer Deletion Restriction - Admin-only with two-step confirmation
3. Negative Value Restriction - min=0 on all Rate/Amount inputs
4. Additional Charges System - Dynamic entries with name, amount, GST% per charge
5. Copyable Details - Phone, billing/shipping address on Order Detail (click-to-copy)
6. Shipping Method Column - Added to All Orders table
7. Edit Shipping in Dispatch - Editable shipping method in dispatch dashboard
8. Duplicate Order/PI - Duplicate button pre-fills new form
9. Mobile Camera Upload Fix - Backend handles missing/wrong extensions from cameras
10. Camera in Edit Mode - Camera buttons alongside Gallery/Files in edit forms

## Phase 9 Features (Completed - March 2026)
1. Charges UI Restructured - 3 separate sections: Shipping Charges, Additional Charges
2. Image Compression - All image uploads compressed before upload (max 1280px, JPEG quality 0.7)

## Phase 10 Features (Completed - March 2026)
1. **Forward to Packaging (Admin)** - Toggle button in All Orders "Fwd Pkg" column. Admin can mark orders as forwarded to packaging (visual reference only).
2. **Tax Invoice Filter (Accounts)** - Filter in Accounts Dashboard for invoices: All / Uploaded / Pending Upload.
3. **Remove Local Charges** - Removed "Local Charges" input from Create Order, Edit Order, Create PI, Edit PI. Only Shipping Charges remain.
4. **Telecaller Payment Edit** - Telecallers can edit payment details (status, mode, screenshots) on their own orders even after dispatch. New PaymentSection component with inline edit.
5. **Admin Full Edit Power** - Admins can edit everything in an order even after dispatch. No dispatch lock for admins.
6. **Image Upload in Order Summary** - PackagingForm in Order Detail now includes full image upload/edit/delete (item images, order images, packed box images). Admin can edit anytime, Packaging team can edit pre-dispatch.

## Credentials
- Admin: admin / admin123

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
