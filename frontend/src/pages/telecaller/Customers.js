import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Search, UserPlus, Edit, Eye, Trash2, ChevronDown, ChevronUp } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/contexts/AuthContext";

const emptyAddress = () => ({ address: "", city: "", state: "", pincode: "" });

export default function Customers() {
  const { user } = useAuth();
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [sameAsBilling, setSameAsBilling] = useState(true);
  const [expandedCustomer, setExpandedCustomer] = useState(null);
  const [customerOrders, setCustomerOrders] = useState([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null);
  const [form, setForm] = useState({
    name: "", gst_no: "", billing_address: emptyAddress(), shipping_address: emptyAddress(),
    phone_numbers: [""], email: "",
  });

  useEffect(() => { loadCustomers(); }, []);

  const loadCustomers = async () => {
    try {
      const res = await api.get("/customers");
      setCustomers(res.data);
    } catch { } finally { setLoading(false); }
  };

  const searchCustomers = async (q) => {
    setSearch(q);
    try {
      const res = await api.get(`/customers?search=${encodeURIComponent(q)}`);
      setCustomers(res.data);
    } catch { }
  };

  const openEdit = (c) => {
    setEditingId(c.id);
    const sameBilling = JSON.stringify(c.billing_address) === JSON.stringify(c.shipping_address);
    setSameAsBilling(sameBilling);
    setForm({
      name: c.name, gst_no: c.gst_no || "",
      billing_address: c.billing_address || emptyAddress(),
      shipping_address: c.shipping_address || emptyAddress(),
      phone_numbers: c.phone_numbers?.length ? c.phone_numbers : [""],
      email: c.email || "",
    });
    setShowDialog(true);
  };

  const openNew = () => {
    setEditingId(null);
    setSameAsBilling(true);
    setForm({ name: "", gst_no: "", billing_address: emptyAddress(), shipping_address: emptyAddress(), phone_numbers: [""], email: "" });
    setShowDialog(true);
  };

  const toggleCustomerOrders = async (customerId) => {
    if (expandedCustomer === customerId) {
      setExpandedCustomer(null);
      setCustomerOrders([]);
      return;
    }
    setExpandedCustomer(customerId);
    setOrdersLoading(true);
    try {
      const res = await api.get(`/customers/${customerId}/orders`);
      setCustomerOrders(res.data);
    } catch {} finally { setOrdersLoading(false); }
  };

  const deleteCustomer = async (c) => {
    try {
      await api.delete(`/customers/${c.id}`);
      toast.success("Customer deleted");
      setShowDeleteConfirm(null);
      loadCustomers();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Cannot delete customer");
      setShowDeleteConfirm(null);
    }
  };

  const handleSave = async () => {
    if (!form.name) return toast.error("Name is required");
    const payload = {
      ...form,
      phone_numbers: form.phone_numbers.filter(Boolean),
      shipping_address: sameAsBilling ? form.billing_address : form.shipping_address,
    };
    try {
      if (editingId) {
        await api.put(`/customers/${editingId}`, payload);
        toast.success("Customer updated");
      } else {
        await api.post("/customers", payload);
        toast.success("Customer created");
      }
      setShowDialog(false);
      loadCustomers();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="customers-page">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
        <Button onClick={openNew} className="rounded-lg" data-testid="add-customer-btn">
          <UserPlus className="w-4 h-4 mr-2" /> Add Customer
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search by name, phone, or GST..."
              className="pl-9"
              value={search}
              onChange={(e) => searchCustomers(e.target.value)}
              data-testid="customer-search"
            />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading...</p>
          ) : customers.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">No customers found</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Name</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Phone</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">GST</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">City</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {customers.map((c) => (
                  <>
                    <TableRow key={c.id} data-testid={`customer-row-${c.id}`}>
                      <TableCell className="font-medium">{c.name}</TableCell>
                      <TableCell className="text-sm hidden sm:table-cell">{c.phone_numbers?.join(", ")}</TableCell>
                      <TableCell className="text-sm font-mono hidden sm:table-cell">{c.gst_no || "-"}</TableCell>
                      <TableCell className="text-sm hidden sm:table-cell">{c.billing_address?.city || "-"}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" onClick={() => toggleCustomerOrders(c.id)} data-testid={`expand-customer-${c.id}`}>
                            {expandedCustomer === c.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => openEdit(c)} data-testid={`edit-customer-${c.id}`}>
                            <Edit className="w-4 h-4" />
                          </Button>
                          {["admin", "telecaller"].includes(user?.role) && (
                            <Button variant="ghost" size="icon" onClick={() => setShowDeleteConfirm(c)} data-testid={`delete-customer-${c.id}`}>
                              <Trash2 className="w-4 h-4 text-destructive" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                    {expandedCustomer === c.id && (
                      <TableRow key={`orders-${c.id}`}>
                        <TableCell colSpan={5} className="bg-muted/50 p-4">
                          {ordersLoading ? <p className="text-sm text-muted-foreground">Loading orders...</p> :
                            customerOrders.length === 0 ? <p className="text-sm text-muted-foreground">No orders found for this customer</p> : (
                            <div className="space-y-2">
                              <p className="text-xs font-medium uppercase text-muted-foreground">{customerOrders.length} Order(s)</p>
                              {customerOrders.map(o => (
                                <Link key={o.id} to={`/orders/${o.id}`} className="flex items-center justify-between p-2 rounded border hover:bg-accent transition-colors">
                                  <div className="flex items-center gap-3">
                                    <span className="font-mono text-sm font-medium">{o.order_number}</span>
                                    <Badge variant="secondary" className={`status-${o.status} text-xs`}>{o.status}</Badge>
                                  </div>
                                  <div className="text-sm text-muted-foreground">
                                    {"\u20B9"}{o.grand_total?.toLocaleString("en-IN")} | {new Date(o.created_at).toLocaleDateString("en-IN")}
                                  </div>
                                </Link>
                              ))}
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? "Edit Customer" : "New Customer"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <Label>Name *</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="cust-dialog-name" />
              </div>
              <div className="col-span-2">
                <Label>GST No.</Label>
                <Input value={form.gst_no} onChange={(e) => setForm({ ...form, gst_no: e.target.value.toUpperCase() })} data-testid="cust-dialog-gst" />
              </div>
            </div>
            <h4 className="text-sm font-semibold">Billing Address</h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Input placeholder="Address" value={form.billing_address.address} onChange={(e) => setForm({ ...form, billing_address: { ...form.billing_address, address: e.target.value } })} />
              </div>
              <Input placeholder="City" value={form.billing_address.city} onChange={(e) => setForm({ ...form, billing_address: { ...form.billing_address, city: e.target.value } })} />
              <Input placeholder="State" value={form.billing_address.state} onChange={(e) => setForm({ ...form, billing_address: { ...form.billing_address, state: e.target.value } })} />
              <Input placeholder="Pincode" value={form.billing_address.pincode} onChange={(e) => setForm({ ...form, billing_address: { ...form.billing_address, pincode: e.target.value } })} />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="sameBilling" checked={sameAsBilling} onCheckedChange={setSameAsBilling} />
              <Label htmlFor="sameBilling" className="text-sm cursor-pointer">Shipping same as billing</Label>
            </div>
            {!sameAsBilling && (
              <>
                <h4 className="text-sm font-semibold">Shipping Address</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <Input placeholder="Address" value={form.shipping_address.address} onChange={(e) => setForm({ ...form, shipping_address: { ...form.shipping_address, address: e.target.value } })} />
                  </div>
                  <Input placeholder="City" value={form.shipping_address.city} onChange={(e) => setForm({ ...form, shipping_address: { ...form.shipping_address, city: e.target.value } })} />
                  <Input placeholder="State" value={form.shipping_address.state} onChange={(e) => setForm({ ...form, shipping_address: { ...form.shipping_address, state: e.target.value } })} />
                  <Input placeholder="Pincode" value={form.shipping_address.pincode} onChange={(e) => setForm({ ...form, shipping_address: { ...form.shipping_address, pincode: e.target.value } })} />
                </div>
              </>
            )}
            <h4 className="text-sm font-semibold">Contact</h4>
            {form.phone_numbers.map((ph, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  value={ph}
                  onChange={(e) => {
                    const phones = [...form.phone_numbers];
                    phones[i] = e.target.value;
                    setForm({ ...form, phone_numbers: phones });
                  }}
                  placeholder="Phone number"
                  data-testid={`cust-phone-${i}`}
                />
                {i === form.phone_numbers.length - 1 && (
                  <Button variant="outline" size="icon" onClick={() => setForm({ ...form, phone_numbers: [...form.phone_numbers, ""] })}>+</Button>
                )}
              </div>
            ))}
            <div>
              <Label className="text-xs">Email</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="cust-dialog-email" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
            <Button onClick={handleSave} data-testid="save-customer-dialog-btn">{editingId ? "Update" : "Create"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!showDeleteConfirm} onOpenChange={() => setShowDeleteConfirm(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Customer</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete <span className="font-medium text-foreground">{showDeleteConfirm?.name}</span>?
            This action cannot be undone. Customers with existing orders cannot be deleted.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteConfirm(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteCustomer(showDeleteConfirm)} data-testid="confirm-delete-customer">Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
