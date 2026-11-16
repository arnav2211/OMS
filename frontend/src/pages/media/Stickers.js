import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Search, RefreshCw, Check, Ban, RotateCcw, Copy, Bell, BellOff, Truck, AlertTriangle, ExternalLink } from "lucide-react";
import MediaOrderDetails from "@/components/MediaOrderDetails";
import CourierStatusDialog from "@/components/CourierStatusDialog";
import { SHIP_FILTERS, SHIP_BADGE, shipLabel } from "@/lib/mediaShipping";
import { getTrackingUrl } from "@/lib/courierTracking";

const VIEWS = [["todo", "To Print"], ["done", "Done"], ["all", "All"]];
const SOURCES = [["all", "All"], ["oms", "OMS"], ["amazon", "Amazon"]];
const STATE_BADGE = {
  printed: ["Printed", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"],
  not_required: ["Not required", "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"],
  pending: ["To print", "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"],
};

const SEEN_KEY = "stickers_seen_v1";
const canNotify = typeof window !== "undefined" && "Notification" in window;

function readSeen() {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    return raw ? new Set(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

function writeSeen(ids) {
  try { localStorage.setItem(SEEN_KEY, JSON.stringify(ids)); } catch { /* private window */ }
}

// An edit gives the order a new key, so an edited order alerts again.
const seenKey = (o) => `${o.source}:${o.id}${o.edit?.at ? `:${o.edit.at}` : ""}`;

function chromeAlert(fresh) {
  if (!canNotify || Notification.permission !== "granted") return;
  const edited = fresh.filter((o) => o.edit);
  const title = fresh.length === 1
    ? (edited.length ? `Order edited: ${fresh[0].order_number}` : `New sticker to print: ${fresh[0].order_number}`)
    : `${fresh.length} orders need stickers${edited.length ? ` (${edited.length} edited)` : ""}`;
  const body = fresh.slice(0, 3).map((o) => (o.edit
    ? `${o.order_number} edited by ${o.edit.by}: ${o.edit.changes.join("; ")}`
    : `${o.order_number} - ${o.lines.filter((l) => l.status === "pending").map((l) => l.product).join(", ")}`))
    .join("\n") + (fresh.length > 3 ? `\n+${fresh.length - 3} more` : "");
  try {
    const n = new Notification(title, { body: body.slice(0, 400), tag: "stickers-new", renotify: true, icon: "/favicon.ico" });
    n.onclick = () => { window.focus(); n.close(); };
  } catch { /* some browsers only allow notifications from a service worker */ }
}

function fmtDate(v) {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? String(v).slice(0, 10) : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

export default function Stickers() {
  const [view, setView] = useState("todo");
  const [source, setSource] = useState("all");
  const [q, setQ] = useState("");
  const [ship, setShip] = useState("all");
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/media/orders", { params: { view, source, q } });
      setOrders(res.data || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not load orders");
    } finally {
      setLoading(false);
    }
  }, [view, source, q]);

  useEffect(() => {
    const t = setTimeout(load, q ? 350 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  const [perm, setPerm] = useState(canNotify ? Notification.permission : "unsupported");
  const loadRef = useRef(load);
  loadRef.current = load;
  const seenRef = useRef(null);

  // Every minute: refresh the list and raise a Chrome alert for orders that newly need stickers.
  // What has been seen is remembered in this browser, so reopening the page alerts only for what came in meanwhile.
  useEffect(() => {
    let stop = false;
    const check = async () => {
      try {
        const res = await api.get("/media/orders", { params: { view: "todo", source: "all" } });
        if (stop) return;
        const list = res.data || [];
        const ids = list.map(seenKey);
        if (seenRef.current === null) seenRef.current = readSeen() || new Set(ids);
        const fresh = list.filter((o) => !seenRef.current.has(seenKey(o)));
        if (fresh.length) {
          chromeAlert(fresh);
          const ed = fresh.filter((o) => o.edit).length;
          toast.info(fresh.length === 1
            ? (ed ? `Order edited: ${fresh[0].order_number}` : `New order for stickers: ${fresh[0].order_number}`)
            : `${fresh.length} orders for stickers${ed ? ` (${ed} edited)` : ""}`);
        }
        seenRef.current = new Set(ids);
        writeSeen(ids);
        document.title = list.length ? `(${list.length}) Stickers` : "Stickers";
      } catch { /* next round */ }
    };
    check();
    const t = setInterval(() => { check(); loadRef.current(); }, 60000);
    return () => { stop = true; clearInterval(t); };
  }, []);

  const enableAlerts = async () => {
    if (!canNotify) return;
    const p = await Notification.requestPermission();
    setPerm(p);
    if (p === "granted") {
      try { new Notification("Sticker alerts are on", { body: "You'll get an alert here when a new order needs stickers.", icon: "/favicon.ico" }); } catch { /* ignore */ }
    }
  };

  const mark = async (o, keys, status) => {
    const tag = `${o.id}:${keys.join(",")}:${status}`;
    setBusy(tag);
    try {
      const res = await api.post(`/media/orders/${o.source}/${o.id}/stickers`, { keys, status });
      setOrders((prev) => prev.map((x) => (x.id === o.id
        ? { ...x, lines: res.data.lines, pending: res.data.lines.filter((l) => l.status === "pending").length }
        : x)));
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not save");
      load();
    } finally {
      setBusy("");
    }
  };

  const editSeen = async (o) => {
    setBusy(`seen:${o.id}`);
    try {
      await api.post(`/media/orders/${o.source}/${o.id}/edit-seen`);
      setOrders((prev) => prev.map((x) => (x.id === o.id ? { ...x, edit: null } : x))
        .filter((x) => view !== "todo" || x.pending || x.edit));
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not save");
    } finally {
      setBusy("");
    }
  };

  const copy = (text) => {
    navigator.clipboard?.writeText(text).then(() => toast.success("Copied"), () => {});
  };

  const totalPending = orders.reduce((n, o) => n + (o.pending || 0), 0);
  const shown = ship === "all" ? orders : orders.filter((o) => (o.method || "") === ship);
  const urgentCount = orders.filter((o) => o.urgent).length;

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Stickers</h1>
          <p className="text-sm text-muted-foreground">
            {view === "todo" ? `${orders.length} order(s), ${totalPending} sticker(s) to print` : `${orders.length} order(s)`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {perm === "default" && (
            <Button size="sm" onClick={enableAlerts} data-testid="stickers-alerts-on">
              <Bell className="w-4 h-4 mr-1" /> Turn on Chrome alerts
            </Button>
          )}
          {perm === "granted" && (
            <span className="text-xs text-emerald-700 dark:text-emerald-400 flex items-center gap-1"><Bell className="w-3.5 h-3.5" /> Alerts on</span>
          )}
          {perm === "denied" && (
            <span className="text-xs text-muted-foreground flex items-center gap-1" title="Click the lock icon next to the address and allow Notifications">
              <BellOff className="w-3.5 h-3.5" /> Alerts blocked in Chrome
            </span>
          )}
          <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="stickers-refresh">
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border overflow-hidden">
          {VIEWS.map(([v, label]) => (
            <button key={v} onClick={() => setView(v)} data-testid={`stickers-view-${v}`}
              className={`px-3 py-1.5 text-sm ${view === v ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>{label}</button>
          ))}
        </div>
        <div className="flex rounded-md border overflow-hidden">
          {SOURCES.map(([v, label]) => (
            <button key={v} onClick={() => setSource(v)} data-testid={`stickers-source-${v}`}
              className={`px-3 py-1.5 text-sm ${source === v ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>{label}</button>
          ))}
        </div>
        <select value={ship} onChange={(e) => setShip(e.target.value)} data-testid="stickers-ship-filter"
          className="h-9 rounded-md border bg-background px-2 text-sm">
          {SHIP_FILTERS.map(([v, label]) => {
            const n = v === "all" ? orders.length : orders.filter((o) => (o.method || "") === v).length;
            return <option key={v} value={v}>{label} ({n})</option>;
          })}
        </select>
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order no., customer or product"
            className="pl-8 h-9" data-testid="stickers-search" />
        </div>
      </div>

      {urgentCount > 0 && (
        <div data-testid="stickers-urgent-alert"
          className="w-full flex items-center gap-2 rounded-md border-2 border-red-500 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-300">
          <AlertTriangle className="w-4 h-4" /> {urgentCount} order(s) marked urgent - they are at the top, do these first
        </div>
      )}

      {!loading && shown.length === 0 && (
        <Card><CardContent className="py-10 text-center text-muted-foreground">
          {view === "todo" ? "Nothing to print right now." : "No orders found."}
        </CardContent></Card>
      )}

      {shown.map((o) => {
        const urgent = !!o.urgent;
        const trackUrl = o.docket ? getTrackingUrl(o.source === "amazon" ? "Amazon" : o.courier, o.docket) : null;
        return (
        <Card key={`${o.source}-${o.id}`} data-testid={`sticker-order-${o.order_number}`}
          className={urgent ? "border-2 border-red-500 bg-red-50/60 dark:bg-red-950/30" : ""}>
          <CardContent className="p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{o.order_number}</span>
                  <Badge className={o.source === "amazon"
                    ? "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300"
                    : "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"}>
                    {o.source === "amazon" ? "Amazon" : o.website ? "Website" : "OMS"}
                  </Badge>
                  <span className="text-xs text-muted-foreground capitalize">{o.status}</span>
                  {urgent && (
                    <Badge className="bg-red-600 text-white animate-pulse" data-testid="sticker-urgent-badge"
                      title={o.urgent_by ? `Marked urgent by ${o.urgent_by}` : ""}>
                      <AlertTriangle className="w-3 h-3 mr-1" /> URGENT{o.urgent_by ? ` · ${o.urgent_by}` : ""}
                    </Badge>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-1 text-xs">
                  <Badge className={SHIP_BADGE[o.method] || "bg-muted text-muted-foreground"} data-testid="sticker-ship-badge">
                    <Truck className="w-3 h-3 mr-1" /> {shipLabel(o)}
                  </Badge>
                  {o.city && <span className="text-muted-foreground">{[o.city, o.state].filter(Boolean).join(", ")}</span>}
                  {o.docket && (
                    <span className="font-mono text-muted-foreground">
                      {o.docket}
                      {trackUrl && (
                        <a href={trackUrl} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center text-primary" title="Open tracking">
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </span>
                  )}
                </div>
                <div className="text-sm text-muted-foreground">
                  {o.customer_name || "-"} · {fmtDate(o.created_at)}
                  {o.ship_by ? ` · ship by ${fmtDate(o.ship_by)}` : ""}
                </div>
                {o.remark && <div className="text-xs mt-1 text-red-700 dark:text-red-400">Remark: {o.remark}</div>}
                {o.edit && (
                  <div className="mt-2 rounded-md border-2 border-amber-400 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-sm" data-testid="sticker-edit-box">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-amber-900 dark:text-amber-200">
                        Order edited by {o.edit.by}, {fmtDate(o.edit.at)} {new Date(o.edit.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <Button size="sm" variant="outline" disabled={!!busy} onClick={() => editSeen(o)} data-testid="sticker-edit-seen">
                        <Check className="w-4 h-4 mr-1" /> Seen
                      </Button>
                    </div>
                    <ul className="mt-1 list-disc pl-5 text-amber-900 dark:text-amber-200">
                      {o.edit.changes.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                    <div className="text-xs text-amber-800/80 dark:text-amber-300/80 mt-1">Changed lines are back to "To print".</div>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                <MediaOrderDetails source={o.source} orderId={o.id} orderNumber={o.order_number} />
                {o.source === "oms" && o.docket && (
                  <CourierStatusDialog orderId={o.id} orderNumber={o.order_number} courier={o.courier} docket={o.docket} variant="button" />
                )}
              {o.lines.length > 1 && (
                <>
                  <Button size="sm" variant="outline" disabled={!!busy} onClick={() => mark(o, [], "printed")} data-testid="sticker-all-printed">
                    <Check className="w-4 h-4 mr-1" /> All printed
                  </Button>
                  <Button size="sm" variant="outline" disabled={!!busy} onClick={() => mark(o, [], "not_required")} data-testid="sticker-all-not-required">
                    <Ban className="w-4 h-4 mr-1" /> None needed
                  </Button>
                </>
              )}
              </div>
            </div>

            <div className="divide-y rounded-md border">
              {o.lines.map((l) => {
                const [label, cls] = STATE_BADGE[l.status] || STATE_BADGE.pending;
                return (
                  <div key={l.key} className="flex flex-wrap items-center gap-2 px-3 py-2">
                    <div className="flex-1 min-w-[200px]">
                      <div className="text-sm font-medium flex items-start gap-1.5">
                        <span className="break-words">{l.product}</span>
                        <button onClick={() => copy(l.product)} title="Copy product name" className="text-muted-foreground hover:text-foreground mt-0.5 shrink-0">
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {l.sample ? "Free sample · " : ""}Qty {l.qty ?? "-"}{l.unit ? ` × ${l.unit}` : ""}{l.sku ? ` · SKU ${l.sku}` : ""}
                        {l.note ? ` · ${l.note}` : ""}
                      </div>
                      {l.status !== "pending" && l.by && (
                        <div className="text-[11px] text-muted-foreground">{label} by {l.by}, {fmtDate(l.at)}</div>
                      )}
                    </div>
                    <Badge className={cls}>{label}</Badge>
                    {l.status === "pending" ? (
                      <div className="flex gap-1.5">
                        <Button size="sm" disabled={!!busy} onClick={() => mark(o, [l.key], "printed")} data-testid={`sticker-printed-${l.key}`}>
                          <Check className="w-4 h-4 mr-1" /> Printed
                        </Button>
                        <Button size="sm" variant="outline" disabled={!!busy} onClick={() => mark(o, [l.key], "not_required")} data-testid={`sticker-not-required-${l.key}`}>
                          <Ban className="w-4 h-4 mr-1" /> Not required
                        </Button>
                      </div>
                    ) : (
                      <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => mark(o, [l.key], "pending")} title="Undo" data-testid={`sticker-undo-${l.key}`}>
                        <RotateCcw className="w-4 h-4 mr-1" /> Undo
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
        );
      })}
    </div>
  );
}
