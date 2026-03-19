import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Package, Truck, ClipboardList, Eye, DollarSign } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

const STATUS_STYLES = {
  new: "status-new",
  packaging: "status-packaging",
  packed: "status-packed",
  dispatched: "status-dispatched",
  cancelled: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

export default function TelecallerDashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [salesPeriod, setSalesPeriod] = useState("today");
  const [salesData, setSalesData] = useState(null);
  const [excludeGst, setExcludeGst] = useState(false);
  const [excludeShipping, setExcludeShipping] = useState(false);
  const [salesDateFrom, setSalesDateFrom] = useState("");
  const [salesDateTo, setSalesDateTo] = useState("");

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      // Dashboard shows only the user's recent orders (not all)
      const [ordersRes, statsRes] = await Promise.all([
        api.get("/orders"),
        api.get("/reports/dashboard"),
      ]);
      setOrders(ordersRes.data);
      setStats(statsRes.data);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const loadSales = async () => {
    try {
      let url = `/reports/telecaller-sales?period=${salesPeriod}&exclude_gst=${excludeGst}&exclude_shipping=${excludeShipping}`;
      if (salesPeriod === "custom" && salesDateFrom) url += `&date_from=${salesDateFrom}`;
      if (salesPeriod === "custom" && salesDateTo) url += `&date_to=${salesDateTo}`;
      const res = await api.get(url);
      setSalesData(res.data);
    } catch {}
  };

  useEffect(() => { loadSales(); }, [salesPeriod, excludeGst, excludeShipping, salesDateFrom, salesDateTo]);

  const recentOrders = orders.slice(0, 10);

  const statCards = [
    { label: "Total Orders", value: stats.total_orders || 0, icon: ClipboardList, color: "text-blue-500" },
    { label: "New", value: stats.new_orders || 0, icon: Plus, color: "text-emerald-500" },
    { label: "In Packaging", value: stats.packaging_orders || 0, icon: Package, color: "text-purple-500" },
    { label: "Dispatched", value: stats.dispatched_orders || 0, icon: Truck, color: "text-amber-500" },
  ];

  return (
    <div className="space-y-6" data-testid="telecaller-dashboard">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Welcome, {user?.name}</h1>
          <p className="text-muted-foreground text-sm mt-1">Here's your order overview</p>
        </div>
        <Link to="/create-order">
          <Button className="rounded-lg" data-testid="create-order-btn">
            <Plus className="w-4 h-4 mr-2" /> New Order
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {statCards.map((s, i) => (
          <Card key={i} className={`stat-card animate-fade-in-up stagger-${i + 1}`}>
            <CardContent className="p-3 sm:p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{s.label}</p>
                  <p className="text-xl sm:text-2xl font-bold mt-1">{s.value}</p>
                </div>
                <s.icon className={`w-6 h-6 sm:w-8 sm:h-8 ${s.color} opacity-70`} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* My Sales */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <CardTitle className="text-lg flex items-center gap-2"><DollarSign className="w-5 h-5 text-primary" /> My Sales</CardTitle>
            <div className="flex flex-wrap items-center gap-3">
              <Select value={salesPeriod} onValueChange={setSalesPeriod}>
                <SelectTrigger className="w-32" data-testid="sales-period-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="today">Today</SelectItem>
                  <SelectItem value="week">This Week</SelectItem>
                  <SelectItem value="month">This Month</SelectItem>
                  <SelectItem value="all">All Time</SelectItem>
                  <SelectItem value="custom">Custom Range</SelectItem>
                </SelectContent>
              </Select>
              <div className="flex items-center gap-2">
                <Checkbox id="exGst" checked={excludeGst} onCheckedChange={setExcludeGst} data-testid="exclude-gst-check" />
                <Label htmlFor="exGst" className="text-xs cursor-pointer">Excl. GST</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox id="exShip" checked={excludeShipping} onCheckedChange={setExcludeShipping} data-testid="exclude-shipping-check" />
                <Label htmlFor="exShip" className="text-xs cursor-pointer">Excl. Shipping</Label>
              </div>
            </div>
          </div>
          {salesPeriod === "custom" && (
            <div className="flex flex-wrap gap-3 mt-3">
              <div className="w-full sm:w-auto">
                <Label className="text-xs">Start Date</Label>
                <Input type="date" value={salesDateFrom} onChange={(e) => setSalesDateFrom(e.target.value)} data-testid="sales-date-from" />
              </div>
              <div className="w-full sm:w-auto">
                <Label className="text-xs">End Date</Label>
                <Input type="date" value={salesDateTo} onChange={(e) => setSalesDateTo(e.target.value)} data-testid="sales-date-to" />
              </div>
            </div>
          )}
        </CardHeader>
        <CardContent>
          {salesData ? (
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center p-3 rounded-lg bg-secondary">
                <p className="text-xs text-muted-foreground uppercase">Orders</p>
                <p className="text-lg sm:text-2xl font-bold mt-1">{salesData.total_orders}</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-secondary">
                <p className="text-xs text-muted-foreground uppercase">Total</p>
                <p className="text-lg sm:text-2xl font-bold mt-1 font-mono">{"\u20B9"}{salesData.total_amount?.toLocaleString("en-IN")}</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-primary/10">
                <p className="text-xs text-muted-foreground uppercase">Product Sales</p>
                <p className="text-lg sm:text-2xl font-bold mt-1 font-mono text-primary">{"\u20B9"}{salesData.product_sales?.toLocaleString("en-IN")}</p>
              </div>
            </div>
          ) : <p className="text-muted-foreground text-sm">Loading...</p>}
        </CardContent>
      </Card>

      {/* Recent Orders Only */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Recent Orders</CardTitle>
            <Link to="/all-orders">
              <Button variant="outline" size="sm" data-testid="view-all-orders-link">View All Orders</Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">Loading...</div>
          ) : recentOrders.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No orders yet. Create your first order!
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Items</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Total</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Date</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentOrders.map((order) => (
                  <TableRow key={order.id} data-testid={`order-row-${order.order_number}`}>
                    <TableCell className="font-mono font-medium text-sm">{order.order_number}</TableCell>
                    <TableCell className="text-sm">{order.customer_name}</TableCell>
                    <TableCell className="hidden sm:table-cell">{order.items?.length || 0}</TableCell>
                    <TableCell className="font-mono text-sm">
                      {"\u20B9"}{order.grand_total?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`${STATUS_STYLES[order.status]} text-xs uppercase`}>
                        {order.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm hidden sm:table-cell">
                      {new Date(order.created_at).toLocaleDateString("en-IN")}
                    </TableCell>
                    <TableCell>
                      <Link to={`/orders/${order.id}`}>
                        <Button variant="ghost" size="icon" data-testid={`view-order-${order.order_number}`}>
                          <Eye className="w-4 h-4" />
                        </Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
