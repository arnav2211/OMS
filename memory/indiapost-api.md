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

**Barcode prefixes** (confirmed by the user, both check digits validate against
our S10 generator): **1000061167 (small) books EM…IN**, e.g. EM299481938IN;
**1000061169 (large) books CM…IN**, e.g. CM640588294IN. The allotted serial
*ranges* are still unknown — only the prefixes are.

Sandbox logins are separate identities from the portal customer IDs:
1000061169 -> **9999365217**, 1000061167 -> 9999496326 (the latter would not
authenticate as of 2 Aug 2026 and needs chasing).

Four domestic tariff APIs are subscribed, not the two the document's booking
section implies: speed-post, business-parcel, **letter-tariff** and
**parcel-tariff**. Letter and Parcel often undercut Business Parcel at low
weight but cannot be booked via process-articles, so they are quote-only.
Letter/Parcel use a different response schema (`basic_charge`,
`cgst`/`sgst`/`igst`, `total_amount`) than SP/BP (`base_tariff`, `total_tax`,
`final_amount`).

Still needed before booking can work: `contract_id` (8 digits) per account,
linked to the customer and carrying a `service_type` — tested with the sandbox
id, the production id, and the document's demo contract, all rejected — plus
the allotted serial range. Contact: integrations.cept@indiapost.gov.in
