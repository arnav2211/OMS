import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { mobilePrintPdf } from "@/lib/mobilePrint";
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
import { Search, RefreshCw, Printer, PackageCheck } from "lucide-react";

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
  const isAdmin = user?.role === "admin";

  const toggleForwardToPackaging = async (orderId, e) => {
    e.stopPropagation();
    try {
      const res = await api.post(`/orders/${orderId}/forward-to-packaging`);
      setOrders(prev => prev.map(o => o.id === orderId ? { ...o, forwarded_to_packaging: res.data.forwarded_to_packaging } : o));
    } catch { toast.error("Failed to update"); }
  };

  useEffect(() => {
    loadOrders();
    if (user?.role === "admin") loadUsers();
  }, [viewAll, selectedTelecaller]);

  const loadUsers = async () => {
    try { const res = await api.get("/users"); setUsers(res.data.filter(u => u.role === "telecaller" || u.role === "admin")); }
    catch { }
  };

  const loadOrders = async () => {
    setLoading(true);
    setSelectedOrders(new Set());
    try {
      const params = new URLSearchParams();
      if (user?.role === "telecaller") {
        params.set("view_all", viewAll ? "true" : "false");
      } else {
        params.set("view_all", "true");
        if (user?.role === "admin" && selectedTelecaller !== "all") params.set("telecaller_id", selectedTelecaller);
      }
      const res = await api.get(`/orders?${params.toString()}`);
      setOrders(res.data);
    } catch { } finally { setLoading(false); }
  };

  const filteredOrders = orders.filter(o => {
    if (statusFilter === "yet_to_dispatch") {
      if (o.status === "dispatched") return false;
    } else if (statusFilter !== "all" && o.status !== statusFilter) return false;
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
      const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
      if (isMobile) {
        mobilePrintPdf(new Blob([res.data], { type: "application/pdf" }), "addresses.pdf");
      } else {
        const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
        const iframe = document.createElement("iframe");
        iframe.style.position = "fixed";
        iframe.style.top = "-10000px";
        iframe.style.left = "-10000px";
        iframe.style.width = "0";
        iframe.style.height = "0";
        iframe.src = blobUrl;
        document.body.appendChild(iframe);
        iframe.onload = () => { setTimeout(() => { iframe.contentWindow.print(); }, 500); };
      }
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
            <div className="relative flex-1 min-w-[140px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Search..." className="pl-9 h-8 text-sm" value={search} onChange={e => setSearch(e.target.value)} data-testid="orders-search-input" />
            </div>
            {/* Period */}
            <Select value={periodFilter} onValueChange={setPeriodFilter}>
              <SelectTrigger className="w-28 sm:w-32 h-8 text-xs" data-testid="period-filter"><SelectValue placeholder="Period" /></SelectTrigger>
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
                <SelectItem value="yet_to_dispatch">Yet to dispatch</SelectItem>
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
              <Table className="min-w-[700px]">
                <TableHeader>
                  <TableRow>
                    {canPrintAddresses && (
                      <TableHead className="w-10">
                        <Checkbox checked={filteredOrders.length > 0 && selectedOrders.size === filteredOrders.length}
                          onCheckedChange={toggleSelectAll} data-testid="select-all-orders-checkbox" />
                      </TableHead>
                    )}
                    <TableHead className="text-xs uppercase whitespace-nowrap">Order #</TableHead>
                    <TableHead className="text-xs uppercase whitespace-nowrap">Customer</TableHead>
                    <TableHead className="text-xs uppercase whitespace-nowrap">Amount</TableHead>
                    <TableHead className="text-xs uppercase whitespace-nowrap">Status</TableHead>
                    <TableHead className="text-xs uppercase whitespace-nowrap">Payment</TableHead>
                    {user?.role === "accounts" && <TableHead className="text-xs uppercase whitespace-nowrap">GST</TableHead>}
                    {user?.role !== "accounts" && <TableHead className="text-xs uppercase whitespace-nowrap">Invoice</TableHead>}
                    {showPaymentCheck && <TableHead className="text-xs uppercase whitespace-nowrap">Check</TableHead>}
                    {user?.role === "admin" && <TableHead className="text-xs uppercase whitespace-nowrap">Executive</TableHead>}
                    <TableHead className="text-xs uppercase whitespace-nowrap">Date</TableHead>
                    <TableHead className="text-xs uppercase whitespace-nowrap">Shipping</TableHead>
                    {isAdmin && <TableHead className="text-xs uppercase whitespace-nowrap">Fwd Pkg</TableHead>}
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
                        <TableCell className="text-sm font-mono whitespace-nowrap">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                        <TableCell><Badge className={`${STATUS_COLORS[o.status] || "bg-gray-100"} text-xs`}>{o.status}</Badge></TableCell>
                        <TableCell><Badge variant="outline" className="text-xs">{o.payment_status}</Badge></TableCell>
                        {user?.role === "accounts" && (
                          <TableCell><Badge variant="outline" className={`text-xs ${o.gst_applicable ? "border-blue-300 text-blue-700" : "border-gray-300 text-gray-500"}`} data-testid={`gst-badge-${o.id}`}>{o.gst_applicable ? "GST" : "Non-GST"}</Badge></TableCell>
                        )}
                        {user?.role !== "accounts" && (
                          <TableCell>
                            {o.gst_applicable ? (
                              <Badge className={`text-xs ${o.tax_invoice_url ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`} data-testid={`invoice-status-${o.id}`}>
                                {o.tax_invoice_url ? "Uploaded" : "Pending"}
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground" data-testid={`invoice-status-${o.id}`}>Not Required</span>
                            )}
                          </TableCell>
                        )}
                        {showPaymentCheck && (
                          <TableCell>
                            <Badge className={`${CHECK_COLORS[checkStatus] || "bg-gray-100"} text-xs`} data-testid={`check-badge-${o.id}`}>
                              {CHECK_LABELS[checkStatus] || "Pending"}
                            </Badge>
                          </TableCell>
                        )}
                        {user?.role === "admin" && <TableCell className="text-sm whitespace-nowrap">{o.telecaller_name || "-"}</TableCell>}
                        <TableCell className="text-sm text-muted-foreground whitespace-nowrap">{new Date(o.created_at).toLocaleDateString("en-IN")}</TableCell>
                        <TableCell className="text-sm whitespace-nowrap" data-testid={`shipping-method-${o.id}`}>
                          {o.shipping_method === "courier" ? (o.courier_name || "Courier") : o.shipping_method === "transport" ? (o.transporter_name || "Transport") : o.shipping_method || "-"}
                        </TableCell>
                        {isAdmin && (
                          <TableCell>
                            <Button
                              variant={o.forwarded_to_packaging ? "default" : "outline"}
                              size="icon"
                              className={`h-7 w-7 ${o.forwarded_to_packaging ? "bg-green-600 hover:bg-green-700" : ""}`}
                              onClick={(e) => toggleForwardToPackaging(o.id, e)}
                              data-testid={`fwd-pkg-${o.id}`}
                              title={o.forwarded_to_packaging ? "Forwarded to Packaging" : "Forward to Packaging"}
                            >
                              <PackageCheck className="w-3.5 h-3.5" />
                            </Button>
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
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
