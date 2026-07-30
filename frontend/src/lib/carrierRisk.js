// DTDC carrier risk (transit insurance).
//
// DTDC levies 2% of the declared invoice value or a flat minimum, whichever is
// higher, plus GST. The charge appears on the invoice, so it raises the value
// the 2% is levied on. The amount is therefore the fixed point of
//     C = 0.02 * (base + C + C * gst)
//   =>  C = 0.02 * base / (1 - 0.02 * (1 + gst))
// where base is everything else on the invoice. Worked example: base 4882 with
// 18% GST gives C = 100, an invoice value of 4882 + 100 + 18 = 5000, and 2% of
// 5000 is exactly the 100 charged.
//
// Kept in sync with calc_carrier_risk() in backend/server.py, which is
// authoritative — the server re-derives this row on every save.

export const CARRIER_RISK_LABEL = "Carrier Risk";
export const CARRIER_RISK_MIN_AMOUNT = 100;
export const CARRIER_RISK_RATE = 0.02;
export const CARRIER_RISK_GST_PERCENT = 18;
export const CARRIER_RISK_COURIER = "DTDC";

/** Carrier risk row for an invoice worth baseValue before the charge is added. */
export function calcCarrierRisk(baseValue, gstPercent = CARRIER_RISK_GST_PERCENT) {
  const base = Math.max(0, Number(baseValue) || 0);
  const percent = Math.max(0, Math.round(Number(gstPercent) || 0));
  const gstFraction = percent / 100;
  const divisor = 1 - CARRIER_RISK_RATE * (1 + gstFraction);
  const raw = divisor > 0 ? (CARRIER_RISK_RATE * base) / divisor : CARRIER_RISK_MIN_AMOUNT;
  // Round before the ceiling so float noise at an exact boundary (base 4882
  // lands on precisely 100) cannot push the charge a whole rupee higher.
  const amount = Math.max(CARRIER_RISK_MIN_AMOUNT, Math.ceil(+raw.toFixed(6)));
  const gstAmount = +(amount * gstFraction).toFixed(2);
  return {
    name: CARRIER_RISK_LABEL,
    amount,
    gst_percent: percent,
    gst_amount: gstAmount,
    total: +(amount + gstAmount).toFixed(2),
    minimum_applied: amount <= CARRIER_RISK_MIN_AMOUNT,
  };
}

/**
 * The carrier-risk charge exactly as it should appear on a document. DTDC always
 * levies 2% + GST, so GST is always part of the cost. When the invoice is
 * GST-applicable it's shown as amount + GST; when it is NOT, the GST is folded
 * into a single inclusive amount (e.g. 118) with no GST wording anywhere.
 */
export function resolveCarrierRiskCharge(baseValue, gstApplicable) {
  const c = calcCarrierRisk(baseValue, CARRIER_RISK_GST_PERCENT);
  if (gstApplicable) return c;
  const inclusive = Math.ceil(c.total);
  return {
    name: CARRIER_RISK_LABEL,
    amount: inclusive,
    gst_percent: 0,
    gst_amount: 0,
    total: inclusive,
    minimum_applied: c.minimum_applied,
  };
}

/** "105 + 18% = 123.90" when GST applies; just "118" when it doesn't. */
export function formatCarrierRisk(charge) {
  if (!charge) return "";
  const total = charge.total ?? charge.amount + (charge.gst_amount || 0);
  if (!charge.gst_percent) return `${charge.amount}`;
  return `${charge.amount} + ${charge.gst_percent}% = ${total.toFixed(2)}`;
}

export function isCarrierRiskCharge(charge) {
  return String(charge?.name || "").trim().toLowerCase() === CARRIER_RISK_LABEL.toLowerCase();
}

/** Carrier risk is derived, so it is never kept in the editable charges list. */
export function stripCarrierRisk(charges) {
  return (charges || []).filter((c) => !isCarrierRiskCharge(c));
}

export function hasCarrierRisk(charges) {
  return (charges || []).some(isCarrierRiskCharge);
}

/**
 * Whether carrier risk should be on for a saved order/PI. Falls back to
 * sniffing the charges list for documents saved before the flag existed.
 */
export function resolveCarrierRiskFlag(doc) {
  if (typeof doc?.carrier_risk_applicable === "boolean") return doc.carrier_risk_applicable;
  return hasCarrierRisk(doc?.additional_charges);
}
