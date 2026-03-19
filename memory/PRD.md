# CitSpray Order Management System - PRD

## Original Problem Statement
Order management system for CitSpray (MANGALAM AGRO) with roles: Admin, Telecaller, Packing Team. Full order lifecycle with PI generation, GST handling, payment tracking, item analytics.

## Architecture
- **Frontend**: React 19 + Tailwind CSS + Shadcn UI (Green theme)
- **Backend**: FastAPI on port 8001 with /api prefix
- **Database**: MongoDB (Motor async)
- **Auth**: JWT with admin-created accounts
- **PDF**: ReportLab for PI generation
- **File Storage**: Local uploads (S3-ready)

## Implemented Features (March 19, 2026)

### v1 - MVP
- JWT auth, 4 user roles, customer CRUD, order lifecycle, GST handling
- Packaging image upload, dispatch management, sales reports

### v2 - Major Enhancement
- **Customer Module**: Duplicate prevention (phone/GST), delete if no orders, view customer orders inline
- **Order Module**: Edit orders, cancel with double confirmation, payment status (unpaid/partial/full), payment screenshots
- **Proforma Invoice**: Full PI builder with GST/Non-GST modes, show rate toggle, PDF download with company header/logo (MANGALAM AGRO), convert PI to order with one click
- **Item Analytics**: Per-item sales with case-insensitive matching, date range filters, drill-down to see who purchased and when
- **Global Formulation Toggle**: Admin Settings tab - single toggle to show/hide formulations across all orders for packaging team
- **Telecaller Sales**: Today/Week/Month filters, exclude GST and shipping charges to see product-only sales
- **Packing Team Dispatch**: Packaging role can now add dispatch details (courier, tracking, LR)
- **Theme**: Green branded theme with CitSpray logo, dark/light mode

## Backlog
### P1
- [ ] S3 image storage (needs AWS credentials)
- [ ] GST external API verification (needs API key)
- [ ] Order editing form (full edit with items recalculation)
- [ ] Print invoice/challan from order

### P2
- [ ] Dashboard charts with Recharts
- [ ] Bulk order operations
- [ ] Export reports to CSV/Excel
- [ ] WhatsApp integration for dispatch notifications

### P3
- [ ] Mobile-responsive packaging interface
- [ ] Audit log for all changes
- [ ] Customer payment history ledger
