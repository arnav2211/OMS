import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, MapPin, ArrowLeft, Upload, X, Edit, Lock, ShieldAlert } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { INDIAN_STATES } from "@/lib/indianStates";

const UNITS = ["mL", "L", "g", "Kg", "pcs", ""];
const SHIPPING_METHODS = [
  { value: "transport", label: "Transport" }, { value: "courier", label: "Courier" },
  { value: "porter", label: "Porter" }, { value: "self_arranged", label: "Self-Arranged" },
  { value: "office_collection", label: "Office Collection" },
];
const COURIER_OPTIONS = ["DTDC", "Anjani", "Professional", "India Post"];
const GST_RATES = [0, 5, 18];
const PAYMENT_MODES = ["Cash", "Online", "Other"];
const emptyItem = () => ({ product_name: "", qty: 0, unit: "", rate: 0, amount: 0, gst_rate: 0, gst_amount: 0, total: 0, description: "" });
const emptySample = () => ({ item_name: "", description: "" });
const emptyAddress = () => ({ address_line: "", city: "", state: "", pincode: "", label: "", address_name: "" });

const STATUS_COLORS = { new: "bg-blue-100 text-blue-800", packaging: "bg-yellow-100 text-yellow-800", packed: "bg-green-100 text-green-800", dispatched: "bg-purple-100 text-purple-800" };

function AddressSelector({ customerId, label, selectedAddress, onSelect, onAddNew, onEdit }) {
  const [addresses, setAddresses] = useState([]);
  const [showPicker, setShowPicker] = useState(false);
  useEffect(() => {
    if (customerId) api.get(`/customers/${customerId}/addresses`).then(r => setAddresses(r.data)).catch(() => {});
  }, [customerId]);
  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium">{label}</Label>
      {selectedAddress ? (
        <div className="flex items-start justify-between p-3 rounded-lg bg-secondary text-sm">
          <span>{selectedAddress.label ? `[${selectedAddress.label}] ` : ""}{selectedAddress.address_name ? `${selectedAddress.address_name} – ` : ""}{selectedAddress.address_line}, {selectedAddress.city}, {selectedAddress.state} - {selectedAddress.pincode}</span>
          <div className="flex gap-1 shrink-0">
            {onEdit && <Button variant="ghost" size="sm" onClick={() => onEdit(selectedAddress)}><Edit className="w-3.5 h-3.5" /></Button>}
            <Button variant="outline" size="sm" onClick={() => setShowPicker(true)}>Change</Button>
          </div>
        </div>
      ) : (
        <Button variant="outline" className="w-full justify-start text-muted-foreground" onClick={() => setShowPicker(true)}>
          <MapPin className="w-4 h-4 mr-2" /> Select {label}
        </Button>
      )}
      <Dialog open={showPicker} onOpenChange={setShowPicker}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Select {label}</DialogTitle></DialogHeader>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {addresses.length === 0 ? <p className="text-sm text-muted-foreground py-4 text-center">No saved addresses.</p> :
              addresses.map(a => (
                <div key={a.id} className="flex items-center justify-between p-3 rounded-lg border hover:bg-accent transition-colors">
                  <button className="flex-1 text-left" onClick={() => { onSelect(a); setShowPicker(false); }}>
                    {a.label && <span className="text-xs font-medium text-primary mr-2">[{a.label}]</span>}
                    <span className="text-sm">{a.address_name ? `${a.address_name} – ` : ""}{a.address_line}, {a.city}, {a.state} - {a.pincode}</span>
                  </button>
                  {onEdit && <Button variant="ghost" size="sm" className="shrink-0 ml-2" onClick={(e) => { e.stopPropagation(); setShowPicker(false); onEdit(a); }}><Edit className="w-3.5 h-3.5" /></Button>}
                </div>
              ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPicker(false)}>Cancel</Button>
            <Button onClick={() => { setShowPicker(false); onAddNew(); }}><Plus className="w-4 h-4 mr-1" /> Add New</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── PACKAGING EDIT SECTION ─────────────────────────────────────────────────
function PackagingEditSection({ order, onSaved }) {
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [itemPackedBy, setItemPackedBy] = useState(order.packaging?.item_packed_by || []);
  const [boxPackedBy, setBoxPackedBy] = useState(order.packaging?.box_packed_by || []);
  const [checkedBy, setCheckedBy] = useState(order.packaging?.checked_by || []);
  const [itemImages, setItemImages] = useState(order.packaging?.item_images || {});
  const [orderImages, setOrderImages] = useState(order.packaging?.order_images || []);
  const [packedBoxImages, setPackedBoxImages] = useState(order.packaging?.packed_box_images || []);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);

  useEffect(() => {
    api.get("/packaging-staff").then(r => setPackagingStaff(r.data.filter(s => s.active))).catch(() => {});
  }, []);

  const toggleStaff = (list, setList, name) =>
    setList(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);

  const uploadImage = async (file, target, itemKey) => {
    const compressed = await compressImage(file);
    const form = new FormData();
    form.append("file", compressed);
    setUploading(true);
    try {
      const res = await api.post("/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      const url = res.data.url;
      if (target === "item" && itemKey) {
        setItemImages(prev => ({ ...prev, [itemKey]: [...(prev[itemKey] || []), url] }));
      } else if (target === "order") {
        setOrderImages(prev => [...prev, url]);
      } else if (target === "packed_box") {
        setPackedBoxImages(prev => [...prev, url]);
      }
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  const removeImage = (target, url, itemKey) => {
    if (target === "item" && itemKey) {
      setItemImages(prev => ({ ...prev, [itemKey]: (prev[itemKey] || []).filter(u => u !== url) }));
    } else if (target === "order") {
      setOrderImages(prev => prev.filter(u => u !== url));
    } else if (target === "packed_box") {
      setPackedBoxImages(prev => prev.filter(u => u !== url));
    }
  };

  const handleSave = async (markPacked = false) => {
    if (markPacked) {
      if (!itemPackedBy.length) return toast.error("Item Packed By is required");
      if (!boxPackedBy.length) return toast.error("Box Packed By is required");
      if (!checkedBy.length) return toast.error("Checked By is required");
    }
    setSaving(true);
    try {
      const payload = {
        item_packed_by: itemPackedBy, box_packed_by: boxPackedBy, checked_by: checkedBy,
        item_images: itemImages, order_images: orderImages, packed_box_images: packedBoxImages,
      };
      if (markPacked) payload.status = "packed";
      await api.put(`/orders/${order.id}/packaging`, payload);
      toast.success(markPacked ? "Order marked as Packed!" : "Packaging updated");
      onSaved();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <div className="space-y-6">
      {/* Staff Selection */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Packaging Staff</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {[["Item Packed By", itemPackedBy, setItemPackedBy], ["Box Packed By", boxPackedBy, setBoxPackedBy], ["Checked By", checkedBy, setCheckedBy]].map(([lbl, list, setter]) => (
            <div key={lbl}>
              <Label className="text-sm font-medium">{lbl}</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {packagingStaff.map(s => (
                  <Button key={s.id} variant={list.includes(s.name) ? "default" : "outline"} size="sm"
                    onClick={() => toggleStaff(list, setter, s.name)} data-testid={`staff-${lbl.replace(/\s/g, '-').toLowerCase()}-${s.name}`}>
                    {s.name}
                  </Button>
                ))}
                {packagingStaff.length === 0 && <p className="text-xs text-muted-foreground">No staff configured</p>}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Images */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Packaging Images</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          {/* Item Images */}
          {order.items?.map(item => (
            <div key={item.product_name}>
              <Label className="text-xs font-medium text-muted-foreground uppercase">{item.product_name}</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {(itemImages[item.product_name] || []).map((url, i) => (
                  <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                    <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" onClick={() => setPreviewImage(`${backendUrl}${url}`)} />
                    <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => removeImage("item", url, item.product_name)}><X className="w-3 h-3" /></button>
                  </div>
                ))}
                <label className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors">
                  <Upload className="w-4 h-4 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground mt-1">Files</span>
                  <input type="file" accept="image/*" className="sr-only" disabled={uploading}
                    onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "item", item.product_name); e.target.value = ""; }} />
                </label>
                <label className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors bg-secondary/30">
                  <Upload className="w-4 h-4 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground mt-1">Camera</span>
                  <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading}
                    onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "item", item.product_name); e.target.value = ""; }} />
                </label>
              </div>
            </div>
          ))}

          {/* Order Images */}
          <div>
            <Label className="text-xs font-medium text-muted-foreground uppercase">Full Order Images</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {orderImages.map((url, i) => (
                <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                  <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" onClick={() => setPreviewImage(`${backendUrl}${url}`)} />
                  <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => removeImage("order", url)}><X className="w-3 h-3" /></button>
                </div>
              ))}
              <label className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors">
                <Upload className="w-4 h-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground mt-1">Files</span>
                <input type="file" accept="image/*" className="sr-only" disabled={uploading}
                  onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "order"); e.target.value = ""; }} />
              </label>
              <label className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors bg-secondary/30">
                <Upload className="w-4 h-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground mt-1">Camera</span>
                <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading}
                  onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "order"); e.target.value = ""; }} />
              </label>
            </div>
          </div>

          {/* Packed Box Images */}
          <div>
            <Label className="text-xs font-medium text-muted-foreground uppercase">Packed Box Images</Label>
            <div className="flex flex-wrap gap-2 mt-2">
              {packedBoxImages.map((url, i) => (
                <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                  <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" onClick={() => setPreviewImage(`${backendUrl}${url}`)} />
                  <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => removeImage("packed_box", url)}><X className="w-3 h-3" /></button>
                </div>
              ))}
              <label className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors">
                <Upload className="w-4 h-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground mt-1">Files</span>
                <input type="file" accept="image/*" className="sr-only" disabled={uploading}
                  onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "packed_box"); e.target.value = ""; }} />
              </label>
              <label className="w-20 h-20 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors bg-secondary/30">
                <Upload className="w-4 h-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground mt-1">Camera</span>
                <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading}
                  onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "packed_box"); e.target.value = ""; }} />
              </label>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={() => handleSave(false)} disabled={saving} data-testid="save-packaging-btn">
          {saving ? "Saving..." : "Save Progress"}
        </Button>
        {order.status !== "packed" && (
          <Button onClick={() => handleSave(true)} disabled={saving} data-testid="mark-packed-btn">
            {saving ? "Saving..." : "Mark as Packed"}
          </Button>
        )}
      </div>

      <Dialog open={!!previewImage} onOpenChange={() => setPreviewImage(null)}>
        <DialogContent className="max-w-3xl p-2">
          <DialogHeader><DialogTitle className="sr-only">Preview</DialogTitle></DialogHeader>
          {previewImage && <img src={previewImage} alt="Preview" className="w-full h-auto rounded-lg max-h-[80vh] object-contain" />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── DISPATCH EDIT SECTION ───────────────────────────────────────────────────
function DispatchEditSection({ order, onSaved }) {
  const [dispatchType, setDispatchType] = useState(order.shipping_method || "");
  const [courierName, setCourierName] = useState(order.courier_name || "");
  const [transporterName, setTransporterName] = useState(order.transporter_name || "");
  const [lrNo, setLrNo] = useState(order.dispatch?.lr_no || "");
  const [saving, setSaving] = useState(false);

  const handleDispatch = async () => {
    if (!dispatchType) return toast.error("Select dispatch type");
    setSaving(true);
    try {
      await api.put(`/orders/${order.id}/dispatch`, {
        courier_name: courierName, transporter_name: transporterName, lr_no: lrNo, dispatch_type: dispatchType,
      });
      toast.success("Order dispatched!");
      onSaved();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-base">Dispatch Details</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {order.status === "dispatched" ? (
          <div className="space-y-4">
            <div className="space-y-2 text-sm">
              <p className="text-green-600 font-medium">This order has already been dispatched.</p>
              {order.dispatch?.dispatched_at && <p className="text-muted-foreground">Dispatched: {new Date(order.dispatch.dispatched_at).toLocaleString("en-IN")}</p>}
              {order.dispatch?.courier_name && <p>Courier: {order.dispatch.courier_name}</p>}
              {order.dispatch?.transporter_name && <p>Transporter: {order.dispatch.transporter_name}</p>}
              {order.dispatch?.lr_no && <p>LR No: {order.dispatch.lr_no}</p>}
            </div>
            <Separator />
            <p className="text-sm font-medium">Update Shipping Method</p>
            <div><Label>Shipping Method</Label>
              <Select value={dispatchType} onValueChange={setDispatchType}>
                <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent>
                  {SHIPPING_METHODS.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {dispatchType === "courier" && (
              <div><Label>Courier</Label>
                <Select value={courierName} onValueChange={setCourierName}>
                  <SelectTrigger><SelectValue placeholder="Select courier" /></SelectTrigger>
                  <SelectContent>{COURIER_OPTIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {dispatchType === "transport" && (
              <div><Label>Transporter Name</Label>
                <Input value={transporterName} onChange={e => setTransporterName(e.target.value)} />
              </div>
            )}
            <div className="flex justify-end">
              <Button onClick={async () => {
                setSaving(true);
                try {
                  await api.put(`/orders/${order.id}/shipping-method`, {
                    shipping_method: dispatchType, courier_name: courierName, transporter_name: transporterName
                  });
                  toast.success("Shipping method updated!");
                  onSaved();
                } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
                finally { setSaving(false); }
              }} disabled={saving} data-testid="update-shipping-btn">
                {saving ? "Updating..." : "Update Shipping"}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div><Label>Dispatch Type</Label>
              <Select value={dispatchType} onValueChange={setDispatchType}>
                <SelectTrigger data-testid="dispatch-type-select"><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent>
                  {SHIPPING_METHODS.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {dispatchType === "courier" && (
              <div><Label>Courier</Label>
                <Select value={courierName} onValueChange={setCourierName}>
                  <SelectTrigger><SelectValue placeholder="Select courier" /></SelectTrigger>
                  <SelectContent>{COURIER_OPTIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {dispatchType === "transport" && (
              <div><Label>Transporter Name</Label>
                <Input value={transporterName} onChange={e => setTransporterName(e.target.value)} data-testid="transporter-name-input" />
              </div>
            )}
            <div><Label>LR / Tracking No.</Label>
              <Input value={lrNo} onChange={e => setLrNo(e.target.value)} data-testid="lr-no-input" />
            </div>
            <div className="flex justify-end">
              <Button onClick={handleDispatch} disabled={saving} data-testid="dispatch-order-btn">
                {saving ? "Dispatching..." : "Dispatch Order"}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── MAIN EDIT ORDER COMPONENT ───────────────────────────────────────────────
export default function EditOrder() {
  const { orderId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Main order fields (admin/telecaller)
  const [purpose, setPurpose] = useState("");
  const [items, setItems] = useState([emptyItem()]);
  const [gstApplicable, setGstApplicable] = useState(false);
  const [shippingMethod, setShippingMethod] = useState("");
  const [courierName, setCourierName] = useState("");
  const [transporterName, setTransporterName] = useState("");
  const [shippingCharge, setShippingCharge] = useState(0);
  const [additionalCharges, setAdditionalCharges] = useState([]);
  const [remark, setRemark] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("unpaid");
  const [amountPaid, setAmountPaid] = useState(0);
  const [modeOfPayment, setModeOfPayment] = useState("");
  const [paymentModeDetails, setPaymentModeDetails] = useState("");
  const [freeSamples, setFreeSamples] = useState([]);
  const [billingAddress, setBillingAddress] = useState(null);
  const [shippingAddress, setShippingAddress] = useState(null);
  const [sameAsBilling, setSameAsBilling] = useState(true);
  const [showAddAddress, setShowAddAddress] = useState(false);
  const [addressTarget, setAddressTarget] = useState("billing");
  const [editingAddrId, setEditingAddrId] = useState(null);
  const [newAddr, setNewAddr] = useState(emptyAddress());
  const [pincodeLoading, setPincodeLoading] = useState(false);
  const [stateSearch, setStateSearch] = useState("");
  const [paymentScreenshots, setPaymentScreenshots] = useState([]);
  const [extraShippingDetails, setExtraShippingDetails] = useState("");
  const [showEditCustomer, setShowEditCustomer] = useState(false);
  const [editCustData, setEditCustData] = useState({ name: "", gst_no: "", phone_numbers: [""], email: "", alias: "" });
  const [formulationLocked, setFormulationLocked] = useState(false);
  const [hasEditPermission, setHasEditPermission] = useState(false);
  const [editRequestSent, setEditRequestSent] = useState(false);
  const [editRequestReason, setEditRequestReason] = useState("");

  useEffect(() => { loadOrder(); }, [orderId]);

  const loadOrder = async () => {
    try {
      const res = await api.get(`/orders/${orderId}`);
      const o = res.data;
      setOrder(o);
      setPurpose(o.purpose || "");
      setItems(o.items?.length ? o.items.map(i => ({ ...i })) : [emptyItem()]);
      setGstApplicable(o.gst_applicable || false);
      setShippingMethod(o.shipping_method || "");
      setCourierName(o.courier_name || "");
      setTransporterName(o.transporter_name || "");
      setShippingCharge(o.shipping_charge || 0);
      const allCharges = o.additional_charges || [];
      setAdditionalCharges(allCharges.filter(c => c.name !== "Local Charges"));
      setRemark(o.remark || "");
      setPaymentStatus(o.payment_status || "unpaid");
      setAmountPaid(o.amount_paid || 0);
      setModeOfPayment(o.mode_of_payment || "");
      setPaymentModeDetails(o.payment_mode_details || "");
      setFreeSamples(o.free_samples || []);
      setBillingAddress(o.billing_address || null);
      setShippingAddress(o.shipping_address || null);
      setSameAsBilling(!o.shipping_address_id || o.billing_address_id === o.shipping_address_id);
      setPaymentScreenshots(o.payment_screenshots || []);
      setExtraShippingDetails(o.extra_shipping_details || "");
      // Check formulation lock status
      setFormulationLocked(o.formulation_locked || false);
      setHasEditPermission(o.has_edit_permission || false);
    } catch {
      toast.error("Order not found");
      navigate(-1);
    } finally { setLoading(false); }
  };

  const updateItem = (idx, field, value) => {
    setItems(prev => {
      const updated = [...prev];
      const item = { ...updated[idx], [field]: value };
      if (field === "rate" && item.qty > 0) item.amount = +(item.rate * item.qty).toFixed(2);
      else if (field === "amount" && item.qty > 0) item.rate = +(item.amount / item.qty).toFixed(2);
      else if (field === "qty" && item.rate > 0) item.amount = +(item.rate * item.qty).toFixed(2);
      if (gstApplicable && item.gst_rate > 0) item.gst_amount = +(item.amount * item.gst_rate / 100).toFixed(2);
      else item.gst_amount = 0;
      item.total = +(item.amount + item.gst_amount).toFixed(2);
      updated[idx] = item;
      return updated;
    });
  };

  useEffect(() => {
    setItems(prev => prev.map(item => {
      const gst_amount = gstApplicable && item.gst_rate > 0 ? +(item.amount * item.gst_rate / 100).toFixed(2) : 0;
      return { ...item, gst_amount, total: +(item.amount + gst_amount).toFixed(2) };
    }));
  }, [gstApplicable]);

  const subtotal = items.reduce((s, i) => s + i.amount, 0);
  const totalItemGst = items.reduce((s, i) => s + i.gst_amount, 0);
  const shippingGst = gstApplicable && shippingCharge > 0 ? +(shippingCharge * 0.18).toFixed(2) : 0;
  const totalAdditional = additionalCharges.reduce((s, c) => s + (c.amount || 0), 0);
  const totalAdditionalGst = additionalCharges.reduce((s, c) => {
    if (gstApplicable && c.gst_percent > 0) return s + +((c.amount || 0) * c.gst_percent / 100).toFixed(2);
    return s;
  }, 0);
  const grandTotal = Math.ceil(subtotal + totalItemGst + shippingCharge + shippingGst + totalAdditional + totalAdditionalGst);
  const balanceAmount = paymentStatus === "full" ? 0 : paymentStatus === "partial" ? Math.max(0, grandTotal - amountPaid) : grandTotal;

  // State search for address
  const saveNewAddress = async () => {
    if (!newAddr.address_line || !newAddr.city || !newAddr.state || !newAddr.pincode) return toast.error("All address fields required");
    if (!/^\d{6}$/.test(newAddr.pincode)) return toast.error("Pincode must be 6 digits");
    if (!INDIAN_STATES.includes(newAddr.state)) return toast.error("Please select a valid State/UT from the dropdown");
    try {
      let res;
      if (editingAddrId) {
        res = await api.put(`/customers/${order.customer_id}/addresses/${editingAddrId}`, newAddr);
        if (billingAddress?.id === editingAddrId) { setBillingAddress(res.data); if (sameAsBilling) setShippingAddress(res.data); }
        if (shippingAddress?.id === editingAddrId) setShippingAddress(res.data);
        toast.success("Address updated");
      } else {
        res = await api.post(`/customers/${order.customer_id}/addresses`, newAddr);
        if (addressTarget === "billing") { setBillingAddress(res.data); if (sameAsBilling) setShippingAddress(res.data); }
        else setShippingAddress(res.data);
        toast.success("Address saved");
      }
      setShowAddAddress(false); setNewAddr(emptyAddress()); setEditingAddrId(null);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const openEditAddress = (addr) => {
    setEditingAddrId(addr.id);
    setNewAddr({ address_line: addr.address_line, city: addr.city, state: addr.state, pincode: addr.pincode, label: addr.label || "", address_name: addr.address_name || "" });
    setShowAddAddress(true);
  };

  const handleScreenshotUpload = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    for (const file of files) {
      const compressed = await compressImage(file);
      const formData = new FormData();
      formData.append("file", compressed);
      try {
        const res = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
        setPaymentScreenshots(prev => [...prev, res.data.url]);
      } catch { toast.error("Upload failed"); }
    }
    e.target.value = "";
  };

  const openEditCustomer = () => {
    if (!order?.customer_id) return;
    api.get(`/customers/${order.customer_id}`).then(r => {
      const c = r.data;
      setEditCustData({
        name: c.name || "", gst_no: c.gst_no || "",
        phone_numbers: c.phone_numbers?.length ? [...c.phone_numbers] : [""],
        email: c.email || "", alias: c.alias || "",
      });
      setShowEditCustomer(true);
    }).catch(() => toast.error("Failed to load customer"));
  };

  const saveEditCustomer = async () => {
    if (!editCustData.name) return toast.error("Name required");
    const phones = editCustData.phone_numbers.filter(Boolean);
    if (phones.length === 0) return toast.error("At least one phone number required");
    try {
      await api.put(`/customers/${order.customer_id}`, { ...editCustData, phone_numbers: phones });
      setShowEditCustomer(false);
      toast.success("Customer updated");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to update"); }
  };

  const requestEditPermission = async () => {
    try {
      await api.post(`/orders/${orderId}/request-edit`, { reason: editRequestReason });
      setEditRequestSent(true);
      toast.success("Edit permission request sent to Admin");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to send request"); }
  };

  const handleSave = async () => {
    if (items.some(i => !i.product_name)) return toast.error("All items need a product name");
    if (modeOfPayment === "Other" && !paymentModeDetails) return toast.error("Specify payment details for 'Other'");
    setSaving(true);
    try {
      const payload = {
        purpose,
        items: items.map(({ product_name, qty, unit, rate, amount, gst_rate, gst_amount, total, description, formulation }) => ({
          product_name, qty, unit, rate, amount, gst_rate, gst_amount, total, description, formulation: formulation || "",
        })),
        gst_applicable: gstApplicable,
        shipping_method: shippingMethod,
        courier_name: courierName,
        transporter_name: transporterName,
        shipping_charge: shippingCharge,
        shipping_gst: shippingGst,
        additional_charges: [
          ...additionalCharges.filter(c => c.name).map(c => ({
            name: c.name, amount: Math.max(0, c.amount || 0), gst_percent: c.gst_percent || 0,
            gst_amount: gstApplicable && c.gst_percent > 0 ? +((c.amount || 0) * c.gst_percent / 100).toFixed(2) : 0,
          })),
        ],
        subtotal: +subtotal.toFixed(2),
        total_gst: +(totalItemGst + shippingGst).toFixed(2),
        grand_total: grandTotal,
        remark,
        payment_status: paymentStatus,
        amount_paid: paymentStatus === "full" ? grandTotal : amountPaid,
        balance_amount: balanceAmount,
        mode_of_payment: modeOfPayment,
        payment_mode_details: paymentModeDetails,
        free_samples: freeSamples.filter(s => s.item_name),
        payment_screenshots: paymentScreenshots,
        billing_address_id: billingAddress?.id || "",
        shipping_address_id: sameAsBilling ? (billingAddress?.id || "") : (shippingAddress?.id || ""),
        billing_address: billingAddress,
        shipping_address: sameAsBilling ? billingAddress : shippingAddress,
        extra_shipping_details: extraShippingDetails,
      };
      await api.put(`/orders/${orderId}`, payload);
      toast.success("Order updated!");
      navigate(`/orders/${orderId}`);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to update"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>;
  if (!order) return null;

  const isDispatched = order.status === "dispatched";
  const isMyOrder = user?.role === "telecaller" && order.telecaller_id !== user?.id;
  const isAdmin = user?.role === "admin";
  const isEditBlocked = formulationLocked && !isAdmin && !hasEditPermission;

  // ── FORMULATION LOCK SCREEN ──
  if (isEditBlocked) {
    return (
      <div className="max-w-lg mx-auto mt-16 space-y-4 px-4" data-testid="formulation-locked-view">
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="pt-6 space-y-4 text-center">
            <Lock className="w-12 h-12 text-amber-600 mx-auto" />
            <h2 className="text-lg font-semibold">Order Locked</h2>
            <p className="text-sm text-muted-foreground">
              This order (<b>{order.order_number}</b>) has formulations and is locked to protect production data. Only Admin can edit directly.
            </p>
            {editRequestSent ? (
              <Badge variant="secondary" className="text-sm py-1">Request Sent — Waiting for Admin Approval</Badge>
            ) : (
              <div className="space-y-3 pt-2">
                <Textarea placeholder="Reason for edit request (recommended)" value={editRequestReason} onChange={e => setEditRequestReason(e.target.value)} className="text-sm" data-testid="edit-request-reason" />
                <Button onClick={requestEditPermission} className="w-full" data-testid="request-edit-btn">
                  <ShieldAlert className="w-4 h-4 mr-2" /> Request Edit Permission
                </Button>
              </div>
            )}
            <Button variant="outline" onClick={() => navigate(-1)} className="w-full">Go Back</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── DISPATCH ROLE VIEW ──
  if (user?.role === "dispatch") {
    return (
      <div className="max-w-2xl mx-auto space-y-4 px-1" data-testid="edit-order-page">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}><ArrowLeft className="w-5 h-5" /></Button>
          <div>
            <h1 className="text-xl font-bold">{order.order_number}</h1>
            <div className="flex items-center gap-2 mt-1">
              <Badge className={`${STATUS_COLORS[order.status] || "bg-gray-100"} text-xs`}>{order.status}</Badge>
              <span className="text-sm text-muted-foreground">{order.customer_name}</span>
            </div>
          </div>
        </div>
        {isDispatched && (
          <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 text-sm text-purple-800">
            This order has been dispatched. Editing is locked.
          </div>
        )}
        <DispatchEditSection order={order} onSaved={() => navigate(`/orders/${orderId}`)} />
      </div>
    );
  }

  // ── PACKAGING ROLE VIEW ──
  if (user?.role === "packaging") {
    return (
      <div className="max-w-4xl mx-auto space-y-4 px-1" data-testid="edit-order-page">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}><ArrowLeft className="w-5 h-5" /></Button>
          <div>
            <h1 className="text-xl font-bold">{order.order_number}</h1>
            <div className="flex items-center gap-2 mt-1">
              <Badge className={`${STATUS_COLORS[order.status] || "bg-gray-100"} text-xs`}>{order.status}</Badge>
              <span className="text-sm text-muted-foreground">{order.customer_name}</span>
            </div>
          </div>
        </div>
        {isDispatched ? (
          <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 text-sm text-purple-800">
            This order has been dispatched. Editing is locked.
          </div>
        ) : (
          <PackagingEditSection order={order} onSaved={() => navigate(`/orders/${orderId}`)} />
        )}
      </div>
    );
  }

  // ── TELECALLER: own orders only ──
  if (user?.role === "telecaller" && isMyOrder) {
    return (
      <div className="max-w-2xl mx-auto px-1 py-8 text-center">
        <p className="text-muted-foreground">You can only edit your own orders.</p>
        <Button className="mt-4" onClick={() => navigate(-1)}>Go Back</Button>
      </div>
    );
  }

  // ── ADMIN / TELECALLER FULL EDIT ──
  return (
    <div className="max-w-5xl mx-auto space-y-4 sm:space-y-6 px-1 sm:px-0" data-testid="edit-order-page">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}><ArrowLeft className="w-5 h-5" /></Button>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Edit {order.order_number}</h1>
          <div className="flex items-center gap-2 mt-1">
            <Badge className={`${STATUS_COLORS[order.status] || "bg-gray-100"} text-xs`}>{order.status}</Badge>
            <span className="text-sm text-muted-foreground">{order.customer_name}</span>
            <Button variant="outline" size="sm" className="h-6 text-xs" onClick={openEditCustomer} data-testid="edit-customer-btn-order"><Edit className="w-3 h-3 mr-1" /> Edit Customer</Button>
          </div>
        </div>
      </div>

      {isDispatched && !isAdmin && (
        <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 text-sm text-purple-800" data-testid="dispatch-lock-notice">
          This order has been dispatched. Editing is locked.
        </div>
      )}

      {(isDispatched && !isAdmin) ? null : (
        <>
          {/* Addresses */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Addresses</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <AddressSelector customerId={order.customer_id} label="Billing Address" selectedAddress={billingAddress}
                onSelect={a => { setBillingAddress(a); if (sameAsBilling) setShippingAddress(a); }}
                onAddNew={() => { setAddressTarget("billing"); setEditingAddrId(null); setNewAddr(emptyAddress()); setShowAddAddress(true); }}
                onEdit={openEditAddress} />
              <div className="flex items-center gap-2">
                <Checkbox id="editSameAddr" checked={sameAsBilling} onCheckedChange={v => { setSameAsBilling(v); if (v) setShippingAddress(billingAddress); }} />
                <Label htmlFor="editSameAddr" className="cursor-pointer text-sm">Shipping same as Billing</Label>
              </div>
              {!sameAsBilling && (
                <AddressSelector customerId={order.customer_id} label="Shipping Address" selectedAddress={shippingAddress}
                  onSelect={a => setShippingAddress(a)}
                  onAddNew={() => { setAddressTarget("shipping"); setEditingAddrId(null); setNewAddr(emptyAddress()); setShowAddAddress(true); }}
                  onEdit={openEditAddress} />
              )}
            </CardContent>
          </Card>

          {/* Purpose */}
          <Card>
            <CardContent className="pt-6">
              <Label>Purpose / Requirement</Label>
              <Textarea className="mt-2" value={purpose} onChange={e => setPurpose(e.target.value)} data-testid="edit-purpose" />
            </CardContent>
          </Card>

          {/* GST Toggle */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Checkbox id="editGst" checked={gstApplicable} onCheckedChange={setGstApplicable} />
                <Label htmlFor="editGst" className="cursor-pointer">GST Applicable</Label>
              </div>
            </CardContent>
          </Card>

          {/* Items */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Order Items</CardTitle>
                <Button variant="outline" size="sm" onClick={() => setItems(p => [...p, emptyItem()])} data-testid="edit-add-item">
                  <Plus className="w-4 h-4 mr-1" /> Add Item
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {items.map((item, idx) => (
                <div key={idx} className="p-4 rounded-lg border bg-secondary/30 space-y-3" data-testid={`edit-item-${idx}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">Item {idx + 1}</span>
                    {items.length > 1 && <Button variant="ghost" size="icon" onClick={() => setItems(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                    <div className="col-span-2"><Label className="text-xs">Product Name</Label><Input value={item.product_name} onChange={e => updateItem(idx, "product_name", e.target.value)} data-testid={`edit-item-name-${idx}`} /></div>
                    <div><Label className="text-xs">Qty</Label><Input type="number" value={item.qty || ""} onChange={e => updateItem(idx, "qty", +e.target.value)} data-testid={`edit-item-qty-${idx}`} /></div>
                    <div><Label className="text-xs">Unit</Label>
                      <Select value={item.unit} onValueChange={v => updateItem(idx, "unit", v)}>
                        <SelectTrigger><SelectValue placeholder="Unit" /></SelectTrigger>
                        <SelectContent>{UNITS.map(u => <SelectItem key={u || "blank"} value={u || "blank"}>{u || "(none)"}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div><Label className="text-xs">Rate</Label><Input type="number" min={0} value={item.rate || ""} onChange={e => updateItem(idx, "rate", Math.max(0, +e.target.value))} data-testid={`edit-item-rate-${idx}`} /></div>
                    <div><Label className="text-xs">Amount</Label><Input type="number" min={0} value={item.amount || ""} onChange={e => updateItem(idx, "amount", Math.max(0, +e.target.value))} data-testid={`edit-item-amount-${idx}`} /></div>
                  </div>
                  <div><Label className="text-xs">Description</Label><Input value={item.description || ""} onChange={e => updateItem(idx, "description", e.target.value)} /></div>
                  {gstApplicable && (
                    <div className="flex items-center gap-3">
                      <div className="w-32"><Label className="text-xs">GST Rate</Label>
                        <Select value={String(item.gst_rate)} onValueChange={v => updateItem(idx, "gst_rate", +v)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>{GST_RATES.map(r => <SelectItem key={r} value={String(r)}>{r}%</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div><Label className="text-xs">GST Amt</Label><p className="text-sm font-mono mt-1">₹{item.gst_amount.toFixed(2)}</p></div>
                      <div><Label className="text-xs">Total</Label><p className="text-sm font-mono font-medium mt-1">₹{item.total.toFixed(2)}</p></div>
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Free Samples */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Free Samples (Optional)</CardTitle>
                <Button variant="outline" size="sm" onClick={() => setFreeSamples(p => [...p, emptySample()])}><Plus className="w-4 h-4 mr-1" /> Add Sample</Button>
              </div>
            </CardHeader>
            {freeSamples.length > 0 && (
              <CardContent className="space-y-3">
                {freeSamples.map((sample, idx) => (
                  <div key={idx} className="flex gap-2 items-start">
                    <div className="flex-1 grid grid-cols-2 gap-2">
                      <div><Label className="text-xs">Sample Item</Label><Input value={sample.item_name} onChange={e => { const s = [...freeSamples]; s[idx] = { ...s[idx], item_name: e.target.value }; setFreeSamples(s); }} /></div>
                      <div><Label className="text-xs">Description</Label><Input value={sample.description} onChange={e => { const s = [...freeSamples]; s[idx] = { ...s[idx], description: e.target.value }; setFreeSamples(s); }} /></div>
                    </div>
                    <Button variant="ghost" size="icon" className="mt-5" onClick={() => setFreeSamples(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                  </div>
                ))}
              </CardContent>
            )}
          </Card>

          {/* Shipping */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Shipping</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div><Label>Shipping Method</Label>
                  <Select value={shippingMethod} onValueChange={setShippingMethod}>
                    <SelectTrigger data-testid="edit-shipping-method"><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>{SHIPPING_METHODS.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {shippingMethod === "courier" && (
                  <div><Label>Courier</Label>
                    <Select value={courierName} onValueChange={setCourierName}>
                      <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>{COURIER_OPTIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                )}
                {shippingMethod === "transport" && (
                  <div><Label>Transporter</Label><Input value={transporterName} onChange={e => setTransporterName(e.target.value)} /></div>
                )}
              </div>
              <div>
                <Label>Extra Shipping Details <span className="text-xs text-muted-foreground">(Optional)</span></Label>
                <Input value={extraShippingDetails} onChange={e => setExtraShippingDetails(e.target.value)} placeholder="Driver contact, landmark, special notes..." data-testid="edit-extra-shipping-details" />
              </div>
            </CardContent>
          </Card>

          {/* Charges */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Charges</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Shipping Charges</Label>
                <Input type="number" min={0} value={shippingCharge || ""} onChange={e => setShippingCharge(Math.max(0, +e.target.value))} placeholder="0" data-testid="edit-shipping-charge-input" />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Additional Charges</Label>
                <Button variant="outline" size="sm" onClick={() => setAdditionalCharges(p => [...p, { name: "", amount: 0, gst_percent: 0 }])} data-testid="edit-add-charge-btn"><Plus className="w-4 h-4 mr-1" /> Add Charge</Button>
              </div>
              {additionalCharges.length === 0 && <p className="text-sm text-muted-foreground">No additional charges.</p>}
              {additionalCharges.map((charge, idx) => (
                <div key={idx} className="flex gap-2 items-end" data-testid={`edit-charge-${idx}`}>
                  <div className="flex-1">
                    <Label className="text-xs">Charge Name</Label>
                    <Input value={charge.name} onChange={e => { const c = [...additionalCharges]; c[idx] = { ...c[idx], name: e.target.value }; setAdditionalCharges(c); }} placeholder="e.g. Insurance, Handling" />
                  </div>
                  <div className="w-28">
                    <Label className="text-xs">Amount</Label>
                    <Input type="number" min={0} value={charge.amount || ""} onChange={e => { const c = [...additionalCharges]; c[idx] = { ...c[idx], amount: Math.max(0, +e.target.value) }; setAdditionalCharges(c); }} />
                  </div>
                  {gstApplicable && (
                    <div className="w-24">
                      <Label className="text-xs">GST %</Label>
                      <Select value={String(charge.gst_percent || 0)} onValueChange={v => { const c = [...additionalCharges]; c[idx] = { ...c[idx], gst_percent: +v }; setAdditionalCharges(c); }}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>{GST_RATES.map(r => <SelectItem key={r} value={String(r)}>{r}%</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                  )}
                  <Button variant="ghost" size="icon" onClick={() => setAdditionalCharges(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Payment */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Payment</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div><Label>Payment Status</Label>
                  <Select value={paymentStatus} onValueChange={setPaymentStatus}>
                    <SelectTrigger data-testid="edit-payment-status"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="unpaid">Unpaid</SelectItem><SelectItem value="partial">Partial</SelectItem><SelectItem value="full">Full</SelectItem></SelectContent>
                  </Select>
                </div>
                <div><Label>Mode of Payment</Label>
                  <Select value={modeOfPayment} onValueChange={setModeOfPayment}>
                    <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>{PAYMENT_MODES.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {modeOfPayment === "Other" && <div><Label>Payment Details *</Label><Input value={paymentModeDetails} onChange={e => setPaymentModeDetails(e.target.value)} /></div>}
              </div>
              {paymentStatus === "partial" && (
                <div className="grid grid-cols-2 gap-4">
                  <div><Label>Amount Paid</Label><Input type="number" value={amountPaid || ""} onChange={e => setAmountPaid(+e.target.value)} data-testid="edit-amount-paid" /></div>
                  <div><Label>Balance</Label><Input type="number" value={balanceAmount} readOnly className="bg-muted" /></div>
                </div>
              )}
              <div>
                <Label>Payment Screenshots</Label>
                <div className="flex flex-wrap gap-2 mt-1">
                  <label className="cursor-pointer inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90">
                    Gallery / Files
                    <input type="file" multiple accept="image/*" onChange={handleScreenshotUpload} className="hidden" data-testid="edit-payment-screenshot-input" />
                  </label>
                  <label className="cursor-pointer inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80">
                    Camera
                    <input type="file" accept="image/*" capture="environment" onChange={handleScreenshotUpload} className="hidden" data-testid="edit-payment-screenshot-camera" />
                  </label>
                </div>
                {paymentScreenshots.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {paymentScreenshots.map((url, i) => (
                      <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
                        <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt="" className="w-full h-full object-cover" />
                        <button className="absolute inset-0 bg-red-500/80 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                          onClick={() => setPaymentScreenshots(prev => prev.filter((_, j) => j !== i))}>
                          <X className="w-4 h-4 text-white" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Remark */}
          <Card><CardContent className="pt-6"><Label>Remarks</Label><Textarea className="mt-2" value={remark} onChange={e => setRemark(e.target.value)} data-testid="edit-remark" /></CardContent></Card>

          {/* Summary */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Order Summary</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-mono">₹{subtotal.toFixed(2)}</span></div>
                {gstApplicable && <div className="flex justify-between"><span className="text-muted-foreground">Item GST</span><span className="font-mono">₹{totalItemGst.toFixed(2)}</span></div>}
                {shippingCharge > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping Charges</span><span className="font-mono">₹{shippingCharge.toFixed(2)}</span></div>}
                {shippingGst > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping GST (18%)</span><span className="font-mono">₹{shippingGst.toFixed(2)}</span></div>}
                {additionalCharges.filter(c => c.amount > 0).map((c, i) => (
                  <div key={i}>
                    <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"}</span><span className="font-mono">₹{(c.amount || 0).toFixed(2)}</span></div>
                    {gstApplicable && c.gst_percent > 0 && <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"} GST ({c.gst_percent}%)</span><span className="font-mono">₹{((c.amount || 0) * c.gst_percent / 100).toFixed(2)}</span></div>}
                  </div>
                ))}
                <Separator />
                <div className="flex justify-between text-base font-bold"><span>Grand Total (Rounded Up)</span><span className="font-mono">₹{grandTotal}</span></div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => navigate(-1)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="min-w-[140px]" data-testid="save-edit-order-btn">
              {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </>
      )}

      {/* Add Address Dialog */}
      <Dialog open={showAddAddress} onOpenChange={setShowAddAddress}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editingAddrId ? "Edit Address" : "Add New Address"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Label</Label><Input value={newAddr.label} onChange={e => setNewAddr({ ...newAddr, label: e.target.value })} /></div>
            <div><Label>Address Name (Recipient)</Label><Input value={newAddr.address_name} onChange={e => setNewAddr({ ...newAddr, address_name: e.target.value })} placeholder={order?.customer_name || "Defaults to customer name"} /></div>
            <div><Label>Address Line *</Label><Input value={newAddr.address_line} onChange={e => setNewAddr({ ...newAddr, address_line: e.target.value })} /></div>
            <div><Label>Pincode *</Label>
              <Input value={newAddr.pincode} onChange={e => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                setNewAddr({ ...newAddr, pincode: v });
              }} maxLength={6} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>City *</Label><Input value={newAddr.city} onChange={e => setNewAddr({ ...newAddr, city: e.target.value })} /></div>
              <div>
                <Label>State *</Label>
                <div className="relative">
                  <Input value={newAddr.state} onChange={e => { setNewAddr({ ...newAddr, state: e.target.value }); setStateSearch(e.target.value); }}
                    placeholder="Type to search..." autoComplete="off" />
                  {stateSearch && !INDIAN_STATES.includes(newAddr.state) && (
                    <div className="absolute z-50 w-full mt-1 bg-background border rounded-md shadow-lg max-h-40 overflow-y-auto">
                      {INDIAN_STATES.filter(s => s.toLowerCase().includes(stateSearch.toLowerCase())).map(s => (
                        <button key={s} type="button" className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent"
                          onClick={() => { setNewAddr({ ...newAddr, state: s }); setStateSearch(""); }}>
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddAddress(false)}>Cancel</Button>
            <Button onClick={saveNewAddress}>Save Address</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Customer Dialog */}
      <Dialog open={showEditCustomer} onOpenChange={setShowEditCustomer}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Customer</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2"><Label>Customer / Company Name *</Label><Input value={editCustData.name} onChange={e => setEditCustData({ ...editCustData, name: e.target.value })} data-testid="edit-cust-name" /></div>
              <div className="col-span-2">
                <Label>GST No.</Label>
                <Input value={editCustData.gst_no} onChange={e => setEditCustData({ ...editCustData, gst_no: e.target.value.toUpperCase() })} placeholder="e.g. 27AABCU9603R1ZM" data-testid="edit-cust-gst" />
              </div>
            </div>
            <Separator />
            <h4 className="text-sm font-semibold">Contact</h4>
            {editCustData.phone_numbers.map((ph, i) => (
              <div key={i} className="flex gap-2">
                <div className="flex items-center gap-1 flex-1">
                  <span className="text-sm text-muted-foreground whitespace-nowrap">+91</span>
                  <Input value={ph} onChange={e => { const phones = [...editCustData.phone_numbers]; phones[i] = e.target.value; setEditCustData({ ...editCustData, phone_numbers: phones }); }} placeholder="10-digit number" data-testid={`edit-cust-phone-${i}`} />
                </div>
                {i === editCustData.phone_numbers.length - 1 && (
                  <Button variant="outline" size="icon" onClick={() => setEditCustData({ ...editCustData, phone_numbers: [...editCustData.phone_numbers, ""] })}><Plus className="w-4 h-4" /></Button>
                )}
              </div>
            ))}
            <div><Label className="text-xs">Email (optional)</Label><Input type="email" value={editCustData.email} onChange={e => setEditCustData({ ...editCustData, email: e.target.value })} data-testid="edit-cust-email" /></div>
            <div><Label className="text-xs">Alias (optional)</Label><Input value={editCustData.alias || ""} onChange={e => setEditCustData({ ...editCustData, alias: e.target.value })} placeholder="Short name / nickname" data-testid="edit-cust-alias" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditCustomer(false)}>Cancel</Button>
            <Button onClick={saveEditCustomer} data-testid="save-edit-customer-btn">Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
