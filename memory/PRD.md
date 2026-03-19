# CitSpray Order Management System - PRD

## Original Problem Statement
Build a comprehensive Order Management System for "CitSpray" company with roles: Admin, Telecaller, Packaging, Dispatch. Workflow includes order creation, formulation management, packaging tracking, and dispatch handling.

## Tech Stack
- **Backend**: FastAPI + Motor (async MongoDB)
- **Frontend**: React + Tailwind CSS + Shadcn/UI
- **Database**: MongoDB
- **PDF**: ReportLab

## User Roles
- **Admin**: Full access, formulation management, user/staff management, reports
- **Telecaller (Executive)**: Create orders, manage customers, view own sales
- **Packaging**: Pack orders, upload images, view formulations (if enabled globally)
- **Dispatch**: Mark orders as dispatched, enter courier/transport details

## Phase 1 (MVP) - COMPLETED
- [x] JWT auth with 4 roles
- [x] Customer CRUD with duplicate checks
- [x] Order lifecycle (create, edit, cancel, track status)
- [x] Dark/light theme toggle
- [x] Green CitSpray branding

## Phase 2 (Enhancements) - COMPLETED
- [x] Payment tracking (Unpaid, Partial, Full)
- [x] Proforma Invoice builder with PDF generation
- [x] Item Sales Analytics
- [x] Telecaller sales dashboard with period filters
- [x] Global formulation visibility toggle

## Phase 3 (Current) - COMPLETED (March 19, 2026)
- [x] Data reset for fresh start
- [x] Removed per-item formulation visibility (global control only)
- [x] Merged Dashboard + All Orders into single view
- [x] Telecaller sees own orders by default, toggle to view all (anonymized)
- [x] Hide "created by" executive name from other executives
- [x] Admin Executive Reports tab (view individual telecaller dashboards)
- [x] Packaging: 3 mandatory multi-select fields (Item Packed By, Box Packed By, Checked By)
- [x] Admin-manageable packaging staff list (default: Yogita, Sapna, Samiksha)
- [x] Dispatch logic: Porter/Self-arranged/Office Collection = no LR needed
- [x] Transport: transporter name optional for telecallers, LR mandatory for dispatch
- [x] Courier: predefined dropdown only (DTDC, Anjani, Professional, India Post)
- [x] Order print (PDF) for packaging/admin with formulations always included
- [x] Formulation history for admin/packaging
- [x] Mobile-responsive improvements across all pages

## Key API Endpoints
- POST /api/auth/login - Login
- GET/POST /api/users - User management
- GET/POST /api/customers - Customer CRUD
- GET/POST /api/orders - Order CRUD
- PUT /api/orders/{id}/formulation - Update formulations (admin)
- PUT /api/orders/{id}/packaging - Update packaging (3 multi-select fields)
- PUT /api/orders/{id}/dispatch - Dispatch order
- PUT /api/orders/{id}/cancel - Cancel order
- GET /api/orders/{id}/print - Generate order PDF for packaging
- GET /api/packaging-staff - List packaging staff
- POST /api/packaging-staff - Add staff
- DELETE /api/packaging-staff/{id} - Remove staff (soft delete)
- GET /api/courier-options - Get courier dropdown list
- GET /api/settings - Get global settings
- PUT /api/settings - Update settings
- GET /api/reports/sales - Admin sales report
- GET /api/reports/dashboard - Dashboard stats
- GET /api/reports/telecaller-sales - Telecaller sales
- GET /api/reports/telecaller-dashboard/{id} - Admin view telecaller dashboard
- GET /api/reports/item-sales - Item analytics
- GET /api/orders/formulation-history/{customer_id} - Formulation history
- POST /api/admin/reset-data - Reset all data
- POST/GET /api/proforma-invoices - PI CRUD
- GET /api/proforma-invoices/{id}/pdf - PI PDF

## Database Collections
- users, customers, orders, proforma_invoices, settings, packaging_staff, counters

## Credentials
- Admin: admin / admin123

## Future / Backlog
- [ ] Object storage integration for images
- [ ] GST external API verification (currently format check only)
- [ ] Dashboard charts with Recharts
- [ ] Bulk order operations / CSV export
- [ ] WhatsApp integration for dispatch notifications
- [ ] Audit log for all changes
- [ ] Customer payment history ledger
