import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Search, RefreshCw, Check, Ban, RotateCcw, Copy } from "lucide-react";

const VIEWS = [["todo", "To Print"], ["done", "Done"], ["all", "All"]];
const SOURCES = [["all", "All"], ["oms", "OMS"], ["amazon", "Amazon"]];
const STATE_BADGE = {
  printed: ["Printed", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"],
  not_required: ["Not required", "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"],
  pending: ["To print", "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"],
};

function fmtDate(v) {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? String(v).slice(0, 10) : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

export default function Stickers() {
  const [view, setView] = useState("todo");
  const [source, setSource] = useState("all");
  const [q, setQ] = useState("");
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

  // keep the queue fresh while the page stays open
  useEffect(() => {
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

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

  const copy = (text) => {
    navigator.clipboard?.writeText(text).then(() => toast.success("Copied"), () => {});
  };

  const totalPending = orders.reduce((n, o) => n + (o.pending || 0), 0);

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Stickers</h1>
          <p className="text-sm text-muted-foreground">
            {view === "todo" ? `${orders.length} order(s), ${totalPending} sticker(s) to print` : `${orders.length} order(s)`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} data-testid="stickers-refresh">
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
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
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order no., customer or product"
            className="pl-8 h-9" data-testid="stickers-search" />
        </div>
      </div>

      {!loading && orders.length === 0 && (
        <Card><CardContent className="py-10 text-center text-muted-foreground">
          {view === "todo" ? "Nothing to print right now." : "No orders found."}
        </CardContent></Card>
      )}

      {orders.map((o) => (
        <Card key={`${o.source}-${o.id}`} data-testid={`sticker-order-${o.order_number}`}>
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
                </div>
                <div className="text-sm text-muted-foreground">
                  {o.customer_name || "-"} · {fmtDate(o.created_at)}
                  {o.ship_by ? ` · ship by ${fmtDate(o.ship_by)}` : ""}
                </div>
                {o.remark && <div className="text-xs mt-1 text-red-700 dark:text-red-400">Remark: {o.remark}</div>}
              </div>
              {o.lines.length > 1 && (
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" disabled={!!busy} onClick={() => mark(o, [], "printed")} data-testid="sticker-all-printed">
                    <Check className="w-4 h-4 mr-1" /> All printed
                  </Button>
                  <Button size="sm" variant="outline" disabled={!!busy} onClick={() => mark(o, [], "not_required")} data-testid="sticker-all-not-required">
                    <Ban className="w-4 h-4 mr-1" /> None needed
                  </Button>
                </div>
              )}
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
      ))}
    </div>
  );
}
