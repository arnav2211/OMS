import { useState, useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { Plus, Trash2, Search, UserPlus, MapPin, Edit } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";
import { INDIAN_STATES } from "@/lib/indianStates";

const UNITS = ["mL", "L", "g", "Kg", "pcs", ""];
const SHIPPING_METHODS = [
  { value: "transport", label: "Transport" },
  { value: "courier", label: "Courier" },
  { value: "porter", label: "Porter" },
  { value: "self_arranged", label: "Self-Arranged Shipping" },
  { value: "office_collection", label: "Office Collection" },
];
const COURIER_OPTIONS = ["DTDC", "Anjani", "Professional", "India Post"];
const GST_RATES = [0, 5, 18];
const PAYMENT_MODES = ["Cash", "Online", "Other"];

const emptyItem = () => ({
  product_name: "", qty: 0, unit: "", rate: 0, amount: 0, gst_rate: 0, gst_amount: 0, total: 0, description: "",
});

const emptyAddress = () => ({ address_line: "", city: "", state: "", pincode: "", label: "" });
const emptySample = () => ({ item_name: "", description: "" });

function normalizePhone(phone) {
  const cleaned = phone.replace(/[\s\-\(\)]/g, "");
  const digits = cleaned.replace(/[^\d]/g, "");
  if (digits.length === 10) return `+91${digits}`;
  if (digits.length === 12 && digits.startsWith("91")) return `+${digits}`;
  return cleaned;
}

function AddressSelector({ customerId, label, selectedAddress, onSelect, onAddNew }) {
  const [addresses, setAddresses] = useState([]);
  const [showPicker, setShowPicker] = useState(false);

  useEffect(() => {
    if (customerId) {
      api.get(`/customers/${customerId}/addresses`).then(r => setAddresses(r.data)).catch(() => {});
    }
  }, [customerId]);

  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium">{label}</Label>
      {selectedAddress ? (
        <div className="flex items-start justify-between p-3 rounded-lg bg-secondary text-sm" data-testid={`selected-${label.toLowerCase().replace(/\s/g, '-')}`}>
          <div>
            {selectedAddress.label && <span className="text-xs font-medium text-primary mr-2">[{selectedAddress.label}]</span>}
            <span>{selectedAddress.address_line}, {selectedAddress.city}, {selectedAddress.state} - {selectedAddress.pincode}</span>
          </div>
          <Button variant="outline" size="sm" onClick={() => setShowPicker(true)} data-testid={`change-${label.toLowerCase().replace(/\s/g, '-')}`}>Change</Button>
        </div>
      ) : (
        <Button variant="outline" className="w-full justify-start text-muted-foreground" onClick={() => setShowPicker(true)} data-testid={`select-${label.toLowerCase().replace(/\s/g, '-')}`}>
          <MapPin className="w-4 h-4 mr-2" /> Select {label}
        </Button>
      )}
      <Dialog open={showPicker} onOpenChange={setShowPicker}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Select {label}</DialogTitle></DialogHeader>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {addresses.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">No saved addresses. Add one below.</p>
            ) : (
              addresses.map(a => (
                <button key={a.id} className="w-full text-left p-3 rounded-lg border hover:bg-accent transition-colors" onClick={() => { onSelect(a); setShowPicker(false); }}
                  data-testid={`addr-pick-${a.id}`}>
                  {a.label && <span className="text-xs font-medium text-primary mr-2">[{a.label}]</span>}
                  <span className="text-sm">{a.address_line}, {a.city}, {a.state} - {a.pincode}</span>
                </button>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPicker(false)}>Cancel</Button>
            <Button onClick={() => { setShowPicker(false); onAddNew(); }} data-testid="add-new-address-btn"><Plus className="w-4 h-4 mr-1" /> Add New Address</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function CreateOrder() {
  const navigate = useNavigate();
  const { piId } = useParams(); // For PI conversion mode
  const [searchParams] = useSearchParams();
  const duplicateOrderId = searchParams.get("duplicate");
  const [piConverting, setPiConverting] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCust, setNewCust] = useState({ name: "", gst_no: "", phone_numbers: [""], email: "", alias: "" });
  const [newCustAddresses, setNewCustAddresses] = useState([]);
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
  const [paymentScreenshots, setPaymentScreenshots] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [gstLoading, setGstLoading] = useState(false);
  const [modeOfPayment, setModeOfPayment] = useState("");
  const [paymentModeDetails, setPaymentModeDetails] = useState("");
  const [freeSamples, setFreeSamples] = useState([]);

  // Address selection
  const [billingAddress, setBillingAddress] = useState(null);
  const [shippingAddress, setShippingAddress] = useState(null);
  const [sameAsBilling, setSameAsBilling] = useState(true);
  const [showAddAddress, setShowAddAddress] = useState(false);
  const [addressTarget, setAddressTarget] = useState("billing"); // "billing" or "shipping"
  const [newAddr, setNewAddr] = useState(emptyAddress());
  const [pincodeLoading, setPincodeLoading] = useState(false);
  const [extraShippingDetails, setExtraShippingDetails] = useState("");
  const [showEditCustomer, setShowEditCustomer] = useState(false);
  const [editCustData, setEditCustData] = useState({ name: "", gst_no: "", phone_numbers: [""], email: "", alias: "" });

  useEffect(() => {
    api.get("/customers").then((r) => setCustomers(r.data)).catch(() => {});
  }, []);

  // Load PI data for conversion
  useEffect(() => {
    if (!piId) return;
    setPiConverting(true);
    api.get(`/proforma-invoices/${piId}`).then(r => {
      const pi = r.data;
      setPurpose(pi.purpose || "");
      setItems(pi.items?.length ? pi.items.map(i => ({ ...i, formulation: "" })) : [emptyItem()]);
      setGstApplicable(pi.gst_applicable || false);
      setShippingMethod(pi.shipping_method || "");
      setCourierName(pi.courier_name || "");
      setTransporterName(pi.transporter_name || "");
      setShippingCharge(pi.shipping_charge || 0);
      const allCharges = pi.additional_charges || [];
      setAdditionalCharges(allCharges.filter(c => c.name !== "Local Charges"));
      setRemark(pi.remark || "");
      setFreeSamples(pi.free_samples || []);
      // Pre-select customer
      if (pi.customer_id) {
        api.get(`/customers/${pi.customer_id}`).then(cr => {
          setSelectedCustomer(cr.data);
          setCustomerSearch(cr.data.name || "");
        }).catch(() => {});
      }
      // Pre-select addresses
      if (pi.billing_address) setBillingAddress(pi.billing_address);
      if (pi.shipping_address) setShippingAddress(pi.shipping_address);
      if (pi.billing_address_id && pi.shipping_address_id) {
        setSameAsBilling(pi.billing_address_id === pi.shipping_address_id);
      }
      toast.success("PI data loaded - review and create order");
    }).catch(() => toast.error("Failed to load PI data"));
  }, [piId]);

  // Load duplicate order data
  useEffect(() => {
    if (!duplicateOrderId) return;
    api.post(`/orders/${duplicateOrderId}/duplicate`).then(r => {
      const d = r.data;
      if (d.customer_id) {
        api.get(`/customers/${d.customer_id}`).then(cr => {
          setSelectedCustomer(cr.data);
          setCustomerSearch(cr.data.name || "");
        }).catch(() => {});
      }
      setPurpose(d.purpose || "");
      setItems(d.items?.length ? d.items.map(i => ({ ...i })) : [emptyItem()]);
      setGstApplicable(d.gst_applicable || false);
      setShippingMethod(d.shipping_method || "");
      setCourierName(d.courier_name || "");
      setTransporterName(d.transporter_name || "");
      setShippingCharge(d.shipping_charge || 0);
      const allCharges2 = d.additional_charges || [];
      setAdditionalCharges(allCharges2.filter(c => c.name !== "Local Charges"));
      setRemark(d.remark || "");
      setFreeSamples(d.free_samples || []);
      setModeOfPayment(d.mode_of_payment || "");
      setPaymentModeDetails(d.payment_mode_details || "");
      if (d.billing_address) setBillingAddress(d.billing_address);
      if (d.shipping_address) setShippingAddress(d.shipping_address);
      if (d.billing_address_id && d.shipping_address_id) {
        setSameAsBilling(d.billing_address_id === d.shipping_address_id);
      }
      toast.success("Order data loaded for duplication");
    }).catch(() => toast.error("Failed to load order for duplication"));
  }, [duplicateOrderId]);

  const filteredCustomers = customers.filter(
    (c) =>
      c.name?.toLowerCase().includes(customerSearch.toLowerCase()) ||
      c.phone_numbers?.some((p) => p.includes(customerSearch)) ||
      c.gst_no?.toLowerCase().includes(customerSearch.toLowerCase()) ||
      c.alias?.toLowerCase().includes(customerSearch.toLowerCase())
  );

  const updateItem = (idx, field, value) => {
    setItems((prev) => {
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

  const addItem = () => setItems((prev) => [...prev, emptyItem()]);
  const removeItem = (idx) => { if (items.length > 1) setItems((prev) => prev.filter((_, i) => i !== idx)); };

  useEffect(() => {
    setItems((prev) => prev.map((item) => {
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
  const rawTotal = subtotal + totalItemGst + shippingCharge + shippingGst + totalAdditional + totalAdditionalGst;
  const grandTotal = Math.ceil(rawTotal);
  const balanceAmount = paymentStatus === "full" ? 0 : paymentStatus === "partial" ? Math.max(0, grandTotal - amountPaid) : grandTotal;

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

  const verifyGst = async (gstNo) => {
    if (!gstNo || gstNo.length < 15) return;
    setGstLoading(true);
    try {
      const res = await api.get(`/gst-verify/${gstNo}`);
      const data = res.data;
      if (data.state_name) {
        toast.success(`GST Valid - ${data.state_name}`);
        if (data.legal_name || data.trade_name) {
          setNewCust((p) => ({ ...p, name: p.name || data.trade_name || data.legal_name || "" }));
        }
      }
    } catch (err) { toast.error(err.response?.data?.detail || "Invalid GST number"); }
    finally { setGstLoading(false); }
  };

  // Pincode field (no auto-fill, manual entry only)
  const [stateSearch, setStateSearch] = useState("");

  // Save new address
  const saveNewAddress = async () => {
    if (!newAddr.address_line || !newAddr.city || !newAddr.state || !newAddr.pincode) {
      return toast.error("All address fields are required");
    }
    if (!/^\d{6}$/.test(newAddr.pincode)) return toast.error("Pincode must be 6 digits");
    if (!/^[a-zA-Z\s]+$/.test(newAddr.city)) return toast.error("City must contain only letters");
    if (!INDIAN_STATES.includes(newAddr.state)) return toast.error("Please select a valid State/UT from the dropdown");

    try {
      const res = await api.post(`/customers/${selectedCustomer.id}/addresses`, newAddr);
      if (addressTarget === "billing") {
        setBillingAddress(res.data);
        if (sameAsBilling) setShippingAddress(res.data);
      } else {
        setShippingAddress(res.data);
      }
      setShowAddAddress(false);
      setNewAddr(emptyAddress());
      toast.success("Address saved");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to save address"); }
  };

  const createCustomer = async () => {
    if (!newCust.name) return toast.error("Customer name is required");
    const phones = newCust.phone_numbers.filter(Boolean);
    if (phones.length === 0) return toast.error("At least one phone number is required");
    if (newCust.gst_no && !/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$/.test(newCust.gst_no.toUpperCase())) {
      return toast.error("Invalid GST number format");
    }
    if (newCust.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newCust.email)) {
      return toast.error("Invalid email format");
    }
    try {
      const payload = { ...newCust, phone_numbers: phones };
      const res = await api.post("/customers", payload);
      setSelectedCustomer(res.data);
      setCustomers((prev) => [res.data, ...prev]);
      setShowNewCustomer(false);
      toast.success("Customer created");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to create customer"); }
  };

  const openEditCustomer = () => {
    setEditCustData({
      name: selectedCustomer.name || "",
      gst_no: selectedCustomer.gst_no || "",
      phone_numbers: selectedCustomer.phone_numbers?.length ? [...selectedCustomer.phone_numbers] : [""],
      email: selectedCustomer.email || "",
      alias: selectedCustomer.alias || "",
    });
    setShowEditCustomer(true);
  };

  const saveEditCustomer = async () => {
    if (!editCustData.name) return toast.error("Name required");
    const phones = editCustData.phone_numbers.filter(Boolean);
    if (phones.length === 0) return toast.error("At least one phone number required");
    try {
      const res = await api.put(`/customers/${selectedCustomer.id}`, { ...editCustData, phone_numbers: phones });
      setSelectedCustomer(res.data);
      setCustomers(prev => prev.map(c => c.id === res.data.id ? res.data : c));
      setShowEditCustomer(false);
      toast.success("Customer updated");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to update"); }
  };

  const handleSubmit = async () => {
    if (!selectedCustomer) return toast.error("Select a customer");
    if (items.some((i) => !i.product_name)) return toast.error("All items need a product name");
    if (shippingMethod === "courier" && !courierName) return toast.error("Select a courier");
    if (modeOfPayment === "Other" && !paymentModeDetails) return toast.error("Please specify payment details for 'Other'");

    setSubmitting(true);
    try {
      const payload = {
        customer_id: selectedCustomer.id,
        purpose,
        items: items.map(({ product_name, qty, unit, rate, amount, gst_rate, gst_amount, total, description }) => ({
          product_name, qty, unit, rate, amount, gst_rate, gst_amount, total, description,
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
        remark,
        payment_status: paymentStatus,
        amount_paid: paymentStatus === "full" ? grandTotal : amountPaid,
        payment_screenshots: paymentScreenshots,
        mode_of_payment: modeOfPayment,
        payment_mode_details: paymentModeDetails,
        free_samples: freeSamples.filter(s => s.item_name),
        billing_address_id: billingAddress?.id || "",
        shipping_address_id: sameAsBilling ? (billingAddress?.id || "") : (shippingAddress?.id || ""),
        extra_shipping_details: extraShippingDetails,
      };
      const res = await api.post("/orders", payload);
      toast.success(`Order ${res.data.order_number} created!`);
      if (piId) {
        // Mark PI as converted
        await api.patch(`/proforma-invoices/${piId}/mark-converted`, { order_id: res.data.id }).catch(() => {});
      }
      navigate(`/orders/${res.data.id}`);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to create order"); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-4 sm:space-y-6 px-1 sm:px-0" data-testid="create-order-page">
      <div className="flex items-center gap-3">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
          {piConverting ? "Convert PI to Order" : "Create New Order"}
        </h1>
        {piConverting && <span className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded-full font-medium">From PI</span>}
      </div>

      {/* Customer Selection */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Customer</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {selectedCustomer ? (
            <div className="flex items-center justify-between p-3 rounded-lg bg-secondary">
              <div>
                <p className="font-medium">{selectedCustomer.name}</p>
                <p className="text-sm text-muted-foreground">
                  {selectedCustomer.phone_numbers?.join(", ")} {selectedCustomer.gst_no && `| GST: ${selectedCustomer.gst_no}`}
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={openEditCustomer} data-testid="edit-customer-btn"><Edit className="w-3 h-3 mr-1" /> Edit</Button>
                <Button variant="outline" size="sm" onClick={() => { setSelectedCustomer(null); setBillingAddress(null); setShippingAddress(null); }} data-testid="change-customer-btn">Change</Button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input placeholder="Search by name, phone, or GST..." className="pl-9" value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} data-testid="customer-search-input" />
                </div>
                <Button variant="outline" onClick={() => setShowNewCustomer(true)} data-testid="new-customer-btn"><UserPlus className="w-4 h-4 mr-2" /> New Customer</Button>
              </div>
              {customerSearch && (
                <div className="border rounded-lg max-h-48 overflow-y-auto">
                  {filteredCustomers.length === 0 ? (
                    <p className="p-3 text-sm text-muted-foreground">No customers found</p>
                  ) : filteredCustomers.map((c) => (
                    <button key={c.id} className="w-full text-left px-3 py-2 hover:bg-accent transition-colors border-b last:border-0"
                      onClick={() => { setSelectedCustomer(c); setCustomerSearch(""); }} data-testid={`select-customer-${c.id}`}>
                      <p className="text-sm font-medium">{c.name}</p>
                      <p className="text-xs text-muted-foreground">{c.phone_numbers?.join(", ")}</p>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Address Selection (only when customer selected) */}
      {selectedCustomer && (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Addresses</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <AddressSelector customerId={selectedCustomer.id} label="Billing Address" selectedAddress={billingAddress}
              onSelect={(a) => { setBillingAddress(a); if (sameAsBilling) setShippingAddress(a); }}
              onAddNew={() => { setAddressTarget("billing"); setNewAddr(emptyAddress()); setShowAddAddress(true); }} />
            <div className="flex items-center gap-2">
              <Checkbox id="sameAddr" checked={sameAsBilling} onCheckedChange={(v) => { setSameAsBilling(v); if (v) setShippingAddress(billingAddress); }}
                data-testid="same-as-billing-checkbox" />
              <Label htmlFor="sameAddr" className="cursor-pointer text-sm">Shipping same as Billing</Label>
            </div>
            {!sameAsBilling && (
              <AddressSelector customerId={selectedCustomer.id} label="Shipping Address" selectedAddress={shippingAddress}
                onSelect={(a) => setShippingAddress(a)}
                onAddNew={() => { setAddressTarget("shipping"); setNewAddr(emptyAddress()); setShowAddAddress(true); }} />
            )}
          </CardContent>
        </Card>
      )}

      {/* Purpose */}
      <Card>
        <CardContent className="pt-6">
          <Label>Purpose / Requirement</Label>
          <Textarea placeholder="Enter the purpose..." className="mt-2" value={purpose} onChange={(e) => setPurpose(e.target.value)} data-testid="order-purpose-input" />
        </CardContent>
      </Card>

      {/* GST Toggle */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-3">
            <Checkbox id="gst" checked={gstApplicable} onCheckedChange={setGstApplicable} data-testid="gst-applicable-checkbox" />
            <Label htmlFor="gst" className="cursor-pointer">GST Applicable</Label>
          </div>
        </CardContent>
      </Card>

      {/* Items */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Order Items</CardTitle>
            <Button variant="outline" size="sm" onClick={addItem} data-testid="add-item-btn"><Plus className="w-4 h-4 mr-1" /> Add Item</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {items.map((item, idx) => (
            <div key={idx} className="p-4 rounded-lg border bg-secondary/30 space-y-3" data-testid={`order-item-${idx}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-muted-foreground">Item {idx + 1}</span>
                {items.length > 1 && (
                  <Button variant="ghost" size="icon" onClick={() => removeItem(idx)} data-testid={`remove-item-${idx}`}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-6 gap-2 sm:gap-3">
                <div className="col-span-2">
                  <Label className="text-xs">Product Name</Label>
                  <Input value={item.product_name} onChange={(e) => updateItem(idx, "product_name", e.target.value)} placeholder="Product name" data-testid={`item-name-${idx}`} />
                </div>
                <div><Label className="text-xs">Qty</Label><Input type="number" value={item.qty || ""} onChange={(e) => updateItem(idx, "qty", +e.target.value)} data-testid={`item-qty-${idx}`} /></div>
                <div>
                  <Label className="text-xs">Unit</Label>
                  <Select value={item.unit} onValueChange={(v) => updateItem(idx, "unit", v)}>
                    <SelectTrigger data-testid={`item-unit-${idx}`}><SelectValue placeholder="Unit" /></SelectTrigger>
                    <SelectContent>{UNITS.map((u) => (<SelectItem key={u || "blank"} value={u || "blank"}>{u || "(none)"}</SelectItem>))}</SelectContent>
                  </Select>
                </div>
                <div><Label className="text-xs">Rate</Label><Input type="number" min={0} value={item.rate || ""} onChange={(e) => updateItem(idx, "rate", Math.max(0, +e.target.value))} data-testid={`item-rate-${idx}`} /></div>
                <div><Label className="text-xs">Amount</Label><Input type="number" min={0} value={item.amount || ""} onChange={(e) => updateItem(idx, "amount", Math.max(0, +e.target.value))} data-testid={`item-amount-${idx}`} /></div>
              </div>
              <div>
                <Label className="text-xs">Description (optional)</Label>
                <Input value={item.description} onChange={(e) => updateItem(idx, "description", e.target.value)} placeholder="Item description..." data-testid={`item-desc-${idx}`} />
              </div>
              {gstApplicable && (
                <div className="flex items-center gap-3">
                  <div className="w-32">
                    <Label className="text-xs">GST Rate</Label>
                    <Select value={String(item.gst_rate)} onValueChange={(v) => updateItem(idx, "gst_rate", +v)}>
                      <SelectTrigger data-testid={`item-gst-rate-${idx}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{GST_RATES.map((r) => (<SelectItem key={r} value={String(r)}>{r}%</SelectItem>))}</SelectContent>
                    </Select>
                  </div>
                  <div><Label className="text-xs">GST Amt</Label><p className="text-sm font-mono mt-1">{"\u20B9"}{item.gst_amount.toFixed(2)}</p></div>
                  <div><Label className="text-xs">Item Total</Label><p className="text-sm font-mono font-medium mt-1">{"\u20B9"}{item.total.toFixed(2)}</p></div>
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
            <Button variant="outline" size="sm" onClick={() => setFreeSamples(p => [...p, emptySample()])} data-testid="add-sample-btn"><Plus className="w-4 h-4 mr-1" /> Add Sample</Button>
          </div>
        </CardHeader>
        {freeSamples.length > 0 && (
          <CardContent className="space-y-3">
            {freeSamples.map((sample, idx) => (
              <div key={idx} className="flex gap-2 items-start" data-testid={`free-sample-${idx}`}>
                <div className="flex-1 grid grid-cols-2 gap-2">
                  <div><Label className="text-xs">Sample Item</Label><Input value={sample.item_name} onChange={e => { const s = [...freeSamples]; s[idx] = { ...s[idx], item_name: e.target.value }; setFreeSamples(s); }} placeholder="e.g. Citronella Oil Sample - 10ml" data-testid={`sample-name-${idx}`} /></div>
                  <div><Label className="text-xs">Description</Label><Input value={sample.description} onChange={e => { const s = [...freeSamples]; s[idx] = { ...s[idx], description: e.target.value }; setFreeSamples(s); }} placeholder="Additional details" data-testid={`sample-desc-${idx}`} /></div>
                </div>
                <Button variant="ghost" size="icon" className="mt-5" onClick={() => setFreeSamples(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>
              </div>
            ))}
          </CardContent>
        )}
      </Card>

      {/* Shipping */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Shipping Details</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>Shipping Method</Label>
              <Select value={shippingMethod} onValueChange={setShippingMethod}>
                <SelectTrigger data-testid="shipping-method-select"><SelectValue placeholder="Select method" /></SelectTrigger>
                <SelectContent>{SHIPPING_METHODS.map((m) => (<SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>))}</SelectContent>
              </Select>
            </div>
            {shippingMethod === "courier" && (
              <div>
                <Label>Courier *</Label>
                <Select value={courierName} onValueChange={setCourierName}>
                  <SelectTrigger data-testid="courier-name-select"><SelectValue placeholder="Select courier" /></SelectTrigger>
                  <SelectContent>{COURIER_OPTIONS.map((c) => (<SelectItem key={c} value={c}>{c}</SelectItem>))}</SelectContent>
                </Select>
              </div>
            )}
            {shippingMethod === "transport" && (
              <div>
                <Label>Transporter Name</Label>
                <Input value={transporterName} onChange={(e) => setTransporterName(e.target.value)} placeholder="Transporter name (optional)" data-testid="transporter-name-input" />
              </div>
            )}
          </div>
          <div>
            <Label>Extra Shipping Details <span className="text-xs text-muted-foreground">(Optional)</span></Label>
            <Input value={extraShippingDetails} onChange={e => setExtraShippingDetails(e.target.value)} placeholder="Driver contact, landmark, special notes..." data-testid="extra-shipping-details-input" />
          </div>
        </CardContent>
      </Card>

      {/* Additional Charges */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Charges</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {/* Shipping Charges */}
          <div>
            <Label>Shipping Charges</Label>
            <Input type="number" min={0} value={shippingCharge || ""} onChange={e => setShippingCharge(Math.max(0, +e.target.value))} placeholder="0" data-testid="shipping-charge-input" />
          </div>

          <Separator />

          {/* Additional Charges - Dynamic list */}
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">Additional Charges</Label>
            <Button variant="outline" size="sm" onClick={() => setAdditionalCharges(p => [...p, { name: "", amount: 0, gst_percent: 0 }])} data-testid="add-charge-btn"><Plus className="w-4 h-4 mr-1" /> Add Charge</Button>
          </div>
          {additionalCharges.length === 0 && <p className="text-sm text-muted-foreground">No additional charges. Add insurance, handling, or other charges.</p>}
          {additionalCharges.map((charge, idx) => (
            <div key={idx} className="flex gap-2 items-end" data-testid={`charge-${idx}`}>
              <div className="flex-1">
                <Label className="text-xs">Charge Name</Label>
                <Input value={charge.name} onChange={e => { const c = [...additionalCharges]; c[idx] = { ...c[idx], name: e.target.value }; setAdditionalCharges(c); }} placeholder="e.g. Insurance, Handling" data-testid={`charge-name-${idx}`} />
              </div>
              <div className="w-28">
                <Label className="text-xs">Amount</Label>
                <Input type="number" min={0} value={charge.amount || ""} onChange={e => { const c = [...additionalCharges]; c[idx] = { ...c[idx], amount: Math.max(0, +e.target.value) }; setAdditionalCharges(c); }} data-testid={`charge-amount-${idx}`} />
              </div>
              {gstApplicable && (
                <div className="w-24">
                  <Label className="text-xs">GST %</Label>
                  <Select value={String(charge.gst_percent || 0)} onValueChange={v => { const c = [...additionalCharges]; c[idx] = { ...c[idx], gst_percent: +v }; setAdditionalCharges(c); }}>
                    <SelectTrigger data-testid={`charge-gst-${idx}`}><SelectValue /></SelectTrigger>
                    <SelectContent>{GST_RATES.map(r => <SelectItem key={r} value={String(r)}>{r}%</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              )}
              <Button variant="ghost" size="icon" onClick={() => setAdditionalCharges(p => p.filter((_, i) => i !== idx))} data-testid={`remove-charge-${idx}`}><Trash2 className="w-4 h-4 text-destructive" /></Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Payment */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Payment</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>Payment Status</Label>
              <Select value={paymentStatus} onValueChange={setPaymentStatus}>
                <SelectTrigger data-testid="payment-status-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="unpaid">Unpaid</SelectItem>
                  <SelectItem value="partial">Partial Paid</SelectItem>
                  <SelectItem value="full">Full Paid</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Mode of Payment</Label>
              <Select value={modeOfPayment} onValueChange={setModeOfPayment}>
                <SelectTrigger data-testid="mode-of-payment-select"><SelectValue placeholder="Select mode" /></SelectTrigger>
                <SelectContent>{PAYMENT_MODES.map(m => (<SelectItem key={m} value={m}>{m}</SelectItem>))}</SelectContent>
              </Select>
            </div>
            {modeOfPayment === "Other" && (
              <div>
                <Label>Payment Details *</Label>
                <Input value={paymentModeDetails} onChange={e => setPaymentModeDetails(e.target.value)} placeholder="Specify payment details" data-testid="payment-mode-details-input" />
              </div>
            )}
          </div>
          {paymentStatus === "partial" && (
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Amount Paid</Label><Input type="number" value={amountPaid || ""} onChange={e => setAmountPaid(+e.target.value)} data-testid="amount-paid-input" /></div>
              <div><Label>Balance</Label><Input type="number" value={balanceAmount || ""} readOnly className="bg-muted" /></div>
            </div>
          )}
          <div>
            <Label>Payment Screenshots (optional)</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              <label className="cursor-pointer inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90">
                Gallery / Files
                <input type="file" multiple accept="image/*" onChange={handleScreenshotUpload} className="hidden" data-testid="payment-screenshot-input" />
              </label>
              <label className="cursor-pointer inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80">
                Camera
                <input type="file" accept="image/*" capture="environment" onChange={handleScreenshotUpload} className="hidden" data-testid="payment-screenshot-camera" />
              </label>
            </div>
            {paymentScreenshots.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {paymentScreenshots.map((url, i) => (
                  <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
                    <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt="" className="w-full h-full object-cover" />
                    <button className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity" onClick={() => setPaymentScreenshots(prev => prev.filter((_, j) => j !== i))}>
                      <span className="text-white text-xs">X</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Remark */}
      <Card>
        <CardContent className="pt-6">
          <Label>Remarks / Special Requests</Label>
          <Textarea placeholder="Any special instructions..." className="mt-2" value={remark} onChange={(e) => setRemark(e.target.value)} data-testid="order-remark-input" />
        </CardContent>
      </Card>

      {/* Summary */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Order Summary</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-mono">{"\u20B9"}{subtotal.toFixed(2)}</span></div>
            {gstApplicable && <div className="flex justify-between"><span className="text-muted-foreground">Item GST</span><span className="font-mono">{"\u20B9"}{totalItemGst.toFixed(2)}</span></div>}
            {shippingCharge > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping Charges</span><span className="font-mono">{"\u20B9"}{shippingCharge.toFixed(2)}</span></div>}
            {shippingGst > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping GST (18%)</span><span className="font-mono">{"\u20B9"}{shippingGst.toFixed(2)}</span></div>}
            {additionalCharges.filter(c => c.amount > 0).map((c, i) => (
              <div key={i}>
                <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"}</span><span className="font-mono">{"\u20B9"}{(c.amount || 0).toFixed(2)}</span></div>
                {gstApplicable && c.gst_percent > 0 && <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"} GST ({c.gst_percent}%)</span><span className="font-mono">{"\u20B9"}{((c.amount || 0) * c.gst_percent / 100).toFixed(2)}</span></div>}
              </div>
            ))}
            <Separator />
            <div className="flex justify-between text-base font-bold">
              <span>Grand Total (Rounded Up)</span><span className="font-mono">{"\u20B9"}{grandTotal}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={() => navigate(-1)} data-testid="cancel-order-btn">Cancel</Button>
        <Button onClick={handleSubmit} disabled={submitting} className="rounded-lg min-w-[140px]" data-testid="submit-order-btn">
          {submitting ? "Creating..." : piId ? "Convert to Order" : "Create Order"}
        </Button>
      </div>

      {/* New Customer Dialog */}
      <Dialog open={showNewCustomer} onOpenChange={setShowNewCustomer}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Customer</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2"><Label>Customer / Company Name *</Label><Input value={newCust.name} onChange={(e) => setNewCust({ ...newCust, name: e.target.value })} data-testid="new-cust-name" /></div>
              <div className="col-span-2">
                <Label>GST No.</Label>
                <div className="flex gap-2">
                  <Input value={newCust.gst_no} onChange={(e) => setNewCust({ ...newCust, gst_no: e.target.value.toUpperCase() })} placeholder="e.g. 27AABCU9603R1ZM" data-testid="new-cust-gst" />
                  <Button variant="outline" size="sm" onClick={() => verifyGst(newCust.gst_no)} disabled={gstLoading} data-testid="verify-gst-btn">{gstLoading ? "..." : "Verify"}</Button>
                </div>
              </div>
            </div>
            <Separator />
            <h4 className="text-sm font-semibold">Contact</h4>
            {newCust.phone_numbers.map((ph, i) => (
              <div key={i} className="flex gap-2">
                <div className="flex items-center gap-1 flex-1">
                  <span className="text-sm text-muted-foreground whitespace-nowrap">+91</span>
                  <Input value={ph} onChange={(e) => { const phones = [...newCust.phone_numbers]; phones[i] = e.target.value; setNewCust({ ...newCust, phone_numbers: phones }); }} placeholder="10-digit mobile number" data-testid={`new-cust-phone-${i}`} />
                </div>
                {i === newCust.phone_numbers.length - 1 && (
                  <Button variant="outline" size="icon" onClick={() => setNewCust({ ...newCust, phone_numbers: [...newCust.phone_numbers, ""] })}><Plus className="w-4 h-4" /></Button>
                )}
              </div>
            ))}
            <div><Label className="text-xs">Email (optional)</Label><Input type="email" value={newCust.email} onChange={(e) => setNewCust({ ...newCust, email: e.target.value })} data-testid="new-cust-email" /></div>
            <div><Label className="text-xs">Alias (optional)</Label><Input value={newCust.alias} onChange={(e) => setNewCust({ ...newCust, alias: e.target.value })} placeholder="Short name / nickname" data-testid="new-cust-alias" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewCustomer(false)}>Cancel</Button>
            <Button onClick={createCustomer} data-testid="save-customer-btn">Save Customer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Address Dialog */}
      <Dialog open={showAddAddress} onOpenChange={setShowAddAddress}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Add New Address</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Label (e.g. Office, Warehouse)</Label><Input value={newAddr.label} onChange={e => setNewAddr({ ...newAddr, label: e.target.value })} data-testid="addr-label" /></div>
            <div><Label>Address Line *</Label><Input value={newAddr.address_line} onChange={e => setNewAddr({ ...newAddr, address_line: e.target.value })} data-testid="addr-line" /></div>
            <div>
              <Label>Pincode *</Label>
              <Input value={newAddr.pincode} onChange={e => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                setNewAddr({ ...newAddr, pincode: v });
              }} placeholder="6-digit pincode" maxLength={6} data-testid="addr-pincode" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>City *</Label><Input value={newAddr.city} onChange={e => setNewAddr({ ...newAddr, city: e.target.value })} data-testid="addr-city" /></div>
              <div>
                <Label>State *</Label>
                <div className="relative">
                  <Input value={newAddr.state} onChange={e => { setNewAddr({ ...newAddr, state: e.target.value }); setStateSearch(e.target.value); }}
                    placeholder="Type to search..." data-testid="addr-state" autoComplete="off" />
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
            <Button onClick={saveNewAddress} data-testid="save-address-btn">Save Address</Button>
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
                  <Input value={ph} onChange={e => { const phones = [...editCustData.phone_numbers]; phones[i] = e.target.value; setEditCustData({ ...editCustData, phone_numbers: phones }); }} placeholder="10-digit mobile number" data-testid={`edit-cust-phone-${i}`} />
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
