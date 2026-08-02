import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, Activity, ExternalLink } from "lucide-react";
import { getTrackingUrl } from "@/lib/courierTracking";

/**
 * Live courier status for one order, via /courier-status/{id}.
 * Works for DTDC (tracking API), Anjani (public AWB API) and Amazon Shipping.
 * Shared by All Orders, Order Detail and Courier Expenses so they stay consistent.
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
        // Outline + label: a bare ghost icon was too easy to miss in the table.
        <Button variant="outline" size="sm"
          className={`h-6 px-1.5 text-[10px] gap-1 shrink-0 ${className}`}
          onClick={(e) => { e.stopPropagation(); e.preventDefault(); fetchStatus(); }}
          title="Live courier status" data-testid={`live-status-${orderId}`}>
          <Activity className="w-3 h-3" /> Track
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
              <Row label="Promised delivery" value={data.promised_delivery ? new Date(data.promised_delivery).toLocaleDateString("en-IN") : null} />

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

          <DialogFooter className="gap-2 sm:justify-between">
            {(() => {
              // Link out to the courier's own tracking page as well.
              const cn = data?.courier || courier;
              const dn = data?.docket || docket;
              const url = getTrackingUrl(cn, dn);
              return url ? (
                <a href={url} target="_blank" rel="noopener noreferrer" className="sm:mr-auto">
                  <Button variant="outline" size="sm" data-testid="open-courier-site">
                    <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                    Open on {cn}
                  </Button>
                </a>
              ) : <span />;
            })()}
            <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
