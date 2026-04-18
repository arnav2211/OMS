# CitSpray Order Management System - PRD

## Original Problem Statement
Build a comprehensive Order Management System for CitSpray Aroma Sciences with role-based access (Admin, Telecaller, Packaging, Dispatch, Accounts), Amazon order parsing, PDF generation, and advanced analytics.

## Core Requirements
- Multi-role authentication and routing
- Full CRUD for orders, customers, PIs
- Amazon order PDF parsing
- Invoice upload with PDF merging (Tax + E-way)
- Packaging workflow with image uploads and barcode scanning
- Dispatch workflow with courier tracking
- Payment tracking and verification
- Admin analytics and executive reports
- Admin urgent alert system

## What's Been Implemented

### Authentication & Roles
- JWT-based auth with 5 roles: Admin, Telecaller, Packaging, Dispatch, Accounts
- Role-based routing and access control

### Order Management
- Create, Edit, Duplicate, Delete orders
- Multi-line addresses with copy buttons
- Customer GST display with copy
- Free sample formulation support
- Extra shipping details field
- Formulation history tracking

### Customer Management
- CRUD with alias field
- Searchable across all modules
- Direct editing from order/PI forms
- State/UT dropdown validation (INDIAN_STATES)

### Proforma Invoice (PI)
- Create, Edit, Print PIs
- Search bar (Customer, Alias, Phone, GST, ID)

### Packaging Module
- Pack dialog with staff assignment
- Item, order, packed box image uploads
- Composite keys for image grouping
- SlipScanner with barcode scanning (pyzbar + html5-qrcode)
- Image crop functionality (react-image-crop)
- **Status auto-transition**: Saving packaging from Order Detail page now auto-transitions "new" → "packaging" (Fixed 2026-04-18)

### Dispatch Module
- Dispatch dialog with editable shipping method
- LR/Tracking No. mandatory for Courier and Transport
- Courier-specific Regex validation: DTDC, Anjani, Professional, India Post
- Track button opens courier's official tracking URL
- Porter link extraction from pasted messages (bare porter.in/... links supported)
- Porter Track + Share Tracking Link buttons
- Dispatch slip upload with barcode scanning
- Share packed boxes + dispatch slip combined

### Accounts Module
- Tax Invoice upload with E-way Bill merge (PyPDF2)
- Server-side pagination with gst_only flag
- Payment verification (Received/Pending/Re-check)

### Amazon Orders
- PDF parsing with pdfplumber
- Easy Ship bulk dispatch
- Self Ship with courier assignment + LR validation
- Track button for dispatched orders

### Admin Features
- Executive reports with IST timezone fix
- Excl. GST / Excl. Shipping calculations fixed (properly decomposes total_gst into items/shipping/additional GST) (Fixed 2026-04-17)
- Admin alert/popup system with continuous audio alarm
- Order search in admin alerts
- Alert cancellation
- **Sidebar**: Amazon Orders/Packing/Dispatch grouped under collapsible "Amazon" menu; Packaging & Dispatch remain standalone (Updated 2026-04-18)

### Utility Tools
- DTDC Serviceability & Rate Calculator (/DTDC)
- Shree Anjani Serviceability Checker (/ANJANI)

### UI/UX
- Mobile print via Web Share API
- Global numeric input scroll prevention
- Search bars in PI, Packaging, Dispatch modules

## Architecture
- Backend: FastAPI + Motor (MongoDB) + Pydantic
- Frontend: React + Tailwind CSS + Shadcn/UI
- Special libs: pyzbar, html5-qrcode, react-image-crop, PyPDF2, reportlab

## Key Technical Notes
- State validation uses INDIAN_STATES array (strict matching)
- Mobile print uses navigator.share() API
- pyzbar requires libzbar0 OS package
- Admin alerts use 3-second polling + Web Audio API
- Porter link regex handles bare porter.in/... URLs (no https:// prefix required)
- Admin sidebar uses grouped nav with hover (desktop) / tap (mobile) for Amazon sub-items
- Packaging auto-transition: backend auto-sets status to "packaging" when current is "new" and no explicit status sent

## Prioritized Backlog

### P1
- Refactor server.py monolith (~3700 lines) into modular FastAPI routers

### P3
- Export to CSV/Excel functionality
- WhatsApp integration for dispatch notifications
- Comprehensive Audit Log
- Customer payment history ledger

## Mocked APIs
- GST verification (/api/gst-verify)
- Pincode lookup (/api/pincode)
