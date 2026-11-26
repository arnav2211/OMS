import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2 } from "lucide-react";

// Mode of payment value that turns on split payments (several payments for one order).
export const SPLIT_MODE = "Split";
export const SPLIT_LABEL = "Split (Cash + Online / 2× UPI)";
const ROW_MODES = ["Cash", "Online", "UPI", "Bank Transfer", "Cheque", "Other"];

export const splitTotal = (rows) => (rows || []).reduce((s, r) => s + (parseFloat(r.amount) || 0), 0);

// Payment status the server will set from the rows (it recomputes them itself too).
export function splitStatus(rows, grandTotal) {
  const paid = splitTotal(rows);
  if (grandTotal > 0 && paid >= grandTotal - 0.5) return "full";
  return paid > 0 ? "partial" : "unpaid";
}

export const blankSplitRows = () => [{ mode: "Cash", amount: "", note: "" }, { mode: "Online", amount: "", note: "" }];

/** Rows of { mode, amount, note }. The total paid, balance and status follow from them. */
export default function SplitPayments({ rows, onChange, grandTotal }) {
  const list = rows?.length ? rows : blankSplitRows();
  const set = (i, k, v) => onChange(list.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const paid = splitTotal(list);
  const balance = Math.max(0, (grandTotal || 0) - paid);
  const over = paid - (grandTotal || 0) > 0.5;
  return (
    <div className="space-y-2 rounded-lg border p-3 bg-secondary/20" data-testid="split-payments">
      <Label className="text-sm">Payments received</Label>
      {list.map((r, i) => (
        <div key={i} className="grid grid-cols-[110px_1fr_1.3fr_auto] sm:grid-cols-[140px_140px_1fr_auto] gap-2 items-center">
          <Select value={r.mode} onValueChange={(v) => set(i, "mode", v)}>
            <SelectTrigger className="h-9" data-testid={`split-mode-${i}`}><SelectValue /></SelectTrigger>
            <SelectContent>{ROW_MODES.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
          </Select>
          <Input className="h-9" type="number" inputMode="decimal" placeholder="Amount ₹" value={r.amount}
            onChange={(e) => set(i, "amount", e.target.value)} data-testid={`split-amount-${i}`} />
          <Input className="h-9" placeholder="Note (e.g. 2nd UPI, ref no.)" value={r.note || ""}
            onChange={(e) => set(i, "note", e.target.value)} data-testid={`split-note-${i}`} />
          <Button type="button" variant="ghost" size="icon" className="h-9 w-9" disabled={list.length <= 1}
            onClick={() => onChange(list.filter((_, j) => j !== i))} data-testid={`split-remove-${i}`}>
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...list, { mode: "Online", amount: "", note: "" }])}
          data-testid="split-add">
          <Plus className="w-4 h-4 mr-1" /> Add payment
        </Button>
        <div className="text-sm text-right">
          <span className="text-muted-foreground">Paid </span><b className="font-mono">₹{paid.toLocaleString("en-IN")}</b>
          <span className="text-muted-foreground"> · Balance </span>
          <b className={`font-mono ${balance > 0.5 ? "text-amber-600" : "text-green-600"}`}>₹{balance.toLocaleString("en-IN")}</b>
          {over && <div className="text-xs text-red-600">More than the order total (₹{(grandTotal || 0).toLocaleString("en-IN")})</div>}
        </div>
      </div>
    </div>
  );
}
