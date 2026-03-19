import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
  ClipboardList, Users, Package, Truck, BarChart3, Search,
  Eye, Edit, DollarSign, Plus, Trash2, Printer,
} from "lucide-react";

const STATUS_STYLES = {
  new: "status-new",
  packaging: "status-packaging",
  packed: "status-packed",
  dispatched: "status-dispatched",
  cancelled: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

export default function AdminDashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState({});
  const [orders, setOrders] = useState([]);
  const [salesData, setSalesData] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [formulationGlobal, setFormulationGlobal] = useState(false);

  // Formulation dialog
  const [showFormulation, setShowFormulation] = useState(false);
  const [formulationOrder, setFormulationOrder] = useState(null);
  const [formulationItems, setFormulationItems] = useState([]);

  // Packaging staff management
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [newStaffName, setNewStaffName] = useState("");

  // Reports
  const [telecallers, setTelecallers] = useState([]);
  const [selectedTelecaller, setSelectedTelecaller] = useState("");
  const [telecallerStats, setTelecallerStats] = useState(null);
  const [telecallerSales, setTelecallerSales] = useState(null);
  const [reportPeriod, setReportPeriod] = useState("today");
  const [excludeGst, setExcludeGst] = useState(false);
  const [excludeShipping, setExcludeShipping] = useState(false);

  useEffect(() => { loadAll(); }, []);

  const loadAll = async () => {
    try {
      const [statsRes, ordersRes, salesRes, settingsRes, staffRes, usersRes] = await Promise.all([
        api.get("/reports/dashboard"),
        api.get("/orders"),
        api.get("/reports/sales"),
        api.get("/settings"),
        api.get("/packaging-staff"),
        api.get("/users"),
      ]);
      setStats(statsRes.data);
      setOrders(ordersRes.data);
      setSalesData(salesRes.data);
      setFormulationGlobal(settingsRes.data?.show_formulation || false);
      setPackagingStaff(staffRes.data);
      setTelecallers(usersRes.data.filter(u => u.role === "telecaller" && u.active));
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const toggleFormulationGlobal = async (value) => {
    try {
      await api.put("/settings", { show_formulation: value });
      setFormulationGlobal(value);
      toast.success(value ? "Formulations visible to all" : "Formulations hidden");
    } catch { toast.error("Failed to update"); }
  };

  const searchOrders = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await api.get(`/orders?${params.toString()}`);
      setOrders(res.data);
    } catch { }
  };

  useEffect(() => { searchOrders(); }, [statusFilter, dateFrom, dateTo]);

  // Formulation dialog
  const openFormulation = (order) => {
    setFormulationOrder(order);
    setFormulationItems(
      order.items.map((item, idx) => ({
        index: idx,
        product_name: item.product_name,
        formulation: item.formulation || "",
      }))
    );
    setShowFormulation(true);
  };

  const saveFormulations = async () => {
    try {
      await api.put(`/orders/${formulationOrder.id}/formulation`, { items: formulationItems });
      toast.success("Formulations updated");
      setShowFormulation(false);
      loadAll();
    } catch { toast.error("Failed to update formulations"); }
  };

  // Packaging staff
  const addStaff = async () => {
    if (!newStaffName.trim()) return;
    try {
      await api.post("/packaging-staff", { name: newStaffName.trim() });
      setNewStaffName("");
      const res = await api.get("/packaging-staff");
      setPackagingStaff(res.data);
      toast.success("Staff added");
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const removeStaff = async (id) => {
    try {
      await api.delete(`/packaging-staff/${id}`);
      const res = await api.get("/packaging-staff");
      setPackagingStaff(res.data);
      toast.success("Staff removed");
    } catch { toast.error("Failed to remove"); }
  };

  // Reports - load telecaller dashboard
  const loadTelecallerReport = async (tid) => {
    if (!tid) return;
    setSelectedTelecaller(tid);
    try {
      const [dashRes, salesRes] = await Promise.all([
        api.get(`/reports/telecaller-dashboard/${tid}`),
        api.get(`/reports/telecaller-sales?telecaller_id=${tid}&period=${reportPeriod}&exclude_gst=${excludeGst}&exclude_shipping=${excludeShipping}`),
      ]);
      setTelecallerStats(dashRes.data);
      setTelecallerSales(salesRes.data);
    } catch { toast.error("Failed to load report"); }
  };

  useEffect(() => {
    if (selectedTelecaller) loadTelecallerReport(selectedTelecaller);
  }, [reportPeriod, excludeGst, excludeShipping]);

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const handlePrint = (orderId) => {
    window.open(`${backendUrl}/api/orders/${orderId}/print`, '_blank');
  };

  const statCards = [
    { label: "Total Orders", value: stats.total_orders || 0, icon: ClipboardList, color: "text-blue-500" },
    { label: "New Orders", value: stats.new_orders || 0, icon: Package, color: "text-emerald-500" },
    { label: "Packed", value: stats.packed_orders || 0, icon: Package, color: "text-amber-500" },
    { label: "Dispatched", value: stats.dispatched_orders || 0, icon: Truck, color: "text-purple-500" },
    { label: "Customers", value: stats.total_customers || 0, icon: Users, color: "text-rose-500" },
    { label: "Revenue", value: `\u20B9${(salesData?.total_revenue || 0).toLocaleString("en-IN")}`, icon: DollarSign, color: "text-emerald-600" },
  ];

  return (
    <div className="space-y-6" data-testid="admin-dashboard">
      <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Admin Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {statCards.map((s, i) => (
          <Card key={i} className={`stat-card animate-fade-in-up stagger-${i + 1}`}>
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-center gap-2">
                <s.icon className={`w-4 h-4 sm:w-5 sm:h-5 ${s.color} opacity-70`} />
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider truncate">{s.label}</p>
              </div>
              <p className="text-lg sm:text-xl font-bold mt-1">{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="orders" className="space-y-4">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="orders" data-testid="tab-orders">Orders</TabsTrigger>
          <TabsTrigger value="sales" data-testid="tab-sales">Sales Report</TabsTrigger>
          <TabsTrigger value="reports" data-testid="tab-reports">Executive Reports</TabsTrigger>
          <TabsTrigger value="settings" data-testid="tab-settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="orders">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-col sm:flex-row flex-wrap items-end gap-3">
                <div className="relative flex-1 min-w-0 w-full sm:w-auto">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search order # or customer..."
                    className="pl-9"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && searchOrders()}
                    data-testid="admin-order-search"
                  />
                </div>
                <div className="w-full sm:w-36">
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger data-testid="admin-status-filter"><SelectValue placeholder="Status" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Status</SelectItem>
                      <SelectItem value="new">New</SelectItem>
                      <SelectItem value="packaging">Packaging</SelectItem>
                      <SelectItem value="packed">Packed</SelectItem>
                      <SelectItem value="dispatched">Dispatched</SelectItem>
                      <SelectItem value="cancelled">Cancelled</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-full sm:w-auto">
                  <Label className="text-xs">From</Label>
                  <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="admin-date-from" />
                </div>
                <div className="w-full sm:w-auto">
                  <Label className="text-xs">To</Label>
                  <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="admin-date-to" />
                </div>
                <Button variant="outline" size="sm" onClick={searchOrders} data-testid="admin-search-btn">
                  <Search className="w-4 h-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Executive</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Total</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Date</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.map((order) => (
                    <TableRow key={order.id} data-testid={`admin-order-${order.order_number}`}>
                      <TableCell className="font-mono font-medium text-sm">{order.order_number}</TableCell>
                      <TableCell className="text-sm">{order.customer_name}</TableCell>
                      <TableCell className="text-sm hidden sm:table-cell">{order.telecaller_name}</TableCell>
                      <TableCell className="font-mono text-sm">{"\u20B9"}{order.grand_total?.toLocaleString("en-IN")}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={`${STATUS_STYLES[order.status]} text-xs uppercase`}>{order.status}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">
                        {new Date(order.created_at).toLocaleDateString("en-IN")}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" onClick={() => openFormulation(order)} data-testid={`formulation-btn-${order.order_number}`}>
                            <Edit className="w-4 h-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handlePrint(order.id)} data-testid={`print-btn-${order.order_number}`}>
                            <Printer className="w-4 h-4" />
                          </Button>
                          <Link to={`/orders/${order.id}`}>
                            <Button variant="ghost" size="icon"><Eye className="w-4 h-4" /></Button>
                          </Link>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {orders.length === 0 && (
                <p className="text-center py-8 text-muted-foreground">No orders found</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sales">
          <Card>
            <CardHeader><CardTitle className="text-base">Sales by Executive</CardTitle></CardHeader>
            <CardContent>
              {salesData?.telecaller_stats?.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs uppercase tracking-wider">Executive</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider">Orders</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider">Revenue</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {salesData.telecaller_stats.map((t, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-medium">{t.name}</TableCell>
                        <TableCell>{t.order_count}</TableCell>
                        <TableCell className="font-mono">{"\u20B9"}{t.total_amount?.toLocaleString("en-IN")}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-center py-8 text-muted-foreground">No sales data yet</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reports">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Executive Dashboard Viewer</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col sm:flex-row gap-3 flex-wrap">
                <div className="w-full sm:w-48">
                  <Label className="text-xs">Select Executive</Label>
                  <Select value={selectedTelecaller} onValueChange={(v) => loadTelecallerReport(v)}>
                    <SelectTrigger data-testid="report-telecaller-select"><SelectValue placeholder="Choose..." /></SelectTrigger>
                    <SelectContent>
                      {telecallers.map(t => (
                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {selectedTelecaller && (
                  <>
                    <div className="w-full sm:w-36">
                      <Label className="text-xs">Period</Label>
                      <Select value={reportPeriod} onValueChange={setReportPeriod}>
                        <SelectTrigger data-testid="report-period-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="today">Today</SelectItem>
                          <SelectItem value="week">This Week</SelectItem>
                          <SelectItem value="month">This Month</SelectItem>
                          <SelectItem value="all">All Time</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-end gap-3">
                      <div className="flex items-center gap-2">
                        <Checkbox id="repExGst" checked={excludeGst} onCheckedChange={setExcludeGst} />
                        <Label htmlFor="repExGst" className="text-xs cursor-pointer">Excl. GST</Label>
                      </div>
                      <div className="flex items-center gap-2">
                        <Checkbox id="repExShip" checked={excludeShipping} onCheckedChange={setExcludeShipping} />
                        <Label htmlFor="repExShip" className="text-xs cursor-pointer">Excl. Shipping</Label>
                      </div>
                    </div>
                  </>
                )}
              </div>

              {telecallerStats && selectedTelecaller && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {[
                      { label: "Total Orders", value: telecallerStats.total_orders },
                      { label: "New", value: telecallerStats.new_orders },
                      { label: "In Packaging", value: telecallerStats.packaging_orders },
                      { label: "Dispatched", value: telecallerStats.dispatched_orders },
                    ].map((s, i) => (
                      <div key={i} className="text-center p-3 rounded-lg bg-secondary">
                        <p className="text-xs text-muted-foreground uppercase">{s.label}</p>
                        <p className="text-2xl font-bold mt-1">{s.value || 0}</p>
                      </div>
                    ))}
                  </div>
                  {telecallerSales && (
                    <div className="grid grid-cols-3 gap-3">
                      <div className="text-center p-3 rounded-lg bg-secondary">
                        <p className="text-xs text-muted-foreground uppercase">Orders</p>
                        <p className="text-xl font-bold mt-1">{telecallerSales.total_orders}</p>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-secondary">
                        <p className="text-xs text-muted-foreground uppercase">Total</p>
                        <p className="text-xl font-bold mt-1 font-mono">{"\u20B9"}{telecallerSales.total_amount?.toLocaleString("en-IN")}</p>
                      </div>
                      <div className="text-center p-3 rounded-lg bg-primary/10">
                        <p className="text-xs text-muted-foreground uppercase">Product Sales</p>
                        <p className="text-xl font-bold mt-1 font-mono text-primary">{"\u20B9"}{telecallerSales.product_sales?.toLocaleString("en-IN")}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings">
          <div className="space-y-4">
            <Card>
              <CardHeader><CardTitle className="text-base">Formulation Visibility</CardTitle></CardHeader>
              <CardContent>
                <div className="flex items-center justify-between p-4 rounded-lg border">
                  <div>
                    <p className="font-medium">Show formulations globally</p>
                    <p className="text-sm text-muted-foreground">When ON, formulations are visible to packaging team for all orders</p>
                  </div>
                  <Switch checked={formulationGlobal} onCheckedChange={toggleFormulationGlobal} data-testid="global-formulation-toggle" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-base">Packaging Staff</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="flex gap-2">
                  <Input
                    placeholder="Add new staff name..."
                    value={newStaffName}
                    onChange={(e) => setNewStaffName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addStaff()}
                    data-testid="new-staff-name-input"
                  />
                  <Button onClick={addStaff} size="sm" data-testid="add-staff-btn">
                    <Plus className="w-4 h-4 mr-1" /> Add
                  </Button>
                </div>
                <div className="space-y-2">
                  {packagingStaff.map((s) => (
                    <div key={s.id} className="flex items-center justify-between p-2 rounded border" data-testid={`staff-${s.name}`}>
                      <span className="text-sm font-medium">{s.name}</span>
                      <Button variant="ghost" size="icon" onClick={() => removeStaff(s.id)} data-testid={`remove-staff-${s.name}`}>
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                  ))}
                  {packagingStaff.length === 0 && (
                    <p className="text-sm text-muted-foreground">No staff members configured</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* Formulation Dialog - No per-item visibility toggle */}
      <Dialog open={showFormulation} onOpenChange={setShowFormulation}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Formulations - {formulationOrder?.order_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {formulationItems.map((item, idx) => (
              <div key={idx} className="p-4 rounded-lg border space-y-3" data-testid={`formulation-item-${idx}`}>
                <span className="font-medium text-sm">{item.product_name}</span>
                <Textarea
                  value={item.formulation}
                  onChange={(e) => {
                    const updated = [...formulationItems];
                    updated[idx].formulation = e.target.value;
                    setFormulationItems(updated);
                  }}
                  placeholder="Enter formulation details..."
                  rows={3}
                  data-testid={`formulation-text-${idx}`}
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFormulation(false)}>Cancel</Button>
            <Button onClick={saveFormulations} data-testid="save-formulations-btn">Save Formulations</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
