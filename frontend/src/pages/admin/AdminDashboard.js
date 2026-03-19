import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import {
  ClipboardList, Users, Package, Truck, BarChart3, Search,
  Eye, Edit, Calendar, DollarSign,
} from "lucide-react";

const STATUS_STYLES = {
  new: "status-new",
  packaging: "status-packaging",
  packed: "status-packed",
  dispatched: "status-dispatched",
};

export default function AdminDashboard() {
  const [stats, setStats] = useState({});
  const [orders, setOrders] = useState([]);
  const [salesData, setSalesData] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);

  // Formulation
  const [formulationOrder, setFormulationOrder] = useState(null);
  const [showFormulation, setShowFormulation] = useState(false);
  const [formulationItems, setFormulationItems] = useState([]);

  useEffect(() => { loadAll(); }, []);

  const loadAll = async () => {
    try {
      const [statsRes, ordersRes, salesRes] = await Promise.all([
        api.get("/reports/dashboard"),
        api.get("/orders"),
        api.get("/reports/sales"),
      ]);
      setStats(statsRes.data);
      setOrders(ordersRes.data);
      setSalesData(salesRes.data);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
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
        show_formulation: item.show_formulation || false,
      }))
    );
    setShowFormulation(true);
  };

  const saveFormulations = async () => {
    try {
      await api.put(`/orders/${formulationOrder.id}/formulation`, {
        items: formulationItems,
      });
      toast.success("Formulations updated");
      setShowFormulation(false);
      loadAll();
    } catch (err) {
      toast.error("Failed to update formulations");
    }
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
      <h1 className="text-2xl font-bold tracking-tight">Admin Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map((s, i) => (
          <Card key={i} className={`stat-card animate-fade-in-up stagger-${i + 1}`}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <s.icon className={`w-5 h-5 ${s.color} opacity-70`} />
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{s.label}</p>
              </div>
              <p className="text-xl font-bold mt-2">{s.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="orders" className="space-y-4">
        <TabsList>
          <TabsTrigger value="orders" data-testid="tab-orders">Orders</TabsTrigger>
          <TabsTrigger value="sales" data-testid="tab-sales">Sales Report</TabsTrigger>
        </TabsList>

        <TabsContent value="orders">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="relative flex-1 min-w-[200px]">
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
                <div className="w-36">
                  <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger data-testid="admin-status-filter">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Status</SelectItem>
                      <SelectItem value="new">New</SelectItem>
                      <SelectItem value="packaging">Packaging</SelectItem>
                      <SelectItem value="packed">Packed</SelectItem>
                      <SelectItem value="dispatched">Dispatched</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">From</Label>
                  <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="admin-date-from" />
                </div>
                <div>
                  <Label className="text-xs">To</Label>
                  <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="admin-date-to" />
                </div>
                <Button variant="outline" size="sm" onClick={searchOrders} data-testid="admin-search-btn">
                  <Search className="w-4 h-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Telecaller</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Total</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                    <TableHead className="text-xs uppercase tracking-wider">Date</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.map((order) => (
                    <TableRow key={order.id} data-testid={`admin-order-${order.order_number}`}>
                      <TableCell className="font-mono font-medium">{order.order_number}</TableCell>
                      <TableCell>{order.customer_name}</TableCell>
                      <TableCell className="text-sm">{order.telecaller_name}</TableCell>
                      <TableCell className="font-mono">{"\u20B9"}{order.grand_total?.toLocaleString("en-IN")}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={`${STATUS_STYLES[order.status]} text-xs uppercase`}>
                          {order.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {new Date(order.created_at).toLocaleDateString("en-IN")}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" onClick={() => openFormulation(order)} data-testid={`formulation-btn-${order.order_number}`}>
                            <Edit className="w-4 h-4" />
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
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sales">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sales by Telecaller</CardTitle>
            </CardHeader>
            <CardContent>
              {salesData?.telecaller_stats?.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs uppercase tracking-wider">Telecaller</TableHead>
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
      </Tabs>

      {/* Formulation Dialog */}
      <Dialog open={showFormulation} onOpenChange={setShowFormulation}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Formulations - {formulationOrder?.order_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {formulationItems.map((item, idx) => (
              <div key={idx} className="p-4 rounded-lg border space-y-3" data-testid={`formulation-item-${idx}`}>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm">{item.product_name}</span>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id={`show-${idx}`}
                      checked={item.show_formulation}
                      onCheckedChange={(v) => {
                        const updated = [...formulationItems];
                        updated[idx].show_formulation = v;
                        setFormulationItems(updated);
                      }}
                      data-testid={`show-formulation-${idx}`}
                    />
                    <Label htmlFor={`show-${idx}`} className="text-xs cursor-pointer">Show to Packaging</Label>
                  </div>
                </div>
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
