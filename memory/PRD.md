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
- Order creation, editing, status workflow (new → packaging → packed → dispatched)
- Proforma Invoice (PI) creation, editing, PDF generation, PI-to-order conversion
- Payment tracking with screenshots
- Packaging dashboard with image uploads
- Dispatch management
- PDF generation (order prints, address labels, PI PDFs)
- Tax invoice generation with UPI QR codes
- Formulation management
- Item analytics

## Phase 8 Features (Completed - March 2026)
1. **Print Behavior Fix** - Print triggers browser print dialog directly via iframe
2. **Customer Deletion Restriction** - Admin-only with two-step confirmation
3. **Negative Value Restriction** - min=0 on Rate/Amount in all order/PI forms
4. **Additional Charges System** - Dynamic entries with name, amount, GST% per charge
5. **Copyable Details** - Phone, billing/shipping address on Order Detail (click-to-copy)
6. **Shipping Method Column** - Added to All Orders table
7. **Edit Shipping in Dispatch** - Editable shipping method in dispatch dashboard
8. **Duplicate Order/PI** - Duplicate button pre-fills new form
9. **Mobile Camera Upload Fix** - Backend handles missing/wrong extensions from cameras
10. **Camera in Edit Mode** - Camera buttons alongside Gallery/Files in edit forms

## API Endpoints
- `POST /api/auth/login` - JWT login
- `GET/POST /api/customers` - List/Create customers
- `DELETE /api/customers/{id}` - Admin-only delete
- `GET/POST /api/orders` - List/Create orders
- `PUT /api/orders/{id}` - Update order
- `PUT /api/orders/{id}/packaging` - Update packaging
- `PUT /api/orders/{id}/dispatch` - Dispatch order
- `PUT /api/orders/{id}/shipping-method` - Update shipping method (Admin/Dispatch/Packaging)
- `POST /api/orders/{id}/duplicate` - Get order data for duplication
- `POST /api/proforma-invoices/{id}/duplicate` - Get PI data for duplication
- `GET/POST /api/proforma-invoices` - List/Create PIs
- `PUT /api/proforma-invoices/{id}` - Update PI
- `POST /api/upload` - File upload (camera-compatible)

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
