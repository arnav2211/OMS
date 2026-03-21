# CitSpray Order Management System - PRD

## Original Problem Statement
Build a comprehensive Order Management System for "CitSpray" (aroma sciences company) with multi-role access, customer management, order lifecycle, proforma invoices, packaging/dispatch workflows, and analytics.

## Core Requirements
- **Authentication:** JWT-based auth with 4 roles (Admin, Telecaller, Packaging, Dispatch)
- **Customer Management:** CRUD with phone/GST/email validation, Address Directory
- **Orders:** Full lifecycle (create → packaging → packed → dispatched), formulations, payment tracking, free samples
- **Proforma Invoices:** PDF generation with bank details and UPI QR codes
- **Dashboard Analytics:** Company-wide and per-executive performance reports with period filters
- **Role-Based Access:** Strict formulation visibility rules per role

## Tech Stack
- Backend: FastAPI + Motor (async MongoDB)
- Frontend: React + Tailwind CSS + Shadcn/UI
- Database: MongoDB
- PDF: ReportLab + QR Code generation (qrcode/pillow)
- Validation: phonenumbers, pydantic

## What's Been Implemented

### Phase 1-4: Foundation & Restructuring
- Authentication, Customer CRUD, Order lifecycle, PI system, Packaging/Dispatch modules
- Printable order sheets, Role-based nav, Date filters, Order deletion

### Phase 5: Major Overhaul
- Customer validation (phone/GST/email), Address Directory, Order enhancements (description, payment mode, rounding)
- Dispatch lock, PI PDF with bank details + UPI QR, Formulation visibility rules, Admin analytics

### Phase 5.1: Fixes & Enhancements (CURRENT - COMPLETED)
1. **Admin Dashboard Report Fixes** - My Report and Executive Report now work correctly using query param API
2. **Date Filter Improvements** - Both reports support This Month (default), This Week, Today, Custom Date Range
3. **Free Samples Feature** - Optional free samples (item_name + description) in Order and PI creation, visible in Order Detail and PDFs
4. **Order Detail Bug Fix** - Fixed "Order not found" error (useParams mismatch: orderId vs id)
5. **Formulation Access Control** - Strict: Admin=ALWAYS, Packaging=toggle-dependent, Telecaller/Dispatch=NEVER
6. **Customer Address Management** - After creating new customer, address dialog opens automatically
7. **Order Detail Images** - Payment proof, item images, order images, packed box images all visible with clickable preview
8. **Admin Account Protection** - Cannot deactivate admin account (UI button hidden + backend guard)

## Testing Status
- Phase 5 Backend: 100% (25/25)
- Phase 5.1 Backend: 100% (20/20)
- Phase 5.1 Frontend: 100%
- Test reports: /app/test_reports/iteration_5.json, /app/test_reports/iteration_6.json

## Key Endpoints
- POST /api/auth/token - Login
- GET/POST/PUT/DELETE /api/customers - Customer CRUD
- GET/POST/PUT/DELETE /api/customers/{id}/addresses - Address Directory
- GET /api/pincode/{pincode} - Pincode auto-fill
- GET/POST /api/orders - Order CRUD (includes free_samples)
- PUT /api/orders/{id}/formulation - Update formulations (Admin + Packaging when toggle ON)
- GET /api/orders/{id}/print?token= - Print order PDF
- GET/POST/PUT/DELETE /api/proforma-invoices - PI CRUD (includes free_samples)
- GET /api/proforma-invoices/{id}/pdf?token= - PI PDF with bank details + QR
- GET /api/reports/admin-analytics - Company analytics with period/filters
- GET /api/reports/telecaller-sales?telecaller_id=X&period=Y - Executive/My Report

## Backlog (P2/P3)
- [ ] Pagination on all list endpoints
- [ ] Export to CSV/Excel
- [ ] WhatsApp integration for dispatch notifications
- [ ] Audit log for all changes
- [ ] Customer payment history ledger
