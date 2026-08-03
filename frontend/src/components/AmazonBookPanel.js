import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, RefreshCw, Printer, PackageCheck, Clock, AlertTriangle, Truck } from "lucide-react";
import { fmtAmazonRate, fmtAmazonRateBreakdown } from "@/lib/amazonShipping";

const fmtWindow = (w) => {
  if (!w?.start && !w?.end) return null;
  const o = { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" };
  const s = w.start ? new Date(w.start).toLocaleString("en-IN", o) : null;
  const e = w.end ? new Date(w.end).toLocaleString("en-IN", o) : null;
  return s && e ? `${s} — ${e}` : (s || e);
};

export default function AmazonBookPanel() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [quoting, setQuoting] = useState({});
  const [booking, setBooking] = useState(false);
  // { order, rates } — the confirmation step before any money is spent
  const [confirm, setConfirm] = useState(null);
  const [selectedRate, setSelectedRate] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/amazon/bookable");
      setOrders(res.data || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load bookable orders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const getRates = async (order) => {
    setQuoting(p => ({ ...p, [order.id]: true }));
    try {
      const res = await api.post("/amazon/quote", { order_id: order.id });
      if (!res.data.ok) {
        toast.error(res.data.message || "No rates available");
        if (res.data.detail) toast.error(res.data.detail, { duration: 7000 });
        return;
      }
      setSelectedRate(res.data.rates[0] || null);
      setConfirm({ order, rates: res.data.rates,
                   isCod: res.data.is_cod, codAmount: res.data.cod_amount });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not fetch rates");
    } finally {
      setQuoting(p => ({ ...p, [order.id]: false }));
    }
  };

  const doBook = async () => {
    if (!confirm || !selectedRate) return;
    setBooking(true);
    try {
      const res = await api.post("/amazon/book", {
        order_id: confirm.order.id,
        service_id: selectedRate.service_id || selectedRate.rate_id,
      });
      toast.success(`Booked! Tracking: ${res.data.shipment?.tracking_id || "—"}`, { duration: 8000 });
      setConfirm(null);
      setSelectedRate(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Booking failed", { duration: 9000 });
    } finally {
      setBooking(false);
    }
  };

  const printLabel = (order) => {
    const token = localStorage.getItem("token");
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/amazon/label/${order.id}?token=${token}`, "_blank");
  };

  return (
    <div className="space-y-4" data-testid="amazon-book-panel">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-muted-foreground">
          Orders set to <b>Amazon</b> courier that packing has weighed. Booking charges your Amazon Shipping account.
        </p>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
          ) : (
            <Table className="min-w-[860px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="whitespace-nowrap">Order #</TableHead>
                  <TableHead className="whitespace-nowrap">Customer</TableHead>
                  <TableHead className="whitespace-nowrap">Destination</TableHead>
                  <TableHead className="whitespace-nowrap">Weight</TableHead>
                  <TableHead className="whitespace-nowrap">Boxes</TableHead>
                  <TableHead className="whitespace-nowrap">Amazon Status</TableHead>
                  <TableHead className="whitespace-nowrap">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground py-10">
                      No orders ready. Set an order's courier to <b>Amazon</b> and have packing enter the weight.
                    </TableCell>
                  </TableRow>
                )}
                {orders.map(o => {
                  const sh = o.amazon_shipment;
                  const sa = o.shipping_address || {};
                  return (
                    <TableRow key={o.id} data-testid={`amz-book-row-${o.id}`}>
                      <TableCell className="font-mono text-sm">{o.order_number}</TableCell>
                      <TableCell className="text-sm">
                        {o.customer_name}
                        {o.is_cod && (
                          <Badge className="ml-1.5 bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 text-[10px] px-1 py-0 align-middle">
                            COD ₹{Number(o.cod_amount || 0).toFixed(0)}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {sa.city || "—"}{sa.pincode ? ` · ${sa.pincode}` : ""}
                      </TableCell>
                      <TableCell className="text-sm font-mono">{o.weight_kg} kg</TableCell>
                      <TableCell className="text-sm">{o.num_boxes}</TableCell>
                      <TableCell>
                        {sh?.shipment_id ? (
                          <div className="flex flex-col gap-0.5">
                            <Badge className="bg-green-100 text-green-800 text-xs w-fit">Booked</Badge>
                            <span className="font-mono text-[11px] text-muted-foreground">{sh.tracking_id}</span>
                          </div>
                        ) : (
                          <Badge variant="outline" className="text-xs">Not booked</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {sh?.shipment_id ? (
                          <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => printLabel(o)} data-testid={`amz-print-${o.id}`}>
                            <Printer className="w-3 h-3 mr-1" /> Print Label
                          </Button>
                        ) : (
                          <Button size="sm" className="text-xs h-7" disabled={!!quoting[o.id]} onClick={() => getRates(o)} data-testid={`amz-rates-${o.id}`}>
                            {quoting[o.id] ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Truck className="w-3 h-3 mr-1" />}
                            Get Rates & Book
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Confirmation — nothing is purchased until this is confirmed */}
      <Dialog open={!!confirm} onOpenChange={(o) => { if (!o && !booking) { setConfirm(null); setSelectedRate(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Confirm Amazon Booking</DialogTitle>
            <DialogDescription>
              Order {confirm?.order?.order_number} · {confirm?.order?.customer_name} · {confirm?.order?.weight_kg} kg
            </DialogDescription>
          </DialogHeader>

          {/* Always state the payment mode — never let prepaid be an assumption. */}
          {confirm?.isCod ? (
            <div className="rounded-md border-2 border-amber-500 bg-amber-50/70 dark:bg-amber-950/30 px-3 py-2.5 text-sm">
              <div className="font-bold text-amber-700 dark:text-amber-400 tracking-wide">
                BOOKING AS: CASH ON DELIVERY
              </div>
              <div className="mt-0.5">
                Amazon will collect <b>₹{Number(confirm.codAmount || 0).toFixed(2)}</b> from the
                customer and remit it to you. Rates below include Amazon's COD fee.
              </div>
            </div>
          ) : (
            <div className="rounded-md border-2 border-sky-500/70 bg-sky-50/60 dark:bg-sky-950/25 px-3 py-2.5 text-sm">
              <div className="font-bold text-sky-700 dark:text-sky-400 tracking-wide">
                BOOKING AS: PREPAID
              </div>
              <div className="mt-0.5">
                Nothing will be collected on delivery. If this order is COD, close this and tick
                <b> Cash on delivery</b> on the order first.
              </div>
            </div>
          )}

          <div className="space-y-2">
            {confirm?.rates?.map((r, i) => {
              const active = (selectedRate?.rate_id || selectedRate?.service_id) === (r.rate_id || r.service_id);
              return (
                <button
                  key={i}
                  onClick={() => setSelectedRate(r)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${active ? "border-primary bg-accent" : "border-border hover:bg-accent/50"}`}
                  data-testid={`amz-rate-opt-${i}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-sm">{r.service}</span>
                    <div className="text-right shrink-0">
                      <div className="font-mono font-semibold">{fmtAmazonRate(r.amount, r.currency)}</div>
                      <div className="text-[11px] text-muted-foreground font-mono">{fmtAmazonRateBreakdown(r.amount, r.currency)}</div>
                    </div>
                  </div>
                  {fmtWindow(r.promise?.pickupWindow) && (
                    <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1 flex items-center gap-1">
                      <PackageCheck className="w-3 h-3" /> Pickup: {fmtWindow(r.promise.pickupWindow)}
                    </p>
                  )}
                  {fmtWindow(r.promise?.deliveryWindow) && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" /> Delivery: {fmtWindow(r.promise.deliveryWindow)}
                    </p>
                  )}
                </button>
              );
            })}
          </div>

          <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-3">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">
              This purchases a real shipment on your Amazon Shipping account
              {selectedRate?.amount ? <> for <b>{fmtAmazonRate(selectedRate.amount, selectedRate.currency)}</b> ({fmtAmazonRateBreakdown(selectedRate.amount, selectedRate.currency)})</> : null} and schedules a pickup. It cannot be undone from here.
            </p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setConfirm(null); setSelectedRate(null); }} disabled={booking}>Cancel</Button>
            <Button onClick={doBook} disabled={booking || !selectedRate} data-testid="amz-confirm-book">
              {booking ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking…</> : "Confirm & Book"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
