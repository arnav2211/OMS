import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, RefreshCw, Printer, AlertTriangle, Truck, PackageCheck, ShieldCheck } from "lucide-react";

const ACCOUNT_COLORS = {
  RL1386: "bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300",
  RL1423: "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300",
  RL1387: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
};

export default function DTDCBookPanel() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [confirm, setConfirm] = useState(null);      // { order, preview }
  const [booking, setBooking] = useState(false);
  const [dispatchFor, setDispatchFor] = useState(null);
  const [docketNo, setDocketNo] = useState("");
  const [dispatching, setDispatching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/dtdc/bookable");
      setOrders(res.data || []);
      setSelected(new Set());
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load DTDC orders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const booked = orders.filter(o => o.dtdc_shipment?.reference_number);
  const bookedSelected = [...selected].filter(id => booked.some(b => b.id === id));

  // DTDC labels print full-size on A4. Single opens the original PDF (or the
  // instant replica while DTDC's sync lags); bulk is one label page per A4 page.
  const sheetUrl = (ids) =>
    `${process.env.REACT_APP_BACKEND_URL}/api/dtdc/labels-sheet?ids=${ids.join(",")}&token=${localStorage.getItem("token")}`;

  const printOne = (o) =>
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/dtdc/label/${o.id}?token=${localStorage.getItem("token")}`, "_blank");

  // Unbooked selection drives bulk booking; booked selection drives slip printing.
  const unbookedSelected = [...selected].filter(
    id => orders.some(o => o.id === id && !o.dtdc_shipment?.reference_number));
  const [bulkBooking, setBulkBooking] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);

  const bulkBook = async () => {
    if (unbookedSelected.length === 0) return;
    setBulkBooking(true);
    try {
      const res = await api.post("/dtdc/bulk-book", { order_ids: unbookedSelected });
      setBulkResult(res.data);
      if (res.data.booked_count) toast.success(`Booked ${res.data.booked_count} consignment(s)`);
      if (res.data.failed_count) toast.error(`${res.data.failed_count} failed — see the summary`);
      setSelected(new Set());
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Bulk booking failed");
    } finally {
      setBulkBooking(false);
    }
  };

  const printBulk = () => {
    if (bookedSelected.length === 0) return toast.error("Select booked orders to print");
    window.open(sheetUrl(bookedSelected), "_blank");
  };

  const openConfirm = async (o) => {
    setBusy(p => ({ ...p, [o.id]: true }));
    try {
      const res = await api.post("/dtdc/preview", { order_id: o.id });
      setConfirm({ order: o, preview: res.data });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not prepare booking", { duration: 8000 });
    } finally {
      setBusy(p => ({ ...p, [o.id]: false }));
    }
  };

  const doBook = async () => {
    if (!confirm) return;
    setBooking(true);
    try {
      const res = await api.post("/dtdc/book", { order_id: confirm.order.id });
      toast.success(`Booked on ${res.data.shipment?.account} — ${res.data.shipment?.awb || res.data.shipment?.reference_number}`, { duration: 9000 });
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Booking failed", { duration: 10000 });
    } finally {
      setBooking(false);
    }
  };

  const doDispatch = async () => {
    if (!dispatchFor) return;
    setDispatching(true);
    try {
      await api.post("/dtdc/dispatch", { order_id: dispatchFor.id, docket_no: docketNo.trim() });
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

  const syncNow = async () => {
    try {
      const res = await api.post("/dtdc/sync-tracking");
      toast.success(res.data.count ? `${res.data.count} order(s) dispatched` : "No pickups reported yet");
      if (res.data.count) load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sync failed");
    }
  };

  const toggle = (id) => setSelected(prev => {
    const n = new Set(prev);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  return (
    <div className="space-y-4" data-testid="dtdc-book-panel">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-muted-foreground">
          DTDC orders weighed by packing. Booking charges the routed account — no Excel needed.
        </p>
        <div className="flex gap-2">
          <Button size="sm" onClick={bulkBook}
                  disabled={unbookedSelected.length === 0 || bulkBooking}
                  data-testid="dtdc-bulk-book">
            {bulkBooking ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Truck className="w-4 h-4 mr-1" />}
            Book Selected ({unbookedSelected.length})
          </Button>
          <Button variant="outline" size="sm" onClick={printBulk} disabled={bookedSelected.length === 0} data-testid="dtdc-bulk-print">
            <Printer className="w-4 h-4 mr-1" /> Print Slips ({bookedSelected.length})
          </Button>
          <Button variant="outline" size="sm" onClick={syncNow} data-testid="dtdc-sync">
            <PackageCheck className="w-4 h-4 mr-1" /> Check Pickups
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

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
              <div key={i} className="text-xs text-destructive">
                <b>{f.order_number}</b>: {f.error}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
          ) : (
            <Table className="min-w-[1000px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={orders.length > 0 && selected.size === orders.length}
                      onCheckedChange={(v) => setSelected(v ? new Set(orders.map(o => o.id)) : new Set())}
                      aria-label="Select all"
                      data-testid="dtdc-select-all" />
                  </TableHead>
                  <TableHead className="whitespace-nowrap">Order #</TableHead>
                  <TableHead className="whitespace-nowrap">Customer</TableHead>
                  <TableHead className="whitespace-nowrap">Destination</TableHead>
                  <TableHead className="whitespace-nowrap">Wt / Boxes</TableHead>
                  <TableHead className="whitespace-nowrap">Routes to</TableHead>
                  <TableHead className="whitespace-nowrap">Est.</TableHead>
                  <TableHead className="whitespace-nowrap">Status</TableHead>
                  <TableHead className="whitespace-nowrap">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center text-muted-foreground py-10">
                      No DTDC orders ready. Set an order's courier to <b>DTDC</b> and have packing enter the weight.
                    </TableCell>
                  </TableRow>
                )}
                {orders.map(o => {
                  const sh = o.dtdc_shipment;
                  const isBooked = !!sh?.reference_number;
                  return (
                    <TableRow key={o.id} data-testid={`dtdc-row-${o.id}`}>
                      <TableCell>
                        {/* Selectable whether booked or not: booked rows feed
                            Print Slips, unbooked rows feed Book Selected. */}
                        <Checkbox checked={selected.has(o.id)} onCheckedChange={() => toggle(o.id)} data-testid={`dtdc-select-${o.id}`} />
                      </TableCell>
                      <TableCell className="font-mono text-sm">{o.order_number}</TableCell>
                      <TableCell className="text-sm">{o.customer_name}</TableCell>
                      <TableCell className="text-sm">
                        {o.shipping_address?.city || "—"}
                        {o.shipping_address?.pincode ? ` · ${o.shipping_address.pincode}` : ""}
                        {!o.serviceable && <Badge variant="outline" className="ml-1.5 text-[10px] border-red-300 text-red-600">not serviceable</Badge>}
                      </TableCell>
                      <TableCell className="text-sm font-mono whitespace-nowrap">{o.weight_kg} kg / {o.num_boxes}</TableCell>
                      <TableCell>
                        {o.account ? (
                          <div className="flex flex-col gap-0.5">
                            <Badge className={`${ACCOUNT_COLORS[o.account] || ""} text-xs w-fit`}>{o.account}</Badge>
                            <span className="text-[10px] text-muted-foreground">{o.service_type}</span>
                            {o.risk_surcharge && (
                              <span className="text-[10px] text-red-600 flex items-center gap-0.5">
                                <ShieldCheck className="w-2.5 h-2.5" /> risk on
                              </span>
                            )}
                          </div>
                        ) : <span className="text-xs text-muted-foreground">—</span>}
                      </TableCell>
                      <TableCell className="text-sm font-mono">{o.est_charge ? `₹${o.est_charge}` : "—"}</TableCell>
                      <TableCell>
                        {isBooked ? (
                          <div className="flex flex-col gap-0.5">
                            <Badge className="bg-green-100 text-green-800 text-xs w-fit">Booked</Badge>
                            <span className="font-mono text-[10px] text-muted-foreground">{sh.awb || sh.reference_number}</span>
                          </div>
                        ) : <Badge variant="outline" className="text-xs">Not booked</Badge>}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1 flex-wrap">
                          {!isBooked ? (
                            <Button size="sm" className="text-xs h-7" disabled={!!busy[o.id] || !o.serviceable}
                              onClick={() => openConfirm(o)} data-testid={`dtdc-book-${o.id}`}>
                              {busy[o.id] ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Truck className="w-3 h-3 mr-1" />}
                              Book
                            </Button>
                          ) : (
                            <>
                              <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => printOne(o)} data-testid={`dtdc-print-${o.id}`}>
                                <Printer className="w-3 h-3 mr-1" /> Slip
                              </Button>
                              <Button variant="outline" size="sm" className="text-xs h-7"
                                onClick={() => { setDispatchFor(o); setDocketNo(sh.awb || sh.reference_number || ""); }}
                                data-testid={`dtdc-dispatch-${o.id}`}>
                                Dispatch
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Booking confirmation — nothing is booked until confirmed */}
      <Dialog open={!!confirm} onOpenChange={(v) => { if (!v && !booking) setConfirm(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm DTDC Booking</DialogTitle>
            <DialogDescription>
              {confirm?.order?.order_number} · {confirm?.order?.customer_name}
            </DialogDescription>
          </DialogHeader>
          {confirm?.preview && (
            <div className="space-y-2 text-sm">
              {[
                ["Account", confirm.preview.account],
                ["Service", confirm.preview.service_type],
                ["Series", confirm.preview.series],
                ["Destination", confirm.preview.city],
                ["Weight / Boxes", `${confirm.preview.weight_kg} kg · ${confirm.preview.num_boxes}`],
                ["Declared value", `₹${confirm.preview.declared_value}`],
                ["Carrier risk", confirm.preview.risk_surcharge ? "YES" : "No"],
                ["Est. charge", `₹${confirm.preview.est_charge}`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border/60 pb-1">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-medium">{v}</span>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-3">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">
              This creates a real consignment on account <b>{confirm?.preview?.account}</b> and schedules a pickup.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)} disabled={booking}>Cancel</Button>
            <Button onClick={doBook} disabled={booking} data-testid="dtdc-confirm-book">
              {booking ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Booking…</> : "Confirm & Book"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Manual dispatch before pickup is reported */}
      <Dialog open={!!dispatchFor} onOpenChange={(v) => { if (!v && !dispatching) setDispatchFor(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Dispatch Order</DialogTitle>
            <DialogDescription>
              {dispatchFor?.order_number} · marks it dispatched without waiting for DTDC pickup.
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label>Docket / Consignment No.</Label>
            <Input value={docketNo} onChange={e => setDocketNo(e.target.value)} className="mt-1.5 font-mono"
              placeholder="Docket number" data-testid="dtdc-docket-input" />
            <p className="text-xs text-muted-foreground mt-1.5">
              The DTDC slip is fetched and attached automatically as the dispatch slip.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDispatchFor(null)} disabled={dispatching}>Cancel</Button>
            <Button onClick={doDispatch} disabled={dispatching || !docketNo.trim()} data-testid="dtdc-confirm-dispatch">
              {dispatching ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Dispatching…</> : "Mark Dispatched"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
