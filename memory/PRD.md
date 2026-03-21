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

### Phase 5.1: Fixes & Enhancements (COMPLETED)
1. Admin Dashboard Report Fixes, Date Filter Improvements
2. Free Samples Feature in Orders and PIs
3. Order Detail Bug Fix (useParams mismatch)
4. Formulation Access Control (Admin + Packaging with toggle)
5. Customer Address Management improvements
6. Order Detail Images all visible with clickable preview
7. Admin Account Protection against deactivation

### Phase 7: Critical Fixes & Major Features (COMPLETED - 2026-03-21)
1. **Full Order Edit Control** - New `/orders/:orderId/edit` page (EditOrder.js)
   - Admin: full form (customer, items, pricing, addresses, payment, shipping)
   - Telecaller: own orders only, full form
   - Packaging: packaging section only (images, packed by, status)
   - Dispatch: dispatch section only (courier, LR no., status)
   - Dispatch lock: no editing once dispatched
2. **Fix PI → Order Conversion** - Route `/pi/:piId/convert` added, CreateOrder.js pre-fills from PI data, marks PI as "converted" on submit
3. **Remove Delete User** - Delete button removed from UserManagement.js (admin panel)
4. **Formulation Save Bug** - Backend fixed to match items by position; Textarea import fixed in OrderDetail.js
5. **Image Management** - Delete X buttons on payment screenshots and packaging images; `DELETE /api/orders/{id}/images` endpoint
6. **Telecaller Notifications** - 30s polling in Layout.js; toast + audio beep for packed/dispatched orders; notification bell counter
7. **Bulk Shipping Address Print** - Checkboxes in AllOrders.js for admin/packaging; `POST /api/orders/print-addresses` generates A4 2-column PDF

## Testing Status
- Phase 5 Backend: 100% (25/25)
- Phase 5.1: 100%
- Phase 7: 100% (25/25 backend, 100% frontend)
- Test reports: /app/test_reports/iteration_5.json, /app/test_reports/iteration_6.json, /app/test_reports/iteration_7.json

## Key Endpoints
- POST /api/auth/token - Login
- GET/POST/PUT/DELETE /api/customers - Customer CRUD
- GET/POST/PUT/DELETE /api/customers/{id}/addresses - Address Directory
- GET /api/pincode/{pincode} - Pincode auto-fill
- GET/POST /api/orders - Order CRUD (includes free_samples)
- PUT /api/orders/{id} - Update full order (admin/telecaller)
- PUT /api/orders/{id}/formulation - Update formulations
- PUT /api/orders/{id}/packaging - Update packaging data/status
- PUT /api/orders/{id}/dispatch - Dispatch order
- DELETE /api/orders/{id}/images - Remove single image (payment/packaging)
- POST /api/orders/print-addresses - Bulk address PDF generation
- GET /api/orders/my-notifications?since= - Telecaller status change notifications
- GET /api/orders/{id}/print?token= - Print order PDF
- GET/POST/PUT/DELETE /api/proforma-invoices - PI CRUD
- GET /api/proforma-invoices/{id}/pdf?token= - PI PDF with bank details + QR
- GET /api/reports/admin-analytics - Company analytics
- GET /api/reports/telecaller-sales - Executive/My Report

## Backlog (P2/P3)
- [ ] Pagination on all list endpoints (known performance risk)
- [ ] Export to CSV/Excel
- [ ] WhatsApp integration for dispatch notifications
- [ ] Audit log for all changes
- [ ] Customer payment history ledger
- [ ] server.py modularization into FastAPI routers (1900+ lines)
