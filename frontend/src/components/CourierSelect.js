import { useState, useEffect } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { KNOWN_COURIERS, COURIER_DROPDOWN } from "@/lib/courierTracking";

/**
 * Courier picker with an "Others" free-text option.
 *
 * `value` / `onChange` speak the stored `courier_name` string directly:
 *  - a named courier ("DTDC", "Amazon", ...) is selected in the dropdown
 *  - anything else is treated as "Others" and shown in the text box, and the
 *    typed name IS the courier_name (so it displays everywhere unchanged).
 * No backend field is needed — courier_name has always been a free string.
 */
export default function CourierSelect({ value = "", onChange, disabled, triggerTestId }) {
  const deriveMode = (v) => (!v ? "" : KNOWN_COURIERS.includes(v) ? v : "Others");
  // Don't echo the literal word "Others" (legacy rows) back into the text box.
  const deriveText = (v) => (v && !KNOWN_COURIERS.includes(v) && v !== "Others" ? v : "");

  const [mode, setMode] = useState(deriveMode(value));
  const [otherText, setOtherText] = useState(deriveText(value));

  // Re-sync only when the parent value genuinely differs from what we're showing
  // (guards against clobbering in-progress typing, incl. trailing spaces).
  useEffect(() => {
    const current = mode === "Others" ? otherText.trim() : mode;
    if ((value || "") !== current) {
      setMode(deriveMode(value));
      setOtherText(deriveText(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleSelect = (v) => {
    setMode(v);
    if (v === "Others") {
      onChange && onChange(otherText.trim());
    } else {
      setOtherText("");
      onChange && onChange(v);
    }
  };

  const handleText = (t) => {
    setOtherText(t);
    onChange && onChange(t.trim());
  };

  return (
    <>
      <Select value={mode} onValueChange={handleSelect} disabled={disabled}>
        <SelectTrigger data-testid={triggerTestId}>
          <SelectValue placeholder="Select courier" />
        </SelectTrigger>
        <SelectContent>
          {COURIER_DROPDOWN.map((c) => (
            <SelectItem key={c} value={c}>{c}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {mode === "Others" && (
        <Input
          className="mt-2"
          value={otherText}
          onChange={(e) => handleText(e.target.value)}
          placeholder="Specify courier name"
          disabled={disabled}
          data-testid="courier-other-input"
        />
      )}
    </>
  );
}
