---
name: indiapost-api
description: India Post (DoP/CEPT) API integration — the two contracts, what blocks booking, and the facts that differ from other couriers
metadata:
  type: project
---

India Post integration for CitSpray/Mangalam Agro. Two customer IDs:
**1000061169** (bigger parcels) and **1000061167** (smaller parcels).

Three facts that differ from [[dtdc-booking]] and Amazon and drive the design:

1. **India Post does not allocate the tracking number.** Each customer is
   allotted a barcode series and generates article numbers itself — UPU S10:
   2 letters, 8-digit serial, check digit (weighted modulus 11, factors
   8,6,4,2,3,5,9,7), then "IN". Verified against all 11 real article numbers
   in the approach document. Booking is impossible without the allotted series.
2. **Sandbox access is provisioned separately from the portal.** As of
   2 Aug 2026 both IDs return `Invalid user credentials` on
   `test.cept.gov.in/beextcustomer/v1/access/login`, while the document's own
   demo credential returns 200 from the identical request — so the accounts are
   simply not registered. The portal's "Register for Sandbox Environment" form
   was still un-submitted; the user chose to submit it themselves.
3. **No IP whitelisting for sandbox, only for production.** The VPS reaches
   the sandbox fine. The production base URL is not published anywhere — it is
   issued with the production credentials at go-live.

Useful: the masterdata office lookup (`/bemasterdata/v1/offices/limited-details`)
needs **no authentication at all**, so pincode serviceability works without
credentials — a pincode is serviceable if it has an office with
`delivery_office_flag` true and `office_type_code` not BPO. Unlike DTDC's
endpoint this genuinely discriminates (999999 correctly returns nothing).

Cap is **35 kg**, well past the Amazon 22 kg limit. Tariff weights must be
whole grams. `final_amount` is already GST-inclusive, so no surcharge maths.

Still needed before booking can work: `contract_id` (8 digits) per account and
the allotted barcode series. Contact: integrations.cept@indiapost.gov.in
