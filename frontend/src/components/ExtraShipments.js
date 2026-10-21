import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import CourierSelect from "@/components/CourierSelect";
import { getTrackingUrl } from "@/lib/courierTracking";
import { toast } from "sonner";
import { Plus, Truck, Bus, ExternalLink, Trash2, Loader2, ImagePlus, Package } from "lucide-react";

// Part of an order sent by a different mode from the main dispatch
// (e.g. most items by DTDC, a few cartons by bus). Each part has its own
// courier / transport, LR no., contents and slip.
const MODES = [["courier", "Courier"], ["transport", "Transport"], ["bus", "Bus"], ["hand", "By hand"], ["other", "Other"]];
const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const blank = { mode: "bus", courier_name: "", transporter_name: "", lr_no: "", contents: "", boxes: "", note: "", slip_images: [] };

export default function ExtraShipments({ order, onChanged }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const canEdit = ["admin", "dispatch", "packaging"].includes(user?.role) && order.status !== "cancelled";
  const parts = (order.extra_shipments || []).filter(s => !s.removed);
  if (!parts.length && !canEdit) return null;

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const uploadSlip = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      set("slip_images", [...form.slip_images, res.data.url]);
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.post(`/orders/${order.id}/extra-shipments`, form);
      toast.success("Shipment added to the order");
      setOpen(false);
      setForm(blank);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not add the shipment");
    } finally { setSaving(false); }
  };

  const remove = async (s) => {
    if (!window.confirm(`Remove this ${s.mode} shipment from the order? (It stays on record.)`)) return;
    try {
      await api.put(`/orders/${order.id}/extra-shipments/${s.id}`, { removed: true });
      onChanged && onChanged();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not remove"); }
  };

  const addLr = async (s) => {
    const lr = window.prompt("LR / docket number for this shipment", s.lr_no || "");
    if (lr === null) return;
    try {
      await api.put(`/orders/${order.id}/extra-shipments/${s.id}`, { lr_no: lr });
      onChanged && onChanged();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not save"); }
  };

  return (
    <Card data-testid="extra-shipments-card">
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base">Other shipments of this order</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">When some items go by a different mode (e.g. by bus) from the main dispatch above.</p>
        </div>
        {canEdit && (
          <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="extra-shipment-add">
            <Plus className="w-4 h-4 mr-1" /> Add shipment
          </Button>
        )}
      </CardHeader>
      {parts.length > 0 && (
        <CardContent className="space-y-3">
          {parts.map((s, i) => {
            const track = s.mode === "courier" && s.lr_no ? getTrackingUrl(s.courier_name, s.lr_no) : null;
            return (
              <div key={s.id} className="rounded-lg border p-3 space-y-1.5" data-testid={`extra-shipment-${i}`}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2">
                    {s.mode === "bus" ? <Bus className="w-4 h-4 text-amber-600" /> : <Truck className="w-4 h-4 text-blue-600" />}
                    <span className="font-semibold text-sm">{s.mode === "courier" ? s.courier_name : s.transporter_name || MODES.find(m => m[0] === s.mode)?.[1]}</span>
                    <Badge variant="outline" className="text-[10px] capitalize">{s.mode}</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">{new Date(s.dispatched_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · {s.dispatched_by}</span>
                </div>
                <div className="text-sm"><Package className="inline w-3.5 h-3.5 mr-1 text-muted-foreground" />{s.contents}{s.boxes ? <span className="text-muted-foreground"> · {s.boxes} box(es)</span> : null}</div>
                <div className="flex items-center gap-2 text-sm flex-wrap">
                  <span className="text-muted-foreground">LR / docket:</span>
                  {s.lr_no ? <span className="font-mono">{s.lr_no}</span> : <span className="text-amber-600">not added</span>}
                  {track && <a href={track} target="_blank" rel="noopener noreferrer" className="inline-flex items-center text-blue-600 text-xs hover:underline"><ExternalLink className="w-3 h-3 mr-0.5" /> Track</a>}
                  {canEdit && <button type="button" onClick={() => addLr(s)} className="text-xs text-primary hover:underline">{s.lr_no ? "Edit" : "Add LR"}</button>}
                </div>
                {s.note && <div className="text-xs text-muted-foreground">{s.note}</div>}
                {s.slip_images?.length > 0 && (
                  <div className="flex gap-2 flex-wrap pt-1">
                    {s.slip_images.map(u => (
                      <a key={u} href={`${BACKEND}${u}`} target="_blank" rel="noopener noreferrer">
                        <img src={`${BACKEND}${u}`} alt="slip" className="h-16 w-16 object-cover rounded border" />
                      </a>
                    ))}
                  </div>
                )}
                {canEdit && (
                  <button type="button" onClick={() => remove(s)} className="text-xs text-destructive hover:underline inline-flex items-center">
                    <Trash2 className="w-3 h-3 mr-0.5" /> Remove
                  </button>
                )}
              </div>
            );
          })}
        </CardContent>
      )}

      <Dialog open={open} onOpenChange={(v) => !saving && setOpen(v)}>
        <DialogContent className="max-w-md" data-testid="extra-shipment-dialog">
          <DialogHeader>
            <DialogTitle>Add another shipment — {order.order_number}</DialogTitle>
            <DialogDescription>For items of this order sent separately from the main dispatch.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1">
              {MODES.map(([k, l]) => (
                <button key={k} type="button" onClick={() => set("mode", k)}
                  className={`rounded-md border px-3 py-1.5 text-sm ${form.mode === k ? "border-primary bg-primary/10 font-semibold" : "hover:bg-muted"}`}>{l}</button>
              ))}
            </div>
            {form.mode === "courier" ? (
              <div><Label className="text-xs">Courier</Label><CourierSelect value={form.courier_name} onChange={v => set("courier_name", v)} /></div>
            ) : (
              <div><Label className="text-xs">{form.mode === "bus" ? "Bus / travels name" : form.mode === "transport" ? "Transporter" : "Sent through"}</Label>
                <Input value={form.transporter_name} onChange={e => set("transporter_name", e.target.value)} placeholder={form.mode === "bus" ? "e.g. Purple Travels" : ""} /></div>
            )}
            <div><Label className="text-xs">Which items went this way *</Label>
              <Textarea rows={2} value={form.contents} onChange={e => set("contents", e.target.value)} placeholder="e.g. Pine Oil 42% - 2 cans (50 kg)" data-testid="extra-shipment-contents" /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label className="text-xs">LR / docket no.</Label><Input value={form.lr_no} onChange={e => set("lr_no", e.target.value)} /></div>
              <div><Label className="text-xs">Boxes</Label><Input value={form.boxes} onChange={e => set("boxes", e.target.value)} inputMode="numeric" /></div>
            </div>
            <div><Label className="text-xs">Note</Label><Input value={form.note} onChange={e => set("note", e.target.value)} placeholder="Optional, e.g. bus no., driver phone" /></div>
            <div>
              <Label className="text-xs">Slip / receipt photo</Label>
              <div className="flex gap-2 flex-wrap items-center mt-1">
                {form.slip_images.map(u => <img key={u} src={`${BACKEND}${u}`} alt="slip" className="h-14 w-14 object-cover rounded border" />)}
                <label className="inline-flex items-center gap-1 text-xs border rounded-md px-2 py-1.5 cursor-pointer hover:bg-muted">
                  {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ImagePlus className="w-3.5 h-3.5" />} Add photo
                  <input type="file" accept="image/*,application/pdf" className="hidden" onChange={e => { uploadSlip(e.target.files?.[0]); e.target.value = ""; }} />
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
            <Button onClick={save} disabled={saving || uploading} data-testid="extra-shipment-save">
              {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Plus className="w-4 h-4 mr-1" />} Add shipment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
