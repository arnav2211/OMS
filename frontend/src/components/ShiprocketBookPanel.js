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
import { Loader2, RefreshCw, Printer, PackageCheck, Clock, AlertTriangle, Truck, Wallet, ShieldCheck } from "lucide-react";

const inr = (n) => `₹${Number(n || 0).toFixed(2)}`;

// Mirrors AmazonBookPanel. One difference: Shiprocket fronts many couriers, so
// the confirmation step lists them all and the booker picks one.
export default function ShiprocketBookPanel() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [wallet, setWallet] = useState(null);
  const [quoting, setQuoting] = useState({});
  const [booking, setBooking] = useState(false);
  // Explicit payment mode for this booking. Defaults to prepaid so COD is
  // never applied by omission.
  const [payMode, setPayMode] = useState("prepaid");
  const [insure, setInsure] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkMode, setBulkMode] = useState("prepaid");
  const [bulkBooking, setBulkBooking] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  // { order, couriers } — the confirmation step before any money is spent
  const [confirm, setConfirm] = useState(null);
  const [courier, setCourier] = useState(null);
  const [dispatchFor, setDispatchFor] = useState(null);
  const [docketNo, setDocketNo] = useState("");
  const [dispatching, setDispatching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/shiprocket/bookable");
      setOrders(res.data || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load bookable orders");
    } finally {
      setLoading(false);
    }
    api.get("/shiprocket/wallet").then(r => setWallet(r.data.balance)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = (id) => setSelected(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const isBooked = (o) => !!o.shiprocket_shipment?.awb;
  const selectedIds = [...selected].filter(id => orders.some(o => o.id === id && !isBooked(o)));
  const bookedSelected = [...selected].filter(id => orders.some(o => o.id === id && isBooked(o)));

  const openLabels = (ids) => {
    const token = localStorage.getItem("token");
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/shiprocket/labels?ids=${ids.join(",")}&token=${token}`, "_blank");
  };

  // Zero-total orders (free samples) need a declared value typed in by the
  // booker. Returns undefined when not needed, null when the user cancelled.
  const askDeclared = (o) => {
    if (+(o.grand_total || 0) > 0) return undefined;
    const v = window.prompt(`Order ${o.order_number} total is ₹0. Enter the declared value (₹) for this shipment:`);
    if (v === null) return null;
    const n = parseFloat(v);
    if (!n || n <= 0) { toast.error("Enter a valid amount greater than 0"); return null; }
    return n;
  };

  const bulkBook = async () => {
    if (selectedIds.length === 0) return;
    const declaredValues = {};
    for (const id of selectedIds) {
      const dv = askDeclared(orders.find(x => x.id === id) || {});
      if (dv === null) return;            // cancelled - abort the whole batch
      if (dv !== undefined) declaredValues[id] = dv;
    }
    if (!window.confirm(`Book ${selectedIds.length} order(s) on Shiprocket as ${bulkMode === "cod" ? "COD" : "Prepaid"}? Each one goes on its CHEAPEST courier and is charged to the wallet.`)) return;
    setBulkBooking(true);
    try {
      const res = await api.post("/shiprocket/bulk-book",
                                 { order_ids: selectedIds, payment_mode: bulkMode, declared_values: declaredValues });
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
      const res = await api.post("/shiprocket/quote", { order_id: order.id, payment_mode: useMode });
      if (!res.data.ok) return toast.error(res.data.message || "No couriers available");
      setCourier(res.data.couriers[0] || null);
      setConfirm({ order, couriers: res.data.couriers, codAmount: res.data.cod_amount });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not fetch rates");
    } finally {
      setQuoting(p => ({ ...p, [order.id]: false }));
    }
  };

  const closeConfirm = () => { setConfirm(null); setCourier(null); setInsure(false); };

  const doBook = async () => {
    if (!confirm || !courier) return;
    const dv = askDeclared(confirm.order);
    if (dv === null) return;
    setBooking(true);
    try {
      const res = await api.post("/shiprocket/book", {
        order_id: confirm.order.id, courier_id: courier.courier_id,
        payment_mode: payMode, declared_value: dv, insure,
      });
      const s = res.data.shipment || {};
      toast.success(`Booked on ${s.courier_name}. AWB: ${s.awb || "—"}`, { duration: 8000 });
      closeConfirm();
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Booking failed", { duration: 9000 });
    } finally {
      setBooking(false);
    }
  };

  const cancelOne = async (o) => {
    if (!window.confirm(`Cancel the Shiprocket shipment for ${o.order_number}? The AWB is voided, the charge returns to the wallet, and you can rebook after.`)) return;
    try {
      const res = await api.post("/shiprocket/cancel", { order_id: o.id });
      toast.success(`Shipment cancelled (${res.data.cancelled || o.order_number})`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Cancel failed", { duration: 9000 });
    }
  };

  const bulkCancel = async () => {
    if (bookedSelected.length === 0) return;
    if (!window.confirm(`Cancel ${bookedSelected.length} Shiprocket shipment(s)? They are voided and you can rebook after.`)) return;
    try {
      const res = await api.post("/shiprocket/bulk-cancel", { order_ids: bookedSelected });
      toast.success(`${res.data.booked_count} cancelled${res.data.failed_count ? `, ${res.data.failed_count} failed` : ""}`);
      if (res.data.failed_count) setBulkResult(res.data);
      setSelected(new Set());
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Bulk cancel failed");
    }
  };

  const doDispatch = async () => {
    if (!dispatchFor) return;
    setDispatching(true);
    try {
      await api.post("/shiprocket/dispatch", { order_id: dispatchFor.id, docket_no: docketNo.trim() });
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
    <div className="space-y-4" data-testid="shiprocket-book-panel">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-muted-foreground">
          Orders set to <b>Shiprocket</b> courier that packing has weighed. Booking is charged to the Shiprocket wallet.
        </p>
        <div className="flex items-center gap-2">
          {wallet != null && (
            <Badge variant="outline" className={`gap-1 py-1 ${wallet < 500 ? "border-red-400 text-red-600" : ""}`} data-testid="sr-wallet">
              <Wallet className="w-3.5 h-3.5" /> Wallet {inr(wallet)}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      {(selectedIds.length > 0 || bookedSelected.length > 0) && (
        <Card className="border-primary/60">
          <CardContent className="pt-4 flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">
              {selected.size} selected
              {selectedIds.length > 0 && ` · ${selectedIds.length} to book`}
              {bookedSelected.length > 0 && ` · ${bookedSelected.length} booked`}
            </span>
            <div className="flex gap-1">
              {[["prepaid", "Prepaid"], ["cod", "COD"]].map(([m, label]) => (
                <button key={m} type="button" onClick={() => setBulkMode(m)}
                        data-testid={`sr-bulk-mode-${m}`}
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
            <Button size="sm" onClick={bulkBook} disabled={bulkBooking || selectedIds.length === 0} data-testid="sr-bulk-book">
              {bulkBooking
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking {selectedIds.length}…</>
                : <><Truck className="w-4 h-4 mr-1" /> Book {selectedIds.length} on cheapest · {bulkMode === "cod" ? "COD" : "Prepaid"}</>}
            </Button>
            <Button variant="outline" size="sm" onClick={() => openLabels(bookedSelected)}
                    disabled={bookedSelected.length === 0} data-testid="sr-print-labels">
              <Printer className="w-4 h-4 mr-1" /> Print Labels ({bookedSelected.length})
            </Button>
            <Button variant="outline" size="sm" onClick={bulkCancel} disabled={bookedSelected.length === 0}
                    className="text-destructive" data-testid="sr-bulk-cancel">
              Cancel Shipments ({bookedSelected.length})
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} disabled={bulkBooking}>Clear</Button>
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
                Bulk result: {bulkResult.booked_count} done, {bulkResult.failed_count} failed
              </span>
              <Button variant="ghost" size="sm" onClick={() => setBulkResult(null)}>Dismiss</Button>
            </div>
            {(bulkResult.booked || []).map((b, i) => b.result?.shipment && (
              <div key={i} className="text-xs text-muted-foreground">
                <b>{b.order_number}</b>: {b.result.shipment.courier_name} · {inr(b.result.shipment.rate)} · AWB {b.result.shipment.awb}
              </div>
            ))}
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
            <Table className="min-w-[900px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={orders.length > 0 && selected.size === orders.length}
                      onCheckedChange={(v) => setSelected(v ? new Set(orders.map(o => o.id)) : new Set())}
                      aria-label="Select all" data-testid="sr-select-all" />
                  </TableHead>
                  <TableHead className="whitespace-nowrap">Order #</TableHead>
                  <TableHead className="whitespace-nowrap">Customer</TableHead>
                  <TableHead className="whitespace-nowrap">Destination</TableHead>
                  <TableHead className="whitespace-nowrap">Weight</TableHead>
                  <TableHead className="whitespace-nowrap">Boxes</TableHead>
                  <TableHead className="whitespace-nowrap">Shiprocket Status</TableHead>
                  <TableHead className="whitespace-nowrap">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-muted-foreground py-10">
                      No orders ready. Set an order's courier to <b>Shiprocket</b> and have packing enter the weight.
                    </TableCell>
                  </TableRow>
                )}
                {orders.map(o => {
                  const sh = o.shiprocket_shipment;
                  const sa = o.shipping_address || {};
                  return (
                    <TableRow key={o.id} data-testid={`sr-book-row-${o.id}`}>
                      <TableCell>
                        <Checkbox checked={selected.has(o.id)} onCheckedChange={() => toggle(o.id)} data-testid={`sr-select-${o.id}`} />
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
                      <TableCell className="text-sm">{sa.city || "—"}{sa.pincode ? ` · ${sa.pincode}` : ""}</TableCell>
                      <TableCell className="text-sm font-mono">{o.weight_kg} kg</TableCell>
                      <TableCell className="text-sm">{o.num_boxes}</TableCell>
                      <TableCell>
                        {isBooked(o) ? (
                          <div className="flex flex-col gap-0.5">
                            <div className="flex items-center gap-1 flex-wrap">
                              <Badge className="bg-green-100 text-green-800 text-xs w-fit">Booked</Badge>
                              <span className="text-xs font-medium">{sh.courier_name}</span>
                              {sh.insured && <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" title="Insured" />}
                            </div>
                            <span className="font-mono text-[11px] text-muted-foreground">{sh.awb} · {inr(sh.rate)}</span>
                            {sh.pickup_date && <span className="text-[11px] text-emerald-700 dark:text-emerald-400">Pickup: {sh.pickup_date}</span>}
                            {sh.etd && <span className="text-[11px] text-muted-foreground">Delivery by: {sh.etd}</span>}
                          </div>
                        ) : (
                          <Badge variant="outline" className="text-xs">Not booked</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {isBooked(o) ? (
                          <div className="flex gap-1 flex-wrap">
                            <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => openLabels([o.id])} data-testid={`sr-print-${o.id}`}>
                              <Printer className="w-3 h-3 mr-1" /> Print Label
                            </Button>
                            <Button variant="outline" size="sm" className="text-xs h-7"
                              onClick={() => { setDispatchFor(o); setDocketNo(sh.awb || ""); }} data-testid={`sr-dispatch-${o.id}`}>
                              Dispatch
                            </Button>
                            <Button variant="outline" size="sm" className="text-xs h-7 text-destructive"
                              onClick={() => cancelOne(o)} data-testid={`sr-cancel-${o.id}`}>
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <Button size="sm" className="text-xs h-7" disabled={!!quoting[o.id]} onClick={() => getRates(o)} data-testid={`sr-rates-${o.id}`}>
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
      <Dialog open={!!confirm} onOpenChange={(o) => { if (!o && !booking) closeConfirm(); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Confirm Shiprocket Booking</DialogTitle>
            <DialogDescription>
              Order {confirm?.order?.order_number} · {confirm?.order?.customer_name} · {confirm?.order?.weight_kg} kg
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-md border-2 px-3 py-2.5 space-y-2"
               style={{ borderColor: payMode === "cod" ? "rgb(245 158 11)" : "rgb(14 165 233)" }}>
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">How is this shipment paid?</div>
            <div className="flex gap-2">
              {[["prepaid", "Prepaid"], ["cod", "Cash on delivery"]].map(([m, label]) => (
                <button key={m} type="button" disabled={booking}
                        onClick={() => confirm?.order && getRates(confirm.order, m)}
                        data-testid={`sr-paymode-${m}`}
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
            {payMode === "cod"
              ? <p className="text-sm">The courier will collect <b>{inr(confirm?.codAmount)}</b> from the customer. Rates below include the COD fee.</p>
              : <p className="text-sm text-muted-foreground">Nothing will be collected on delivery.</p>}
          </div>

          <div className="space-y-2">
            {confirm?.couriers?.map((c, i) => {
              const active = courier?.courier_id === c.courier_id;
              return (
                <button key={c.courier_id} onClick={() => setCourier(c)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${active ? "border-primary bg-accent" : "border-border hover:bg-accent/50"}`}
                  data-testid={`sr-courier-opt-${i}`}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-sm">
                      {c.name}
                      {i === 0 && <Badge className="ml-1.5 bg-emerald-600 text-white text-[10px] px-1 py-0">CHEAPEST</Badge>}
                    </span>
                    <div className="text-right shrink-0">
                      <div className="font-mono font-semibold">{inr(c.rate)}</div>
                      <div className="text-[11px] text-muted-foreground">GST included</div>
                    </div>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1">
                    {[c.surface ? "Surface" : "Air", c.rating && `rating ${c.rating}`,
                      c.rto_charges != null && `return (RTO) ${inr(c.rto_charges)}`].filter(Boolean).join(" · ")}
                  </div>
                  {c.cutoff_time && (
                    <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1 flex items-center gap-1">
                      <PackageCheck className="w-3 h-3" /> Same-day pickup if booked before {c.cutoff_time}
                    </p>
                  )}
                  {c.etd && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" /> Expected delivery: {c.etd}{c.days ? ` (${c.days} days)` : ""}
                    </p>
                  )}
                </button>
              );
            })}
          </div>

          <label className="flex items-start gap-2 rounded-md border p-3 cursor-pointer">
            <Checkbox checked={insure} onCheckedChange={v => setInsure(!!v)} className="mt-0.5" data-testid="sr-insure" />
            <span className="text-sm">
              <b>Insure this shipment</b> (Shiprocket "Secure Shipment")
              <span className="block text-xs text-muted-foreground">
                Extra fee charged by Shiprocket. Without it, a lost or damaged parcel is refunded only up to a small fixed limit, not the full invoice value.
              </span>
            </span>
          </label>

          <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-3">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">
              This buys a real shipment{courier ? <> on <b>{courier.name}</b> for <b>{inr(courier.rate)}</b></> : null} from the Shiprocket wallet and schedules a pickup.
            </p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeConfirm} disabled={booking}>Cancel</Button>
            <Button onClick={doBook} disabled={booking || !courier} data-testid="sr-confirm-book">
              {booking
                ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking…</>
                : payMode === "cod" ? `Book as COD — collect ${inr(confirm?.codAmount)}` : "Book as Prepaid"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!dispatchFor} onOpenChange={(v) => { if (!v && !dispatching) { setDispatchFor(null); setDocketNo(""); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Dispatch Order</DialogTitle>
            <DialogDescription>{dispatchFor?.order_number} · marks it dispatched in the OMS.</DialogDescription>
          </DialogHeader>
          <div>
            <Label>Tracking / AWB No.</Label>
            <Input value={docketNo} onChange={e => setDocketNo(e.target.value)} className="mt-1.5 font-mono"
              placeholder="AWB number" data-testid="sr-docket-input" />
            <p className="text-xs text-muted-foreground mt-1.5">The Shiprocket label is attached automatically as the dispatch slip.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDispatchFor(null); setDocketNo(""); }} disabled={dispatching}>Cancel</Button>
            <Button onClick={doDispatch} disabled={dispatching || !docketNo.trim()} data-testid="sr-confirm-dispatch">
              {dispatching ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Dispatching…</> : "Mark Dispatched"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
