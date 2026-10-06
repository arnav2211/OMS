import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Download, Search, AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

// "Fetch from Tally": finds the order's sales bills in Bahi (by the bill's Reference No., e.g. CS-1749) and
// attaches them as the order's tax invoice — each bill in Tally's format followed by its e-way bill.
// An invoice that is already uploaded is never replaced.
const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dmy = (s) => (s ? new Date(s + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "2-digit" }) : "");

export default function TallyFetchDialog({ order, open, onOpenChange, onAttached }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState({});
  const [eway, setEway] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = async (query = "") => {
    if (!order?.id) return;
    setLoading(true);
    try {
      const res = await api.get(`/orders/${order.id}/tally-bills`, { params: { q: query } });
      setData(res.data);
      setPicked((prev) => {
        const next = { ...prev };
        res.data.bills.forEach((b) => { if (next[b.key] === undefined) next[b.key] = b.matches_order && !b.cancelled; });
        return next;
      });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not reach Tally (Bahi)");
    } finally { setLoading(false); }
  };

  useEffect(() => { if (open) { setData(null); setPicked({}); setQ(""); load(""); } /* eslint-disable-next-line */ }, [open, order?.id]);

  const chosen = (data?.bills || []).filter((b) => picked[b.key]);
  const attach = async () => {
    setSaving(true);
    try {
      await api.post(`/orders/${order.id}/tally-bills/attach`, { bills: chosen, include_eway: eway });
      toast.success(`Invoice attached from Tally (${chosen.map((b) => b.number).join(", ")})`);
      onOpenChange(false);
      onAttached && onAttached();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not attach the invoice");
    } finally { setSaving(false); }
  };

  const locked = data?.has_invoice;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="tally-fetch-modal">
        <DialogHeader>
          <DialogTitle>Fetch invoice from Tally — {order?.order_number}</DialogTitle>
          <DialogDescription>
            Bills whose Reference No. in Tally is this order number are ticked. One bill can cover several orders
            (Reference “CS-1749, CS-1750” or “CS-1749/50”); if this order has more than one bill, tick them all — they are joined into one PDF.
          </DialogDescription>
        </DialogHeader>

        {locked && (
          <div className="flex items-start gap-2 text-sm rounded-md bg-amber-50 text-amber-800 px-3 py-2" data-testid="tally-fetch-locked">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>This order already has an invoice uploaded{data?.from_tally ? ` (from Tally${data.fetched_by ? " by " + data.fetched_by : ""})` : ""}.
              Fetch from Tally never replaces it.</span>
          </div>
        )}

        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); load(q); }}>
          <Input placeholder="Not listed? Search bill no., party or reference" value={q} onChange={(e) => setQ(e.target.value)} data-testid="tally-fetch-search" />
          <Button type="submit" variant="outline" disabled={loading}><Search className="w-4 h-4" /></Button>
        </form>

        <div className="border rounded-md divide-y max-h-[50vh] overflow-y-auto" data-testid="tally-fetch-list">
          {loading && !data && <div className="p-6 text-center text-sm text-muted-foreground">Looking in Tally…</div>}
          {data && data.bills.length === 0 && (
            <div className="p-6 text-center text-sm text-muted-foreground">
              No Tally bill has “{data.order_number}” as its Reference No. yet. Search above by bill number or party.
            </div>
          )}
          {(data?.bills || []).map((b) => (
            <label key={b.key} className={`flex items-start gap-3 p-3 cursor-pointer hover:bg-muted/40 ${b.cancelled ? "opacity-60" : ""}`}>
              <Checkbox className="mt-1" checked={!!picked[b.key]} disabled={locked || b.cancelled}
                onCheckedChange={(v) => setPicked((p) => ({ ...p, [b.key]: !!v }))} data-testid={`tally-bill-${b.key}`} />
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold">{b.number}</span>
                  <span className="text-xs text-muted-foreground">{dmy(b.date)} · {b.company}</span>
                  {b.matches_order && <Badge className="text-[10px] bg-green-100 text-green-800">Ref {b.reference}</Badge>}
                  {!b.matches_order && b.reference && <Badge variant="outline" className="text-[10px]">Ref {b.reference}</Badge>}
                  {b.other_orders?.length > 0 && <Badge className="text-[10px] bg-blue-100 text-blue-800">Also for {b.other_orders.join(", ")}</Badge>}
                  {b.ewb_no && <Badge className="text-[10px] bg-amber-100 text-amber-800">e-Way Bill</Badge>}
                  {b.irn && <Badge className="text-[10px] bg-emerald-100 text-emerald-800">e-Invoice</Badge>}
                  {b.cancelled && <Badge className="text-[10px] bg-red-100 text-red-800">Cancelled</Badge>}
                  {b.attached && <Badge className="text-[10px]">Attached</Badge>}
                  {b.changed && <Badge className="text-[10px] bg-orange-100 text-orange-800">Changed in Tally since</Badge>}
                </div>
                <div className="text-sm truncate">{b.party}</div>
              </div>
              <div className="text-sm font-mono whitespace-nowrap">{inr(b.amount)}</div>
            </label>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={eway} onCheckedChange={(v) => setEway(!!v)} disabled={locked} /> Include e-way bills
          </label>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
            <Button onClick={attach} disabled={locked || saving || chosen.length === 0} data-testid="tally-fetch-attach">
              <Download className="w-4 h-4 mr-1.5" />
              {saving ? "Making PDF…" : `Attach ${chosen.length || ""} bill${chosen.length === 1 ? "" : "s"}`}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
