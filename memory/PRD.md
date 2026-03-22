# CitSpray Order Management System - PRD

## Original Problem Statement
Full-stack Order Management System for CitSpray Aroma Sciences with role-based dashboards, customer/order management, PDF generation, and payment tracking.

## Core Roles
- **Admin**: Full system access, analytics, user management, settings
- **Telecaller**: Create orders, manage customers, generate PIs, view own/all orders
- **Packaging**: Manage packing (images, checklist)
- **Dispatch**: Manage dispatch (courier, transporter, LR no)
- **Accounts**: Upload tax invoices (GST orders only), verify payments (all orders)

## Tech Stack
- **Backend**: FastAPI, Motor (MongoDB), Pydantic, JWT, ReportLab, Passlib
- **Frontend**: React, React Router, Tailwind CSS, Shadcn/UI, Axios, sonner, lucide-react
- **Database**: MongoDB

## What's Been Implemented

### Phase 1-6 (Foundation)
- JWT authentication with role-based access
- Customer CRUD with addresses
- Order CRUD with full lifecycle (new -> packaging -> packed -> dispatched)
- PI (Proforma Invoice) builder with PDF generation
- Role-based dashboards for all roles
- PDF generation for PIs, Order Sheets, Address Labels
- Real-time notifications for telecallers

### Phase 7 Part 1
- Full Order Edit page with role-based field access
- PI to Order conversion
- "Delete User" button removed
- Formulation save bug fixed
- Image deletion for payment/packaging images
- Telecaller notifications (UI + sound)
- Bulk shipping address printing

### Phase 7 Part 2
- PDF design overhaul (PI + Order Sheet)
- Logo aspect ratio fix
- Non-GST PI renamed to "Quotation"

### Phase 7 Part 3 (COMPLETED - March 22, 2026)
- **Share Feature**: PI PDF sharing via navigator.share (mobile) or download+WhatsApp (desktop)
- **Share Packing Images**: From OrderDetail page, shares actual image files
- **Share Tax Invoice**: PDF file sharing for Admin, Telecaller, Field Manager
- **Field Manager Role**: Same as Telecaller, own orders only, no payment check access
- **Accounts Role**: Invoice uploads (PDF only, GST orders), payment verification (all orders)
- **Accounts Dashboard**: Metrics (invoices, GST without invoice, payments received/pending)
- **Payment Check System**: Only accounts can update, re-check logic on payment update
- **Sales (Payments Received)**: Separate section in Telecaller and Admin dashboards
- **Payment Filters**: Period, Status, Payment, Check Status in All Orders page
- **WhatsApp Integration**: wa.me links with customer phone numbers

## Key API Endpoints
- POST /api/auth/login - JWT login
- GET/POST /api/orders - List/Create orders
- PUT /api/orders/{id} - Update order (triggers re-check if payment changed)
- PUT /api/orders/{id}/invoice - Upload tax invoice (accounts only)
- DELETE /api/orders/{id}/invoice - Delete invoice (accounts only)
- PUT /api/orders/{id}/payment-check - Update payment check (accounts ONLY)
- GET /api/reports/dashboard - Dashboard stats

## Pending/Future Tasks
- GET /api/reports/payment-sales - Sales from received payments (admin/telecaller)
- GET /api/reports/accounts-dashboard - Accounts metrics
- GET/POST /api/proforma-invoices - PI management
- GET /api/proforma-invoices/{id}/pdf - Download PI PDF

## Mocked APIs
- GST verification (/api/gst-verify/{gst_no})
- Pincode lookup (/api/pincode)

## Test Credentials
- Admin: admin / admin123
- Accounts: accounts1 / accounts123
- Field Manager: field1 / field123

### Correction Patch (March 22, 2026)
- Restored Units column in PI PDF (GST + Non-GST)
- PI status auto-changes to "Converted" on conversion (new PATCH endpoint)
- Telecaller can Edit/Delete own orders (pre-dispatch only)
- Admin can now also mark payment as Received/Pending (alongside Accounts)
- Payment Verification section added to OrderDetail for Admin and Accounts (with Mark Received/Pending buttons)
- Telecaller sees read-only payment check status in OrderDetail
- **P2**: Performance optimization (pagination on all list endpoints)
- **P2**: server.py modularization into FastAPI routers (2400+ lines)
- **P3**: Export to CSV/Excel
- **P3**: WhatsApp integration for automated dispatch notifications
- **P3**: Audit log for all changes
- **P3**: Customer payment history ledger
