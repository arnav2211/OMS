import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Search, Package, Truck, ClipboardList, Eye } from "lucide-react";

const STATUS_STYLES = {
  new: "status-new",
  packaging: "status-packaging",
  packed: "status-packed",
  dispatched: "status-dispatched",
};

export default function TelecallerDashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [stats, setStats] = useState({});
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [ordersRes, statsRes] = await Promise.all([
        api.get("/orders"),
        api.get("/reports/dashboard"),
      ]);
      setOrders(ordersRes.data);
      setStats(statsRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = orders.filter(
    (o) =>
      o.order_number?.toLowerCase().includes(search.toLowerCase()) ||
      o.customer_name?.toLowerCase().includes(search.toLowerCase())
  );

  const statCards = [
    { label: "Total Orders", value: stats.total_orders || 0, icon: ClipboardList, color: "text-blue-500" },
    { label: "New", value: stats.new_orders || 0, icon: Plus, color: "text-emerald-500" },
    { label: "In Packaging", value: stats.packaging_orders || 0, icon: Package, color: "text-purple-500" },
    { label: "Dispatched", value: stats.dispatched_orders || 0, icon: Truck, color: "text-amber-500" },
  ];

  return (
    <div className="space-y-6" data-testid="telecaller-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Welcome, {user?.name}</h1>
          <p className="text-muted-foreground text-sm mt-1">Here's your order overview</p>
        </div>
        <Link to="/create-order">
          <Button className="rounded-lg" data-testid="create-order-btn">
            <Plus className="w-4 h-4 mr-2" /> New Order
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s, i) => (
          <Card key={i} className={`stat-card animate-fade-in-up stagger-${i + 1}`}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{s.label}</p>
                  <p className="text-2xl font-bold mt-1">{s.value}</p>
                </div>
                <s.icon className={`w-8 h-8 ${s.color} opacity-70`} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Orders Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Recent Orders</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search orders..."
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                data-testid="order-search-input"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">Loading...</div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No orders found. Create your first order!
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Items</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Total</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Date</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.slice(0, 50).map((order) => (
                  <TableRow key={order.id} data-testid={`order-row-${order.order_number}`}>
                    <TableCell className="font-mono font-medium">{order.order_number}</TableCell>
                    <TableCell>{order.customer_name}</TableCell>
                    <TableCell>{order.items?.length || 0}</TableCell>
                    <TableCell className="font-mono">
                      {"\u20B9"}{order.grand_total?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`${STATUS_STYLES[order.status]} text-xs uppercase`}>
                        {order.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
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
