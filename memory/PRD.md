# CitSpray Order Management System - PRD

## Original Problem Statement
Build a comprehensive Order Management System for "CitSpray" company with roles: Admin, Telecaller, Packaging, Dispatch.

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
- [x] Order lifecycle (create, edit, track status)
- [x] Dark/light theme toggle
- [x] Green CitSpray branding

## Phase 2 (Enhancements) - COMPLETED
- [x] Payment tracking (Unpaid, Partial, Full)
- [x] Proforma Invoice builder with PDF generation
- [x] Item Sales Analytics
- [x] Telecaller sales dashboard with period filters
- [x] Global formulation visibility toggle

## Phase 3 (Restructure) - COMPLETED (March 19, 2026)
- [x] Data reset for fresh start
- [x] Removed per-item formulation visibility (global control only)
- [x] Dashboard shows recent orders only
- [x] Packaging: 3 mandatory multi-select fields (Item Packed By, Box Packed By, Checked By)
- [x] Admin-manageable packaging staff list
- [x] Dispatch logic: Porter/Self-arranged/Office Collection = no LR needed
- [x] Transport: LR mandatory for dispatch, transporter name optional for telecallers
- [x] Courier: predefined dropdown (DTDC, Anjani, Professional, India Post)
- [x] Order print (PDF) for packaging/admin with formulations always included
- [x] Formulation history for admin/packaging

## Phase 4 (Fixes & Restructure) - COMPLETED (March 19, 2026)
- [x] Print auth fix: token passed via query param for new-tab PDF access
- [x] Replace Cancel Order with Delete Order (permanent deletion, 2 confirmations)
- [x] New "All Orders" sidebar nav item for ALL roles
- [x] All Orders page with payment status filter (Fully Paid, Partial, Unpaid)
- [x] Role-based visibility: non-admin can't see executive name, telecaller/dispatch can't see formulations in All Orders
- [x] Dashboard now shows Recent Orders only (latest 10), not all
- [x] Custom date range filter in Executive Reports (admin)
- [x] Custom date range filter in telecaller's own sales dashboard
- [x] Data reset (testing cleanup) - preserved users and config

## Key API Endpoints
- POST /api/auth/login
- GET/POST /api/users
- GET/POST /api/customers
- GET/POST /api/orders (view_all param for all-orders view)
- DELETE /api/orders/{id} (permanent delete)
- PUT /api/orders/{id}/formulation
- PUT /api/orders/{id}/packaging
- PUT /api/orders/{id}/dispatch
- GET /api/orders/{id}/print?token=JWT (PDF with auth via query param)
- GET /api/packaging-staff, POST, DELETE
- GET /api/courier-options
- GET/PUT /api/settings
- GET /api/reports/sales, /dashboard, /telecaller-sales (with date_from, date_to), /telecaller-dashboard/{id}, /item-sales
- GET /api/orders/formulation-history/{customer_id}
- POST /api/admin/reset-data
- POST/GET /api/proforma-invoices, /pdf

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
