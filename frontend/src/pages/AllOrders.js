import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Eye, ClipboardList } from "lucide-react";

const STATUS_STYLES = {
  new: "status-new",
  packaging: "status-packaging",
  packed: "status-packed",
  dispatched: "status-dispatched",
  cancelled: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const PAYMENT_STYLES = {
  unpaid: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  full: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
};

export default function AllOrders() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [paymentFilter, setPaymentFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.role === "admin";

  useEffect(() => { loadOrders(); }, [statusFilter, paymentFilter, dateFrom, dateTo]);

  const loadOrders = async () => {
    try {
      const params = new URLSearchParams();
      params.set("view_all", "true");
      if (search) params.set("search", search);
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await api.get(`/orders?${params.toString()}`);
      let data = res.data;
      // Client-side payment filter
      if (paymentFilter !== "all") {
        data = data.filter((o) => o.payment_status === paymentFilter);
      }
      setOrders(data);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const handleSearch = () => loadOrders();

  const getPaymentLabel = (status) => {
    if (status === "full") return "Fully Paid";
    if (status === "partial") return "Partial";
    return "Unpaid";
  };

  return (
    <div className="space-y-6" data-testid="all-orders-page">
      <h1 className="text-xl sm:text-2xl font-bold tracking-tight">All Orders</h1>

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
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                data-testid="all-orders-search"
              />
            </div>
            <div className="w-full sm:w-36">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger data-testid="all-orders-status-filter"><SelectValue placeholder="Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="packaging">Packaging</SelectItem>
                  <SelectItem value="packed">Packed</SelectItem>
                  <SelectItem value="dispatched">Dispatched</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="w-full sm:w-36">
              <Select value={paymentFilter} onValueChange={setPaymentFilter}>
                <SelectTrigger data-testid="all-orders-payment-filter"><SelectValue placeholder="Payment" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Payment</SelectItem>
                  <SelectItem value="full">Fully Paid</SelectItem>
                  <SelectItem value="partial">Partial</SelectItem>
                  <SelectItem value="unpaid">Unpaid</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="w-full sm:w-auto">
              <Label className="text-xs">From</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="all-orders-date-from" />
            </div>
            <div className="w-full sm:w-auto">
              <Label className="text-xs">To</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="all-orders-date-to" />
            </div>
            <Button variant="outline" size="sm" onClick={handleSearch} data-testid="all-orders-search-btn">
              <Search className="w-4 h-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading...</p>
          ) : orders.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No orders found</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                  {isAdmin && <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Executive</TableHead>}
                  <TableHead className="text-xs uppercase tracking-wider">Total</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Payment</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Date</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id} data-testid={`all-order-${order.order_number}`}>
                    <TableCell className="font-mono font-medium text-sm">{order.order_number}</TableCell>
                    <TableCell className="text-sm">{order.customer_name}</TableCell>
                    {isAdmin && <TableCell className="text-sm hidden sm:table-cell">{order.telecaller_name || "-"}</TableCell>}
                    <TableCell className="font-mono text-sm">{"\u20B9"}{order.grand_total?.toLocaleString("en-IN")}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`${PAYMENT_STYLES[order.payment_status || "unpaid"]} text-xs`}>
                        {getPaymentLabel(order.payment_status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`${STATUS_STYLES[order.status]} text-xs uppercase`}>{order.status}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">
                      {new Date(order.created_at).toLocaleDateString("en-IN")}
                    </TableCell>
                    <TableCell>
                      <Link to={`/orders/${order.id}`}>
                        <Button variant="ghost" size="icon" data-testid={`view-all-order-${order.order_number}`}>
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
