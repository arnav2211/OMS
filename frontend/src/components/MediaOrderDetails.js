import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, FileText, ExternalLink } from "lucide-react";
import { getTrackingUrl } from "@/lib/courierTracking";
import { shipLabel } from "@/lib/mediaShipping";

const rupee = (v) => (v === undefined || v === null || v === "" ? "-" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`);
const when = (v) => {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? String(v) : d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

function Row({ label, value }) {
  if (value === undefined || value === null || value === "" || value === false) return null;
  return (
    <div className="flex justify-between gap-3 border-b border-border/60 py-1 text-sm">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="text-right break-words min-w-0">{value}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
      {children}
    </div>
  );
}

function addressText(a) {
  if (!a) return "";
  if (typeof a === "string") return a;
  return [a.address_name, a.address_line, a.city, a.state, a.pincode].filter(Boolean).join(", ");
}

function Photos({ title, urls }) {
  const list = (urls || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <div>
      <div className="text-xs text-muted-foreground mb-1">{title}</div>
      <div className="flex flex-wrap gap-2">
        {list.map((u) => (
          <a key={u} href={u} target="_blank" rel="noreferrer">
            <img src={u} alt="" loading="lazy" className="h-20 w-20 rounded border object-cover" />
          </a>
        ))}
      </div>
    </div>
  );
}

/** Read-only view of a whole order for the media team, who cannot open the order pages. */
export default function MediaOrderDetails({ source, orderId, orderNumber }) {
  const [open, setOpen] = useState(false);
  const [o, setO] = useState(null);
  const [err, setErr] = useState("");

  const show = async () => {
    setOpen(true);
    setO(null);
    setErr("");
    try {
      setO((await api.get(`/media/orders/${source}/${orderId}/details`)).data);
    } catch (e) {
      setErr(e.response?.data?.detail || "Could not load the order");
    }
  };

  const pk = o?.packaging || {};
  const itemPhotos = Object.values(pk.item_images || {}).flat();
  const trackUrl = o && o.docket ? getTrackingUrl(o.courier, o.docket) : null;

  return (
    <>
      <Button size="sm" variant="outline" onClick={show} data-testid={`media-details-${orderNumber}`}>
        <FileText className="w-4 h-4 mr-1" /> Details
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">
              {orderNumber}
              {o?.sticker_urgent?.on && <Badge className="bg-red-600 text-white">URGENT · {o.sticker_urgent.by}</Badge>}
              {o?.status && <span className="text-sm font-normal capitalize text-muted-foreground">{o.status}</span>}
            </DialogTitle>
          </DialogHeader>
          {!o && !err && <div className="py-10 flex justify-center"><Loader2 className="w-6 h-6 animate-spin" /></div>}
          {err && <p className="text-sm text-red-600">{err}</p>}
          {o && (
            <div className="space-y-5">
              <div className="grid gap-5 md:grid-cols-2">
                <Section title="Order">
                  <Row label="Customer" value={o.customer_name} />
                  <Row label="Phone" value={source === "amazon" ? o.phone : null} />
                  <Row label="Purpose" value={o.purpose} />
                  <Row label="Telecaller" value={o.telecaller_name} />
                  <Row label="Created" value={when(o.created_at)} />
                  <Row label="Amazon order" value={o.amazon_order_id} />
                  <Row label="Website order" value={o.shopify_order_name} />
                  <Row label="Ship by" value={when(o.latest_ship_date)} />
                  <Row label="Payment" value={[o.payment_status, o.mode_of_payment].filter(Boolean).join(" · ")} />
                  <Row label="COD to collect" value={o.is_cod ? rupee(o.cod_amount) : null} />
                  <Row label="Grand total" value={rupee(o.grand_total)} />
                </Section>
                <Section title="Shipping">
                  <Row label="Goes by" value={shipLabel(o)} />
                  <Row label="Docket / AWB" value={o.docket} />
                  <Row label="Track" value={trackUrl ? <a href={trackUrl} target="_blank" rel="noreferrer" className="text-primary inline-flex items-center gap-1">Open tracking <ExternalLink className="w-3 h-3" /></a> : null} />
                  <Row label="Dispatched" value={when(o.dispatch?.dispatched_at)} />
                  <Row label="Shipping note" value={o.extra_shipping_details} />
                  <Row label="Ship to" value={addressText(o.shipping_address || o.address)} />
                </Section>
              </div>

              {o.remark && <div className="rounded-md bg-red-50 dark:bg-red-950/30 p-2 text-sm text-red-700 dark:text-red-300">Remark: {o.remark}</div>}

              <Section title="Items">
                <div className="divide-y rounded-md border">
                  {(o.items || []).map((it, i) => (
                    <div key={i} className="flex gap-3 p-2">
                      {it.image_url && (
                        <a href={it.image_url} target="_blank" rel="noreferrer">
                          <img src={it.image_url} alt="" loading="lazy" className="h-14 w-14 rounded border object-cover" />
                        </a>
                      )}
                      <div className="flex-1 min-w-0 text-sm">
                        <div className="font-medium">{it.product_name || it.name || it.title}</div>
                        {it.description && <div className="text-xs text-muted-foreground">{it.description}</div>}
                        {it.formulation && <div className="text-xs text-amber-700 dark:text-amber-400 whitespace-pre-wrap">{it.formulation}</div>}
                        {it.sku && <div className="text-xs text-muted-foreground">SKU {it.sku}</div>}
                      </div>
                      <div className="text-sm text-right shrink-0">
                        <div>{it.qty ?? it.quantity} {it.unit}</div>
                        {it.total !== undefined && <div className="text-xs text-muted-foreground">{rupee(it.total)}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>

              {(o.free_samples || []).length > 0 && (
                <Section title="Free samples">
                  {(o.free_samples || []).map((f, i) => (
                    <div key={i} className="text-sm">{f.product_name || f.name} {f.qty ? `· ${f.qty} ${f.unit || ""}` : ""}{f.description ? ` · ${f.description}` : ""}</div>
                  ))}
                </Section>
              )}

              {(o.additional_charges || []).length > 0 && (
                <Section title="Additional charges">
                  {o.additional_charges.map((c, i) => <Row key={i} label={c.name} value={rupee(c.amount)} />)}
                </Section>
              )}

              <Section title="Packing">
                <Row label="Weight" value={pk.weight_kg ? `${pk.weight_kg} kg` : null} />
                <Row label="Boxes" value={pk.num_boxes} />
                <Row label="Items packed by" value={(pk.item_packed_by || []).join(", ")} />
                <Row label="Box packed by" value={(pk.box_packed_by || []).join(", ")} />
                <div className="space-y-2 pt-1">
                  <Photos title="Item photos" urls={itemPhotos} />
                  <Photos title="Order photos" urls={pk.order_images} />
                  <Photos title="Packed box" urls={pk.packed_box_images} />
                </div>
              </Section>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
