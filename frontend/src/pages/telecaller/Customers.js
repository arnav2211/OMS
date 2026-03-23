import React, { useState, useEffect } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, UserPlus, Edit, Trash2, ChevronDown, ChevronUp, MapPin, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/contexts/AuthContext";

export default function Customers() {
  const { user } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [expandedCustomer, setExpandedCustomer] = useState(null);
  const [customerOrders, setCustomerOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null);
  const [form, setForm] = useState({ name: "", gst_no: "", phone_numbers: [""], email: "" });

  // Address management
  const [showAddresses, setShowAddresses] = useState(null);
  const [addresses, setAddresses] = useState([]);
  const [showAddrDialog, setShowAddrDialog] = useState(false);
  const [addrForm, setAddrForm] = useState({ address_line: "", city: "", state: "", pincode: "", label: "" });
  const [editingAddrId, setEditingAddrId] = useState(null);
  const [pincodeLoading, setPincodeLoading] = useState(false);

  useEffect(() => { loadCustomers(); }, []);

  const loadCustomers = async () => {
    try { const res = await api.get("/customers"); setCustomers(res.data); }
    catch { } finally { setLoading(false); }
  };

  const searchCustomers = async (q) => {
    setSearch(q);
    try { const res = await api.get(`/customers?search=${encodeURIComponent(q)}`); setCustomers(res.data); }
    catch { }
  };

  const openEdit = (c) => {
    setEditingId(c.id);
    setForm({ name: c.name, gst_no: c.gst_no || "", phone_numbers: c.phone_numbers?.length ? [...c.phone_numbers] : [""], email: c.email || "" });
    setShowDialog(true);
  };

  const openNew = () => {
    setEditingId(null);
    setForm({ name: "", gst_no: "", phone_numbers: [""], email: "" });
    setShowDialog(true);
  };

  const toggleCustomerOrders = async (customerId) => {
    if (expandedCustomer === customerId) { setExpandedCustomer(null); setCustomerOrders([]); return; }
    setExpandedCustomer(customerId); setOrdersLoading(true);
    try { const res = await api.get(`/customers/${customerId}/orders`); setCustomerOrders(res.data); }
    catch { } finally { setOrdersLoading(false); }
  };

  const deleteCustomer = async (c) => {
    try { await api.delete(`/customers/${c.id}`); toast.success("Customer deleted"); setShowDeleteConfirm(null); loadCustomers(); }
    catch (err) { toast.error(err.response?.data?.detail || "Cannot delete customer"); setShowDeleteConfirm(null); }
  };

  const handleSave = async () => {
    if (!form.name) return toast.error("Name is required");
    const phones = form.phone_numbers.filter(Boolean);
    if (phones.length === 0) return toast.error("At least one phone number is required");
    if (form.gst_no && !/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$/.test(form.gst_no.toUpperCase())) {
      return toast.error("Invalid GST number format");
    }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) return toast.error("Invalid email format");
    const payload = { ...form, phone_numbers: phones };
    try {
      if (editingId) { await api.put(`/customers/${editingId}`, payload); toast.success("Customer updated"); setShowDialog(false); }
      else {
        const res = await api.post("/customers", payload);
        toast.success("Customer created. Add an address for this customer.");
        setShowDialog(false);
        setShowAddresses(res.data.id);
        loadAddresses(res.data.id);
        openNewAddr(res.data.id);
      }
      loadCustomers();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  // Address management
  const loadAddresses = async (customerId) => {
    try { const res = await api.get(`/customers/${customerId}/addresses`); setAddresses(res.data); }
    catch { setAddresses([]); }
  };

  const toggleAddresses = (customerId) => {
    if (showAddresses === customerId) { setShowAddresses(null); return; }
    setShowAddresses(customerId); loadAddresses(customerId);
  };

  const lookupPincode = async (pincode) => {
    if (!/^\d{6}$/.test(pincode)) return;
    setPincodeLoading(true);
    try {
      const res = await api.get(`/pincode/${pincode}`);
      if (res.data.city || res.data.state) {
        setAddrForm(p => ({ ...p, city: res.data.city || p.city, state: res.data.state || p.state }));
        toast.success(`${res.data.city}, ${res.data.state}`);
      }
    } catch { }
    finally { setPincodeLoading(false); }
  };

  const openNewAddr = (customerId) => {
    setEditingAddrId(null);
    setAddrForm({ address_line: "", city: "", state: "", pincode: "", label: "" });
    setShowAddrDialog(true);
  };

  const openEditAddr = (addr) => {
    setEditingAddrId(addr.id);
    setAddrForm({ address_line: addr.address_line, city: addr.city, state: addr.state, pincode: addr.pincode, label: addr.label || "" });
    setShowAddrDialog(true);
  };

  const saveAddress = async () => {
    if (!addrForm.address_line || !addrForm.city || !addrForm.state || !addrForm.pincode) return toast.error("All address fields are required");
    if (!/^\d{6}$/.test(addrForm.pincode)) return toast.error("Pincode must be 6 digits");
    if (!/^[a-zA-Z\s]+$/.test(addrForm.city)) return toast.error("City must contain only letters");
    if (!/^[a-zA-Z\s]+$/.test(addrForm.state)) return toast.error("State must contain only letters");
    try {
      if (editingAddrId) { await api.put(`/customers/${showAddresses}/addresses/${editingAddrId}`, addrForm); toast.success("Address updated"); }
      else { await api.post(`/customers/${showAddresses}/addresses`, addrForm); toast.success("Address added"); }
      setShowAddrDialog(false); loadAddresses(showAddresses);
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const deleteAddress = async (addrId) => {
    try { await api.delete(`/customers/${showAddresses}/addresses/${addrId}`); toast.success("Address deleted"); loadAddresses(showAddresses); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-6" data-testid="customers-page">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
        <Button onClick={openNew} className="rounded-lg" data-testid="add-customer-btn"><UserPlus className="w-4 h-4 mr-2" /> Add Customer</Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input placeholder="Search by name, phone, or GST..." className="pl-9" value={search} onChange={(e) => searchCustomers(e.target.value)} data-testid="customer-search" />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (<p className="text-center py-8 text-muted-foreground">Loading...</p>) :
           customers.length === 0 ? (<p className="text-center py-8 text-muted-foreground">No customers found</p>) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Name</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Phone</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">GST</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Email</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {customers.map((c) => (
                  <React.Fragment key={c.id}>
                    <TableRow data-testid={`customer-row-${c.id}`}>
                      <TableCell className="font-medium">{c.name}</TableCell>
                      <TableCell className="text-sm hidden sm:table-cell">{c.phone_numbers?.join(", ")}</TableCell>
                      <TableCell className="text-sm font-mono hidden sm:table-cell">{c.gst_no || "-"}</TableCell>
                      <TableCell className="text-sm hidden sm:table-cell">{c.email || "-"}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" onClick={() => toggleAddresses(c.id)} title="Addresses" data-testid={`addr-btn-${c.id}`}>
                            <MapPin className="w-4 h-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => toggleCustomerOrders(c.id)} data-testid={`expand-customer-${c.id}`}>
                            {expandedCustomer === c.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => openEdit(c)} data-testid={`edit-customer-${c.id}`}><Edit className="w-4 h-4" /></Button>
                          {user?.role === "admin" && (
                            <Button variant="ghost" size="icon" onClick={() => setShowDeleteConfirm({ customer: c, step: 1 })} data-testid={`delete-customer-${c.id}`}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                    {showAddresses === c.id && (
                      <TableRow key={`addr-${c.id}`}>
                        <TableCell colSpan={5} className="bg-blue-50/50 dark:bg-blue-900/10 p-4">
                          <div className="flex items-center justify-between mb-3">
                            <p className="text-xs font-medium uppercase text-muted-foreground">Address Directory ({addresses.length})</p>
                            <Button variant="outline" size="sm" onClick={() => openNewAddr(c.id)} data-testid={`add-addr-${c.id}`}><Plus className="w-3 h-3 mr-1" /> Add Address</Button>
                          </div>
                          {addresses.length === 0 ? (
                            <p className="text-sm text-muted-foreground">No addresses saved. Add one to use during order creation.</p>
                          ) : (
                            <div className="space-y-2">
                              {addresses.map(a => (
                                <div key={a.id} className="flex items-center justify-between p-2 rounded border bg-background">
                                  <div className="text-sm">
                                    {a.label && <Badge variant="secondary" className="mr-2 text-xs">{a.label}</Badge>}
                                    {a.address_line}, {a.city}, {a.state} - {a.pincode}
                                  </div>
                                  <div className="flex gap-1">
                                    <Button variant="ghost" size="icon" onClick={() => openEditAddr(a)}><Edit className="w-3 h-3" /></Button>
                                    <Button variant="ghost" size="icon" onClick={() => deleteAddress(a.id)}><Trash2 className="w-3 h-3 text-destructive" /></Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    )}
                    {expandedCustomer === c.id && (
                      <TableRow key={`orders-${c.id}`}>
                        <TableCell colSpan={5} className="bg-muted/50 p-4">
                          {ordersLoading ? <p className="text-sm text-muted-foreground">Loading orders...</p> :
                            customerOrders.length === 0 ? <p className="text-sm text-muted-foreground">No orders found</p> : (
                            <div className="space-y-2">
                              <p className="text-xs font-medium uppercase text-muted-foreground">{customerOrders.length} Order(s)</p>
                              {customerOrders.map(o => (
                                <Link key={o.id} to={`/orders/${o.id}`} className="flex items-center justify-between p-2 rounded border hover:bg-accent transition-colors">
                                  <div className="flex items-center gap-3">
                                    <span className="font-mono text-sm font-medium">{o.order_number}</span>
                                    <Badge variant="secondary" className={`status-${o.status} text-xs`}>{o.status}</Badge>
                                  </div>
                                  <div className="text-sm text-muted-foreground">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")} | {new Date(o.created_at).toLocaleDateString("en-IN")}</div>
                                </Link>
                              ))}
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Customer Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingId ? "Edit Customer" : "New Customer"}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2"><Label>Name *</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="cust-dialog-name" /></div>
              <div className="col-span-2"><Label>GST No.</Label><Input value={form.gst_no} onChange={(e) => setForm({ ...form, gst_no: e.target.value.toUpperCase() })} data-testid="cust-dialog-gst" /></div>
            </div>
            <h4 className="text-sm font-semibold">Contact</h4>
            {form.phone_numbers.map((ph, i) => (
              <div key={i} className="flex gap-2">
                <div className="flex items-center gap-1 flex-1">
                  <span className="text-sm text-muted-foreground whitespace-nowrap">+91</span>
                  <Input value={ph} onChange={(e) => { const phones = [...form.phone_numbers]; phones[i] = e.target.value; setForm({ ...form, phone_numbers: phones }); }} placeholder="10-digit mobile number" data-testid={`cust-phone-${i}`} />
                </div>
                {i === form.phone_numbers.length - 1 && (
                  <Button variant="outline" size="icon" onClick={() => setForm({ ...form, phone_numbers: [...form.phone_numbers, ""] })}>+</Button>
                )}
              </div>
            ))}
            <div><Label className="text-xs">Email (optional)</Label><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="cust-dialog-email" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
            <Button onClick={handleSave} data-testid="save-customer-dialog-btn">{editingId ? "Update" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Address Dialog */}
      <Dialog open={showAddrDialog} onOpenChange={setShowAddrDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editingAddrId ? "Edit Address" : "Add Address"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Label</Label><Input value={addrForm.label} onChange={e => setAddrForm({ ...addrForm, label: e.target.value })} placeholder="e.g. Office, Warehouse" data-testid="addr-dialog-label" /></div>
            <div><Label>Address Line *</Label><Input value={addrForm.address_line} onChange={e => setAddrForm({ ...addrForm, address_line: e.target.value })} data-testid="addr-dialog-line" /></div>
            <div>
              <Label>Pincode *</Label>
              <Input value={addrForm.pincode} onChange={e => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                setAddrForm({ ...addrForm, pincode: v });
                if (v.length === 6) lookupPincode(v);
              }} maxLength={6} data-testid="addr-dialog-pincode" />
              {pincodeLoading && <p className="text-xs text-muted-foreground mt-1">Looking up...</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>City *</Label><Input value={addrForm.city} onChange={e => setAddrForm({ ...addrForm, city: e.target.value })} data-testid="addr-dialog-city" /></div>
              <div><Label>State *</Label><Input value={addrForm.state} onChange={e => setAddrForm({ ...addrForm, state: e.target.value })} data-testid="addr-dialog-state" /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddrDialog(false)}>Cancel</Button>
            <Button onClick={saveAddress} data-testid="save-addr-dialog-btn">{editingAddrId ? "Update" : "Add"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation - Two Step */}
      <Dialog open={!!showDeleteConfirm} onOpenChange={() => setShowDeleteConfirm(null)}>
        <DialogContent>
          {showDeleteConfirm?.step === 1 ? (
            <>
              <DialogHeader><DialogTitle>Delete Customer</DialogTitle></DialogHeader>
              <p className="text-sm text-muted-foreground">
                Are you sure you want to delete <span className="font-medium text-foreground">{showDeleteConfirm?.customer?.name}</span>?
              </p>
              <p className="text-sm text-muted-foreground">Customers with existing orders cannot be deleted.</p>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowDeleteConfirm(null)}>Cancel</Button>
                <Button variant="destructive" onClick={() => setShowDeleteConfirm({ ...showDeleteConfirm, step: 2 })} data-testid="confirm-delete-step1">Yes, Continue</Button>
              </DialogFooter>
            </>
          ) : showDeleteConfirm?.step === 2 ? (
            <>
              <DialogHeader><DialogTitle className="text-destructive">Final Warning</DialogTitle></DialogHeader>
              <div className="space-y-2">
                <p className="text-sm font-semibold text-destructive">This action is permanent and cannot be undone!</p>
                <p className="text-sm text-muted-foreground">All related records may be affected. Are you absolutely sure you want to permanently delete <span className="font-bold text-foreground">{showDeleteConfirm?.customer?.name}</span>?</p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowDeleteConfirm(null)}>Cancel</Button>
                <Button variant="destructive" onClick={() => deleteCustomer(showDeleteConfirm.customer)} data-testid="confirm-delete-step2">Permanently Delete</Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
