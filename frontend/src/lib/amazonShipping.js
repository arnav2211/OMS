// Amazon Shipping quotes the freight BASE RATE only — its getRates response
// carries a single BASE_RATE line item and no tax component. Courier services
// in India attract 18% GST, which Amazon adds on the invoice, so every rate we
// show the user is grossed up here.
export const AMAZON_GST_PERCENT = 18;

/** Rate including GST, rounded to paise. */
export function amazonRateWithGst(amount) {
  const base = Number(amount);
  if (!Number.isFinite(base)) return null;
  return +(base * (1 + AMAZON_GST_PERCENT / 100)).toFixed(2);
}

/** "₹76.70" — the amount the account is actually billed. */
export function fmtAmazonRate(amount, currency = "INR") {
  const total = amazonRateWithGst(amount);
  if (total === null) return "";
  const sym = !currency || currency === "INR" ? "₹" : `${currency} `;
  return `${sym}${total.toFixed(2)}`;
}

/** "₹65 + 18% GST" — the breakdown shown under the headline figure. */
export function fmtAmazonRateBreakdown(amount, currency = "INR") {
  const base = Number(amount);
  if (!Number.isFinite(base)) return "";
  const sym = !currency || currency === "INR" ? "₹" : `${currency} `;
  return `${sym}${base} + ${AMAZON_GST_PERCENT}% GST`;
}
