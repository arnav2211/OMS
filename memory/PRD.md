# CitSpray Order Management System - PRD

## Original Problem Statement
Order management system for CitSpray with 4 user roles: Telecaller, Packaging, Dispatch, Admin. Full order lifecycle from customer intake through packaging, dispatch, and tracking.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + Shadcn UI
- **Backend**: FastAPI (Python) on port 8001
- **Database**: MongoDB (Motor async driver)
- **Auth**: JWT-based with admin-created accounts
- **File Storage**: Local uploads (S3-ready with boto3)

## User Personas
1. **Admin**: Full control - user management, formulations, all orders, sales reports
2. **Telecaller**: Creates orders, manages customers, tracks order progress
3. **Packaging**: Receives orders, views formulations, uploads images, marks as packed
4. **Dispatch**: Enters courier/transport details, LR numbers, marks as dispatched

## Core Requirements (Static)
- Customer database with reusability across orders
- Order creation with product items, GST (18%, 5%, 0%), auto-calculations
- Shipping methods: Transport, Courier, Porter, Self-Arranged, Office Collection
- Order lifecycle: New → Packaging → Packed → Dispatched
- Formulation management per item (admin controls visibility)
- Image upload for packaging (per-item, whole order, packed box)
- GST verification (format validation + state extraction)
- Sales reports by telecaller
- Dark/Light mode toggle

## What's Been Implemented (March 19, 2026)
### Backend (server.py)
- JWT authentication with login/me endpoints
- User CRUD (admin-only)
- Customer CRUD with search (name, phone, GST)
- Order CRUD with full lifecycle management
- Formulation management per order item
- Packaging image upload and status management
- Dispatch details management
- GST format verification + state code extraction
- Local file upload endpoint
- Dashboard stats and sales reports
- Admin user auto-seeded (admin/admin123)

### Frontend Pages
- Login page (split-screen with citrus branding)
- Admin Dashboard (stats, orders table, filters, formulation dialog, sales report)
- Telecaller Dashboard (stats, order list, search)
- Create Order form (customer select/create, items with GST, shipping, summary)
- Customer Management (list, search, create/edit dialog)
- Packaging Dashboard (queue, formulation view, image upload per item)
- Dispatch Dashboard (queue, dispatch form with courier/LR details)
- User Management (create, edit, toggle active, delete)
- Order Detail (progress tracker, customer info, items, dispatch info, images)
- Dark/Light mode toggle

## Prioritized Backlog
### P0 (Critical)
- [x] All core features implemented

### P1 (High)
- [ ] S3 image upload (needs AWS credentials)
- [ ] GST external API verification (needs API key from gstincheck.co.in)
- [ ] Email notifications for order status changes
- [ ] Print/PDF invoice generation

### P2 (Medium)
- [ ] Telecaller login and role-specific testing
- [ ] Order editing for telecallers
- [ ] Bulk order operations
- [ ] Customer order history view
- [ ] Advanced search with date pickers using Calendar component

### P3 (Low)
- [ ] Mobile-responsive packaging interface for tablets
- [ ] Export reports to CSV/Excel
- [ ] Dashboard charts with Recharts
- [ ] Order status timeline in detail view
- [ ] Audit log for all changes

## Next Tasks
1. Configure S3 for production image storage
2. Add GST API key for external verification
3. Print invoice/challan feature
4. Add Recharts visualizations to admin dashboard
