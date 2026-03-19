import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api, { API_BASE } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Plus, Trash2, Search, FileText, Download, ArrowRight, UserPlus, Eye } from "lucide-react";

const UNITS = ["mL", "L", "g", "Kg", "pcs", ""];
const GST_RATES = [0, 5, 18];
const emptyItem = () => ({ product_name: "", qty: 0, unit: "", rate: 0, amount: 0, gst_rate: 0, gst_amount: 0, total: 0 });

export default function PIBuilder() {
  const navigate = useNavigate();
  const [pis, setPis] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("list");

  // Form state
  const [customers, setCustomers] = useState([]);
  const [customerSearch, setCustomerSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [items, setItems] = useState([emptyItem()]);
  const [gstApplicable, setGstApplicable] = useState(false);
  const [showRate, setShowRate] = useState(true);
  const [shippingCharge, setShippingCharge] = useState(0);
  const [remark, setRemark] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editingPi, setEditingPi] = useState(null);

  // Convert dialog
  const [showConvert, setShowConvert] = useState(false);
  const [convertPi, setConvertPi] = useState(null);
  const [convertData, setConvertData] = useState({ shipping_method: "", courier_name: "", purpose: "", payment_status: "unpaid", amount_paid: 0 });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [pisRes, custRes] = await Promise.all([api.get("/proforma-invoices"), api.get("/customers")]);
      setPis(pisRes.data);
      setCustomers(custRes.data);
    } catch {} finally { setLoading(false); }
  };

  const filteredCustomers = customers.filter(c =>
    c.name?.toLowerCase().includes(customerSearch.toLowerCase()) ||
    c.phone_numbers?.some(p => p.includes(customerSearch))
  );

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
  const grandTotal = +(subtotal + totalGst + shippingCharge + shippingGst).toFixed(2);

  const resetForm = () => {
    setSelectedCustomer(null); setItems([emptyItem()]); setGstApplicable(false);
    setShowRate(true); setShippingCharge(0); setRemark(""); setEditingPi(null); setCustomerSearch("");
  };

  const handleSubmit = async () => {
    if (!selectedCustomer) return toast.error("Select a customer");
    if (items.some(i => !i.product_name)) return toast.error("All items need a product name");
    setSubmitting(true);
    try {
      const payload = { customer_id: selectedCustomer.id, items, gst_applicable: gstApplicable, show_rate: showRate, shipping_charge: shippingCharge, remark };
      if (editingPi) {
        await api.put(`/proforma-invoices/${editingPi.id}`, payload);
        toast.success("PI updated");
      } else {
        await api.post("/proforma-invoices", payload);
        toast.success("PI created");
      }
      resetForm(); setTab("list"); loadData();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSubmitting(false); }
  };

  const editPi = (pi) => {
    setEditingPi(pi);
    const cust = customers.find(c => c.id === pi.customer_id);
    setSelectedCustomer(cust || { id: pi.customer_id, name: pi.customer_name });
    setItems(pi.items.map(i => ({ ...i })));
    setGstApplicable(pi.gst_applicable);
    setShowRate(pi.show_rate);
    setShippingCharge(pi.shipping_charge);
    setRemark(pi.remark || "");
    setTab("create");
  };

  const downloadPdf = async (piId) => {
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/proforma-invoices/${piId}/pdf`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `PI.pdf`; a.click();
      window.URL.revokeObjectURL(url);
    } catch { toast.error("Failed to download PDF"); }
  };

  const startConvert = (pi) => { setConvertPi(pi); setConvertData({ shipping_method: "", courier_name: "", purpose: "", payment_status: "unpaid", amount_paid: 0 }); setShowConvert(true); };

  const handleConvert = async () => {
    if (!convertPi) return;
    try {
      const res = await api.post(`/proforma-invoices/${convertPi.id}/convert`, convertData);
      toast.success(`Order ${res.data.order_number} created from PI`);
      setShowConvert(false); loadData();
      navigate(`/orders/${res.data.id}`);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const STATUS_COLORS = { draft: "status-new", sent: "status-packaging", converted: "status-dispatched" };

  return (
    <div className="space-y-6" data-testid="pi-builder">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Proforma Invoices</h1>
        <Button onClick={() => { resetForm(); setTab("create"); }} className="rounded-lg" data-testid="new-pi-btn">
          <Plus className="w-4 h-4 mr-2" /> New PI
        </Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList><TabsTrigger value="list">All PIs</TabsTrigger><TabsTrigger value="create">{editingPi ? "Edit PI" : "Create PI"}</TabsTrigger></TabsList>

        <TabsContent value="list">
          <Card>
            <CardContent className="pt-6">
              {loading ? <p className="text-center py-8 text-muted-foreground">Loading...</p> : pis.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground"><FileText className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No proforma invoices yet</p></div>
              ) : (
                <Table>
                  <TableHeader><TableRow>
                    <TableHead className="text-xs uppercase">PI #</TableHead><TableHead className="text-xs uppercase">Customer</TableHead>
                    <TableHead className="text-xs uppercase">Items</TableHead><TableHead className="text-xs uppercase">Total</TableHead>
                    <TableHead className="text-xs uppercase">GST</TableHead><TableHead className="text-xs uppercase">Status</TableHead>
                    <TableHead className="text-xs uppercase">Date</TableHead><TableHead></TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {pis.map(pi => (
                      <TableRow key={pi.id} data-testid={`pi-row-${pi.pi_number}`}>
                        <TableCell className="font-mono font-medium">{pi.pi_number}</TableCell>
                        <TableCell>{pi.customer_name}</TableCell>
                        <TableCell>{pi.items?.length}</TableCell>
                        <TableCell className="font-mono">{"\u20B9"}{pi.grand_total?.toLocaleString("en-IN")}</TableCell>
                        <TableCell>{pi.gst_applicable ? "Yes" : "No"}</TableCell>
                        <TableCell><Badge variant="secondary" className={`${STATUS_COLORS[pi.status]} text-xs uppercase`}>{pi.status}</Badge></TableCell>
                        <TableCell className="text-sm text-muted-foreground">{new Date(pi.created_at).toLocaleDateString("en-IN")}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="icon" onClick={() => downloadPdf(pi.id)} data-testid={`pdf-${pi.pi_number}`}><Download className="w-4 h-4" /></Button>
                            <Button variant="ghost" size="icon" onClick={() => editPi(pi)} data-testid={`edit-pi-${pi.pi_number}`}><Eye className="w-4 h-4" /></Button>
                            {pi.status !== "converted" && (
                              <Button variant="outline" size="sm" onClick={() => startConvert(pi)} data-testid={`convert-${pi.pi_number}`}>
                                <ArrowRight className="w-3 h-3 mr-1" /> Order
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="create">
          <div className="max-w-5xl space-y-6">
            {/* Customer */}
            <Card><CardHeader className="pb-3"><CardTitle className="text-base">Customer</CardTitle></CardHeader>
              <CardContent>
                {selectedCustomer ? (
                  <div className="flex items-center justify-between p-3 rounded-lg bg-secondary">
                    <div><p className="font-medium">{selectedCustomer.name}</p><p className="text-sm text-muted-foreground">{selectedCustomer.phone_numbers?.join(", ")}</p></div>
                    <Button variant="outline" size="sm" onClick={() => setSelectedCustomer(null)}>Change</Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input placeholder="Search customer..." className="pl-9" value={customerSearch} onChange={e => setCustomerSearch(e.target.value)} data-testid="pi-customer-search" /></div>
                    {customerSearch && <div className="border rounded-lg max-h-40 overflow-y-auto">
                      {filteredCustomers.map(c => (<button key={c.id} className="w-full text-left px-3 py-2 hover:bg-accent border-b last:border-0" onClick={() => { setSelectedCustomer(c); setCustomerSearch(""); }}>
                        <p className="text-sm font-medium">{c.name}</p></button>))}
                    </div>}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Toggles */}
            <Card><CardContent className="pt-6 flex flex-wrap gap-6">
              <div className="flex items-center gap-3"><Checkbox checked={gstApplicable} onCheckedChange={setGstApplicable} id="pi-gst" data-testid="pi-gst-toggle" /><Label htmlFor="pi-gst" className="cursor-pointer">GST Applicable</Label></div>
              <div className="flex items-center gap-3"><Switch checked={showRate} onCheckedChange={setShowRate} id="pi-rate" data-testid="pi-rate-toggle" /><Label htmlFor="pi-rate" className="cursor-pointer">Show Rate in PDF</Label></div>
            </CardContent></Card>

            {/* Items */}
            <Card><CardHeader className="pb-3"><div className="flex items-center justify-between"><CardTitle className="text-base">Items</CardTitle>
              <Button variant="outline" size="sm" onClick={() => setItems(p => [...p, emptyItem()])} data-testid="pi-add-item"><Plus className="w-4 h-4 mr-1" /> Add</Button></div></CardHeader>
              <CardContent className="space-y-3">
                {items.map((item, idx) => (
                  <div key={idx} className="p-3 rounded-lg border bg-secondary/30 space-y-2" data-testid={`pi-item-${idx}`}>
                    <div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">Item {idx + 1}</span>
                      {items.length > 1 && <Button variant="ghost" size="icon" onClick={() => setItems(p => p.filter((_, i) => i !== idx))}><Trash2 className="w-4 h-4 text-destructive" /></Button>}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
                      <div className="col-span-2"><Label className="text-xs">Product</Label><Input value={item.product_name} onChange={e => updateItem(idx, "product_name", e.target.value)} /></div>
                      <div><Label className="text-xs">Qty</Label><Input type="number" value={item.qty || ""} onChange={e => updateItem(idx, "qty", +e.target.value)} /></div>
                      <div><Label className="text-xs">Unit</Label><Select value={item.unit} onValueChange={v => updateItem(idx, "unit", v)}><SelectTrigger><SelectValue placeholder="Unit" /></SelectTrigger><SelectContent>{UNITS.map(u => <SelectItem key={u || "blank"} value={u || "blank"}>{u || "(none)"}</SelectItem>)}</SelectContent></Select></div>
                      <div><Label className="text-xs">Rate</Label><Input type="number" value={item.rate || ""} onChange={e => updateItem(idx, "rate", +e.target.value)} /></div>
                      <div><Label className="text-xs">Amount</Label><Input type="number" value={item.amount || ""} onChange={e => updateItem(idx, "amount", +e.target.value)} /></div>
                    </div>
                    {gstApplicable && <div className="flex items-center gap-3">
                      <div className="w-28"><Label className="text-xs">GST</Label><Select value={String(item.gst_rate)} onValueChange={v => updateItem(idx, "gst_rate", +v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{GST_RATES.map(r => <SelectItem key={r} value={String(r)}>{r}%</SelectItem>)}</SelectContent></Select></div>
                      <p className="text-xs text-muted-foreground mt-4">GST: {"\u20B9"}{item.gst_amount.toFixed(2)} | Total: {"\u20B9"}{item.total.toFixed(2)}</p>
                    </div>}
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card><CardContent className="pt-6 space-y-3">
              <div className="grid grid-cols-2 gap-4">
                <div><Label>Shipping Charge</Label><Input type="number" value={shippingCharge || ""} onChange={e => setShippingCharge(+e.target.value)} /></div>
                <div><Label>Remarks</Label><Input value={remark} onChange={e => setRemark(e.target.value)} /></div>
              </div>
              <Separator />
              <div className="space-y-1 text-sm max-w-xs ml-auto">
                <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-mono">{"\u20B9"}{subtotal.toFixed(2)}</span></div>
                {gstApplicable && <div className="flex justify-between"><span className="text-muted-foreground">GST</span><span className="font-mono">{"\u20B9"}{totalGst.toFixed(2)}</span></div>}
                {shippingCharge > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping</span><span className="font-mono">{"\u20B9"}{shippingCharge.toFixed(2)}</span></div>}
                {shippingGst > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping GST</span><span className="font-mono">{"\u20B9"}{shippingGst.toFixed(2)}</span></div>}
                <Separator /><div className="flex justify-between font-bold text-base"><span>Total</span><span className="font-mono">{"\u20B9"}{grandTotal.toFixed(2)}</span></div>
              </div>
            </CardContent></Card>

            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => { resetForm(); setTab("list"); }}>Cancel</Button>
              <Button onClick={handleSubmit} disabled={submitting} data-testid="save-pi-btn">{submitting ? "Saving..." : editingPi ? "Update PI" : "Create PI"}</Button>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* Convert Dialog */}
      <Dialog open={showConvert} onOpenChange={setShowConvert}>
        <DialogContent><DialogHeader><DialogTitle>Convert {convertPi?.pi_number} to Order</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Shipping Method</Label><Select value={convertData.shipping_method} onValueChange={v => setConvertData(p => ({ ...p, shipping_method: v }))}><SelectTrigger data-testid="convert-shipping"><SelectValue placeholder="Select" /></SelectTrigger><SelectContent>
              <SelectItem value="transport">Transport</SelectItem><SelectItem value="courier">Courier</SelectItem><SelectItem value="porter">Porter</SelectItem>
              <SelectItem value="self_arranged">Self-Arranged</SelectItem><SelectItem value="office_collection">Office Collection</SelectItem>
            </SelectContent></Select></div>
            {convertData.shipping_method === "courier" && <div><Label>Courier Name</Label><Input value={convertData.courier_name} onChange={e => setConvertData(p => ({ ...p, courier_name: e.target.value }))} /></div>}
            <div><Label>Purpose</Label><Input value={convertData.purpose} onChange={e => setConvertData(p => ({ ...p, purpose: e.target.value }))} /></div>
            <div><Label>Payment Status</Label><Select value={convertData.payment_status} onValueChange={v => setConvertData(p => ({ ...p, payment_status: v }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>
              <SelectItem value="unpaid">Unpaid</SelectItem><SelectItem value="partial">Partial</SelectItem><SelectItem value="full">Full Paid</SelectItem>
            </SelectContent></Select></div>
            {convertData.payment_status === "partial" && <div><Label>Amount Paid</Label><Input type="number" value={convertData.amount_paid || ""} onChange={e => setConvertData(p => ({ ...p, amount_paid: +e.target.value }))} /></div>}
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setShowConvert(false)}>Cancel</Button>
            <Button onClick={handleConvert} data-testid="confirm-convert-btn"><ArrowRight className="w-4 h-4 mr-1" /> Convert to Order</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
