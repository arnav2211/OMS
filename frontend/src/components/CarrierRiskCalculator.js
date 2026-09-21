import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { IndianRupee, ShieldCheck } from "lucide-react";
import {
  calcCarrierRisk,
  formatCarrierRisk,
  CARRIER_RISK_GST_PERCENT,
  CARRIER_RISK_MIN_AMOUNT,
} from "@/lib/carrierRisk";

// DTDC carrier risk on an invoice value. GST always applies on this tool.
export default function CarrierRiskCalculator() {
  const [invoiceValue, setInvoiceValue] = useState("");
  const parsed = parseFloat(invoiceValue);
  const risk = Number.isFinite(parsed) && parsed > 0 ? calcCarrierRisk(parsed, CARRIER_RISK_GST_PERCENT) : null;

  return (
    <Card data-testid="carrier-risk-card">
      <CardHeader className="pb-4">
        <CardTitle className="text-base flex items-center gap-2">
          <ShieldCheck className="w-4 h-4" /> Carrier Risk Calculator (DTDC)
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          DTDC charges {"₹"}{CARRIER_RISK_MIN_AMOUNT} or 2% of the invoice value, whichever is higher, plus GST.
          The charge is part of the invoice, so it is included in the value the 2% is taken on.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>Invoice Value (before carrier risk)</Label>
          <div className="relative mt-1">
            <IndianRupee className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input value={invoiceValue} onChange={(e) => setInvoiceValue(e.target.value.replace(/[^\d.]/g, ""))}
              placeholder="0" className="pl-9" inputMode="decimal" data-testid="carrier-risk-invoice-input" />
          </div>
        </div>

        {risk && (
          <>
            <Separator />
            <div className="rounded-md bg-muted/50 p-4 text-center">
              <p className="text-xs text-muted-foreground uppercase font-medium">Carrier Risk</p>
              <p className="text-2xl font-bold text-primary mt-1 font-mono" data-testid="carrier-risk-formula">{formatCarrierRisk(risk)}</p>
              {risk.minimum_applied && (
                <p className="text-xs text-muted-foreground mt-1">Minimum {"₹"}{CARRIER_RISK_MIN_AMOUNT} applied (2% is lower)</p>
              )}
            </div>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Carrier Risk</span>
                <span className="font-mono" data-testid="carrier-risk-amount">{"₹"}{risk.amount.toFixed(2)}</span>
              </div>
              {risk.gst_amount > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">GST ({risk.gst_percent}%)</span>
                  <span className="font-mono">{"₹"}{risk.gst_amount.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between font-medium">
                <span>Added to Invoice</span>
                <span className="font-mono" data-testid="carrier-risk-total">{"₹"}{risk.total.toFixed(2)}</span>
              </div>
              <Separator />
              <div className="flex justify-between text-base font-bold">
                <span>Invoice Value with Carrier Risk</span>
                <span className="font-mono" data-testid="carrier-risk-declared-value">{"₹"}{(parsed + risk.total).toFixed(2)}</span>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
