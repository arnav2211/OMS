import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, Activity } from "lucide-react";

/**
 * Live courier status for one order, via /courier-status/{id}.
 * Works for DTDC (tracking API) and Anjani (public AWB API).
 * Shared by All Orders, Order Detail and Courier Expenses so the three stay consistent.
 */
export default function CourierStatusDialog({ orderId, orderNumber, courier, docket,
                                              variant = "icon", className = "" }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = async () => {
    setOpen(true);
    setData(null);
    setLoading(true);
    try {
      const res = await api.get(`/courier-status/${orderId}`);
      setData(res.data);
    } catch (err) {
      setData({ ok: false, message: err.response?.data?.detail || "Could not fetch status" });
    } finally {
      setLoading(false);
    }
  };

  const Row = ({ label, value }) =>
    value ? (
      <div className="flex justify-between gap-3 border-b border-border/60 pb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-right">{value}</span>
      </div>
    ) : null;

  return (
    <>
      {variant === "icon" ? (
        <Button variant="ghost" size="icon" className={`h-7 w-7 ${className}`}
          onClick={(e) => { e.stopPropagation(); e.preventDefault(); fetchStatus(); }}
          title="Live courier status" data-testid={`live-status-${orderId}`}>
          <Activity className="w-3.5 h-3.5" />
        </Button>
      ) : (
        <Button variant="outline" size="sm" className={`h-7 text-xs ${className}`}
          onClick={fetchStatus} data-testid={`live-status-${orderId}`}>
          <Activity className="w-3 h-3 mr-1" /> Live Status
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Courier Status{orderNumber ? ` — ${orderNumber}` : ""}</DialogTitle>
          </DialogHeader>

          {loading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-primary" /></div>
          ) : !data ? null : !data.ok ? (
            <div className="py-3 space-y-1">
              <p className="text-sm text-muted-foreground">{data.message}</p>
              {docket && <p className="text-xs font-mono text-muted-foreground">Docket: {docket}</p>}
            </div>
          ) : (
            <div className="space-y-2 text-sm">
              <Row label="Courier" value={data.courier} />
              <Row label="Docket" value={<span className="font-mono">{data.docket}</span>} />
              <div className="flex justify-between gap-3 border-b border-border/60 pb-1">
                <span className="text-muted-foreground">Status</span>
                <span className="font-semibold text-right">{data.status || "—"}</span>
              </div>
              <Row label="Route" value={data.from ? `${data.from} → ${data.to}` : null} />
              <Row label="Hub" value={data.hub} />
              <Row label="Booked" value={data.booking_date ? new Date(data.booking_date).toLocaleDateString("en-IN") : null} />

              {(data.events || []).length > 0 && (
                <div className="pt-2">
                  <p className="text-xs font-semibold mb-1.5">Recent events</p>
                  <div className="space-y-1.5 max-h-52 overflow-y-auto">
                    {data.events.map((e, i) => (
                      <div key={i} className="text-xs border-l-2 border-primary/40 pl-2">
                        <span className="font-medium">{e.customer_update || e.type}</span>
                        {e.hub_name && <span className="text-muted-foreground"> · {e.hub_name}</span>}
                        {e.event_time && (
                          <div className="text-[10px] text-muted-foreground">
                            {new Date(Number(e.event_time) || e.event_time).toLocaleString("en-IN")}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
