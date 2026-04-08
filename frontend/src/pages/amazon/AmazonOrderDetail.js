import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft, Package, Truck, X, Upload, Copy, Edit2, ExternalLink } from "lucide-react";
import { validateLrNumber, getTrackingUrl, COURIER_LR_PATTERNS } from "@/lib/courierTracking";

const STATUS_BADGE = {
  new: "bg-blue-100 text-blue-800",
  packaging: "bg-yellow-100 text-yellow-800",
  packed: "bg-purple-100 text-purple-800",
  dispatched: "bg-green-100 text-green-800",
};

export default function AmazonOrderDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isPacking = user?.role === "packaging";

  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showPackaging, setShowPackaging] = useState(false);
  const [showDispatch, setShowDispatch] = useState(false);
  const [saving, setSaving] = useState(false);
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [previewImage, setPreviewImage] = useState(null);
  const [lrNumber, setLrNumber] = useState("");
  const [lrValidationError, setLrValidationError] = useState("");
  const [editingCourier, setEditingCourier] = useState(false);
  const [courierValue, setCourierValue] = useState("");

  const COURIERS = ["DTDC", "Anjani", "Professional", "India Post"];
  const canEditCourier = ["admin", "packaging", "dispatch"].includes(user?.role) && order?.status !== "dispatched" && order?.ship_type === "self_ship";

  const canEditPackaging = isAdmin || (isPacking && order?.status !== "dispatched");
  const canDispatch = ["admin", "packaging", "dispatch"].includes(user?.role) && order?.status === "packed";
  const isDispatched = order?.status === "dispatched";

  useEffect(() => { loadOrder(); loadStaff(); }, [id]);

  const loadOrder = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/amazon/orders/${id}`);
      setOrder(res.data);
    } catch { toast.error("Order not found"); navigate("/amazon-orders"); }
    finally { setLoading(false); }
  };

  const loadStaff = async () => {
    try { const res = await api.get("/packaging-staff"); setPackagingStaff(res.data); } catch {}
  };

  const savePackaging = async (data) => {
    setSaving(true);
    try {
      await api.put(`/amazon/orders/${id}/packaging`, data);
      toast.success("Packaging updated");
      setShowPackaging(false);
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const markPacked = async () => {
    try {
      await api.put(`/amazon/orders/${id}/mark-packed`);
      toast.success("Marked as packed");
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const dispatchOrder = async () => {
    if (order.ship_type === "self_ship") {
      if (!lrNumber.trim()) return toast.error("LR Number is mandatory");
      // Regex validation for courier-specific LR
      if (order.courier_name) {
        const validation = validateLrNumber(order.courier_name, lrNumber);
        if (!validation.valid) {
          setLrValidationError(validation.message);
          return toast.error(validation.message);
        }
      }
    }
    setSaving(true);
    try {
      await api.put(`/amazon/orders/${id}/dispatch`, { lr_number: lrNumber });
      toast.success("Order dispatched");
      setShowDispatch(false);
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const copyText = (t) => { navigator.clipboard.writeText(t); toast.success("Copied"); };

  const saveCourier = async () => {
    if (!courierValue) return toast.error("Select a courier");
    try {
      await api.put(`/amazon/orders/${id}/courier`, { courier_name: courierValue });
      toast.success("Courier updated");
      setEditingCourier(false);
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  if (loading || !order) return <div className="flex items-center justify-center py-20 text-muted-foreground">Loading...</div>;

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <div className="space-y-4 max-w-3xl mx-auto" data-testid="amazon-order-detail">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/amazon-orders")}><ArrowLeft className="w-5 h-5" /></Button>
          <div>
            <h1 className="text-lg font-bold font-mono">{order.am_order_number}</h1>
            <p className="text-xs text-muted-foreground font-mono">{order.amazon_order_id}</p>
          </div>
          <Badge variant="outline" className={`capitalize ${STATUS_BADGE[order.status]}`}>{order.status}</Badge>
        </div>
        <div className="flex gap-2">
          {canEditPackaging && !isDispatched && (
            <Button variant="outline" size="sm" onClick={() => setShowPackaging(true)} data-testid="am-update-pkg-btn"><Package className="w-4 h-4 mr-1" /> Update Packaging</Button>
          )}
          {isAdmin && isDispatched && (
            <Button variant="outline" size="sm" onClick={() => setShowPackaging(true)} data-testid="am-update-pkg-btn"><Package className="w-4 h-4 mr-1" /> Update Packaging</Button>
          )}
          {order.status === "packaging" && (isAdmin || isPacking) && (
            <Button variant="secondary" size="sm" onClick={markPacked} data-testid="am-mark-packed-btn">Mark Packed</Button>
          )}
          {canDispatch && (
            <Button size="sm" onClick={() => setShowDispatch(true)} data-testid="am-dispatch-btn"><Truck className="w-4 h-4 mr-1" /> Dispatch</Button>
          )}
        </div>
      </div>

      {/* Customer Info */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Customer Information</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Name</span>
            <span className="text-sm font-medium">{order.customer_name}</span>
          </div>
          <div className="flex justify-between items-start gap-4">
            <span className="text-sm text-muted-foreground shrink-0">Address</span>
            <div className="text-sm text-right flex items-center gap-1">
              <span>{order.address}</span>
              <button onClick={() => copyText(order.address)} className="p-1 hover:bg-accent rounded"><Copy className="w-3 h-3 text-muted-foreground" /></button>
            </div>
          </div>
          {order.phone && (
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Phone</span>
              <div className="flex items-center gap-1">
                <span className="text-sm font-mono">{order.phone}</span>
                <button onClick={() => copyText(order.phone)} className="p-1 hover:bg-accent rounded"><Copy className="w-3 h-3 text-muted-foreground" /></button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Shipping */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Shipping Details</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Type</span><span className="text-sm capitalize">{order.ship_type?.replace("_", " ")}</span></div>
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Method</span><span className="text-sm capitalize">{order.shipping_method}</span></div>
          {order.ship_type === "self_ship" && (
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Courier</span>
              {editingCourier ? (
                <div className="flex items-center gap-2">
                  <Select value={courierValue} onValueChange={setCourierValue}>
                    <SelectTrigger className="w-36 h-8 text-xs" data-testid="courier-edit-select"><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>{COURIERS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button size="sm" className="h-8 text-xs" onClick={saveCourier} data-testid="save-courier-btn">Save</Button>
                  <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setEditingCourier(false)}>Cancel</Button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <span className="text-sm">{order.courier_name || <span className="italic text-muted-foreground">Not set</span>}</span>
                  {canEditCourier && (
                    <button onClick={() => { setCourierValue(order.courier_name || ""); setEditingCourier(true); }} className="p-1 hover:bg-accent rounded" data-testid="edit-courier-btn">
                      <Edit2 className="w-3 h-3 text-muted-foreground" />
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
          {order.dispatch?.lr_number && (
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">LR Number</span>
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono">{order.dispatch.lr_number}</span>
                {(() => {
                  const trackUrl = getTrackingUrl(order.courier_name, order.dispatch.lr_number);
                  return trackUrl ? (
                    <a href={trackUrl} target="_blank" rel="noopener noreferrer">
                      <Button variant="outline" size="sm" className="h-7 text-xs" data-testid="am-track-btn">
                        <ExternalLink className="w-3 h-3 mr-1" /> Track
                      </Button>
                    </a>
                  ) : null;
                })()}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Items */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Items ({order.items?.length})</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader><TableRow>
              <TableHead className="text-xs">Product</TableHead>
              <TableHead className="text-xs text-right">Qty</TableHead>
              <TableHead className="text-xs text-right">Price</TableHead>
              <TableHead className="text-xs text-right">Amount</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {order.items?.map((item, i) => (
                <TableRow key={i}>
                  <TableCell className="text-sm">{item.product_name}</TableCell>
                  <TableCell className="text-sm text-right">{item.quantity} {item.unit}</TableCell>
                  <TableCell className="text-sm text-right font-mono">{"\u20B9"}{item.unit_price?.toLocaleString("en-IN")}</TableCell>
                  <TableCell className="text-sm text-right font-mono">{"\u20B9"}{item.amount?.toLocaleString("en-IN")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex justify-end p-4 border-t">
            <div className="text-right">
              <span className="text-sm text-muted-foreground mr-4">Grand Total</span>
              <span className="text-lg font-bold font-mono">{"\u20B9"}{order.grand_total?.toLocaleString("en-IN")}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Packaging Images */}
      {(order.packaging?.item_images && Object.keys(order.packaging.item_images).some(k => order.packaging.item_images[k]?.length > 0)) || order.packaging?.order_images?.length > 0 || order.packaging?.packed_box_images?.length > 0 ? (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Packing Images</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {Object.entries(order.packaging?.item_images || {}).filter(([, urls]) => urls?.length > 0).map(([key, urls]) => (
              <div key={key}>
                <p className="text-xs font-medium text-muted-foreground uppercase mb-2">{key}</p>
                <div className="flex flex-wrap gap-2">
                  {urls.map((url, i) => (
                    <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                      <button className="w-full h-full" onClick={() => setPreviewImage(`${backendUrl}${url}`)}>
                        <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                      </button>
                      {canEditPackaging && (
                        <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={async () => { try { await api.delete(`/amazon/orders/${id}/images?image_type=item_image&image_url=${encodeURIComponent(url)}&item_name=${encodeURIComponent(key)}`); toast.success("Removed"); loadOrder(); } catch { toast.error("Failed"); } }}>
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {order.packaging?.order_images?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase mb-2">Full Order Images</p>
                <div className="flex flex-wrap gap-2">
                  {order.packaging.order_images.map((url, i) => (
                    <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                      <button className="w-full h-full" onClick={() => setPreviewImage(`${backendUrl}${url}`)}><img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" /></button>
                      {canEditPackaging && (
                        <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={async () => { try { await api.delete(`/amazon/orders/${id}/images?image_type=order_image&image_url=${encodeURIComponent(url)}`); toast.success("Removed"); loadOrder(); } catch { toast.error("Failed"); } }}>
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {order.packaging?.packed_box_images?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase mb-2">Packed Box Images</p>
                <div className="flex flex-wrap gap-2">
                  {order.packaging.packed_box_images.map((url, i) => (
                    <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                      <button className="w-full h-full" onClick={() => setPreviewImage(`${backendUrl}${url}`)}><img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" /></button>
                      {canEditPackaging && (
                        <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={async () => { try { await api.delete(`/amazon/orders/${id}/images?image_type=packed_box_image&image_url=${encodeURIComponent(url)}`); toast.success("Removed"); loadOrder(); } catch { toast.error("Failed"); } }}>
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {/* Packaging Staff */}
      {(order.packaging?.item_packed_by?.length > 0 || order.packaging?.box_packed_by?.length > 0 || order.packaging?.checked_by?.length > 0) && (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Packaging Staff</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {order.packaging.item_packed_by?.length > 0 && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Item Packed By</span><span className="text-sm">{order.packaging.item_packed_by.join(", ")}</span></div>}
            {order.packaging.box_packed_by?.length > 0 && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Box Packed By</span><span className="text-sm">{order.packaging.box_packed_by.join(", ")}</span></div>}
            {order.packaging.checked_by?.length > 0 && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Checked By</span><span className="text-sm">{order.packaging.checked_by.join(", ")}</span></div>}
          </CardContent>
        </Card>
      )}

      {/* Image Preview Dialog */}
      {previewImage && (
        <Dialog open onOpenChange={() => setPreviewImage(null)}>
          <DialogContent className="max-w-2xl p-2">
            <img src={previewImage} alt="Preview" className="w-full rounded-lg" />
          </DialogContent>
        </Dialog>
      )}

      {/* Packaging Dialog */}
      <Dialog open={showPackaging} onOpenChange={setShowPackaging}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Update Packaging</DialogTitle></DialogHeader>
          <AmazonPackagingForm order={order} staffList={packagingStaff} onSave={savePackaging} onCancel={() => setShowPackaging(false)} saving={saving} />
        </DialogContent>
      </Dialog>

      {/* Dispatch Dialog */}
      <Dialog open={showDispatch} onOpenChange={setShowDispatch}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Dispatch Order</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {order.ship_type === "self_ship" && (
              <div>
                <Label className="text-sm">LR Number <span className="text-red-500">*</span></Label>
                <Input
                  value={lrNumber}
                  onChange={e => { setLrNumber(e.target.value); setLrValidationError(""); }}
                  className={lrValidationError ? "border-red-500" : ""}
                  placeholder={order.courier_name ? `Format: ${COURIER_LR_PATTERNS[order.courier_name]?.label || "Enter LR number"}` : "Enter LR / Tracking number"}
                  data-testid="am-lr-input"
                />
                {lrValidationError && <p className="text-xs text-red-500 mt-1" data-testid="am-lr-validation-error">{lrValidationError}</p>}
              </div>
            )}
            {order.ship_type === "easy_ship" && (
              <p className="text-sm text-muted-foreground">Easy Ship — no LR number needed. Click dispatch to confirm.</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDispatch(false)}>Cancel</Button>
            <Button onClick={dispatchOrder} disabled={saving || (order.ship_type === "self_ship" && !lrNumber.trim())} data-testid="am-confirm-dispatch">{saving ? "Dispatching..." : "Dispatch"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AmazonPackagingForm({ order, staffList, onSave, onCancel, saving }) {
  const [itemPackedBy, setItemPackedBy] = useState(order.packaging?.item_packed_by || []);
  const [boxPackedBy, setBoxPackedBy] = useState(order.packaging?.box_packed_by || []);
  const [checkedBy, setCheckedBy] = useState(order.packaging?.checked_by || []);
  const [itemImages, setItemImages] = useState(order.packaging?.item_images || {});
  const [orderImages, setOrderImages] = useState(order.packaging?.order_images || []);
  const [packedBoxImages, setPackedBoxImages] = useState(order.packaging?.packed_box_images || []);
  const [uploading, setUploading] = useState(false);

  const toggleStaff = (list, setList, name) => {
    setList(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);
  };

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

  return (
    <div className="space-y-4">
      {[["Item Packed By", itemPackedBy, setItemPackedBy], ["Box Packed By", boxPackedBy, setBoxPackedBy], ["Checked By", checkedBy, setCheckedBy]].map(([label, list, setter]) => (
        <div key={label}>
          <Label className="text-sm">{label}</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            {staffList.map(s => (
              <Button key={s.id} variant={list.includes(s.name) ? "default" : "outline"} size="sm" onClick={() => toggleStaff(list, setter, s.name)}>{s.name}</Button>
            ))}
          </div>
        </div>
      ))}
      <Separator />
      <Label className="text-sm font-medium">Packaging Images</Label>
      {order.items?.map(item => (
        <div key={item.product_name}>
          <Label className="text-xs font-medium text-muted-foreground uppercase">{item.product_name}</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            {(itemImages[item.product_name] || []).map((url, i) => (
              <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
                <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => removeImage("item", url, item.product_name)}><X className="w-3 h-3" /></button>
              </div>
            ))}
            <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent">
              <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Files</span>
              <input type="file" accept="image/*" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "item", item.product_name); e.target.value = ""; }} />
            </label>
            <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent bg-secondary/30">
              <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Camera</span>
              <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "item", item.product_name); e.target.value = ""; }} />
            </label>
          </div>
        </div>
      ))}
      <div>
        <Label className="text-xs font-medium text-muted-foreground uppercase">Full Order Images</Label>
        <div className="flex flex-wrap gap-2 mt-1">
          {orderImages.map((url, i) => (
            <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
              <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
              <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={() => removeImage("order", url)}><X className="w-3 h-3" /></button>
            </div>
          ))}
          <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent">
            <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Files</span>
            <input type="file" accept="image/*" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "order"); e.target.value = ""; }} />
          </label>
          <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent bg-secondary/30">
            <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Camera</span>
            <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "order"); e.target.value = ""; }} />
          </label>
        </div>
      </div>
      <div>
        <Label className="text-xs font-medium text-muted-foreground uppercase">Packed Box Images</Label>
        <div className="flex flex-wrap gap-2 mt-1">
          {packedBoxImages.map((url, i) => (
            <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
              <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
              <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={() => removeImage("packed_box", url)}><X className="w-3 h-3" /></button>
            </div>
          ))}
          <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent">
            <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Files</span>
            <input type="file" accept="image/*" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "packed_box"); e.target.value = ""; }} />
          </label>
          <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent bg-secondary/30">
            <Upload className="w-3 h-3 text-muted-foreground" /><span className="text-[10px] text-muted-foreground">Camera</span>
            <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading} onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "packed_box"); e.target.value = ""; }} />
          </label>
        </div>
      </div>
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
