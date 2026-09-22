import { useState, useEffect, useCallback, useMemo } from "react";
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
import {
  Loader2, RefreshCw, Printer, PackageCheck, Clock, AlertTriangle, Truck, Wallet, ShieldCheck, Scale, Trophy,
  ExternalLink,
} from "lucide-react";
import { fmtAmazonRate, fmtAmazonRateBreakdown } from "@/lib/amazonShipping";

// One screen for every courier we book by API. Each courier keeps its own
// endpoints and its own confirmation step; this page only brings them together.
const COURIERS = {
  DTDC: { api: "dtdc", badge: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200", noun: "consignment" },
  Amazon: { api: "amazon", badge: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200", noun: "shipment" },
  Shiprocket: { api: "shiprocket", badge: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200", noun: "shipment" },
  Anjani: { badge: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200" },
};
const FILTERS = ["All", "DTDC", "Amazon", "Shiprocket", "Unassigned"];
// Neither courier has a recharge API - money is added on their own sites.
const RECHARGE_URL = { Shiprocket: "https://app.shiprocket.in/" };
const LOW_WALLET = 500;
const inr = (n) => `₹${Number(n || 0).toFixed(2)}`;

const fmtWindow = (w) => {
  if (!w?.start && !w?.end) return null;
  const o = { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" };
  const s = w.start ? new Date(w.start).toLocaleString("en-IN", o) : null;
  const e = w.end ? new Date(w.end).toLocaleString("en-IN", o) : null;
  return s && e ? `${s} — ${e}` : (s || e);
};

export default function BookShipments() {
  const [orders, setOrders] = useState([]);
  const [unassigned, setUnassigned] = useState([]);
  const [loadErrors, setLoadErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [wallet, setWallet] = useState(null);
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState(new Set());
  const [busy, setBusy] = useState({});
  const [bulkBusy, setBulkBusy] = useState("");
  const [bulkResult, setBulkResult] = useState(null);
  // { order, courier, preview | rates | couriers, ... } — the step before money is spent
  const [confirm, setConfirm] = useState(null);
  const [choice, setChoice] = useState(null);
  const [payMode, setPayMode] = useState("prepaid");
  const [insure, setInsure] = useState(false);
  const [booking, setBooking] = useState(false);
  const [dispatchFor, setDispatchFor] = useState(null);
  const [docketNo, setDocketNo] = useState("");
  const [dispatching, setDispatching] = useState(false);
  const [cheapest, setCheapest] = useState({});       // order id -> compare result
  // Bulk review: order id -> { courier, mode, loading, error, preview | options, choice, declared, insure }
  const [review, setReview] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/shipments/bookable");
      setOrders(res.data.orders || []);
      setUnassigned(res.data.unassigned || []);
      setLoadErrors(res.data.errors || {});
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load orders");
    } finally {
      setLoading(false);
    }
    api.get("/shiprocket/wallet").then(r => setWallet(r.data.balance)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const counts = useMemo(() => {
    const c = { All: orders.length, Unassigned: unassigned.length };
    for (const o of orders) c[o.courier] = (c[o.courier] || 0) + 1;
    return c;
  }, [orders, unassigned]);

  const visible = filter === "All" ? orders : orders.filter(o => o.courier === filter);
  const byId = useMemo(() => Object.fromEntries(orders.map(o => [o.id, o])), [orders]);
  const picked = [...selected].map(id => byId[id]).filter(Boolean);
  const toBook = picked.filter(o => !o.booked);
  const bookedSel = picked.filter(o => o.booked);

  const toggle = (id) => setSelected(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const openLabels = (ids) => {
    if (!ids.length) return;
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/shipments/labels?ids=${ids.join(",")}&token=${localStorage.getItem("token")}`, "_blank");
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

  // ── single booking: each courier keeps its own confirmation step ──
  const startBooking = async (o, mode) => {
    const useMode = mode || (o.is_cod ? "cod" : "prepaid");
    setBusy(p => ({ ...p, [o.id]: true }));
    try {
      if (o.courier === "DTDC") {
        const res = await api.post("/dtdc/preview", { order_id: o.id });
        setConfirm({ order: o, courier: "DTDC", preview: res.data });
      } else {
        setPayMode(useMode);
        const res = await api.post(`/${COURIERS[o.courier].api}/quote`, { order_id: o.id, payment_mode: useMode });
        if (!res.data.ok) {
          toast.error(res.data.message || "No rates available");
          if (res.data.detail) toast.error(res.data.detail, { duration: 7000 });
          return;
        }
        const options = o.courier === "Amazon" ? res.data.rates : res.data.couriers;
        const pref = res.data.preferred_courier_id && options.find(c => c.courier_id === res.data.preferred_courier_id);
        setChoice(pref || options[0] || null);
        if (res.data.preferred_courier_id && !pref) toast.warning(`${res.data.preferred_name} chosen at order time is not available now - pick another carrier`, { duration: 7000 });
        setConfirm({ order: o, courier: o.courier, options, codAmount: res.data.cod_amount,
                     box_cm: res.data.box_cm, boxMeasured: res.data.box_measured });
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not prepare the booking", { duration: 8000 });
    } finally {
      setBusy(p => ({ ...p, [o.id]: false }));
    }
  };

  const closeConfirm = () => { setConfirm(null); setChoice(null); setInsure(false); };

  const doBook = async () => {
    if (!confirm) return;
    const o = confirm.order;
    const dv = askDeclared(o);
    if (dv === null) return;
    setBooking(true);
    try {
      let res;
      if (confirm.courier === "DTDC") {
        res = await api.post("/dtdc/book", { order_id: o.id, declared_value: dv });
        toast.success(`Booked on ${res.data.shipment?.account} — ${res.data.shipment?.awb || res.data.shipment?.reference_number}`, { duration: 9000 });
      } else if (confirm.courier === "Amazon") {
        res = await api.post("/amazon/book", { order_id: o.id, service_id: choice.service_id || choice.rate_id,
                                               payment_mode: payMode, declared_value: dv });
        toast.success(`Booked! Tracking: ${res.data.shipment?.tracking_id || "—"}`, { duration: 8000 });
      } else {
        res = await api.post("/shiprocket/book", { order_id: o.id, courier_id: choice.courier_id,
                                                   payment_mode: payMode, declared_value: dv, insure });
        toast.success(`Booked on ${res.data.shipment?.courier_name}. AWB: ${res.data.shipment?.awb || "—"}`, { duration: 8000 });
      }
      closeConfirm();
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Booking failed", { duration: 10000 });
    } finally {
      setBooking(false);
    }
  };

  // ── bulk: the selection may span couriers; each group goes to its own endpoint ──
  const runBulk = async (rows, action, declaredValues = {}, choices = {}) => {
    const merged = { booked: [], failed: [], booked_count: 0, failed_count: 0, action };
    for (const courier of ["DTDC", "Amazon", "Shiprocket"]) {
      const group = rows.filter(o => o.courier === courier);
      if (!group.length) continue;
      const body = { order_ids: group.map(o => o.id) };
      if (action === "book") {
        body.declared_values = declaredValues;
        body.choices = choices;
      }
      try {
        const res = await api.post(`/${COURIERS[courier].api}/bulk-${action}`, body);
        merged.booked.push(...(res.data.booked || []).map(b => ({ ...b, courier })));
        merged.failed.push(...(res.data.failed || []).map(f => ({ ...f, courier })));
      } catch (err) {
        const msg = err.response?.data?.detail || "Request failed";
        merged.failed.push(...group.map(o => ({ order_number: o.order_number, error: msg, courier })));
      }
    }
    merged.booked_count = merged.booked.length;
    merged.failed_count = merged.failed.length;
    return merged;
  };

  // ── bulk: every selected order is quoted and shown for review before anything is bought ──
  const quoteRow = async (o, mode) => {
    const row = { courier: o.courier, mode, loading: true, error: "", preview: null, options: [], choice: null,
                  declared: +(o.grand_total || 0) > 0 ? undefined : "", insure: false };
    try {
      if (o.courier === "DTDC") {
        const res = await api.post("/dtdc/preview", { order_id: o.id });
        row.preview = res.data;
      } else {
        const res = await api.post(`/${COURIERS[o.courier].api}/quote`, { order_id: o.id, payment_mode: mode });
        if (!res.data.ok) row.error = res.data.message || "No rates";
        else {
          row.options = o.courier === "Amazon" ? res.data.rates : res.data.couriers;
          const pref = res.data.preferred_courier_id && row.options.find(c => c.courier_id === res.data.preferred_courier_id);
          row.choice = pref || row.options[0] || null;
          row.preferred = res.data.preferred_name || "";
          row.preferredMissing = !!res.data.preferred_courier_id && !pref;
          row.codAmount = res.data.cod_amount;
        }
      }
    } catch (err) {
      row.error = err.response?.data?.detail || "Could not quote";
    }
    row.loading = false;
    return row;
  };

  const bulkBook = async () => {
    if (!toBook.length) return;
    const init = {};
    for (const o of toBook) init[o.id] = { courier: o.courier, mode: o.is_cod ? "cod" : "prepaid", loading: true, options: [], insure: false };
    setReview(init);
    await Promise.all(toBook.map(async (o) => {
      const row = await quoteRow(o, init[o.id].mode);
      setReview(r => (r ? { ...r, [o.id]: { ...row, declared: r[o.id]?.declared ?? row.declared } } : r));
    }));
  };

  const requoteRow = async (o, mode) => {
    setReview(r => ({ ...r, [o.id]: { ...r[o.id], mode, loading: true, error: "" } }));
    const row = await quoteRow(o, mode);
    setReview(r => (r ? { ...r, [o.id]: { ...row, declared: r[o.id]?.declared, insure: r[o.id]?.insure } } : r));
  };

  const rowFare = (row) => {
    if (!row || row.loading || row.error) return null;
    if (row.courier === "DTDC") return row.preview ? Number(row.preview.est_charge) : null;
    if (row.courier === "Amazon") return row.choice ? Number(row.choice.amount) * 1.18 : null;   // Amazon quotes before GST
    return row.choice ? Number(row.choice.rate) : null;
  };

  const reviewRows = review ? toBook.filter(o => review[o.id]) : [];
  const reviewReady = reviewRows.length > 0 && reviewRows.every(o => {
    const r = review[o.id];
    return !r.loading && !r.error && (r.courier === "DTDC" ? !!r.preview : !!r.choice)
      && (r.declared === undefined || parseFloat(r.declared) > 0);
  });
  const reviewTotal = reviewRows.reduce((t, o) => t + (rowFare(review[o.id]) || 0), 0);

  const confirmBulk = async () => {
    if (!reviewReady) return;
    const declaredValues = {}, choices = {};
    for (const o of reviewRows) {
      const r = review[o.id];
      if (r.declared !== undefined) declaredValues[o.id] = parseFloat(r.declared);
      choices[o.id] = { payment_mode: r.mode, insure: !!r.insure,
                        service_id: r.courier === "Amazon" ? (r.choice.service_id || r.choice.rate_id) : undefined,
                        courier_id: r.courier === "Shiprocket" ? r.choice.courier_id : undefined };
    }
    setBulkBusy("book");
    const res = await runBulk(reviewRows, "book", declaredValues, choices);
    setReview(null);
    setBulkResult(res);
    if (res.booked_count) toast.success(`Booked ${res.booked_count} shipment(s)`);
    if (res.failed_count) toast.error(`${res.failed_count} failed — see the summary`);
    setSelected(new Set());
    setBulkBusy("");
    load();
  };

  const bulkCancel = async () => {
    if (!bookedSel.length) return;
    if (!window.confirm(`Cancel ${bookedSel.length} booked label(s)? They are voided and you can rebook after.`)) return;
    setBulkBusy("cancel");
    const res = await runBulk(bookedSel, "cancel");
    toast.success(`${res.booked_count} cancelled${res.failed_count ? `, ${res.failed_count} failed` : ""}`);
    if (res.failed_count) setBulkResult(res);
    setSelected(new Set());
    setBulkBusy("");
    load();
  };

  const cancelOne = async (o) => {
    if (!window.confirm(`Cancel the ${o.courier} label for ${o.order_number}? It is voided and you can rebook after.`)) return;
    try {
      const res = await api.post(`/${COURIERS[o.courier].api}/cancel`, { order_id: o.id });
      toast.success(`Cancelled (${res.data.cancelled || o.order_number})`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Cancel failed", { duration: 9000 });
    }
  };

  const doDispatch = async () => {
    if (!dispatchFor) return;
    setDispatching(true);
    try {
      await api.post(`/${COURIERS[dispatchFor.courier].api}/dispatch`, { order_id: dispatchFor.id, docket_no: docketNo.trim() });
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

  const syncDtdc = async () => {
    try {
      const res = await api.post("/dtdc/sync-tracking");
      toast.success(res.data.count ? `${res.data.count} DTDC order(s) dispatched` : "No DTDC pickups reported yet");
      if (res.data.count) load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sync failed");
    }
  };

  // ── unassigned: find the cheapest courier, set it with one click ──
  const findCheapest = async (o) => {
    const pin = o.shipping_address?.pincode;
    if (!/^\d{6}$/.test(String(pin || ""))) return toast.error("This order has no valid pincode");
    setBusy(p => ({ ...p, [o.id]: true }));
    try {
      const res = await api.get("/rates/compare", { params: { pincode: pin, weight: parseFloat(o.weight_kg), cod: !!o.is_cod } });
      setCheapest(p => ({ ...p, [o.id]: (res.data.options || []).filter(x => x.serviceable && x.total).slice(0, 4) }));
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not compare right now");
    } finally {
      setBusy(p => ({ ...p, [o.id]: false }));
    }
  };

  const setCourier = async (o, carrier) => {
    const courier = carrier === "Amazon Shipping" ? "Amazon" : carrier;
    try {
      await api.post("/shipments/set-courier", { order_id: o.id, courier_name: courier });
      toast.success(`${o.order_number} → ${courier}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not set the courier", { duration: 9000 });
    }
  };

  const allVisibleSelected = visible.length > 0 && visible.every(o => selected.has(o.id));

  return (
    <div className="space-y-4" data-testid="book-shipments">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Truck className="w-6 h-6" /> Book Shipments</h1>
          <p className="text-sm text-muted-foreground">Every weighed DTDC, Amazon and Shiprocket order in one list. Book, print and dispatch from here.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {wallet != null && (
            <Badge variant="outline" className={`gap-1.5 py-1 ${wallet < LOW_WALLET ? "border-red-400 text-red-600" : ""}`} data-testid="ship-sr-wallet">
              <Wallet className="w-3.5 h-3.5" /> Shiprocket {inr(wallet)}
              <a href={RECHARGE_URL.Shiprocket} target="_blank" rel="noreferrer" className="underline flex items-center gap-0.5 font-semibold">
                Recharge <ExternalLink className="w-3 h-3" />
              </a>
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={syncDtdc} data-testid="ship-dtdc-sync">
            <PackageCheck className="w-4 h-4 mr-1" /> Check DTDC Pickups
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map(f => (
          <button key={f} type="button" onClick={() => setFilter(f)} data-testid={`ship-filter-${f}`}
                  className={`rounded-full border px-3 py-1.5 text-sm transition ${filter === f ? "border-primary bg-primary text-primary-foreground font-semibold" : "border-border hover:bg-muted"}`}>
            {f} <span className="opacity-70">({counts[f] || 0})</span>
          </button>
        ))}
      </div>

      {Object.entries(loadErrors).map(([c, msg]) => (
        <p key={c} className="text-xs text-destructive">{c}: {msg}</p>
      ))}

      {filter !== "Unassigned" && picked.length > 0 && (
        <Card className="border-primary/60 sticky top-0 z-10">
          <CardContent className="pt-4 flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">
              {picked.length} selected
              {toBook.length > 0 && ` · ${toBook.length} to book`}
              {bookedSel.length > 0 && ` · ${bookedSel.length} booked`}
            </span>
            <Button size="sm" onClick={bulkBook} disabled={!!bulkBusy || toBook.length === 0} data-testid="ship-bulk-book">
              {bulkBusy === "book" ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking {toBook.length}…</>
                                   : <><Truck className="w-4 h-4 mr-1" /> Book Selected ({toBook.length})</>}
            </Button>
            <Button variant="outline" size="sm" onClick={() => openLabels(bookedSel.map(o => o.id))}
                    disabled={bookedSel.length === 0} data-testid="ship-bulk-print">
              <Printer className="w-4 h-4 mr-1" /> Print All Labels ({bookedSel.length})
            </Button>
            <Button variant="outline" size="sm" onClick={bulkCancel} disabled={!!bulkBusy || bookedSel.length === 0}
                    className="text-destructive" data-testid="ship-bulk-cancel">
              {bulkBusy === "cancel" ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : null} Cancel Labels ({bookedSel.length})
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())} disabled={!!bulkBusy}>Clear</Button>
          </CardContent>
        </Card>
      )}

      {bulkResult && (
        <Card className={bulkResult.failed_count ? "border-amber-500/60" : "border-emerald-500/60"}>
          <CardContent className="pt-4 text-sm space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-semibold">
                Bulk {bulkResult.action}: {bulkResult.booked_count} done, {bulkResult.failed_count} failed
              </span>
              <div className="flex gap-1">
                {bulkResult.action === "book" && bulkResult.booked_count > 0 && (
                  <Button variant="outline" size="sm" onClick={() => openLabels(bulkResult.booked.map(b => b.order_id))} data-testid="ship-print-just-booked">
                    <Printer className="w-4 h-4 mr-1" /> Print these {bulkResult.booked_count} labels
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => setBulkResult(null)}>Dismiss</Button>
              </div>
            </div>
            {(bulkResult.failed || []).map((f, i) => (
              <div key={i} className="text-xs text-destructive"><b>{f.order_number}</b> ({f.courier}): {f.error}</div>
            ))}
          </CardContent>
        </Card>
      )}

      {filter === "Unassigned" ? (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <Table className="min-w-[820px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Order #</TableHead><TableHead>Customer</TableHead><TableHead>Destination</TableHead>
                  <TableHead>Wt / Boxes</TableHead><TableHead>Cheapest options — click one to set it</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unassigned.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-10">
                    Every weighed courier order already has a courier.
                  </TableCell></TableRow>
                )}
                {unassigned.map(o => (
                  <TableRow key={o.id} data-testid={`ship-unassigned-${o.id}`}>
                    <TableCell className="font-mono text-sm">{o.order_number}</TableCell>
                    <TableCell className="text-sm">
                      {o.customer_name}
                      {o.is_cod && <Badge className="ml-1.5 bg-amber-100 text-amber-800 text-[10px] px-1 py-0">COD ₹{Number(o.cod_amount || 0).toFixed(0)}</Badge>}
                      {o.carrier_risk && <Badge className="ml-1.5 bg-red-100 text-red-800 text-[10px] px-1 py-0">carrier risk → DTDC only</Badge>}
                    </TableCell>
                    <TableCell className="text-sm">{o.shipping_address?.city || "—"}{o.shipping_address?.pincode ? ` · ${o.shipping_address.pincode}` : ""}</TableCell>
                    <TableCell className="text-sm font-mono whitespace-nowrap">{o.weight_kg} kg / {o.num_boxes}</TableCell>
                    <TableCell>
                      {!cheapest[o.id] ? (
                        <Button size="sm" variant="outline" className="text-xs h-7" disabled={!!busy[o.id]} onClick={() => findCheapest(o)}>
                          {busy[o.id] ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Scale className="w-3 h-3 mr-1" />} Find cheapest
                        </Button>
                      ) : cheapest[o.id].length === 0 ? (
                        <span className="text-xs text-destructive">No courier could be priced for this pincode</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {cheapest[o.id].map((x, i) => (
                            <button key={i} type="button" onClick={() => setCourier(o, x.carrier)}
                                    title={x.warning || ""}
                                    className={`rounded-md border px-2 py-1 text-xs text-left hover:bg-accent ${i === 0 ? "border-emerald-500" : "border-border"}`}>
                              <span className="font-semibold">{i === 0 && <Trophy className="w-3 h-3 inline mr-0.5 text-emerald-600" />}{x.carrier}</span>
                              <span className="text-muted-foreground"> {x.service}</span> · <span className="font-mono">{inr(x.total)}</span>
                              {x.warning && <AlertTriangle className="w-3 h-3 inline ml-1 text-amber-600" />}
                            </button>
                          ))}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            {loading ? (
              <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
            ) : (
              <Table className="min-w-[980px]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <Checkbox checked={allVisibleSelected} aria-label="Select all" data-testid="ship-select-all"
                        onCheckedChange={(v) => setSelected(prev => {
                          const n = new Set(prev);
                          visible.forEach(o => (v ? n.add(o.id) : n.delete(o.id)));
                          return n;
                        })} />
                    </TableHead>
                    <TableHead>Courier</TableHead>
                    <TableHead className="whitespace-nowrap">Order #</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>Destination</TableHead>
                    <TableHead className="whitespace-nowrap">Wt / Boxes</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visible.length === 0 && (
                    <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10">
                      No orders ready. Set an order's courier to DTDC, Amazon or Shiprocket and have packing enter the weight.
                    </TableCell></TableRow>
                  )}
                  {visible.map(o => {
                    const sh = o.dtdc_shipment || o.amazon_shipment || o.shiprocket_shipment || {};
                    const sa = o.shipping_address || {};
                    const blocked = o.courier === "DTDC" && o.serviceable === false;
                    return (
                      <TableRow key={o.id} data-testid={`ship-row-${o.id}`}>
                        <TableCell><Checkbox checked={selected.has(o.id)} onCheckedChange={() => toggle(o.id)} data-testid={`ship-select-${o.id}`} /></TableCell>
                        <TableCell>
                          <Badge className={`${COURIERS[o.courier].badge} text-xs`}>{o.courier}</Badge>
                          {o.courier === "DTDC" && o.account && (
                            <div className="text-[10px] text-muted-foreground mt-0.5">
                              {o.account} · {o.service_type}
                              {o.risk_surcharge && <span className="text-red-600"> · <ShieldCheck className="w-2.5 h-2.5 inline" /> risk</span>}
                            </div>
                          )}
                          {o.courier === "Shiprocket" && sh.courier_name && <div className="text-[10px] text-muted-foreground mt-0.5">{sh.courier_name}</div>}
                          {o.courier === "Shiprocket" && !o.booked && o.shiprocket_courier?.name && <div className="text-[10px] text-violet-700 dark:text-violet-300 mt-0.5">wants {o.shiprocket_courier.name}</div>}
                        </TableCell>
                        <TableCell className="font-mono text-sm">{o.order_number}</TableCell>
                        <TableCell className="text-sm">
                          {o.customer_name}
                          {o.is_cod && <Badge className="ml-1.5 bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 text-[10px] px-1 py-0 align-middle">COD ₹{Number(o.cod_amount || 0).toFixed(0)}</Badge>}
                        </TableCell>
                        <TableCell className="text-sm">
                          {sa.city || "—"}{sa.pincode ? ` · ${sa.pincode}` : ""}
                          {blocked && <Badge variant="outline" className="ml-1.5 text-[10px] border-red-300 text-red-600">not serviceable</Badge>}
                        </TableCell>
                        <TableCell className="text-sm font-mono whitespace-nowrap">{o.weight_kg} kg / {o.num_boxes}</TableCell>
                        <TableCell>
                          {o.booked ? (
                            <div className="flex flex-col gap-0.5">
                              <Badge className="bg-green-100 text-green-800 text-xs w-fit">Booked</Badge>
                              <span className="font-mono text-[11px] text-muted-foreground">{o.tracking}{sh.rate ? ` · ${inr(sh.rate)}` : ""}</span>
                              {sh.pickup_date && <span className="text-[11px] text-emerald-700 dark:text-emerald-400">Pickup: {sh.pickup_date}</span>}
                              {sh.etd && <span className="text-[11px] text-muted-foreground">Delivery by: {sh.etd}</span>}
                            </div>
                          ) : (
                            <div className="flex flex-col gap-0.5">
                              <Badge variant="outline" className="text-xs w-fit">Not booked</Badge>
                              {o.est_charge ? <span className="text-[11px] text-muted-foreground">est. ₹{o.est_charge}</span> : null}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          {o.booked ? (
                            <div className="flex gap-1 flex-wrap">
                              <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => openLabels([o.id])} data-testid={`ship-print-${o.id}`}>
                                <Printer className="w-3 h-3 mr-1" /> Label
                              </Button>
                              <Button variant="outline" size="sm" className="text-xs h-7" data-testid={`ship-dispatch-${o.id}`}
                                onClick={() => { setDispatchFor(o); setDocketNo(o.tracking || ""); }}>Dispatch</Button>
                              <Button variant="outline" size="sm" className="text-xs h-7 text-destructive" onClick={() => cancelOne(o)} data-testid={`ship-cancel-${o.id}`}>Cancel</Button>
                            </div>
                          ) : (
                            <Button size="sm" className="text-xs h-7" disabled={!!busy[o.id] || blocked} onClick={() => startBooking(o)} data-testid={`ship-book-${o.id}`}>
                              {busy[o.id] ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Truck className="w-3 h-3 mr-1" />}
                              {o.courier === "DTDC" ? "Book" : "Get Rates & Book"}
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
      )}

      {/* Bulk review — every order's fare, weight, payment mode and carrier, before anything is bought */}
      <Dialog open={!!review} onOpenChange={(v) => { if (!v && bulkBusy !== "book") setReview(null); }}>
        <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Review before booking — {reviewRows.length} order{reviewRows.length === 1 ? "" : "s"}</DialogTitle>
            <DialogDescription>Check the fare, weight and payment mode of every order. Pick the carrier for Shiprocket orders. Nothing is booked until you press the button below.</DialogDescription>
          </DialogHeader>
          <div className="overflow-x-auto">
            <Table className="min-w-[900px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Order</TableHead><TableHead>Courier</TableHead><TableHead>Weight</TableHead><TableHead>To</TableHead>
                  <TableHead>Paid how</TableHead><TableHead>Service / Carrier</TableHead><TableHead className="text-right">Fare (incl. GST)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reviewRows.map(o => {
                  const r = review[o.id];
                  const fare = rowFare(r);
                  const sa = o.shipping_address || {};
                  const optKey = (c) => String(r.courier === "Amazon" ? (c.rate_id || c.service_id) : c.courier_id);
                  return (
                    <TableRow key={o.id} data-testid={`ship-review-${o.id}`}>
                      <TableCell className="align-top">
                        <div className="font-mono text-sm">{o.order_number}</div>
                        <div className="text-xs text-muted-foreground">{o.customer_name}</div>
                        {r.declared !== undefined && (
                          <div className="mt-1">
                            <Input value={r.declared} placeholder="Declared value ₹" inputMode="decimal" className="h-7 w-32 text-xs"
                              onChange={e => setReview(x => ({ ...x, [o.id]: { ...x[o.id], declared: e.target.value.replace(/[^\d.]/g, "") } }))} />
                            <div className="text-[10px] text-amber-600">Order total is ₹0 — enter the declared value</div>
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="align-top">
                        <Badge className={`${COURIERS[o.courier].badge} text-xs`}>{o.courier}</Badge>
                        {r.courier === "DTDC" && r.preview && <div className="text-[10px] text-muted-foreground mt-0.5">{r.preview.account} · {r.preview.service_type}{r.preview.risk_surcharge ? " · risk" : ""}</div>}
                      </TableCell>
                      <TableCell className="align-top font-mono text-sm whitespace-nowrap">{o.weight_kg} kg / {o.num_boxes}</TableCell>
                      <TableCell className="align-top text-sm">{sa.city || "—"}{sa.pincode ? ` · ${sa.pincode}` : ""}</TableCell>
                      <TableCell className="align-top">
                        {r.courier === "DTDC" ? (
                          <span className="text-xs text-muted-foreground">Prepaid (account)</span>
                        ) : (
                          <div className="flex gap-1">
                            {[["prepaid", "Prepaid"], ["cod", "COD"]].map(([m, label]) => (
                              <button key={m} type="button" disabled={r.loading} onClick={() => m !== r.mode && requoteRow(o, m)}
                                      className={`rounded-md border px-2 py-1 text-xs transition ${r.mode === m
                                        ? (m === "cod" ? "border-amber-500 bg-amber-100 dark:bg-amber-900/40 font-semibold" : "border-sky-500 bg-sky-100 dark:bg-sky-900/40 font-semibold")
                                        : "border-border hover:bg-muted"}`}>{label}</button>
                            ))}
                          </div>
                        )}
                        {r.mode === "cod" && r.codAmount > 0 && <div className="text-[10px] text-amber-700 mt-0.5">collect {inr(r.codAmount)}</div>}
                      </TableCell>
                      <TableCell className="align-top">
                        {r.loading ? <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                         : r.error ? <span className="text-xs text-destructive">{r.error}</span>
                         : r.courier === "DTDC" ? <span className="text-xs">{r.preview?.series} · {r.preview?.city}</span>
                         : (
                          <>
                            <select value={r.choice ? optKey(r.choice) : ""}
                              className="h-8 max-w-[260px] rounded-md border border-border bg-background px-2 text-xs"
                              data-testid={`ship-review-pick-${o.id}`}
                              onChange={e => setReview(x => {
                                const pick = x[o.id].options.find(c => optKey(c) === e.target.value);
                                return { ...x, [o.id]: { ...x[o.id], choice: pick || x[o.id].choice } };
                              })}>
                              {r.options.map((c, i) => (
                                <option key={i} value={optKey(c)}>
                                  {r.courier === "Amazon" ? `${c.service} — ${fmtAmazonRate(c.amount, c.currency)}` : `${c.name} — ${inr(c.rate)}${i === 0 ? " (cheapest)" : ""}${c.name === r.preferred ? " (chosen on order)" : ""}`}
                                </option>
                              ))}
                            </select>
                            {r.preferredMissing && <div className="text-[10px] text-amber-600">{r.preferred} (chosen on order) is not offered now</div>}
                            {r.courier === "Shiprocket" && r.choice && (
                              <div className="text-[10px] text-muted-foreground mt-0.5">
                                {r.choice.etd ? `delivery by ${r.choice.etd}` : ""}{r.choice.cutoff_time ? ` · pickup today if before ${r.choice.cutoff_time}` : ""}
                                <label className="ml-2 inline-flex items-center gap-1 cursor-pointer">
                                  <Checkbox checked={!!r.insure} onCheckedChange={v => setReview(x => ({ ...x, [o.id]: { ...x[o.id], insure: !!v } }))} className="h-3 w-3" /> insure
                                </label>
                              </div>
                            )}
                          </>
                        )}
                      </TableCell>
                      <TableCell className="align-top text-right font-mono font-semibold whitespace-nowrap">{fare != null ? inr(fare) : "—"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-3">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">
              This buys {reviewRows.length} real shipment{reviewRows.length === 1 ? "" : "s"} for about <b>{inr(reviewTotal)}</b> in total and schedules pickups. Amazon fares are shown with 18% GST added.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReview(null)} disabled={bulkBusy === "book"}>Cancel</Button>
            <Button onClick={confirmBulk} disabled={!reviewReady || bulkBusy === "book"} data-testid="ship-review-confirm">
              {bulkBusy === "book" ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking…</> : `Book ${reviewRows.length} — ${inr(reviewTotal)}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmation — nothing is purchased until this is confirmed */}
      <Dialog open={!!confirm} onOpenChange={(v) => { if (!v && !booking) closeConfirm(); }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Confirm {confirm?.courier} Booking</DialogTitle>
            <DialogDescription>
              Order {confirm?.order?.order_number} · {confirm?.order?.customer_name} · {confirm?.order?.weight_kg} kg
            </DialogDescription>
          </DialogHeader>

          {confirm?.courier === "DTDC" && confirm.preview && (
            <div className="space-y-2 text-sm">
              {[
                ["Account", confirm.preview.account], ["Service", confirm.preview.service_type],
                ["Series", confirm.preview.series], ["Destination", confirm.preview.city],
                ["Weight / Boxes", `${confirm.preview.weight_kg} kg · ${confirm.preview.num_boxes}`],
                ["Declared value", `₹${confirm.preview.declared_value}`],
                ["Carrier risk", confirm.preview.risk_surcharge ? "YES" : "No"],
                ["Est. charge", `₹${confirm.preview.est_charge}`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border/60 pb-1">
                  <span className="text-muted-foreground">{k}</span><span className="font-medium">{v}</span>
                </div>
              ))}
            </div>
          )}

          {confirm && confirm.courier !== "DTDC" && (
            <>
              <div className="rounded-md border-2 px-3 py-2.5 space-y-2"
                   style={{ borderColor: payMode === "cod" ? "rgb(245 158 11)" : "rgb(14 165 233)" }}>
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">How is this shipment paid?</div>
                <div className="flex gap-2">
                  {[["prepaid", "Prepaid"], ["cod", "Cash on delivery"]].map(([m, label]) => (
                    <button key={m} type="button" disabled={booking} onClick={() => startBooking(confirm.order, m)} data-testid={`ship-paymode-${m}`}
                            className={`flex-1 rounded-md border px-3 py-2 text-sm transition ${
                              payMode === m
                                ? (m === "cod" ? "border-amber-500 bg-amber-100 dark:bg-amber-900/40 font-semibold"
                                               : "border-sky-500 bg-sky-100 dark:bg-sky-900/40 font-semibold")
                                : "border-border hover:bg-muted"}`}>
                      {label}
                    </button>
                  ))}
                </div>
                {payMode === "cod"
                  ? <p className="text-sm">The courier will collect <b>{inr(confirm.codAmount)}</b> from the customer. Rates below include the COD fee.</p>
                  : <p className="text-sm text-muted-foreground">Nothing will be collected on delivery.</p>}
              </div>

              <div className="space-y-2">
                {(confirm.options || []).map((r, i) => {
                  const isAmz = confirm.courier === "Amazon";
                  const key = isAmz ? (r.rate_id || r.service_id) : r.courier_id;
                  const active = (isAmz ? (choice?.rate_id || choice?.service_id) : choice?.courier_id) === key;
                  return (
                    <button key={key ?? i} onClick={() => setChoice(r)} data-testid={`ship-opt-${i}`}
                      className={`w-full text-left rounded-lg border p-3 transition-colors ${active ? "border-primary bg-accent" : "border-border hover:bg-accent/50"}`}>
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium text-sm">
                          {isAmz ? r.service : r.name}
                          {!isAmz && i === 0 && <Badge className="ml-1.5 bg-emerald-600 text-white text-[10px] px-1 py-0">CHEAPEST</Badge>}
                        </span>
                        <div className="text-right shrink-0">
                          <div className="font-mono font-semibold">{isAmz ? fmtAmazonRate(r.amount, r.currency) : inr(r.rate)}</div>
                          <div className="text-[11px] text-muted-foreground font-mono">{isAmz ? fmtAmazonRateBreakdown(r.amount, r.currency) : "GST included"}</div>
                        </div>
                      </div>
                      {isAmz ? (
                        <>
                          {r.billed_weight ? (
                            <div className="text-[11px] text-muted-foreground mt-0.5">
                              Billed weight {r.billed_weight} {(r.billed_weight_unit || "KG").toLowerCase()}
                              {Number(r.billed_weight) > Number(confirm.order.weight_kg) && (
                                <span className="text-amber-600"> — volumetric, from the {confirm.box_cm?.length}×{confirm.box_cm?.width}×{confirm.box_cm?.height} cm box{confirm.boxMeasured === false && " (assumed — not measured)"}</span>
                              )}
                            </div>
                          ) : null}
                          {fmtWindow(r.promise?.pickupWindow) && (
                            <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1 flex items-center gap-1"><PackageCheck className="w-3 h-3" /> Pickup: {fmtWindow(r.promise.pickupWindow)}</p>
                          )}
                          {fmtWindow(r.promise?.deliveryWindow) && (
                            <p className="text-xs text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> Delivery: {fmtWindow(r.promise.deliveryWindow)}</p>
                          )}
                        </>
                      ) : (
                        <>
                          <div className="text-[11px] text-muted-foreground mt-1">
                            {[r.surface ? "Surface" : "Air", r.rating && `rating ${r.rating}`, r.rto_charges != null && `return (RTO) ${inr(r.rto_charges)}`].filter(Boolean).join(" · ")}
                          </div>
                          {r.cutoff_time && <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1 flex items-center gap-1"><PackageCheck className="w-3 h-3" /> Same-day pickup if booked before {r.cutoff_time}</p>}
                          {r.etd && <p className="text-xs text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> Expected delivery: {r.etd}{r.days ? ` (${r.days} days)` : ""}</p>}
                        </>
                      )}
                    </button>
                  );
                })}
              </div>

              {confirm.courier === "Shiprocket" && (
                <label className="flex items-start gap-2 rounded-md border p-3 cursor-pointer">
                  <Checkbox checked={insure} onCheckedChange={v => setInsure(!!v)} className="mt-0.5" data-testid="ship-insure" />
                  <span className="text-sm">
                    <b>Insure this shipment</b> (Shiprocket "Secure Shipment")
                    <span className="block text-xs text-muted-foreground">Extra fee charged by Shiprocket. Without it, a lost or damaged parcel is refunded only up to a small fixed limit.</span>
                  </span>
                </label>
              )}
            </>
          )}

          <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-3">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">
              {confirm?.courier === "DTDC"
                ? <>This creates a real consignment on account <b>{confirm?.preview?.account}</b> and schedules a pickup.</>
                : <>This buys a real {confirm?.courier} shipment and schedules a pickup.</>}
            </p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeConfirm} disabled={booking}>Cancel</Button>
            <Button onClick={doBook} disabled={booking || (confirm?.courier !== "DTDC" && !choice)} data-testid="ship-confirm-book">
              {booking ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking…</>
                : confirm?.courier === "DTDC" ? "Confirm & Book"
                : payMode === "cod" ? `Book as COD — collect ${inr(confirm?.codAmount)}` : "Book as Prepaid"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!dispatchFor} onOpenChange={(v) => { if (!v && !dispatching) { setDispatchFor(null); setDocketNo(""); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Dispatch Order</DialogTitle>
            <DialogDescription>{dispatchFor?.order_number} · {dispatchFor?.courier} · marks it dispatched without waiting for the pickup scan.</DialogDescription>
          </DialogHeader>
          <div>
            <Label>Tracking / Docket No.</Label>
            <Input value={docketNo} onChange={e => setDocketNo(e.target.value)} className="mt-1.5 font-mono" placeholder="Tracking number" data-testid="ship-docket-input" />
            <p className="text-xs text-muted-foreground mt-1.5">The courier label is attached automatically as the dispatch slip.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDispatchFor(null); setDocketNo(""); }} disabled={dispatching}>Cancel</Button>
            <Button onClick={doDispatch} disabled={dispatching || !docketNo.trim()} data-testid="ship-confirm-dispatch">
              {dispatching ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Dispatching…</> : "Mark Dispatched"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
