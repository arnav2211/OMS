import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Search, RefreshCw, Printer } from "lucide-react";

const STATUS_COLORS = {
  new: "bg-blue-100 text-blue-800",
  packaging: "bg-yellow-100 text-yellow-800",
  packed: "bg-green-100 text-green-800",
  dispatched: "bg-purple-100 text-purple-800",
};
const CHECK_COLORS = {
  received: "bg-green-100 text-green-800",
  pending: "bg-yellow-100 text-yellow-800",
  pending_recheck: "bg-red-100 text-red-800",
};
const CHECK_LABELS = { received: "Checked", pending: "Pending", pending_recheck: "Re-check" };

export default function AllOrders() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [payStatusFilter, setPayStatusFilter] = useState("all");
  const [checkStatusFilter, setCheckStatusFilter] = useState("all");
  const [periodFilter, setPeriodFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [viewAll, setViewAll] = useState(false);
  const [users, setUsers] = useState([]);
  const [selectedTelecaller, setSelectedTelecaller] = useState("all");
  const [selectedOrders, setSelectedOrders] = useState(new Set());
  const [printLoading, setPrintLoading] = useState(false);

  const canPrintAddresses = user?.role === "admin" || user?.role === "packaging";
  const showPaymentCheck = ["admin", "telecaller", "accounts"].includes(user?.role);
  const isFieldManager = user?.role === "field_manager";
  const isTelecallerLike = user?.role === "telecaller" || isFieldManager;

  useEffect(() => {
    loadOrders();
    if (user?.role === "admin") loadUsers();
  }, [viewAll, selectedTelecaller]);

  const loadUsers = async () => {
    try { const res = await api.get("/users"); setUsers(res.data.filter(u => u.role === "telecaller" || u.role === "admin" || u.role === "field_manager")); }
    catch { }
  };

  const loadOrders = async () => {
    setLoading(true);
    setSelectedOrders(new Set());
    try {
      const params = new URLSearchParams();
      if (isTelecallerLike) {
        if (isFieldManager) {
          // Field manager always sees own orders only
          params.set("view_all", "false");
        } else {
          params.set("view_all", viewAll ? "true" : "false");
        }
      } else {
        params.set("view_all", "true");
        if (user?.role === "admin" && selectedTelecaller !== "all") params.set("telecaller_id", selectedTelecaller);
      }
      const res = await api.get(`/orders?${params.toString()}`);
      setOrders(res.data);
    } catch { } finally { setLoading(false); }
  };

  const filteredOrders = orders.filter(o => {
    if (statusFilter !== "all" && o.status !== statusFilter) return false;
    if (payStatusFilter !== "all" && o.payment_status !== payStatusFilter) return false;
    if (checkStatusFilter !== "all" && (o.payment_check_status || "pending") !== checkStatusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!o.order_number?.toLowerCase().includes(q) && !o.customer_name?.toLowerCase().includes(q)) return false;
    }
    if (periodFilter !== "all") {
      const now = new Date();
      const orderDate = new Date(o.created_at);
      if (periodFilter === "today") {
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (orderDate < today) return false;
      } else if (periodFilter === "yesterday") {
        const y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
        const ytEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (orderDate < y || orderDate >= ytEnd) return false;
      } else if (periodFilter === "week") {
        const ws = new Date(now); ws.setDate(now.getDate() - now.getDay());
        ws.setHours(0,0,0,0);
        if (orderDate < ws) return false;
      } else if (periodFilter === "month") {
        const ms = new Date(now.getFullYear(), now.getMonth(), 1);
        if (orderDate < ms) return false;
      } else if (periodFilter === "custom" && dateFrom) {
        if (o.created_at < dateFrom) return false;
        if (dateTo && o.created_at > dateTo + "T23:59:59") return false;
      }
    }
    return true;
  });

  const toggleSelect = (id) => {
    setSelectedOrders(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedOrders.size === filteredOrders.length) setSelectedOrders(new Set());
    else setSelectedOrders(new Set(filteredOrders.map(o => o.id)));
  };

  const handlePrintAddresses = async () => {
    if (selectedOrders.size === 0) return toast.error("Select at least one order");
    setPrintLoading(true);
    try {
      const res = await api.post("/orders/print-addresses", { order_ids: [...selectedOrders] }, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      setTimeout(() => window.URL.revokeObjectURL(url), 30000);
    } catch { toast.error("Failed to generate address PDF"); }
    finally { setPrintLoading(false); }
  };

  return (
    <div className="space-y-6" data-testid="all-orders-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">All Orders</h1>
        <div className="flex items-center gap-2">
          {canPrintAddresses && selectedOrders.size > 0 && (
            <Button variant="default" size="sm" onClick={handlePrintAddresses} disabled={printLoading} data-testid="print-addresses-btn">
              <Printer className="w-4 h-4 mr-1" />
              {printLoading ? "Generating..." : `Print Addresses (${selectedOrders.size})`}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={loadOrders} data-testid="refresh-orders"><RefreshCw className="w-4 h-4 mr-1" />Refresh</Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          {/* Filter row */}
          <div className="flex flex-wrap gap-2 items-end">
            <div className="relative flex-1 min-w-[160px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Search..." className="pl-9 h-8 text-sm" value={search} onChange={e => setSearch(e.target.value)} data-testid="orders-search-input" />
            </div>
            {/* Period */}
            <Select value={periodFilter} onValueChange={setPeriodFilter}>
              <SelectTrigger className="w-32 h-8 text-xs" data-testid="period-filter"><SelectValue placeholder="Period" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Time</SelectItem>
                <SelectItem value="today">Today</SelectItem>
                <SelectItem value="yesterday">Yesterday</SelectItem>
                <SelectItem value="week">This Week</SelectItem>
                <SelectItem value="month">This Month</SelectItem>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectContent>
            </Select>
            {periodFilter === "custom" && (
              <>
                <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-36 h-8 text-xs" />
                <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-36 h-8 text-xs" />
              </>
            )}
            {/* Order status */}
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-32 h-8 text-xs" data-testid="status-filter-select"><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="new">New</SelectItem>
                <SelectItem value="packaging">Packaging</SelectItem>
                <SelectItem value="packed">Packed</SelectItem>
                <SelectItem value="dispatched">Dispatched</SelectItem>
              </SelectContent>
            </Select>
            {/* Payment status */}
            <Select value={payStatusFilter} onValueChange={setPayStatusFilter}>
              <SelectTrigger className="w-36 h-8 text-xs" data-testid="pay-status-filter"><SelectValue placeholder="Payment" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Payments</SelectItem>
                <SelectItem value="full">Fully Paid</SelectItem>
                <SelectItem value="partial">Partially Paid</SelectItem>
                <SelectItem value="unpaid">Unpaid</SelectItem>
              </SelectContent>
            </Select>
            {/* Check status — visible to admin/telecaller/accounts */}
            {showPaymentCheck && (
              <Select value={checkStatusFilter} onValueChange={setCheckStatusFilter}>
                <SelectTrigger className="w-36 h-8 text-xs" data-testid="check-status-filter"><SelectValue placeholder="Check Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Checks</SelectItem>
                  <SelectItem value="received">Checked</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="pending_recheck">Pending Re-check</SelectItem>
                </SelectContent>
              </Select>
            )}
            {/* Admin telecaller filter */}
            {user?.role === "admin" && (
              <Select value={selectedTelecaller} onValueChange={setSelectedTelecaller}>
                <SelectTrigger className="w-40 h-8 text-xs" data-testid="executive-filter-select"><SelectValue placeholder="All Executives" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Executives</SelectItem>
                  {users.map(u => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
            {user?.role === "telecaller" && (
              <div className="flex items-center gap-2">
                <Checkbox id="viewAllOrders" checked={viewAll} onCheckedChange={setViewAll} data-testid="view-all-toggle" />
                <Label htmlFor="viewAllOrders" className="cursor-pointer text-sm whitespace-nowrap">Show All</Label>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div></div>
          ) : filteredOrders.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">No orders found</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {canPrintAddresses && (
                      <TableHead className="w-10">
                        <Checkbox checked={filteredOrders.length > 0 && selectedOrders.size === filteredOrders.length}
                          onCheckedChange={toggleSelectAll} data-testid="select-all-orders-checkbox" />
                      </TableHead>
                    )}
                    <TableHead className="text-xs uppercase">Order #</TableHead>
                    <TableHead className="text-xs uppercase">Customer</TableHead>
                    <TableHead className="text-xs uppercase hidden sm:table-cell">Amount</TableHead>
                    <TableHead className="text-xs uppercase">Status</TableHead>
                    <TableHead className="text-xs uppercase hidden sm:table-cell">Payment</TableHead>
                    {showPaymentCheck && <TableHead className="text-xs uppercase hidden md:table-cell">Check</TableHead>}
                    {user?.role === "admin" && <TableHead className="text-xs uppercase hidden lg:table-cell">Executive</TableHead>}
                    <TableHead className="text-xs uppercase hidden sm:table-cell">Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredOrders.map(o => {
                    const checkStatus = o.payment_check_status || "pending";
                    return (
                      <TableRow key={o.id} data-testid={`order-row-${o.id}`} className={selectedOrders.has(o.id) ? "bg-primary/5" : ""}>
                        {canPrintAddresses && (
                          <TableCell>
                            <Checkbox checked={selectedOrders.has(o.id)} onCheckedChange={() => toggleSelect(o.id)} data-testid={`select-order-${o.id}`} />
                          </TableCell>
                        )}
                        <TableCell>
                          <Link to={`/orders/${o.id}`} className="font-mono text-sm font-medium text-primary hover:underline" data-testid={`order-link-${o.id}`}>
                            {o.order_number}
                          </Link>
                        </TableCell>
                        <TableCell className="text-sm">{o.customer_name}</TableCell>
                        <TableCell className="text-sm font-mono hidden sm:table-cell">₹{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                        <TableCell><Badge className={`${STATUS_COLORS[o.status] || "bg-gray-100"} text-xs`}>{o.status}</Badge></TableCell>
                        <TableCell className="hidden sm:table-cell"><Badge variant="outline" className="text-xs">{o.payment_status}</Badge></TableCell>
                        {showPaymentCheck && (
                          <TableCell className="hidden md:table-cell">
                            <Badge className={`${CHECK_COLORS[checkStatus] || "bg-gray-100"} text-xs`} data-testid={`check-badge-${o.id}`}>
                              {CHECK_LABELS[checkStatus] || "Pending"}
                            </Badge>
                          </TableCell>
                        )}
                        {user?.role === "admin" && <TableCell className="text-sm hidden lg:table-cell">{o.telecaller_name || "-"}</TableCell>}
                        <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">{new Date(o.created_at).toLocaleDateString("en-IN")}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>{selectedOrders.size > 0 ? `${selectedOrders.size} selected` : ""}</span>
            <span>{filteredOrders.length} order(s)</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
