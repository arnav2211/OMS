// Named couriers with their own behaviour/LR rules. Anything else the user
// types (via the "Others" option) is stored directly in courier_name and
// treated as a free-form courier that does not require an LR number.
export const KNOWN_COURIERS = ["DTDC", "Anjani", "India Post", "Amazon"];

// What the courier dropdown shows. "Others" reveals a free-text box.
export const COURIER_DROPDOWN = [...KNOWN_COURIERS, "Others"];

/** True when courier_name is a free-form / "Others" courier (not a named one). */
export function isOtherCourier(courierName) {
  return !!courierName && !KNOWN_COURIERS.includes(courierName);
}

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
  "India Post": {
    regex: /^[A-Za-z]{2}[0-9]{9}[A-Za-z]{2}$/,
    label: "2 letters + 9 digits + 2 letters (e.g., EE123456789IN)",
  },
};

// Courier Tracking URLs
const TRACKING_URLS = {
  DTDC: (lr) => `https://txk.dtdc.com/ctbs-tracking/customerInterface.tr?submitName=showCITrackingDetails&cType=Consignment&cnNo=${lr}`,
  Anjani: (lr) => `https://shreeanjani.co.in/tracking?awb=${lr}`,
  Amazon: (lr) => `https://track.amazon.in/tracking/${lr}`,
  "India Post": (lr) => `https://www.indiapost.gov.in`,
};

// Couriers we can pull live status from via /courier-status.
export const LIVE_TRACKING_COURIERS = ["DTDC", "Anjani", "Amazon"];

/** Does this courier support in-app live tracking? Free-text tolerant. */
export function supportsLiveTracking(courierName) {
  const n = String(courierName || "").trim().toLowerCase();
  return n.startsWith("dtdc") || n.startsWith("anjani") || n.startsWith("amazon");
}

/**
 * Validate LR number against courier-specific regex
 * Returns { valid, message }
 */
export function validateLrNumber(courierName, lrNo) {
  if (isOtherCourier(courierName)) {
    return { valid: true, message: "" };
  }
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
  const match = text.match(/(?:https?:\/\/)?(?:www\.)?porter\.in\/[\w/.-]+/i);
  if (!match) return null;
  const link = match[0];
  return link.startsWith("http") ? link : `https://${link}`;
}

/**
 * Check if a dispatch type requires mandatory LR/tracking
 */
export function isLrMandatory(dispatchType, courierName) {
  if (dispatchType === "courier" && isOtherCourier(courierName)) {
    return false;
  }
  return dispatchType === "courier" || dispatchType === "transport";
}
