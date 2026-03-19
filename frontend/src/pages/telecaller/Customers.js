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
import { Search, UserPlus, Edit, Eye } from "lucide-react";
import { Link } from "react-router-dom";

const emptyAddress = () => ({ address: "", city: "", state: "", pincode: "" });

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [sameAsBilling, setSameAsBilling] = useState(true);
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
                  <TableHead className="text-xs uppercase tracking-wider">Phone</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">GST</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">City</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {customers.map((c) => (
                  <TableRow key={c.id} data-testid={`customer-row-${c.id}`}>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableCell className="text-sm">{c.phone_numbers?.join(", ")}</TableCell>
                    <TableCell className="text-sm font-mono">{c.gst_no || "-"}</TableCell>
                    <TableCell className="text-sm">{c.billing_address?.city || "-"}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" onClick={() => openEdit(c)} data-testid={`edit-customer-${c.id}`}>
                        <Edit className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
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
    </div>
  );
}
