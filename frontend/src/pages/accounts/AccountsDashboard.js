import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";
import { Upload, Trash2, FileText, CheckCircle, Clock, RefreshCw, AlertTriangle, BanknoteIcon, Eye, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const PERIODS = [
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "all", label: "All Time" },
  { value: "custom", label: "Custom Range" },
];

const CHECK_BADGE = {
  pending: { label: "Pending", cls: "bg-yellow-100 text-yellow-800" },
  received: { label: "Received", cls: "bg-green-100 text-green-800" },
  pending_recheck: { label: "Re-check", cls: "bg-red-100 text-red-800" },
};

function MetricCard({ icon: Icon, label, value, sub, iconCls }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-lg ${iconCls}`}><Icon className="w-5 h-5" /></div>
          <div>
            <p className="text-2xl font-bold">{value ?? "—"}</p>
            <p className="text-sm text-muted-foreground">{label}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function AccountsDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useState("invoices");
  const [period, setPeriod] = useState("today");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [stats, setStats] = useState(null);

  // Invoice tab state
  const [gstOrders, setGstOrders] = useState([]);
  const [invoiceLoading, setInvoiceLoading] = useState(true);
  const [uploading, setUploading] = useState({});
  const [invoiceFilter, setInvoiceFilter] = useState("all");

  // Payment check tab state
  const [allOrders, setAllOrders] = useState([]);
  const [paymentLoading, setPaymentLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [payStatusFilter, setPayStatusFilter] = useState("all");
  const [checkStatusFilter, setCheckStatusFilter] = useState("all");
  const [payPeriod, setPayPeriod] = useState("all");
  const [payDateFrom, setPayDateFrom] = useState("");
  const [payDateTo, setPayDateTo] = useState("");
  const [updating, setUpdating] = useState({});
  const [previewScreenshots, setPreviewScreenshots] = useState(null);

  useEffect(() => { loadStats(); }, [period, dateFrom, dateTo]);
  useEffect(() => { if (tab === "invoices") loadGstOrders(); }, [tab]);
  useEffect(() => { if (tab === "payment") loadAllOrders(); }, [tab]);

  const loadStats = async () => {
    try {
      const params = new URLSearchParams({ period });
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await api.get(`/reports/accounts-dashboard?${params}`);
      setStats(res.data);
    } catch { }
  };

  const loadGstOrders = async () => {
    setInvoiceLoading(true);
    try {
      const res = await api.get("/orders?view_all=true");
      setGstOrders(res.data.filter(o => o.gst_applicable));
    } catch { } finally { setInvoiceLoading(false); }
  };

  const loadAllOrders = async () => {
    setPaymentLoading(true);
    try {
      const res = await api.get("/orders?view_all=true");
      setAllOrders(res.data);
    } catch { } finally { setPaymentLoading(false); }
  };

  const handleInvoiceUpload = async (orderId, file) => {
    if (!file) return;
    if (file.type !== "application/pdf") return toast.error("Only PDF files are allowed");
    setUploading(p => ({ ...p, [orderId]: true }));
    try {
      const form = new FormData();
      form.append("file", file);
      const uploadRes = await api.post("/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      await api.put(`/orders/${orderId}/invoice`, { invoice_url: uploadRes.data.url });
      toast.success("Invoice uploaded");
      loadGstOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Upload failed"); }
    finally { setUploading(p => ({ ...p, [orderId]: false })); }
  };

  const handleInvoiceDelete = async (orderId) => {
    try {
      await api.delete(`/orders/${orderId}/invoice`);
      toast.success("Invoice removed");
      loadGstOrders();
    } catch { toast.error("Failed to remove"); }
  };

  const updatePaymentCheck = async (orderId, status) => {
    setUpdating(p => ({ ...p, [orderId]: true }));
    try {
      await api.put(`/orders/${orderId}/payment-check`, { payment_check_status: status });
      toast.success("Payment status updated");
      setAllOrders(prev => prev.map(o => o.id === orderId ? { ...o, payment_check_status: status } : o));
    } catch { toast.error("Failed to update"); }
    finally { setUpdating(p => ({ ...p, [orderId]: false })); }
  };

  const filteredAllOrders = allOrders.filter(o => {
    // Hide unpaid orders — nothing to check
    if (o.payment_status === "unpaid") return false;
    if (payStatusFilter !== "all") {
      const map = { "fully_paid": "full", "partial": "partial", "unpaid": "unpaid" };
      if (o.payment_status !== (map[payStatusFilter] || payStatusFilter)) return false;
    }
    if (checkStatusFilter !== "all" && o.payment_check_status !== checkStatusFilter) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      if (!o.order_number?.toLowerCase().includes(q) && !o.customer_name?.toLowerCase().includes(q)) return false;
    }
    // Date filter based on order creation date
    if (payPeriod !== "all") {
      const orderDate = new Date(o.created_at);
      const now = new Date();
      if (payPeriod === "today") {
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (orderDate < start) return false;
      } else if (payPeriod === "week") {
        const start = new Date(now);
        start.setDate(now.getDate() - now.getDay());
        start.setHours(0, 0, 0, 0);
        if (orderDate < start) return false;
      } else if (payPeriod === "month") {
        const start = new Date(now.getFullYear(), now.getMonth(), 1);
        if (orderDate < start) return false;
      } else if (payPeriod === "custom") {
        if (payDateFrom && orderDate < new Date(payDateFrom)) return false;
        if (payDateTo) {
          const endDate = new Date(payDateTo);
          endDate.setHours(23, 59, 59, 999);
          if (orderDate > endDate) return false;
        }
      }
    }
    return true;
  });

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <div className="space-y-6" data-testid="accounts-dashboard">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Accounts Dashboard</h1>
        <div className="flex items-center gap-2">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
            <SelectContent>{PERIODS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
          </Select>
          {period === "custom" && (
            <>
              <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-36" />
              <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-36" />
            </>
          )}
        </div>
      </div>

      {/* Metrics */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <MetricCard icon={FileText} label="Invoices Uploaded" value={stats.total_invoices} iconCls="bg-blue-100 text-blue-700" />
          <MetricCard icon={AlertTriangle} label="GST Without Invoice" value={stats.gst_without_invoice} iconCls="bg-orange-100 text-orange-700" />
          <MetricCard icon={CheckCircle} label="Payments Received" value={stats.payments_received} iconCls="bg-green-100 text-green-700" />
          <MetricCard icon={Clock} label="Payments Pending" value={stats.payments_pending} iconCls="bg-yellow-100 text-yellow-700" />
          <MetricCard icon={FileText} label="GST Orders Total" value={stats.gst_total} iconCls="bg-purple-100 text-purple-700" />
          <MetricCard icon={BanknoteIcon} label="Unpaid Orders" value={stats.unpaid_orders} iconCls="bg-red-100 text-red-700" />
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-4">
          <TabsTrigger value="invoices" data-testid="tab-invoices">Tax Invoices (GST Orders)</TabsTrigger>
          <TabsTrigger value="payment" data-testid="tab-payment">Payment Check (All Orders)</TabsTrigger>
        </TabsList>

        {/* ── INVOICES TAB ─────────────────────────────────── */}
        <TabsContent value="invoices">
          <Card>
            <CardHeader className="pb-3 flex flex-row items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-base">GST Orders — Invoice Management</CardTitle>
              <div className="flex items-center gap-2">
                <Select value={invoiceFilter} onValueChange={setInvoiceFilter}>
                  <SelectTrigger className="w-40 h-8 text-xs" data-testid="invoice-filter"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Invoices</SelectItem>
                    <SelectItem value="uploaded">Uploaded</SelectItem>
                    <SelectItem value="pending">Pending Upload</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={loadGstOrders}><RefreshCw className="w-4 h-4 mr-1" />Refresh</Button>
              </div>
            </CardHeader>
            <CardContent>
              {invoiceLoading ? (
                <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div></div>
              ) : (
                  <Table className="min-w-[600px]">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="whitespace-nowrap">Order #</TableHead>
                        <TableHead className="whitespace-nowrap">Customer</TableHead>
                        <TableHead className="whitespace-nowrap">Amount</TableHead>
                        <TableHead className="whitespace-nowrap">Status</TableHead>
                        <TableHead className="whitespace-nowrap">Invoice</TableHead>
                        <TableHead className="whitespace-nowrap">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {gstOrders.length === 0 && (
                        <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No GST orders found</TableCell></TableRow>
                      )}
                      {gstOrders.filter(o => {
                        if (invoiceFilter === "uploaded") return !!o.tax_invoice_url;
                        if (invoiceFilter === "pending") return !o.tax_invoice_url;
                        return true;
                      }).map(o => (
                        <TableRow key={o.id} data-testid={`invoice-row-${o.id}`}>
                          <TableCell>
                            <Link to={`/orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.order_number}</Link>
                          </TableCell>
                          <TableCell className="text-sm">{o.customer_name}</TableCell>
                          <TableCell className="text-sm font-mono">₹{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                          <TableCell><Badge className="text-xs">{o.status}</Badge></TableCell>
                          <TableCell>
                            {o.tax_invoice_url ? (
                              <a href={`${backendUrl}${o.tax_invoice_url}`} target="_blank" rel="noopener noreferrer"
                                className="text-xs text-primary hover:underline flex items-center gap-1">
                                <FileText className="w-3 h-3" /> View Invoice
                              </a>
                            ) : (
                              <span className="text-xs text-muted-foreground">Not uploaded</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <label className="cursor-pointer">
                                <Button variant="outline" size="sm" asChild disabled={uploading[o.id]}>
                                  <span data-testid={`upload-invoice-${o.id}`}>
                                    <Upload className="w-3 h-3 mr-1" />
                                    {uploading[o.id] ? "Uploading..." : o.tax_invoice_url ? "Replace" : "Upload PDF"}
                                  </span>
                                </Button>
                                <input type="file" accept=".pdf,application/pdf" className="sr-only" disabled={uploading[o.id]}
                                  onChange={e => { if (e.target.files[0]) handleInvoiceUpload(o.id, e.target.files[0]); e.target.value = ""; }} />
                              </label>
                              {o.tax_invoice_url && (
                                <Button variant="ghost" size="icon" onClick={() => handleInvoiceDelete(o.id)} data-testid={`delete-invoice-${o.id}`}>
                                  <Trash2 className="w-3 h-3 text-destructive" />
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── PAYMENT CHECK TAB ─────────────────────────────── */}
        <TabsContent value="payment">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap gap-3 items-end justify-between">
                <CardTitle className="text-base">Payment Verification — All Orders</CardTitle>
                <div className="flex flex-wrap gap-2">
                  <Input placeholder="Search..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} className="w-40 h-8 text-sm" />
                  <Select value={payStatusFilter} onValueChange={setPayStatusFilter}>
                    <SelectTrigger className="w-36 h-8 text-xs"><SelectValue placeholder="Payment Status" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Payments</SelectItem>
                      <SelectItem value="full">Fully Paid</SelectItem>
                      <SelectItem value="partial">Partially Paid</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={checkStatusFilter} onValueChange={setCheckStatusFilter}>
                    <SelectTrigger className="w-36 h-8 text-xs"><SelectValue placeholder="Check Status" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Checks</SelectItem>
                      <SelectItem value="received">Checked</SelectItem>
                      <SelectItem value="pending">Pending</SelectItem>
                      <SelectItem value="pending_recheck">Pending Re-check</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={payPeriod} onValueChange={setPayPeriod}>
                    <SelectTrigger className="w-32 h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Time</SelectItem>
                      <SelectItem value="today">Today</SelectItem>
                      <SelectItem value="week">This Week</SelectItem>
                      <SelectItem value="month">This Month</SelectItem>
                      <SelectItem value="custom">Custom</SelectItem>
                    </SelectContent>
                  </Select>
                  {payPeriod === "custom" && (
                    <>
                      <Input type="date" value={payDateFrom} onChange={e => setPayDateFrom(e.target.value)} className="w-36 h-8 text-sm" />
                      <Input type="date" value={payDateTo} onChange={e => setPayDateTo(e.target.value)} className="w-36 h-8 text-sm" />
                    </>
                  )}
                  <Button variant="outline" size="sm" onClick={loadAllOrders}><RefreshCw className="w-3 h-3" /></Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {paymentLoading ? (
                <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div></div>
              ) : (
                  <Table className="min-w-[900px]">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="whitespace-nowrap">Order #</TableHead>
                        <TableHead className="whitespace-nowrap">Customer</TableHead>
                        <TableHead className="whitespace-nowrap">Date</TableHead>
                        <TableHead className="whitespace-nowrap">Amount</TableHead>
                        <TableHead className="whitespace-nowrap">Payment</TableHead>
                        <TableHead className="whitespace-nowrap">Mode</TableHead>
                        <TableHead className="whitespace-nowrap">GST</TableHead>
                        <TableHead className="whitespace-nowrap">Proof</TableHead>
                        <TableHead className="whitespace-nowrap">Check Status</TableHead>
                        <TableHead className="whitespace-nowrap">Checked By</TableHead>
                        <TableHead className="whitespace-nowrap">Action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredAllOrders.length === 0 && (
                        <TableRow><TableCell colSpan={11} className="text-center text-muted-foreground py-8">No orders found</TableCell></TableRow>
                      )}
                      {filteredAllOrders.map(o => {
                        const checkInfo = CHECK_BADGE[o.payment_check_status || "pending"] || CHECK_BADGE.pending;
                        return (
                          <TableRow key={o.id} data-testid={`payment-row-${o.id}`}>
                            <TableCell>
                              <Link to={`/orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.order_number}</Link>
                            </TableCell>
                            <TableCell className="text-sm">{o.customer_name}</TableCell>
                            <TableCell className="text-sm whitespace-nowrap" data-testid={`order-date-${o.id}`}>{new Date(o.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}</TableCell>
                            <TableCell className="text-sm font-mono">₹{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                            <TableCell><Badge variant="outline" className="text-xs">{o.payment_status}</Badge></TableCell>
                            <TableCell className="text-sm" data-testid={`pay-mode-${o.id}`}>{o.mode_of_payment || "—"}{o.payment_mode_details ? ` (${o.payment_mode_details})` : ""}</TableCell>
                            <TableCell data-testid={`gst-flag-${o.id}`}><Badge variant="outline" className={`text-xs ${o.gst_applicable ? "bg-blue-50 text-blue-700 border-blue-200" : ""}`}>{o.gst_applicable ? "GST" : "Non-GST"}</Badge></TableCell>
                            <TableCell>
                              {o.payment_screenshots?.length > 0 ? (
                                <Button variant="outline" size="sm" className="text-xs h-7" onClick={() => setPreviewScreenshots(o.payment_screenshots)} data-testid={`preview-proof-${o.id}`}>
                                  <Eye className="w-3 h-3 mr-1" />{o.payment_screenshots.length}
                                </Button>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </TableCell>
                            <TableCell>
                              <Badge className={`text-xs ${checkInfo.cls}`} data-testid={`check-status-${o.id}`}>{checkInfo.label}</Badge>
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">{o.payment_checked_by || "—"}</TableCell>
                            <TableCell>
                              <div className="flex gap-1">
                                {o.payment_check_status !== "received" && (
                                  <Button variant="outline" size="sm" className="text-xs h-7 text-green-700 border-green-300 hover:bg-green-50"
                                    onClick={() => updatePaymentCheck(o.id, "received")}
                                    disabled={updating[o.id]} data-testid={`mark-received-${o.id}`}>
                                    Mark Received
                                  </Button>
                                )}
                                {o.payment_check_status === "received" && (
                                  <Button variant="outline" size="sm" className="text-xs h-7 text-yellow-700 border-yellow-300 hover:bg-yellow-50"
                                    onClick={() => updatePaymentCheck(o.id, "pending")}
                                    disabled={updating[o.id]} data-testid={`mark-pending-${o.id}`}>
                                    Mark Pending
                                  </Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
              )}
              {filteredAllOrders.length > 0 && (
                <p className="text-sm text-muted-foreground mt-3 text-right">{filteredAllOrders.length} order(s)</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Payment Screenshot Preview Dialog */}
      <Dialog open={!!previewScreenshots} onOpenChange={() => setPreviewScreenshots(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Payment Screenshots</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            {previewScreenshots?.map((url, i) => (
              <a key={i} href={`${backendUrl}${url}`} target="_blank" rel="noopener noreferrer">
                <img src={`${backendUrl}${url}`} alt={`Payment proof ${i + 1}`} className="w-full rounded-lg border object-cover aspect-square hover:opacity-80 transition-opacity" />
              </a>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
