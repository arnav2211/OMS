// Courier LR/Tracking Number Regex Patterns
export const COURIER_LR_PATTERNS = {
  DTDC: {
    regex: /^[A-Za-z][0-9]{10}$/,
    label: "1 letter + 10 digits (e.g., D1234567890)",
  },
  Anjani: {
    regex: /^[0-9]{10}$/,
    label: "10 digits (e.g., 1234567890)",
  },
  Professional: {
    regex: /^[A-Za-z]{3}[0-9]{9}$/,
    label: "3 letters + 9 digits (e.g., PAT500068734)",
  },
  "India Post": {
    regex: /^[A-Za-z]{2}[0-9]{9}[A-Za-z]{2}$/,
    label: "2 letters + 9 digits + 2 letters (e.g., EE123456789IN)",
  },
};

// Courier Tracking URLs
const TRACKING_URLS = {
  DTDC: (lr) => `https://www.dtdc.in/tracking/shipment-tracking.asp?strCnno=${lr}`,
  Anjani: (lr) => `https://www.shreeanjanicourier.com/`,
  Professional: (lr) => `https://www.tpcindia.com/track-info.aspx?id=${lr}&type=0&service=0`,
  "India Post": (lr) => `https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx?ConsignmentNumber=${lr}`,
};

/**
 * Validate LR number against courier-specific regex
 * Returns { valid, message }
 */
export function validateLrNumber(courierName, lrNo) {
  if (!lrNo || !lrNo.trim()) {
    return { valid: false, message: "Tracking number is required" };
  }
  const pattern = COURIER_LR_PATTERNS[courierName];
  if (!pattern) {
    // No specific pattern for this courier, accept any non-empty value
    return { valid: true, message: "" };
  }
  if (!pattern.regex.test(lrNo.trim())) {
    return {
      valid: false,
      message: `Invalid format for ${courierName}. Expected: ${pattern.label}`,
    };
  }
  return { valid: true, message: "" };
}

/**
 * Get tracking URL for a courier
 * Returns URL string or null if not available
 */
export function getTrackingUrl(courierName, lrNo) {
  if (!courierName || !lrNo) return null;
  const urlFn = TRACKING_URLS[courierName];
  if (!urlFn) return null;
  return urlFn(lrNo.trim());
}

/**
 * Extract porter.in tracking link from pasted text
 * Returns the URL string or null
 */
export function extractPorterLink(text) {
  if (!text) return null;
  const match = text.match(/https?:\/\/(?:www\.)?porter\.in\/[^\s)"\]]+/i);
  return match ? match[0] : null;
}

/**
 * Check if a dispatch type requires mandatory LR/tracking
 */
export function isLrMandatory(dispatchType) {
  return dispatchType === "courier" || dispatchType === "transport";
}
