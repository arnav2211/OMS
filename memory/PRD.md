# CitSpray Order Management System - PRD

## Original Problem Statement
Build a comprehensive Order Management System for "CitSpray" (aroma sciences company) with multi-role access, customer management, order lifecycle, proforma invoices, packaging/dispatch workflows, and analytics.

## Core Requirements
- **Authentication:** JWT-based auth with 4 roles (Admin, Telecaller, Packaging, Dispatch)
- **Customer Management:** CRUD with phone/GST/email validation, Address Directory
- **Orders:** Full lifecycle (create → packaging → packed → dispatched), formulations, payment tracking
- **Proforma Invoices:** PDF generation with bank details and UPI QR codes
- **Dashboard Analytics:** Company-wide and per-executive performance reports
- **Role-Based Access:** Strict formulation visibility rules per role

## Tech Stack
- Backend: FastAPI + Motor (async MongoDB)
- Frontend: React + Tailwind CSS + Shadcn/UI
- Database: MongoDB
- PDF: ReportLab + QR Code generation (qrcode/pillow)
- Validation: phonenumbers, pydantic

## User Personas
1. **Admin** - Full access, analytics, user management, settings
2. **Telecaller (Executive)** - Customer/order CRUD, own sales reports
3. **Packaging** - View/update packaging, formulations (when toggle ON)
4. **Dispatch** - View packed orders, mark as dispatched

## What's Been Implemented

### Phase 1-2: Foundation
- Authentication system with JWT
- Customer CRUD
- Order CRUD with full lifecycle
- Basic dashboard

### Phase 3: Packaging & Dispatch
- Packaging module with multi-select staff fields
- Dispatch workflow with shipping types
- Printable order sheet for packaging
- Role-based navigation

### Phase 4: Restructuring
- Auth fix for print endpoints (token query param)
- Order deletion with double confirmation
- Dedicated "All Orders" page
- Custom date range filters for reports
- 100% test pass rate

### Phase 5: Major Overhaul (CURRENT - COMPLETED)
1. **Customer Validation** - Phone normalization to +91XXXXXXXXXX, 6-digit pincode validation, GST format validation, optional email validation
2. **Address Directory** - Multiple addresses per customer with CRUD, pincode auto-fill (city/state), selection during order/PI creation with "Same as Billing" checkbox
3. **Order Enhancements** - Item description field, Mode of Payment (Cash/Online/Other), mandatory Math.ceil rounding on totals
4. **Dispatch Lock** - Editing disabled after dispatch (except formulation and payment)
5. **PI Improvements** - Customer creation within PI module, address handling, improved PDF layout with phone number
6. **PI Payment Details** - Bank details (GST: Mangalam Agro PNB, Non-GST: Arnav Mukul Agrawal PNB), dynamic UPI QR codes
7. **All Orders Filter** - Admin filters by executive, Telecaller toggle for own/all
8. **Formulation Visibility** - Telecaller: NEVER, Packaging: toggle-dependent, Admin: ALWAYS, Dispatch: NEVER
9. **Admin Dashboard** - Company analytics with period/GST/shipping filters, My Report tab, Executive Reports tab, removed Sales Report
10. **Order PDF Fix** - Formulation displayed beside each item (not at bottom)

## Testing Status
- Phase 5 Backend: 100% (25/25 tests passed)
- Phase 5 Frontend: 95% (all features functional, minor navigation flash)
- Test reports: /app/test_reports/iteration_5.json

## Mocked APIs
- GST Verification: /api/gst-verify/{gst_no} (returns state based on first 2 digits)
- Pincode Lookup: External API with local fallback mapping

## Key Endpoints
- POST /api/auth/token - Login
- GET/POST/PUT/DELETE /api/customers - Customer CRUD
- GET/POST/PUT/DELETE /api/customers/{id}/addresses - Address Directory
- GET /api/pincode/{pincode} - Pincode auto-fill
- GET/POST /api/orders - Order CRUD
- PUT /api/orders/{id}/formulation - Update formulations
- PUT /api/orders/{id}/packaging - Update packaging
- PUT /api/orders/{id}/dispatch - Dispatch order
- DELETE /api/orders/{id}/delete - Delete order
- GET /api/orders/{id}/print?token= - Print order PDF
- GET/POST/PUT/DELETE /api/proforma-invoices - PI CRUD
- GET /api/proforma-invoices/{id}/pdf?token= - Download PI PDF with bank details & QR
- GET /api/reports/admin-analytics - Company-wide analytics
- GET /api/reports/telecaller-sales/{id} - Executive report

## Backlog (P2/P3)
- [ ] Pagination on all list endpoints (deployment agent warning)
- [ ] Export to CSV/Excel
- [ ] WhatsApp integration for dispatch notifications
- [ ] Audit log for all changes
- [ ] Customer payment history ledger
- [ ] Server-side search/filtering optimization
