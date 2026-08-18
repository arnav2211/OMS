import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  // Explicit payment mode for this booking. Defaults to prepaid so COD is
  // never applied by omission, and never inferred silently from the order.
  const [payMode, setPayMode] = useState("prepaid");
  const [selected, setSelected] = useState(new Set());
  const [bulkMode, setBulkMode] = useState("prepaid");
  const [bulkBooking, setBulkBooking] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  // { order, rates } — the confirmation step before any money is spent
  const [confirm, setConfirm] = useState(null);
  const [selectedRate, setSelectedRate] = useState(null);
  // Manual dispatch — mark a booked order shipped without waiting for pickup.
  const [dispatchFor, setDispatchFor] = useState(null);
  const [docketNo, setDocketNo] = useState("");
  const [dispatching, setDispatching] = useState(false);

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

  const toggle = (id) => setSelected(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const bookable = orders.filter(o => !o.amazon_shipment?.shipment_id);
  const selectedIds = [...selected].filter(id => bookable.some(o => o.id === id));
  const bookedSelected = [...selected].filter(id =>
    orders.some(o => o.id === id && o.amazon_shipment?.shipment_id));

  // One A4 sheet, four labels per page in quarter slots, in selection order.
  const printSheet = () => {
    if (bookedSelected.length === 0) return;
    const token = localStorage.getItem("token");
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/amazon/labels-sheet?ids=${bookedSelected.join(",")}&token=${token}`, "_blank");
  };

  const bulkBook = async () => {
    if (selectedIds.length === 0) return;
    setBulkBooking(true);
    try {
      const res = await api.post("/amazon/bulk-book",
                                 { order_ids: selectedIds, payment_mode: bulkMode });
      setBulkResult(res.data);
      if (res.data.booked_count) toast.success(`Booked ${res.data.booked_count} shipment(s)`);
      if (res.data.failed_count) toast.error(`${res.data.failed_count} failed — see the summary`);
      setSelected(new Set());
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Bulk booking failed");
    } finally {
      setBulkBooking(false);
    }
  };

  const getRates = async (order, mode) => {
    const useMode = mode || (order.is_cod ? "cod" : "prepaid");
    setPayMode(useMode);
    setQuoting(p => ({ ...p, [order.id]: true }));
    try {
      const res = await api.post("/amazon/quote", { order_id: order.id, payment_mode: useMode });
      if (!res.data.ok) {
        toast.error(res.data.message || "No rates available");
        if (res.data.detail) toast.error(res.data.detail, { duration: 7000 });
        return;
      }
      setSelectedRate(res.data.rates[0] || null);
      setConfirm({ order, rates: res.data.rates,
                   isCod: res.data.is_cod, codAmount: res.data.cod_amount,
                   box_cm: res.data.box_cm, boxMeasured: res.data.box_measured });
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
        payment_mode: payMode,
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
    // Single print uses the same quarter-A4 sheet as bulk — one label, one quarter.
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/amazon/labels-sheet?ids=${order.id}&token=${token}`, "_blank");
  };

  const doDispatch = async () => {
    if (!dispatchFor) return;
    setDispatching(true);
    try {
      await api.post("/amazon/dispatch", { order_id: dispatchFor.id, docket_no: docketNo.trim() });
      toast.success("Marked dispatched");
      setDispatchFor(null);
      setDocketNo("");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Dispatch failed");
    } finally {
      setDispatching(false);
    }
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

      {(selectedIds.length > 0 || bookedSelected.length > 0) && (
        <Card className="border-primary/60">
          <CardContent className="pt-4 flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">
              {selected.size} selected
              {selectedIds.length > 0 && ` · ${selectedIds.length} to book`}
              {bookedSelected.length > 0 && ` · ${bookedSelected.length} booked`}
            </span>
            {/* The whole batch books on one mode, stated up front and prepaid
                by default, so a bulk run can never silently turn orders COD. */}
            <div className="flex gap-1">
              {[["prepaid", "Prepaid"], ["cod", "COD"]].map(([m, label]) => (
                <button key={m} type="button" onClick={() => setBulkMode(m)}
                        data-testid={`amz-bulk-mode-${m}`}
                        className={`rounded-md border px-3 py-1.5 text-xs transition ${
                          bulkMode === m
                            ? (m === "cod"
                                ? "border-amber-500 bg-amber-100 dark:bg-amber-900/40 font-semibold"
                                : "border-sky-500 bg-sky-100 dark:bg-sky-900/40 font-semibold")
                            : "border-border hover:bg-muted"}`}>
                  {label}
                </button>
              ))}
            </div>
            <Button size="sm" onClick={bulkBook} disabled={bulkBooking || selectedIds.length === 0}
                    data-testid="amz-bulk-book">
              {bulkBooking
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking {selectedIds.length}…</>
                : <><Truck className="w-4 h-4 mr-1" /> Book {selectedIds.length} as {bulkMode === "cod" ? "COD" : "Prepaid"}</>}
            </Button>
            <Button variant="outline" size="sm" onClick={printSheet}
                    disabled={bookedSelected.length === 0}
                    data-testid="amz-print-sheet">
              <Printer className="w-4 h-4 mr-1" /> Print Labels ({bookedSelected.length}) — 4/A4
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} disabled={bulkBooking}>
              Clear
            </Button>
            {bulkMode === "cod" && (
              <span className="text-xs text-amber-600 w-full">
                Every selected order will be booked COD, collecting its own outstanding balance.
              </span>
            )}
          </CardContent>
        </Card>
      )}

      {bulkResult && (
        <Card className={bulkResult.failed_count ? "border-amber-500/60" : "border-emerald-500/60"}>
          <CardContent className="pt-4 text-sm space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-semibold">
                Bulk booking: {bulkResult.booked_count} booked, {bulkResult.failed_count} failed
              </span>
              <Button variant="ghost" size="sm" onClick={() => setBulkResult(null)}>Dismiss</Button>
            </div>
            {(bulkResult.failed || []).map((f, i) => (
              <div key={i} className="text-xs text-destructive"><b>{f.order_number}</b>: {f.error}</div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
          ) : (
            <Table className="min-w-[860px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={orders.length > 0 && selected.size === orders.length}
                      onCheckedChange={(v) => setSelected(v ? new Set(orders.map(o => o.id)) : new Set())}
                      aria-label="Select all"
                      data-testid="amz-select-all" />
                  </TableHead>
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
                    <TableCell colSpan={8} className="text-center text-muted-foreground py-10">
                      No orders ready. Set an order's courier to <b>Amazon</b> and have packing enter the weight.
                    </TableCell>
                  </TableRow>
                )}
                {orders.map(o => {
                  const sh = o.amazon_shipment;
                  const sa = o.shipping_address || {};
                  return (
                    <TableRow key={o.id} data-testid={`amz-book-row-${o.id}`}>
                      <TableCell>
                        {/* Booked rows feed Print Labels, unbooked rows feed Book Selected. */}
                        <Checkbox checked={selected.has(o.id)}
                                  onCheckedChange={() => toggle(o.id)}
                                  data-testid={`amz-select-${o.id}`} />
                      </TableCell>
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
                          <div className="flex gap-1 flex-wrap">
                            <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => printLabel(o)} data-testid={`amz-print-${o.id}`}>
                              <Printer className="w-3 h-3 mr-1" /> Print Label
                            </Button>
                            <Button variant="outline" size="sm" className="text-xs h-7"
                              onClick={() => { setDispatchFor(o); setDocketNo(sh.tracking_id || ""); }}
                              data-testid={`amz-dispatch-${o.id}`}>
                              Dispatch
                            </Button>
                          </div>
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

          {/* Chosen explicitly for every booking; prepaid unless switched. */}
          <div className="rounded-md border-2 px-3 py-2.5 space-y-2"
               style={{ borderColor: payMode === "cod" ? "rgb(245 158 11)" : "rgb(14 165 233)" }}>
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              How is this shipment paid?
            </div>
            <div className="flex gap-2">
              {[["prepaid", "Prepaid"], ["cod", "Cash on delivery"]].map(([m, label]) => (
                <button key={m} type="button" disabled={booking}
                        onClick={() => confirm?.order && getRates(confirm.order, m)}
                        data-testid={`amz-paymode-${m}`}
                        className={`flex-1 rounded-md border px-3 py-2 text-sm transition ${
                          payMode === m
                            ? (m === "cod"
                                ? "border-amber-500 bg-amber-100 dark:bg-amber-900/40 font-semibold"
                                : "border-sky-500 bg-sky-100 dark:bg-sky-900/40 font-semibold")
                            : "border-border hover:bg-muted"}`}>
                  {label}
                </button>
              ))}
            </div>
            {payMode === "cod" ? (
              <p className="text-sm">
                Amazon will collect <b>₹{Number(confirm?.codAmount || 0).toFixed(2)}</b> from the
                customer and remit it to you. Rates below include Amazon's COD fee.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nothing will be collected on delivery.
              </p>
            )}
          </div>

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
                  {(r.charges || []).length > 1 && (
                    <div className="text-[11px] text-muted-foreground mt-1 font-mono">
                      {r.charges.map((c) => `${c.label}: ₹${Number(c.amount).toFixed(2)}`).join("  ·  ")}
                    </div>
                  )}
                  {r.billed_weight ? (
                    <div className="text-[11px] text-muted-foreground mt-0.5">
                      Billed weight {r.billed_weight} {(r.billed_weight_unit || "KG").toLowerCase()}
                      {confirm?.order?.weight_kg &&
                       Number(r.billed_weight) > Number(confirm.order.weight_kg) && (
                        <span className="text-amber-600">
                          {" "}— volumetric, from the {confirm?.box_cm?.length}×{confirm?.box_cm?.width}×{confirm?.box_cm?.height} cm box
                          {confirm?.boxMeasured === false && " (assumed — not measured)"}
                        </span>
                      )}
                    </div>
                  ) : null}
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
              {booking
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking…</>
                : payMode === "cod"
                  ? `Book as COD — collect ₹${Number(confirm?.codAmount || 0).toFixed(2)}`
                  : "Book as Prepaid"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Manual dispatch before Amazon reports pickup */}
      <Dialog open={!!dispatchFor} onOpenChange={(v) => { if (!v && !dispatching) { setDispatchFor(null); setDocketNo(""); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Dispatch Order</DialogTitle>
            <DialogDescription>
              {dispatchFor?.order_number} · marks it dispatched without waiting for Amazon pickup.
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label>Tracking / Docket No.</Label>
            <Input value={docketNo} onChange={e => setDocketNo(e.target.value)} className="mt-1.5 font-mono"
              placeholder="Tracking number" data-testid="amz-docket-input" />
            <p className="text-xs text-muted-foreground mt-1.5">
              The Amazon label is attached automatically as the dispatch slip.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDispatchFor(null); setDocketNo(""); }} disabled={dispatching}>Cancel</Button>
            <Button onClick={doDispatch} disabled={dispatching || !docketNo.trim()} data-testid="amz-confirm-dispatch">
              {dispatching ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Dispatching…</> : "Mark Dispatched"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
