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
import { Separator } from "@/components/ui/separator";
import { RefreshCw, Camera, Image, Upload, X, CheckCircle } from "lucide-react";

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
                  <TableRow key={order.id} data-testid={`am-pkg-row-${order.id}`}>
                    <TableCell>
                      <Link to={`/amazon-orders/${order.id}`} className="font-mono text-sm text-primary hover:underline font-medium">{order.am_order_number}</Link>
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
  const [itemPackedBy, setItemPackedBy] = useState(order.packaging?.item_packed_by || []);
  const [boxPackedBy, setBoxPackedBy] = useState(order.packaging?.box_packed_by || []);
  const [checkedBy, setCheckedBy] = useState(order.packaging?.checked_by || []);
  const [itemImages, setItemImages] = useState(order.packaging?.item_images || {});
  const [orderImages, setOrderImages] = useState(order.packaging?.order_images || []);
  const [packedBoxImages, setPackedBoxImages] = useState(order.packaging?.packed_box_images || []);
  const [uploading, setUploading] = useState(false);

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
          <div className="flex flex-wrap gap-2 mt-1">
            {staffList.map(s => <Button key={s.id} variant={list.includes(s.name) ? "default" : "outline"} size="sm" onClick={() => toggleStaff(list, setter, s.name)}>{s.name}</Button>)}
          </div>
        </div>
      ))}
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
        <Button onClick={() => onSave({ item_packed_by: itemPackedBy, box_packed_by: boxPackedBy, checked_by: checkedBy, item_images: itemImages, order_images: orderImages, packed_box_images: packedBoxImages })} disabled={saving || uploading}>
          {saving ? "Saving..." : "Save Packaging"}
        </Button>
      </DialogFooter>
    </div>
  );
}
