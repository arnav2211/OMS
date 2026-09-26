import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { useAuth } from "@/contexts/AuthContext";
import OrderWorkStrip from "@/components/OrderWorkStrip";
import ShiprocketCarrierPick from "@/components/ShiprocketCarrierPick";
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
import { validateLrNumber, getTrackingUrl, COURIER_LR_PATTERNS, COURIER_DROPDOWN } from "@/lib/courierTracking";
import { Textarea } from "@/components/ui/textarea";

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
  const [srPick, setSrPick] = useState(null);

  const COURIERS = COURIER_DROPDOWN;
  const canEditCourier = ["admin", "packaging", "dispatch"].includes(user?.role) && order?.status !== "dispatched" && order?.ship_type === "self_ship";

  const canEditPackaging = isAdmin || (isPacking && order?.status !== "dispatched");
  // Easy Ship is dispatched by Amazon's pickup scan; only self-ship is dispatched by hand.
  const canDispatch = ["admin", "packaging", "dispatch"].includes(user?.role) && order?.status === "packed" && order?.ship_type === "self_ship";
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
      if (order.courier_name !== "Others" && !lrNumber.trim()) return toast.error("LR Number is mandatory");
      // Regex validation for courier-specific LR
      if (order.courier_name && order.courier_name !== "Others" && lrNumber.trim()) {
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
      if (courierValue === "Shiprocket" && !srPick) return toast.error("Pick a Shiprocket carrier first");
      await api.put(`/amazon/orders/${id}/courier`, { courier_name: courierValue, shiprocket_courier: courierValue === "Shiprocket" ? srPick : null });
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
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  <Select value={courierValue} onValueChange={setCourierValue}>
                    <SelectTrigger className="w-36 h-8 text-xs" data-testid="courier-edit-select"><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>{COURIERS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                  <Button size="sm" className="h-8 text-xs" onClick={saveCourier} data-testid="save-courier-btn">Save</Button>
                  <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setEditingCourier(false)}>Cancel</Button>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <span className="text-sm">{order.courier_name || <span className="italic text-muted-foreground">Not set</span>}
                    {order.courier_name === "Shiprocket" && order.shiprocket_courier?.name && <span className="text-muted-foreground"> · {order.shiprocket_courier.name} ₹{Number(order.shiprocket_courier.rate).toFixed(0)}</span>}
                  </span>
                  {canEditCourier && (
                    <button onClick={() => { setCourierValue(order.courier_name || ""); setSrPick(order.shiprocket_courier || null); setEditingCourier(true); }} className="p-1 hover:bg-accent rounded" data-testid="edit-courier-btn">
                      <Edit2 className="w-3 h-3 text-muted-foreground" />
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
          {order.ship_type === "self_ship" && editingCourier && courierValue === "Shiprocket" && (
            <ShiprocketCarrierPick pincode={(String(order.address || "").match(/(\d{6})/) || [])[1]} cod={!!order.is_cod}
                                   value={srPick || (order.packaging?.weight_kg ? { weight_kg: order.packaging.weight_kg } : null)} onChange={setSrPick} />
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

      {order.ship_type === "self_ship" && <AmazonShipToCard order={order} user={user} />}
      {order.ship_type === "self_ship" && isDispatched && <AmazonConfirmLine order={order} onChanged={loadOrder} />}

      {/* Packing work: one executive does the whole Amazon order, so there are no steps */}
      <OrderWorkStrip kind="amazon" orderId={order.id} status={order.status} onChanged={loadOrder} />

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
                <Label className="text-sm">LR Number {order.courier_name === "Others" ? null : <span className="text-red-500">*</span>}</Label>
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
            <Button onClick={dispatchOrder} disabled={saving || (order.ship_type === "self_ship" && order.courier_name !== "Others" && !lrNumber.trim())} data-testid="am-confirm-dispatch">{saving ? "Dispatching..." : "Dispatch"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AmazonPackagingForm({ order, staffList, onSave, onCancel, saving }) {
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


// Buyer's delivery details for a self-ship label. Amazon does not give them to
// our app, so they are copied from Seller Central (stored encrypted, wiped 30
// days after dispatch). Only admin / dispatch can read them back.
function parseSellerCentral(text) {
  const lines = String(text || "").split(/\n+/).map(l => l.trim()).filter(Boolean);
  const out = {};
  const phoneLine = lines.find(l => /(\+?91[\s-]?)?[6-9]\d{9}/.test(l.replace(/\s/g, "")) && /phone|mob|\d{10}/i.test(l));
  if (phoneLine) out.phone = (phoneLine.replace(/\D/g, "").match(/[6-9]\d{9}$/) || [""])[0];
  const pinLine = lines.find(l => /\b\d{6}\b/.test(l) && l !== phoneLine);
  if (pinLine) {
    out.pincode = pinLine.match(/\b(\d{6})\b/)[1];
    const parts = pinLine.replace(out.pincode, "").split(",").map(x => x.trim()).filter(Boolean);
    if (parts.length >= 2) { out.city = parts[0]; out.state = parts[parts.length - 1]; }
    else if (parts.length === 1) out.city = parts[0];
  }
  const rest = lines.filter(l => l !== phoneLine && l !== pinLine && !/^(ship to|shipping address|address)[:]?$/i.test(l));
  if (rest.length) out.name = rest[0];
  if (rest.length > 1) out.line1 = rest.slice(1).join(", ");
  return out;
}

function AmazonShipToCard({ order, user }) {
  const [info, setInfo] = useState(null);
  const [edit, setEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [paste, setPaste] = useState("");
  const [f, setF] = useState({ name: "", line1: "", city: "", state: "", pincode: "", phone: "" });
  const canEdit = ["admin", "dispatch", "packaging", "accounts"].includes(user?.role) && order.status !== "dispatched";

  const load = async () => {
    try {
      const r = await api.get(`/amazon/orders/${order.id}/ship-to`);
      setInfo(r.data);
      setF({ name: r.data.name || "", line1: r.data.line1 || "", city: r.data.city || "", state: r.data.state || "",
             pincode: r.data.pincode || "", phone: r.data.phone || "" });
    } catch { /* ignore */ }
  };
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [order.id]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/amazon/orders/${order.id}/ship-to`, f);
      toast.success("Delivery address saved");
      setEdit(false); setPaste("");
      load();
    } catch (err) { toast.error(err.response?.data?.detail || "Could not save"); }
    finally { setSaving(false); }
  };

  if (!info) return null;
  return (
    <Card className={info.ready ? "" : "border-2 border-amber-400"} data-testid="am-ship-to">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Buyer delivery address (for our courier)</CardTitle>
          {canEdit && !edit && <Button size="sm" variant="outline" onClick={() => setEdit(true)} data-testid="am-ship-to-edit">{info.ready ? "Edit" : "Enter address"}</Button>}
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {!edit && (info.ready ? (
          info.visible ? (
            <div className="space-y-0.5">
              <div className="font-medium">{info.name}</div>
              <div>{info.line1}</div>
              <div>{info.city}, {info.state} - {info.pincode}</div>
              <div className="font-mono">{info.phone}</div>
            </div>
          ) : (
            <p className="text-emerald-700 dark:text-emerald-400">Address and phone entered{info.entered_by ? ` by ${info.entered_by}` : ""} - ready to book. ({info.city} - {info.pincode})</p>
          )
        ) : (
          <p className="text-amber-700 dark:text-amber-300">
            {info.purged ? "Buyer details were removed 30 days after dispatch (Amazon policy)." :
              "Amazon does not share the buyer's name, street and phone with our app. Copy them from Seller Central (Orders → this order → Ship to) so the courier label can be booked."}
          </p>
        ))}
        {edit && (
          <div className="space-y-2">
            <Label className="text-xs">Paste the "Ship to" block from Seller Central (optional - fills the fields)</Label>
            <Textarea rows={4} value={paste} placeholder={"Name\nHouse / street\nArea\nCity, State 400001\nPhone: 98xxxxxxxx"}
              onChange={e => { setPaste(e.target.value); const p = parseSellerCentral(e.target.value); setF(x => ({ ...x, ...Object.fromEntries(Object.entries(p).filter(([, v]) => v)) })); }} />
            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2"><Label className="text-xs">Buyer name</Label><Input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
              <div className="col-span-2"><Label className="text-xs">Street address</Label><Input value={f.line1} onChange={e => setF({ ...f, line1: e.target.value })} /></div>
              <div><Label className="text-xs">City</Label><Input value={f.city} onChange={e => setF({ ...f, city: e.target.value })} /></div>
              <div><Label className="text-xs">State</Label><Input value={f.state} onChange={e => setF({ ...f, state: e.target.value })} /></div>
              <div><Label className="text-xs">Pincode</Label><Input value={f.pincode} inputMode="numeric" onChange={e => setF({ ...f, pincode: e.target.value.replace(/\D/g, "").slice(0, 6) })} /></div>
              <div><Label className="text-xs">Phone</Label><Input value={f.phone} inputMode="numeric" onChange={e => setF({ ...f, phone: e.target.value })} /></div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => { setEdit(false); load(); }} disabled={saving}>Cancel</Button>
              <Button size="sm" onClick={save} disabled={saving} data-testid="am-ship-to-save">{saving ? "Saving..." : "Save address"}</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AmazonConfirmLine({ order, onChanged }) {
  const c = order.amazon_confirm || null;
  const [busy, setBusy] = useState(false);
  const retry = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/amazon/orders/${order.id}/confirm-shipment`);
      if (r.data.status === "confirmed") toast.success("Shipment confirmed on Amazon");
      else toast.error(r.data.error || "Amazon did not accept it", { duration: 9000 });
      onChanged?.();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };
  return (
    <div className={`flex items-center justify-between gap-2 rounded-md border p-3 text-sm ${c?.status === "confirmed" ? "border-emerald-300 bg-emerald-50 dark:bg-emerald-950/20" : "border-amber-300 bg-amber-50 dark:bg-amber-950/20"}`} data-testid="am-confirm">
      <span>
        {c?.status === "confirmed"
          ? <>Marked shipped on Amazon: <b>{c.carrier}</b> · {c.tracking}</>
          : <>Not yet confirmed on Amazon{c?.error ? `: ${c.error}` : ""}. The OMS retries every 5 minutes.</>}
      </span>
      {c?.status !== "confirmed" && <Button size="sm" variant="outline" onClick={retry} disabled={busy}>{busy ? "..." : "Confirm on Amazon"}</Button>}
    </div>
  );
}
