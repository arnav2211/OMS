import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { RefreshCw, Camera, Image, Upload, X, CheckCircle } from "lucide-react";


// Ship-by urgency from Amazon's latest ship date: "overdue", "today" or "".
const shipByUrgency = (o) => {
  if (!o?.latest_ship_date || ["dispatched", "cancelled"].includes(o.status)) return "";
  const d = new Date(o.latest_ship_date);
  if (d.getTime() < Date.now()) return "overdue";
  return d.toDateString() === new Date().toDateString() ? "today" : "";
};
const shipByLabel = (o) => o?.latest_ship_date
  ? new Date(o.latest_ship_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : "";

const STATUS_BADGE = {
  new: "bg-blue-100 text-blue-800",
  packaging: "bg-yellow-100 text-yellow-800",
  packed: "bg-purple-100 text-purple-800",
  dispatched: "bg-green-100 text-green-800",
};

export default function AmazonPacking() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [staff, setStaff] = useState([]);
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState("active");

  useEffect(() => { loadOrders(); loadStaff(); }, []);

  const loadOrders = async () => {
    setLoading(true);
    try { const res = await api.get("/amazon/orders"); setOrders(res.data); } catch {} finally { setLoading(false); }
  };

  const loadStaff = async () => {
    try { const res = await api.get("/packaging-staff"); setStaff(res.data); } catch {}
  };

  const filtered = orders.filter(o => {
    if (statusFilter === "active") return ["new", "packaging"].includes(o.status);
    if (statusFilter === "packed") return o.status === "packed";
    if (statusFilter === "dispatched") return o.status === "dispatched";
    return true;
  }).sort((a, b) => {
    // Work queue: earliest ship-by date first; orders without one keep their place after.
    if (statusFilter !== "active") return 0;
    const da = a.latest_ship_date ? new Date(a.latest_ship_date).getTime() : Infinity;
    const dbb = b.latest_ship_date ? new Date(b.latest_ship_date).getTime() : Infinity;
    return da - dbb;
  });

  const savePackaging = async (data) => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.put(`/amazon/orders/${selected.id}/packaging`, data);
      toast.success("Packaging updated");
      setSelected(null);
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const markPacked = async (orderId) => {
    try {
      await api.put(`/amazon/orders/${orderId}/mark-packed`);
      toast.success("Marked as packed");
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-4" data-testid="amazon-packing-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-bold">Amazon Packing</h1>
        <div className="flex gap-2 items-center">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-32 h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="packed">Packed</SelectItem>
              <SelectItem value="dispatched">Dispatched</SelectItem>
              <SelectItem value="all">All</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={loadOrders}><RefreshCw className="w-4 h-4" /></Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase">Order #</TableHead>
                  <TableHead className="text-xs uppercase">Customer</TableHead>
                  <TableHead className="text-xs uppercase hidden sm:table-cell">Shipping</TableHead>
                  <TableHead className="text-xs uppercase hidden sm:table-cell">Items</TableHead>
                  <TableHead className="text-xs uppercase">Status</TableHead>
                  <TableHead className="text-xs uppercase">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>}
                {!loading && filtered.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No orders</TableCell></TableRow>}
                {filtered.map(order => (
                  <TableRow key={order.id} className={shipByUrgency(order) ? "bg-red-50 dark:bg-red-950/30" : ""} data-testid={`am-pkg-row-${order.id}`}>
                    <TableCell>
                      <Link to={`/amazon-orders/${order.id}`} className="font-mono text-sm text-primary hover:underline font-medium">{order.am_order_number}</Link>
                      {shipByLabel(order) && !["dispatched", "cancelled"].includes(order.status) && (
                        <div className={`text-[11px] ${shipByUrgency(order) ? "text-red-600 font-semibold" : "text-muted-foreground"}`}>
                          {shipByUrgency(order) === "overdue" ? "SHIP-BY MISSED " : shipByUrgency(order) === "today" ? "SHIP TODAY " : "ship by "}{shipByLabel(order)}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{order.customer_name}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap hidden sm:table-cell">
                      {order.shipping_method === "amazon" ? "Amazon" : order.courier_name || "Courier"}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">{order.items?.length}</TableCell>
                    <TableCell><Badge variant="outline" className={`text-xs capitalize ${STATUS_BADGE[order.status]}`}>{order.status}</Badge></TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {["new", "packaging"].includes(order.status) && (
                          <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => setSelected(order)} data-testid={`am-pkg-update-${order.id}`}>
                            <Camera className="w-3 h-3 mr-1" /> Pack
                          </Button>
                        )}
                        {order.status === "packaging" && (
                          <Button variant="secondary" size="sm" className="text-xs h-7" onClick={() => markPacked(order.id)} data-testid={`am-pkg-done-${order.id}`}>
                            <CheckCircle className="w-3 h-3 mr-1" /> Done
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Packaging Dialog */}
      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Pack: {selected?.am_order_number}</DialogTitle></DialogHeader>
          {selected && <PackForm order={selected} staffList={staff} onSave={savePackaging} onCancel={() => setSelected(null)} saving={saving} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PackForm({ order, staffList, onSave, onCancel, saving }) {
  const { user: formUser } = useAuth();
  const canPickNames = formUser?.role === "admin";     // everyone else: names come from My Work only
  const [itemPackedBy, setItemPackedBy] = useState(order.packaging?.item_packed_by || []);
  const [boxPackedBy, setBoxPackedBy] = useState(order.packaging?.box_packed_by || []);
  const [checkedBy, setCheckedBy] = useState(order.packaging?.checked_by || []);
  const [itemImages, setItemImages] = useState(order.packaging?.item_images || {});
  const [orderImages, setOrderImages] = useState(order.packaging?.order_images || []);
  const [packedBoxImages, setPackedBoxImages] = useState(order.packaging?.packed_box_images || []);
  const [uploading, setUploading] = useState(false);
  const [weightKg, setWeightKg] = useState(order.packaging?.weight_kg || "");
  const [numBoxes, setNumBoxes] = useState(order.packaging?.num_boxes || "1");
  const selfShip = order.ship_type === "self_ship";

  const toggleStaff = (list, setList, name) => setList(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);

  const uploadImage = async (file, target, itemKey) => {
    const compressed = await compressImage(file);
    const form = new FormData();
    form.append("file", compressed);
    setUploading(true);
    try {
      const res = await api.post("/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      const url = res.data.url;
      if (target === "item" && itemKey) setItemImages(prev => ({ ...prev, [itemKey]: [...(prev[itemKey] || []), url] }));
      else if (target === "order") setOrderImages(prev => [...prev, url]);
      else if (target === "packed_box") setPackedBoxImages(prev => [...prev, url]);
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  const removeImage = (target, url, itemKey) => {
    if (target === "item" && itemKey) setItemImages(prev => ({ ...prev, [itemKey]: (prev[itemKey] || []).filter(u => u !== url) }));
    else if (target === "order") setOrderImages(prev => prev.filter(u => u !== url));
    else if (target === "packed_box") setPackedBoxImages(prev => prev.filter(u => u !== url));
  };

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const ImageUploadRow = ({ label, images, target, itemKey }) => (
    <div>
      <Label className="text-xs font-medium text-muted-foreground uppercase">{label}</Label>
      <div className="flex flex-wrap gap-2 mt-1">
        {images.map((url, i) => (
          <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
            <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
            <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={() => removeImage(target, url, itemKey)}><X className="w-3 h-3" /></button>
          </div>
        ))}
        <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent">
          <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Files</span>
          <input type="file" accept="image/*" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], target, itemKey); e.target.value = ""; }} />
        </label>
        <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent bg-secondary/30">
          <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Camera</span>
          <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], target, itemKey); e.target.value = ""; }} />
        </label>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      {[["Item Packed By", itemPackedBy, setItemPackedBy], ["Box Packed By", boxPackedBy, setBoxPackedBy], ["Checked By", checkedBy, setCheckedBy]].map(([label, list, setter]) => (
        <div key={label}>
          <Label className="text-sm">{label}</Label>
          {canPickNames ? (
            <div className="flex flex-wrap gap-2 mt-1">
              {staffList.map(s => <Button key={s.id} variant={list.includes(s.name) ? "default" : "outline"} size="sm" onClick={() => toggleStaff(list, setter, s.name)}>{s.name}</Button>)}
              <p className="w-full text-[11px] text-muted-foreground">Admin override. Staff cannot pick names.</p>
            </div>
          ) : (
            <p className="mt-1 text-sm font-medium">
              {list.length > 0 ? list.join(", ")
                : <span className="text-amber-600 font-normal">Not started yet. In My Work tap "Amazon order", pick this order and enter your PIN.</span>}
            </p>
          )}
        </div>
      ))}
      {selfShip && (
        <div className="grid grid-cols-2 gap-3 rounded-md border border-sky-300 bg-sky-50/60 dark:bg-sky-950/20 p-3">
          <div>
            <Label className="text-sm">Weight (KG) <span className="text-red-500">*</span></Label>
            <Input type="number" step="0.001" min="0" value={weightKg} onChange={e => setWeightKg(e.target.value)} placeholder="Total weight of all boxes" data-testid="am-pkg-weight" />
          </div>
          <div>
            <Label className="text-sm">Boxes</Label>
            <Input type="number" min="1" value={numBoxes} onChange={e => setNumBoxes(e.target.value)} data-testid="am-pkg-boxes" />
          </div>
          <p className="col-span-2 text-[11px] text-muted-foreground">Self-ship order: we ship it ourselves, so the weight sends it to Book Shipments.</p>
        </div>
      )}
      <Separator />
      <Label className="text-sm font-medium">Packaging Images</Label>
      {order.items?.map(item => (
        <ImageUploadRow key={item.product_name} label={item.product_name} images={itemImages[item.product_name] || []} target="item" itemKey={item.product_name} />
      ))}
      <ImageUploadRow label="Full Order Images" images={orderImages} target="order" />
      <ImageUploadRow label="Packed Box Images" images={packedBoxImages} target="packed_box" />
      {uploading && <p className="text-xs text-muted-foreground">Uploading...</p>}
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button onClick={() => onSave({ item_packed_by: itemPackedBy, box_packed_by: boxPackedBy, checked_by: checkedBy, item_images: itemImages, order_images: orderImages, packed_box_images: packedBoxImages, ...(selfShip ? { weight_kg: String(weightKg).trim(), num_boxes: String(numBoxes).trim() || "1" } : {}) })} disabled={saving || uploading}>
          {saving ? "Saving..." : "Save Packaging"}
        </Button>
      </DialogFooter>
    </div>
  );
}
