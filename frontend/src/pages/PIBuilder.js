import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Plus, Trash2, Search, UserPlus, Download, MapPin, FileText, ArrowRight, Share2, Copy, Edit } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Link } from "react-router-dom";
import { INDIAN_STATES } from "@/lib/indianStates";
import { useAuth } from "@/contexts/AuthContext";

const UNITS = ["mL", "L", "g", "Kg", "pcs", ""];
const GST_RATES = [0, 5, 18];

const emptyItem = () => ({ product_name: "", qty: 0, unit: "", rate: 0, amount: 0, gst_rate: 0, gst_amount: 0, total: 0, description: "" });
const emptyAddress = () => ({ address_line: "", city: "", state: "", pincode: "", label: "", address_name: "" });
const emptySample = () => ({ item_name: "", description: "" });

function AddressSelector({ customerId, label, selectedAddress, onSelect, onAddNew }) {
  const [addresses, setAddresses] = useState([]);
  const [showPicker, setShowPicker] = useState(false);
  useEffect(() => {
    if (customerId) api.get(`/customers/${customerId}/addresses`).then(r => setAddresses(r.data)).catch(() => {});
  }, [customerId]);
  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium">{label}</Label>
      {selectedAddress ? (
        <div className="flex items-start justify-between p-3 rounded-lg bg-secondary text-sm" data-testid={`pi-selected-${label.toLowerCase().replace(/\s/g, '-')}`}>
          <div>
            {selectedAddress.label && <span className="text-xs font-medium text-primary mr-2">[{selectedAddress.label}]</span>}
            <span>{selectedAddress.address_name ? `${selectedAddress.address_name} – ` : ""}{selectedAddress.address_line}, {selectedAddress.city}, {selectedAddress.state} - {selectedAddress.pincode}</span>
          </div>
          <Button variant="outline" size="sm" onClick={() => setShowPicker(true)}>Change</Button>
        </div>
      ) : (
        <Button variant="outline" className="w-full justify-start text-muted-foreground" onClick={() => setShowPicker(true)} data-testid={`pi-select-${label.toLowerCase().replace(/\s/g, '-')}`}>
          <MapPin className="w-4 h-4 mr-2" /> Select {label}
        </Button>
      )}
      <Dialog open={showPicker} onOpenChange={setShowPicker}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Select {label}</DialogTitle></DialogHeader>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {addresses.length === 0 ? <p className="text-sm text-muted-foreground py-4 text-center">No saved addresses.</p> :
              addresses.map(a => (
                <button key={a.id} className="w-full text-left p-3 rounded-lg border hover:bg-accent transition-colors" onClick={() => { onSelect(a); setShowPicker(false); }}>
                  {a.label && <span className="text-xs font-medium text-primary mr-2">[{a.label}]</span>}
                  <span className="text-sm">{a.address_name ? `${a.address_name} – ` : ""}{a.address_line}, {a.city}, {a.state} - {a.pincode}</span>
                </button>
              ))
            }
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

export default function PIBuilder() {
  const { user } = useAuth();
  const [piList, setPiList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showBuilder, setShowBuilder] = useState(false);
  const [editingPi, setEditingPi] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [items, setItems] = useState([emptyItem()]);
  const [gstApplicable, setGstApplicable] = useState(false);
  const [showRate, setShowRate] = useState(true);
  const [shippingCharge, setShippingCharge] = useState(0);
  const [additionalCharges, setAdditionalCharges] = useState([]);
  const [remark, setRemark] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [freeSamples, setFreeSamples] = useState([]);
  const [billingAddress, setBillingAddress] = useState(null);
  const [shippingAddress, setShippingAddress] = useState(null);
  const [sameAsBilling, setSameAsBilling] = useState(true);
  const [showAddAddress, setShowAddAddress] = useState(false);
  const [addressTarget, setAddressTarget] = useState("billing");
  const [newAddr, setNewAddr] = useState(emptyAddress());
  const [pincodeLoading, setPincodeLoading] = useState(false);
  const [stateSearch, setStateSearch] = useState("");
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCust, setNewCust] = useState({ name: "", gst_no: "", phone_numbers: [""], email: "" });
  const [sharing, setSharing] = useState({});
  const [showEditCustomer, setShowEditCustomer] = useState(false);
  const [editCustData, setEditCustData] = useState({ name: "", gst_no: "", phone_numbers: [""], email: "", alias: "" });
  const [piSearch, setPiSearch] = useState("");

  const canShare = ["admin", "telecaller"].includes(user?.role);

  useEffect(() => { loadPIs(); loadCustomers(); }, []);

  const loadPIs = async () => {
    try { const res = await api.get("/proforma-invoices"); setPiList(res.data); }
    catch { } finally { setLoading(false); }
  };

  const loadCustomers = async () => {
    try { const res = await api.get("/customers"); setCustomers(res.data); } catch { }
  };

  const filteredCustomers = customers.filter(c =>
    c.name?.toLowerCase().includes(customerSearch.toLowerCase()) ||
    c.phone_numbers?.some(p => p.includes(customerSearch)) ||
    c.gst_no?.toLowerCase().includes(customerSearch.toLowerCase()) ||
    c.alias?.toLowerCase().includes(customerSearch.toLowerCase())
  );

  const createCustomer = async () => {
    if (!newCust.name) return toast.error("Name required");
    const phones = newCust.phone_numbers.filter(Boolean);
    if (phones.length === 0) return toast.error("Phone number required");
    try {
      const res = await api.post("/customers", { ...newCust, phone_numbers: phones });
      setSelectedCustomer(res.data);
      setCustomers(prev => [res.data, ...prev]);
      setShowNewCustomer(false);
      toast.success("Customer created");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const openEditCustomer = () => {
    setEditCustData({
      name: selectedCustomer.name || "", gst_no: selectedCustomer.gst_no || "",
      phone_numbers: selectedCustomer.phone_numbers?.length ? [...selectedCustomer.phone_numbers] : [""],
      email: selectedCustomer.email || "", alias: selectedCustomer.alias || "",
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
  const totalGst = items.reduce((s, i) => s + i.gst_amount, 0);
  const shippingGst = gstApplicable && shippingCharge > 0 ? +(shippingCharge * 0.18).toFixed(2) : 0;
  const totalAdditional = additionalCharges.reduce((s, c) => s + (c.amount || 0), 0);
  const totalAdditionalGst = additionalCharges.reduce((s, c) => {
    if (gstApplicable && c.gst_percent > 0) return s + +((c.amount || 0) * c.gst_percent / 100).toFixed(2);
    return s;
  }, 0);
  const grandTotal = Math.ceil(subtotal + totalGst + shippingCharge + shippingGst + totalAdditional + totalAdditionalGst);

  const saveNewAddress = async () => {
    if (!newAddr.address_line || !newAddr.city || !newAddr.state || !newAddr.pincode) return toast.error("All address fields required");
    if (!/^\d{6}$/.test(newAddr.pincode)) return toast.error("Pincode must be 6 digits");
    if (!INDIAN_STATES.includes(newAddr.state)) return toast.error("Please select a valid State/UT from the dropdown");
    try {
      const res = await api.post(`/customers/${selectedCustomer.id}/addresses`, newAddr);
      if (addressTarget === "billing") { setBillingAddress(res.data); if (sameAsBilling) setShippingAddress(res.data); }
      else setShippingAddress(res.data);
      setShowAddAddress(false); setNewAddr(emptyAddress()); toast.success("Address saved");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const openNewPI = () => {
    setEditingPi(null); setSelectedCustomer(null); setCustomerSearch(""); setItems([emptyItem()]);
    setGstApplicable(false); setShowRate(true); setShippingCharge(0); setAdditionalCharges([]); setRemark("");
    setBillingAddress(null); setShippingAddress(null); setSameAsBilling(true); setFreeSamples([]);
    setShowBuilder(true);
  };

  const openEditPI = (pi) => {
    setEditingPi(pi);
    const cust = customers.find(c => c.id === pi.customer_id);
    setSelectedCustomer(cust || { id: pi.customer_id, name: pi.customer_name });
    setItems(pi.items.length ? pi.items.map(i => ({ ...i })) : [emptyItem()]);
    setGstApplicable(pi.gst_applicable); setShowRate(pi.show_rate !== false);
    setShippingCharge(pi.shipping_charge || 0);
    const allCharges = pi.additional_charges || [];
    setAdditionalCharges(allCharges.filter(c => c.name !== "Local Charges"));
    setRemark(pi.remark || "");
    setBillingAddress(pi.billing_address || null); setShippingAddress(pi.shipping_address || null);
    setSameAsBilling(pi.billing_address_id === pi.shipping_address_id);
    setFreeSamples(pi.free_samples || []);
    setShowBuilder(true);
  };

  const handleSubmit = async () => {
    if (!selectedCustomer) return toast.error("Select a customer");
    if (items.some(i => !i.product_name)) return toast.error("All items need a product name");
    setSubmitting(true);
    try {
      const payload = {
        customer_id: selectedCustomer.id,
        items: items.map(({ product_name, qty, unit, rate, amount, gst_rate, gst_amount, total, description }) => ({
          product_name, qty, unit, rate, amount, gst_rate, gst_amount, total, description
        })),
        gst_applicable: gstApplicable, show_rate: showRate, shipping_charge: shippingCharge,
        additional_charges: [
          ...additionalCharges.filter(c => c.name).map(c => ({
            name: c.name, amount: Math.max(0, c.amount || 0), gst_percent: c.gst_percent || 0,
            gst_amount: gstApplicable && c.gst_percent > 0 ? +((c.amount || 0) * c.gst_percent / 100).toFixed(2) : 0,
          })),
        ],
        remark,
        free_samples: freeSamples.filter(s => s.item_name),
        billing_address_id: billingAddress?.id || "",
        shipping_address_id: sameAsBilling ? (billingAddress?.id || "") : (shippingAddress?.id || ""),
      };
      if (editingPi) { await api.put(`/proforma-invoices/${editingPi.id}`, payload); toast.success("PI updated"); }
      else { await api.post("/proforma-invoices", payload); toast.success("PI created"); }
      setShowBuilder(false); loadPIs();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSubmitting(false); }
  };

  const downloadPI = (pi) => {
    const token = localStorage.getItem("token");
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/proforma-invoices/${pi.id}/pdf?token=${token}`, "_blank");
  };

  const deletePI = async (pi) => {
    try { await api.delete(`/proforma-invoices/${pi.id}`); toast.success("PI deleted"); loadPIs(); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const sharePI = async (pi) => {
    setSharing(p => ({ ...p, [pi.id]: true }));
    try {
      const token = localStorage.getItem("token");
      const pdfUrl = `${process.env.REACT_APP_BACKEND_URL}/api/proforma-invoices/${pi.id}/pdf?token=${token}`;
      const response = await fetch(pdfUrl);
      if (!response.ok) throw new Error("Failed to fetch PDF");
      const blob = await response.blob();
      const fileName = `${pi.pi_number}.pdf`;
      const file = new File([blob], fileName, { type: "application/pdf" });

      // Get customer phone for WhatsApp
      const cust = customers.find(c => c.id === pi.customer_id);
      const phone = cust?.phone_numbers?.[0]?.replace(/[^0-9]/g, "") || "";
      const waPhone = phone.startsWith("91") ? phone : `91${phone}`;

      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: `Proforma Invoice - ${pi.pi_number}` });
      } else {
        // Desktop fallback: download file + open WhatsApp
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success("PDF downloaded. Opening WhatsApp...");
        if (phone) {
          setTimeout(() => window.open(`https://wa.me/${waPhone}`, "_blank"), 500);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") toast.error("Share failed");
    } finally {
      setSharing(p => ({ ...p, [pi.id]: false }));
    }
  };

  return (
    <div className="space-y-6" data-testid="pi-builder-page">
      <div className="flex items-center justify-between">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Proforma Invoices</h1>
        <Button onClick={openNewPI} className="rounded-lg" data-testid="create-pi-btn"><Plus className="w-4 h-4 mr-2" /> New PI</Button>
      </div>

      {/* PI List */}
      {!showBuilder && (
        <Card>
          <CardContent className="pt-6">
            {piList.length > 0 && (
              <div className="mb-4 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input placeholder="Search by PI number, customer, phone, GST..." className="pl-9 max-w-sm" value={piSearch} onChange={e => setPiSearch(e.target.value)} data-testid="pi-list-search" />
              </div>
            )}
            {loading ? <p className="text-center py-8 text-muted-foreground">Loading...</p> :
             piList.length === 0 ? <p className="text-center py-8 text-muted-foreground">No proforma invoices yet.</p> : (() => {
              const q = piSearch.toLowerCase();
              const filtered = q ? piList.filter(pi =>
                pi.pi_number?.toLowerCase().includes(q) ||
                pi.customer_name?.toLowerCase().includes(q) ||
                pi.customer_phone?.some?.(p => p.includes(q)) ||
                pi.customer_gst?.toLowerCase().includes(q) ||
                pi.customer_alias?.toLowerCase().includes(q)
              ) : piList;
              return filtered.length === 0 ? <p className="text-center py-8 text-muted-foreground">No results for "{piSearch}"</p> : (
              <Table className="min-w-[600px]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs whitespace-nowrap">PI No</TableHead>
                    <TableHead className="text-xs whitespace-nowrap">Customer</TableHead>
                    <TableHead className="text-xs text-right whitespace-nowrap">Amount</TableHead>
                    <TableHead className="text-xs whitespace-nowrap">Date</TableHead>
                    <TableHead className="text-xs whitespace-nowrap">Status</TableHead>
                    {user?.role === "admin" && <TableHead className="text-xs whitespace-nowrap">Created By</TableHead>}
                    <TableHead className="text-xs whitespace-nowrap">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map(pi => (
                    <TableRow key={pi.id} data-testid={`pi-row-${pi.id}`}>
                      <TableCell className="font-mono text-sm font-medium">{pi.pi_number}</TableCell>
                      <TableCell className="text-sm">{pi.customer_name}{pi.customer_alias ? <span className="text-xs text-muted-foreground ml-1">({pi.customer_alias})</span> : ""}</TableCell>
                      <TableCell className="text-sm text-right font-mono">{"\u20B9"}{pi.grand_total}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{new Date(pi.created_at).toLocaleDateString("en-IN")}</TableCell>
                      <TableCell><Badge variant="secondary" className="text-xs">{pi.status}</Badge></TableCell>
                      {user?.role === "admin" && <TableCell className="text-sm whitespace-nowrap">{pi.created_by_name || "-"}</TableCell>}
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" onClick={() => downloadPI(pi)} title="Download PDF" data-testid={`download-pi-${pi.id}`}><Download className="w-4 h-4" /></Button>
                          {canShare && (
                            <Button variant="ghost" size="icon" onClick={() => sharePI(pi)} title="Share via WhatsApp" disabled={sharing[pi.id]} data-testid={`share-pi-${pi.id}`}>
                              <Share2 className={`w-4 h-4 ${sharing[pi.id] ? "animate-pulse" : "text-green-600"}`} />
                            </Button>
                          )}
                          <Button variant="ghost" size="icon" onClick={() => openEditPI(pi)} title="Edit" data-testid={`edit-pi-${pi.id}`}><FileText className="w-4 h-4" /></Button>
                          <Button variant="ghost" size="icon" onClick={() => {
                            api.post(`/proforma-invoices/${pi.id}/duplicate`).then(r => {
                              const d = r.data;
                              const cust = customers.find(c => c.id === d.customer_id);
                              setEditingPi(null);
                              setSelectedCustomer(cust || { id: d.customer_id, name: d.customer_name });
                              setItems(d.items?.length ? d.items.map(i => ({ ...i })) : [emptyItem()]);
                              setGstApplicable(d.gst_applicable); setShowRate(d.show_rate !== false);
                              setShippingCharge(d.shipping_charge || 0);
                              const dupCharges = d.additional_charges || [];
                              setAdditionalCharges(dupCharges.filter(c => c.name !== "Local Charges"));
                              setRemark(d.remark || "");
                              setBillingAddress(d.billing_address || null);
                              setShippingAddress(d.shipping_address || null);
                              setSameAsBilling(d.billing_address_id === d.shipping_address_id);
                              setFreeSamples(d.free_samples || []);
                              setShowBuilder(true);
                              toast.success("PI duplicated - edit and save as new");
                            }).catch(() => toast.error("Failed to duplicate PI"));
                          }} title="Duplicate" data-testid={`duplicate-pi-${pi.id}`}><Copy className="w-4 h-4" /></Button>
                          {pi.status === "draft" && (
                            <Link to={`/pi/${pi.id}/convert`}>
                              <Button variant="ghost" size="icon" title="Convert to Order"><ArrowRight className="w-4 h-4" /></Button>
                            </Link>
                          )}
                          <Button variant="ghost" size="icon" onClick={() => deletePI(pi)} title="Delete" data-testid={`delete-pi-${pi.id}`}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ); })()}
          </CardContent>
        </Card>
      )}

      {/* PI Builder */}
      {showBuilder && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Customer</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {selectedCustomer ? (
                <div className="flex items-center justify-between p-3 rounded-lg bg-secondary">
                  <div>
                    <p className="font-medium">{selectedCustomer.name}</p>
                    <p className="text-sm text-muted-foreground">{selectedCustomer.phone_numbers?.join(", ")}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={openEditCustomer} data-testid="pi-edit-customer-btn"><Edit className="w-3 h-3 mr-1" /> Edit</Button>
                    <Button variant="outline" size="sm" onClick={() => { setSelectedCustomer(null); setBillingAddress(null); setShippingAddress(null); }}>Change</Button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input placeholder="Search customers..." className="pl-9" value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} data-testid="pi-customer-search" />
                    </div>
                    <Button variant="outline" onClick={() => setShowNewCustomer(true)} data-testid="pi-new-customer-btn"><UserPlus className="w-4 h-4 mr-2" /> New</Button>
                  </div>
                  {customerSearch && (
                    <div className="border rounded-lg max-h-48 overflow-y-auto">
                      {filteredCustomers.length === 0 ? <p className="p-3 text-sm text-muted-foreground">No customers found</p> :
                        filteredCustomers.map(c => (
                          <button key={c.id} className="w-full text-left px-3 py-2 hover:bg-accent transition-colors border-b last:border-0"
                            onClick={() => { setSelectedCustomer(c); setCustomerSearch(""); }}>
                            <p className="text-sm font-medium">{c.name}</p>
                            <p className="text-xs text-muted-foreground">{c.phone_numbers?.join(", ")}</p>
                          </button>
                        ))
                      }
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* Addresses */}
          {selectedCustomer && (
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">Addresses</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <AddressSelector customerId={selectedCustomer.id} label="Billing Address" selectedAddress={billingAddress}
                  onSelect={(a) => { setBillingAddress(a); if (sameAsBilling) setShippingAddress(a); }}
                  onAddNew={() => { setAddressTarget("billing"); setNewAddr(emptyAddress()); setShowAddAddress(true); }} />
                <div className="flex items-center gap-2">
                  <Checkbox id="piSameAddr" checked={sameAsBilling} onCheckedChange={(v) => { setSameAsBilling(v); if (v) setShippingAddress(billingAddress); }} />
                  <Label htmlFor="piSameAddr" className="cursor-pointer text-sm">Shipping same as Billing</Label>
                </div>
                {!sameAsBilling && (
                  <AddressSelector customerId={selectedCustomer.id} label="Shipping Address" selectedAddress={shippingAddress}
                    onSelect={(a) => setShippingAddress(a)}
                    onAddNew={() => { setAddressTarget("shipping"); setNewAddr(emptyAddress()); setShowAddAddress(true); }} />
                )}
              </CardContent>
            </Card>
          )}

          {/* Options */}
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div className="flex flex-wrap gap-6">
                <div className="flex items-center gap-2">
                  <Checkbox id="piGst" checked={gstApplicable} onCheckedChange={setGstApplicable} data-testid="pi-gst-checkbox" />
                  <Label htmlFor="piGst" className="cursor-pointer">GST Applicable</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox id="piRate" checked={showRate} onCheckedChange={setShowRate} />
                  <Label htmlFor="piRate" className="cursor-pointer">Show Rate in PDF</Label>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Items */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Items</CardTitle>
                <Button variant="outline" size="sm" onClick={() => setItems(p => [...p, emptyItem()])} data-testid="pi-add-item-btn"><Plus className="w-4 h-4 mr-1" /> Add</Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {items.map((item, idx) => (
                <div key={idx} className="p-3 rounded-lg border bg-secondary/30 space-y-2" data-testid={`pi-item-${idx}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">Item {idx + 1}</span>
                    {items.length > 1 && <Button variant="ghost" size="icon" onClick={() => setItems(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                    <div className="col-span-2"><Label className="text-xs">Product</Label><Input value={item.product_name} onChange={e => updateItem(idx, "product_name", e.target.value)} data-testid={`pi-item-name-${idx}`} /></div>
                    <div><Label className="text-xs">Qty</Label><Input type="number" value={item.qty || ""} onChange={e => updateItem(idx, "qty", +e.target.value)} /></div>
                    <div><Label className="text-xs">Unit</Label>
                      <Select value={item.unit} onValueChange={v => updateItem(idx, "unit", v)}>
                        <SelectTrigger><SelectValue placeholder="Unit" /></SelectTrigger>
                        <SelectContent>{UNITS.map(u => <SelectItem key={u || "blank"} value={u || "blank"}>{u || "(none)"}</SelectItem>)}</SelectContent>
                      </Select>
                    </div>
                    <div><Label className="text-xs">Rate</Label><Input type="number" min={0} value={item.rate || ""} onChange={e => updateItem(idx, "rate", Math.max(0, +e.target.value))} /></div>
                    <div><Label className="text-xs">Amount</Label><Input type="number" min={0} value={item.amount || ""} onChange={e => updateItem(idx, "amount", Math.max(0, +e.target.value))} /></div>
                  </div>
                  <div><Label className="text-xs">Description (optional)</Label><Input value={item.description || ""} onChange={e => updateItem(idx, "description", e.target.value)} placeholder="Item description..." /></div>
                  {gstApplicable && (
                    <div className="flex items-center gap-3">
                      <div className="w-24"><Label className="text-xs">GST%</Label>
                        <Select value={String(item.gst_rate)} onValueChange={v => updateItem(idx, "gst_rate", +v)}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>{GST_RATES.map(r => <SelectItem key={r} value={String(r)}>{r}%</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                      <div><Label className="text-xs">GST Amt</Label><p className="text-sm font-mono mt-1">{"\u20B9"}{item.gst_amount.toFixed(2)}</p></div>
                      <div><Label className="text-xs">Total</Label><p className="text-sm font-mono font-medium mt-1">{"\u20B9"}{item.total.toFixed(2)}</p></div>
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
                <Button variant="outline" size="sm" onClick={() => setFreeSamples(p => [...p, emptySample()])} data-testid="pi-add-sample-btn"><Plus className="w-4 h-4 mr-1" /> Add Sample</Button>
              </div>
            </CardHeader>
            {freeSamples.length > 0 && (
              <CardContent className="space-y-3">
                {freeSamples.map((sample, idx) => (
                  <div key={idx} className="flex gap-2 items-start" data-testid={`pi-sample-${idx}`}>
                    <div className="flex-1 grid grid-cols-2 gap-2">
                      <div><Label className="text-xs">Sample Item</Label><Input value={sample.item_name} onChange={e => { const s = [...freeSamples]; s[idx] = { ...s[idx], item_name: e.target.value }; setFreeSamples(s); }} placeholder="e.g. Citronella Oil Sample - 10ml" data-testid={`pi-sample-name-${idx}`} /></div>
                      <div><Label className="text-xs">Description</Label><Input value={sample.description} onChange={e => { const s = [...freeSamples]; s[idx] = { ...s[idx], description: e.target.value }; setFreeSamples(s); }} placeholder="Additional details" /></div>
                    </div>
                    <Button variant="ghost" size="icon" className="mt-5" onClick={() => setFreeSamples(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                  </div>
                ))}
              </CardContent>
            )}
          </Card>

          {/* Charges */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Charges</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Shipping Charges</Label>
                <Input type="number" min={0} value={shippingCharge || ""} onChange={e => setShippingCharge(Math.max(0, +e.target.value))} placeholder="0" data-testid="pi-shipping-charge-input" />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Additional Charges</Label>
                <Button variant="outline" size="sm" onClick={() => setAdditionalCharges(p => [...p, { name: "", amount: 0, gst_percent: 0 }])} data-testid="pi-add-charge-btn"><Plus className="w-4 h-4 mr-1" /> Add Charge</Button>
              </div>
              {additionalCharges.length === 0 && <p className="text-sm text-muted-foreground">No additional charges. Add insurance, handling, or other charges.</p>}
              {additionalCharges.map((charge, idx) => (
                <div key={idx} className="flex gap-2 items-end" data-testid={`pi-charge-${idx}`}>
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

          {/* Remark */}
          <Card>
            <CardContent className="pt-6 space-y-4">
              <div><Label>Remarks</Label><Textarea value={remark} onChange={e => setRemark(e.target.value)} /></div>
            </CardContent>
          </Card>

          {/* Summary */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Summary</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-mono">{"\u20B9"}{subtotal.toFixed(2)}</span></div>
                {gstApplicable && <div className="flex justify-between"><span className="text-muted-foreground">GST</span><span className="font-mono">{"\u20B9"}{totalGst.toFixed(2)}</span></div>}
                {shippingCharge > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping Charges</span><span className="font-mono">{"\u20B9"}{shippingCharge.toFixed(2)}</span></div>}
                {shippingGst > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping GST (18%)</span><span className="font-mono">{"\u20B9"}{shippingGst.toFixed(2)}</span></div>}
                {additionalCharges.filter(c => c.amount > 0).map((c, i) => (
                  <div key={i}>
                    <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"}</span><span className="font-mono">{"\u20B9"}{(c.amount || 0).toFixed(2)}</span></div>
                    {gstApplicable && c.gst_percent > 0 && <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"} GST ({c.gst_percent}%)</span><span className="font-mono">{"\u20B9"}{((c.amount || 0) * c.gst_percent / 100).toFixed(2)}</span></div>}
                  </div>
                ))}
                <Separator />
                <div className="flex justify-between text-base font-bold"><span>Grand Total (Rounded Up)</span><span className="font-mono">{"\u20B9"}{grandTotal}</span></div>
              </div>
            </CardContent>
          </Card>

          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={() => setShowBuilder(false)}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={submitting} className="min-w-[140px]" data-testid="save-pi-btn">
              {submitting ? "Saving..." : editingPi ? "Update PI" : "Create PI"}
            </Button>
          </div>
        </div>
      )}

      {/* New Customer Dialog */}
      <Dialog open={showNewCustomer} onOpenChange={setShowNewCustomer}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>New Customer</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Name *</Label><Input value={newCust.name} onChange={e => setNewCust({ ...newCust, name: e.target.value })} data-testid="pi-new-cust-name" /></div>
            <div><Label>GST No.</Label><Input value={newCust.gst_no} onChange={e => setNewCust({ ...newCust, gst_no: e.target.value.toUpperCase() })} /></div>
            {newCust.phone_numbers.map((ph, i) => (
              <div key={i} className="flex gap-2">
                <div className="flex items-center gap-1 flex-1">
                  <span className="text-sm text-muted-foreground">+91</span>
                  <Input value={ph} onChange={e => { const phones = [...newCust.phone_numbers]; phones[i] = e.target.value; setNewCust({ ...newCust, phone_numbers: phones }); }} placeholder="10-digit number" />
                </div>
                {i === newCust.phone_numbers.length - 1 && <Button variant="outline" size="icon" onClick={() => setNewCust({ ...newCust, phone_numbers: [...newCust.phone_numbers, ""] })}>+</Button>}
              </div>
            ))}
            <div><Label>Email (optional)</Label><Input type="email" value={newCust.email} onChange={e => setNewCust({ ...newCust, email: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewCustomer(false)}>Cancel</Button>
            <Button onClick={createCustomer} data-testid="pi-save-customer-btn">Save Customer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Address Dialog */}
      <Dialog open={showAddAddress} onOpenChange={setShowAddAddress}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Add New Address</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Label</Label><Input value={newAddr.label} onChange={e => setNewAddr({ ...newAddr, label: e.target.value })} placeholder="e.g. Office" /></div>
            <div><Label>Address Name (Recipient)</Label><Input value={newAddr.address_name} onChange={e => setNewAddr({ ...newAddr, address_name: e.target.value })} placeholder={selectedCustomer?.name || "Defaults to customer name"} /></div>
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
              <div className="col-span-2"><Label>GST No.</Label><Input value={editCustData.gst_no} onChange={e => setEditCustData({ ...editCustData, gst_no: e.target.value.toUpperCase() })} placeholder="e.g. 27AABCU9603R1ZM" data-testid="edit-cust-gst" /></div>
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
