import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import {
  BarChart3, Users, Settings, ShoppingCart, IndianRupee, Package, TrendingUp,
  Eye, EyeOff, UserPlus, UserX, Trash2, RefreshCw, ChevronDown, CheckCircle, ShieldCheck,
} from "lucide-react";

const PERIOD_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "custom", label: "Custom Range" },
];

const EXEC_PERF_PERIODS = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "custom", label: "Custom Date" },
];

export default function AdminDashboard() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("analytics");
  const [analytics, setAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [period, setPeriod] = useState("month");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [excludeGst, setExcludeGst] = useState(false);
  const [excludeShipping, setExcludeShipping] = useState(false);
  const [recentOrders, setRecentOrders] = useState([]);
  const [users, setUsers] = useState([]);
  const [showUserDialog, setShowUserDialog] = useState(false);
  const [newUser, setNewUser] = useState({ username: "", password: "", name: "", role: "telecaller" });
  const [showFormulation, setShowFormulation] = useState(false);
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [newStaffName, setNewStaffName] = useState("");

  // Executive reports
  const [executiveReport, setExecutiveReport] = useState(null);
  const [selectedExec, setSelectedExec] = useState(null);
  const [execPeriod, setExecPeriod] = useState("month");
  const [execDateFrom, setExecDateFrom] = useState("");
  const [execDateTo, setExecDateTo] = useState("");
  const [execExcludeGst, setExecExcludeGst] = useState(false);
  const [execExcludeShipping, setExecExcludeShipping] = useState(false);

  // Executive Performance (inside Analytics tab)
  const [execPerfPeriod, setExecPerfPeriod] = useState("today");
  const [execPerfDateFrom, setExecPerfDateFrom] = useState("");
  const [execPerfDateTo, setExecPerfDateTo] = useState("");
  const [execPerfData, setExecPerfData] = useState(null);

  // Admin self report
  const [adminReport, setAdminReport] = useState(null);
  const [adminPeriod, setAdminPeriod] = useState("month");
  const [adminDateFrom, setAdminDateFrom] = useState("");
  const [adminDateTo, setAdminDateTo] = useState("");
  const [adminExcludeGst, setAdminExcludeGst] = useState(false);
  const [adminExcludeShipping, setAdminExcludeShipping] = useState(false);

  // Payment-received sales
  const [paymentSalesPeriod, setPaymentSalesPeriod] = useState("today");
  const [paymentSalesData, setPaymentSalesData] = useState(null);
  const [paymentSalesExGst, setPaymentSalesExGst] = useState(false);
  const [paymentSalesExShip, setPaymentSalesExShip] = useState(false);
  const [paymentSalesDateFrom, setPaymentSalesDateFrom] = useState("");
  const [paymentSalesDateTo, setPaymentSalesDateTo] = useState("");
  const [paymentSalesExecId, setPaymentSalesExecId] = useState("");
  const [editPermissions, setEditPermissions] = useState([]);

  useEffect(() => { loadAnalytics(); loadRecentOrders(); loadUsers(); loadSettings(); loadPackagingStaff(); loadExecPerf(); loadEditPermissions(); }, []);
  useEffect(() => { loadAnalytics(); }, [period, dateFrom, dateTo, excludeGst, excludeShipping]);
  useEffect(() => { loadExecPerf(); }, [execPerfPeriod, execPerfDateFrom, execPerfDateTo]);
  useEffect(() => { if (activeTab === "edit-requests") loadEditPermissions(); }, [activeTab]);
  useEffect(() => { if (selectedExec) loadExecReport(selectedExec); }, [execExcludeGst, execExcludeShipping, execDateFrom, execDateTo]);

  const loadAnalytics = async () => {
    setAnalyticsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("period", period);
      params.set("exclude_gst", excludeGst.toString());
      params.set("exclude_shipping", excludeShipping.toString());
      if (period === "custom") {
        if (dateFrom) params.set("date_from", dateFrom);
        if (dateTo) params.set("date_to", dateTo);
      }
      const res = await api.get(`/reports/admin-analytics?${params.toString()}`);
      setAnalytics(res.data);
    } catch { } finally { setAnalyticsLoading(false); }
  };

  const loadExecPerf = async () => {
    try {
      const params = new URLSearchParams();
      params.set("period", execPerfPeriod);
      if (execPerfPeriod === "custom") {
        if (execPerfDateFrom) params.set("date_from", execPerfDateFrom);
        if (execPerfDateTo) params.set("date_to", execPerfDateTo);
      }
      const res = await api.get(`/reports/admin-analytics?${params.toString()}`);
      setExecPerfData(res.data);
    } catch { }
  };

  const loadRecentOrders = async () => {
    try { const res = await api.get("/orders?view_all=true&page_size=10"); setRecentOrders(res.data.orders || []); }
    catch { }
  };

  const loadUsers = async () => {
    try { const res = await api.get("/users"); setUsers(res.data); } catch { }
  };

  const loadSettings = async () => {
    try { const res = await api.get("/settings"); setShowFormulation(res.data.show_formulation || false); }
    catch { }
  };

  const loadPackagingStaff = async () => {
    try { const res = await api.get("/packaging-staff"); setPackagingStaff(res.data); }
    catch { }
  };

  const toggleFormulation = async () => {
    try {
      const val = !showFormulation;
      await api.put("/settings", { show_formulation: val });
      setShowFormulation(val);
      toast.success(`Formulations ${val ? "visible" : "hidden"} for packaging`);
    } catch { toast.error("Failed"); }
  };

  const createUser = async () => {
    if (!newUser.username || !newUser.password || !newUser.name) return toast.error("All fields required");
    try {
      await api.post("/users", newUser);
      toast.success("User created"); setShowUserDialog(false); loadUsers();
      setNewUser({ username: "", password: "", name: "", role: "telecaller" });
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const toggleUserActive = async (u) => {
    try {
      await api.put(`/users/${u.id}`, { active: !u.active });
      toast.success(`User ${u.active ? "deactivated" : "activated"}`); loadUsers();
    } catch { toast.error("Failed"); }
  };

  const addStaff = async () => {
    if (!newStaffName) return;
    try { await api.post("/packaging-staff", { name: newStaffName }); setNewStaffName(""); loadPackagingStaff(); toast.success("Staff added"); }
    catch { toast.error("Failed"); }
  };

  const toggleStaffActive = async (s) => {
    try { await api.put(`/packaging-staff/${s.id}`, { active: !s.active }); loadPackagingStaff(); }
    catch { }
  };

  const deleteStaff = async (s) => {
    try { await api.delete(`/packaging-staff/${s.id}`); loadPackagingStaff(); toast.success("Removed"); }
    catch { }
  };

  // Load executive report
  const loadExecReport = async (execId, overridePeriod) => {
    setSelectedExec(execId);
    const period = overridePeriod !== undefined ? overridePeriod : execPeriod;
    try {
      const params = new URLSearchParams();
      params.set("telecaller_id", execId);
      if (period === "custom") {
        if (execDateFrom) params.set("date_from", execDateFrom);
        if (execDateTo) params.set("date_to", execDateTo);
      } else {
        params.set("period", period);
      }
      params.set("exclude_gst", execExcludeGst.toString());
      params.set("exclude_shipping", execExcludeShipping.toString());
      const res = await api.get(`/reports/telecaller-sales?${params.toString()}`);
      setExecutiveReport(res.data);
    } catch { toast.error("Failed to load report"); }
  };

  // Load admin self report
  const loadAdminReport = async () => {
    try {
      const params = new URLSearchParams();
      params.set("telecaller_id", user.id);
      if (adminPeriod === "custom") {
        if (adminDateFrom) params.set("date_from", adminDateFrom);
        if (adminDateTo) params.set("date_to", adminDateTo);
      } else {
        params.set("period", adminPeriod);
      }
      params.set("exclude_gst", adminExcludeGst.toString());
      params.set("exclude_shipping", adminExcludeShipping.toString());
      const res = await api.get(`/reports/telecaller-sales?${params.toString()}`);
      setAdminReport(res.data);
    } catch { }
  };

  useEffect(() => { if (activeTab === "my-report") loadAdminReport(); }, [activeTab, adminPeriod, adminDateFrom, adminDateTo, adminExcludeGst, adminExcludeShipping]);

  // Load payment-received sales
  const loadPaymentSales = async () => {
    try {
      const params = new URLSearchParams();
      params.set("period", paymentSalesPeriod);
      params.set("exclude_gst", paymentSalesExGst.toString());
      params.set("exclude_shipping", paymentSalesExShip.toString());
      if (paymentSalesExecId) params.set("telecaller_id", paymentSalesExecId);
      if (paymentSalesPeriod === "custom") {
        if (paymentSalesDateFrom) params.set("date_from", paymentSalesDateFrom);
        if (paymentSalesDateTo) params.set("date_to", paymentSalesDateTo);
      }
      const res = await api.get(`/reports/payment-sales?${params.toString()}`);
      setPaymentSalesData(res.data);
    } catch {}
  };

  useEffect(() => { if (activeTab === "payment-sales") loadPaymentSales(); }, [activeTab, paymentSalesPeriod, paymentSalesExGst, paymentSalesExShip, paymentSalesDateFrom, paymentSalesDateTo, paymentSalesExecId]);

  const STATUS_COLORS = { new: "bg-blue-100 text-blue-800", packaging: "bg-yellow-100 text-yellow-800", packed: "bg-green-100 text-green-800", dispatched: "bg-purple-100 text-purple-800" };

  const loadEditPermissions = async () => {
    try {
      const res = await api.get("/edit-permissions");
      setEditPermissions(res.data || []);
    } catch { /* ignore */ }
  };

  const handleEditPermission = async (permId, action) => {
    try {
      await api.put(`/edit-permissions/${permId}`, { action });
      toast.success(action === "approve" ? "Edit permission approved" : "Edit request rejected");
      loadEditPermissions();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-6" data-testid="admin-dashboard">
      <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Admin Dashboard</h1>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="overflow-x-auto pb-1">
          <TabsList className="inline-flex w-auto min-w-full sm:w-full">
            <TabsTrigger value="analytics" data-testid="tab-analytics" className="text-xs sm:text-sm whitespace-nowrap"><BarChart3 className="w-4 h-4 mr-1 hidden sm:inline" /> Analytics</TabsTrigger>
            <TabsTrigger value="my-report" data-testid="tab-my-report" className="text-xs sm:text-sm whitespace-nowrap"><TrendingUp className="w-4 h-4 mr-1 hidden sm:inline" /> My Report</TabsTrigger>
            <TabsTrigger value="exec-reports" data-testid="tab-exec-reports" className="text-xs sm:text-sm whitespace-nowrap"><Users className="w-4 h-4 mr-1 hidden sm:inline" /> Exec Reports</TabsTrigger>
            <TabsTrigger value="payment-sales" data-testid="tab-payment-sales" className="text-xs sm:text-sm whitespace-nowrap"><CheckCircle className="w-4 h-4 mr-1 hidden sm:inline" /> Payments</TabsTrigger>
            <TabsTrigger value="users" data-testid="tab-users" className="text-xs sm:text-sm whitespace-nowrap"><Users className="w-4 h-4 mr-1 hidden sm:inline" /> Users</TabsTrigger>
            <TabsTrigger value="edit-requests" data-testid="tab-edit-requests" className="text-xs sm:text-sm whitespace-nowrap"><ShieldCheck className="w-4 h-4 mr-1 hidden sm:inline" /> Edit Requests{editPermissions.filter(p => p.status === "pending").length > 0 && <span className="ml-1 bg-red-500 text-white text-xs rounded-full px-1.5">{editPermissions.filter(p => p.status === "pending").length}</span>}</TabsTrigger>
            <TabsTrigger value="settings" data-testid="tab-settings" className="text-xs sm:text-sm whitespace-nowrap"><Settings className="w-4 h-4 mr-1 hidden sm:inline" /> Settings</TabsTrigger>
          </TabsList>
        </div>

        {/* Analytics Tab */}
        <TabsContent value="analytics" className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap gap-2 sm:gap-3 items-end">
                <div>
                  <Label className="text-xs">Period</Label>
                  <Select value={period} onValueChange={setPeriod}>
                    <SelectTrigger className="w-28 sm:w-36" data-testid="analytics-period"><SelectValue /></SelectTrigger>
                    <SelectContent>{PERIOD_OPTIONS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {period === "custom" && (
                  <>
                    <div><Label className="text-xs">From</Label><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-36" /></div>
                    <div><Label className="text-xs">To</Label><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-36" /></div>
                  </>
                )}
                <div className="flex items-center gap-2"><Checkbox id="exGst" checked={excludeGst} onCheckedChange={setExcludeGst} data-testid="exclude-gst" /><Label htmlFor="exGst" className="text-xs cursor-pointer">Excl. GST</Label></div>
                <div className="flex items-center gap-2"><Checkbox id="exShip" checked={excludeShipping} onCheckedChange={setExcludeShipping} data-testid="exclude-shipping" /><Label htmlFor="exShip" className="text-xs cursor-pointer">Excl. Shipping</Label></div>
              </div>
            </CardHeader>
          </Card>

          {analyticsLoading ? <p className="text-center py-8 text-muted-foreground">Loading analytics...</p> : analytics && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
                <Card><CardContent className="pt-4 sm:pt-6 text-center">
                  <ShoppingCart className="w-6 h-6 sm:w-8 sm:h-8 mx-auto text-blue-500 mb-1 sm:mb-2" />
                  <p className="text-lg sm:text-2xl font-bold" data-testid="total-orders">{analytics.total_orders}</p>
                  <p className="text-[10px] sm:text-xs text-muted-foreground">Total Orders</p>
                </CardContent></Card>
                <Card><CardContent className="pt-4 sm:pt-6 text-center">
                  <IndianRupee className="w-6 h-6 sm:w-8 sm:h-8 mx-auto text-green-500 mb-1 sm:mb-2" />
                  <p className="text-lg sm:text-2xl font-bold" data-testid="total-revenue">{"\u20B9"}{analytics.total_revenue?.toLocaleString("en-IN")}</p>
                  <p className="text-[10px] sm:text-xs text-muted-foreground">Total Revenue</p>
                </CardContent></Card>
                <Card><CardContent className="pt-4 sm:pt-6 text-center">
                  <TrendingUp className="w-6 h-6 sm:w-8 sm:h-8 mx-auto text-emerald-500 mb-1 sm:mb-2" />
                  <p className="text-lg sm:text-2xl font-bold" data-testid="product-sales">{"\u20B9"}{analytics.product_sales?.toLocaleString("en-IN")}</p>
                  <p className="text-[10px] sm:text-xs text-muted-foreground">Product Sales</p>
                </CardContent></Card>
                <Card><CardContent className="pt-4 sm:pt-6 text-center">
                  <Package className="w-6 h-6 sm:w-8 sm:h-8 mx-auto text-purple-500 mb-1 sm:mb-2" />
                  <p className="text-lg sm:text-2xl font-bold">{analytics.status_counts?.dispatched || 0}</p>
                  <p className="text-[10px] sm:text-xs text-muted-foreground">Dispatched</p>
                </CardContent></Card>
              </div>

              {/* Status Breakdown */}
              <Card>
                <CardHeader className="pb-3"><CardTitle className="text-base">Order Status Breakdown</CardTitle></CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-4">
                    {Object.entries(analytics.status_counts || {}).map(([status, count]) => (
                      <div key={status} className="flex items-center gap-2">
                        <Badge className={`${STATUS_COLORS[status] || 'bg-gray-100'} text-xs`}>{status}</Badge>
                        <span className="font-mono text-sm font-bold">{count}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Per-Executive Breakdown */}
              {analytics.telecaller_stats?.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <div className="flex flex-wrap items-end justify-between gap-2">
                      <CardTitle className="text-base">Executive Performance</CardTitle>
                      <div className="flex flex-wrap gap-2 items-end">
                        <Select value={execPerfPeriod} onValueChange={setExecPerfPeriod}>
                          <SelectTrigger className="w-36 h-8 text-xs" data-testid="exec-perf-period"><SelectValue /></SelectTrigger>
                          <SelectContent>{EXEC_PERF_PERIODS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
                        </Select>
                        {execPerfPeriod === "custom" && (
                          <>
                            <Input type="date" value={execPerfDateFrom} onChange={e => setExecPerfDateFrom(e.target.value)} className="w-32 h-8 text-xs" />
                            <Input type="date" value={execPerfDateTo} onChange={e => setExecPerfDateTo(e.target.value)} className="w-32 h-8 text-xs" />
                          </>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader><TableRow>
                        <TableHead className="text-xs">Executive</TableHead>
                        <TableHead className="text-xs text-right">Orders</TableHead>
                        <TableHead className="text-xs text-right">Revenue</TableHead>
                      </TableRow></TableHeader>
                      <TableBody>
                        {(execPerfData?.telecaller_stats || []).length === 0 && (
                          <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground text-sm py-4">No orders for this period</TableCell></TableRow>
                        )}
                        {(execPerfData?.telecaller_stats || []).map(t => (
                          <TableRow key={t.id}>
                            <TableCell className="text-sm font-medium">{t.name}</TableCell>
                            <TableCell className="text-sm text-right font-mono" data-testid={`exec-perf-orders-${t.id}`}>{t.order_count}</TableCell>
                            <TableCell className="text-sm text-right font-mono" data-testid={`exec-perf-revenue-${t.id}`}>{"\u20B9"}{t.total_amount?.toLocaleString("en-IN")}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {/* Recent Orders */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Recent Orders</CardTitle>
                <Link to="/orders"><Button variant="outline" size="sm">View All</Button></Link>
              </div>
            </CardHeader>
            <CardContent>
              {recentOrders.length === 0 ? <p className="text-center py-4 text-muted-foreground">No orders yet</p> : (
                <Table className="min-w-[500px]">
                  <TableHeader><TableRow>
                    <TableHead className="text-xs whitespace-nowrap">Order #</TableHead>
                    <TableHead className="text-xs whitespace-nowrap">Customer</TableHead>
                    <TableHead className="text-xs text-right whitespace-nowrap">Amount</TableHead>
                    <TableHead className="text-xs whitespace-nowrap">Status</TableHead>
                    <TableHead className="text-xs whitespace-nowrap">Executive</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {recentOrders.map(o => (
                      <TableRow key={o.id}>
                        <TableCell><Link to={`/orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.order_number}</Link></TableCell>
                        <TableCell className="text-sm">{o.customer_name}</TableCell>
                        <TableCell className="text-sm text-right font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                        <TableCell><Badge className={`${STATUS_COLORS[o.status] || 'bg-gray-100'} text-xs`}>{o.status}</Badge></TableCell>
                        <TableCell className="text-sm whitespace-nowrap">{o.telecaller_name || "-"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* My Report Tab */}
        <TabsContent value="my-report" className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">My Performance Report</CardTitle>
              <div className="flex flex-wrap gap-3 items-end mt-2">
                <div>
                  <Label className="text-xs">Period</Label>
                  <Select value={adminPeriod} onValueChange={setAdminPeriod}>
                    <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                    <SelectContent>{PERIOD_OPTIONS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {adminPeriod === "custom" && (
                  <>
                    <div><Label className="text-xs">From</Label><Input type="date" value={adminDateFrom} onChange={e => setAdminDateFrom(e.target.value)} className="w-36" /></div>
                    <div><Label className="text-xs">To</Label><Input type="date" value={adminDateTo} onChange={e => setAdminDateTo(e.target.value)} className="w-36" /></div>
                  </>
                )}
                <div className="flex items-center gap-2"><Checkbox id="admExGst" checked={adminExcludeGst} onCheckedChange={setAdminExcludeGst} /><Label htmlFor="admExGst" className="text-xs cursor-pointer">Excl. GST</Label></div>
                <div className="flex items-center gap-2"><Checkbox id="admExShip" checked={adminExcludeShipping} onCheckedChange={setAdminExcludeShipping} /><Label htmlFor="admExShip" className="text-xs cursor-pointer">Excl. Shipping</Label></div>
              </div>
            </CardHeader>
            <CardContent>
              {adminReport ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold">{adminReport.total_orders}</p><p className="text-xs text-muted-foreground">Orders</p></CardContent></Card>
                    <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold">{"\u20B9"}{adminReport.total_amount?.toLocaleString("en-IN")}</p><p className="text-xs text-muted-foreground">Revenue</p></CardContent></Card>
                    <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold">{"\u20B9"}{adminReport.product_sales?.toLocaleString("en-IN")}</p><p className="text-xs text-muted-foreground">Product Sales</p></CardContent></Card>
                  </div>
                  {adminReport.orders?.length > 0 && (
                    <Table>
                      <TableHeader><TableRow>
                        <TableHead className="text-xs">Order #</TableHead>
                        <TableHead className="text-xs">Customer</TableHead>
                        <TableHead className="text-xs text-right">Amount</TableHead>
                        <TableHead className="text-xs">Date</TableHead>
                      </TableRow></TableHeader>
                      <TableBody>
                        {adminReport.orders.map(o => (
                          <TableRow key={o.id}>
                            <TableCell><Link to={`/orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.order_number}</Link></TableCell>
                            <TableCell className="text-sm">{o.customer_name}</TableCell>
                            <TableCell className="text-sm text-right font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                            <TableCell className="text-sm">{new Date(o.created_at).toLocaleDateString("en-IN")}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </div>
              ) : <p className="text-center py-4 text-muted-foreground">Loading your report...</p>}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Executive Reports Tab */}
        <TabsContent value="exec-reports" className="space-y-4">
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Executive Reports</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-3 items-end">
                <div>
                  <Label className="text-xs">Select Executive</Label>
                  <Select value={selectedExec || ""} onValueChange={v => { setSelectedExec(v); loadExecReport(v); }}>
                    <SelectTrigger className="w-48" data-testid="exec-select"><SelectValue placeholder="Choose..." /></SelectTrigger>
                    <SelectContent>
                      {users.filter(u => u.role === "telecaller" || u.role === "admin").map(u => (
                        <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Period</Label>
                  <Select value={execPeriod} onValueChange={v => { setExecPeriod(v); if (selectedExec) loadExecReport(selectedExec, v); }}>
                    <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                    <SelectContent>{PERIOD_OPTIONS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                {execPeriod === "custom" && (
                  <>
                    <div><Label className="text-xs">From</Label><Input type="date" value={execDateFrom} onChange={e => setExecDateFrom(e.target.value)} className="w-36" /></div>
                    <div><Label className="text-xs">To</Label><Input type="date" value={execDateTo} onChange={e => setExecDateTo(e.target.value)} className="w-36" /></div>
                  </>
                )}
                <div className="flex items-center gap-2"><Checkbox id="execExGst" checked={execExcludeGst} onCheckedChange={setExecExcludeGst} /><Label htmlFor="execExGst" className="text-xs cursor-pointer">Excl. GST</Label></div>
                <div className="flex items-center gap-2"><Checkbox id="execExShip" checked={execExcludeShipping} onCheckedChange={setExecExcludeShipping} /><Label htmlFor="execExShip" className="text-xs cursor-pointer">Excl. Shipping</Label></div>
              </div>
              {executiveReport && (
                <div className="space-y-4 mt-4">
                  <div className="grid grid-cols-3 gap-4">
                    <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold">{executiveReport.total_orders}</p><p className="text-xs text-muted-foreground">Orders</p></CardContent></Card>
                    <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold">{"\u20B9"}{executiveReport.total_amount?.toLocaleString("en-IN")}</p><p className="text-xs text-muted-foreground">Revenue</p></CardContent></Card>
                    <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold">{"\u20B9"}{executiveReport.product_sales?.toLocaleString("en-IN")}</p><p className="text-xs text-muted-foreground">Product Sales</p></CardContent></Card>
                  </div>
                  {executiveReport.orders?.length > 0 && (
                    <Table>
                      <TableHeader><TableRow>
                        <TableHead className="text-xs">Order #</TableHead>
                        <TableHead className="text-xs">Customer</TableHead>
                        <TableHead className="text-xs text-right">Amount</TableHead>
                        <TableHead className="text-xs">Date</TableHead>
                      </TableRow></TableHeader>
                      <TableBody>
                        {executiveReport.orders.map(o => (
                          <TableRow key={o.id}>
                            <TableCell><Link to={`/orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.order_number}</Link></TableCell>
                            <TableCell className="text-sm">{o.customer_name}</TableCell>
                            <TableCell className="text-sm text-right font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                            <TableCell className="text-sm">{new Date(o.created_at).toLocaleDateString("en-IN")}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Payment Sales Tab */}
        <TabsContent value="payment-sales" className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2"><CheckCircle className="w-5 h-5 text-green-600" /> Sales (Payments Received)</CardTitle>
              <div className="flex flex-wrap gap-3 items-end mt-2">
                <div>
                  <Label className="text-xs">Executive</Label>
                  <Select value={paymentSalesExecId || "self"} onValueChange={v => setPaymentSalesExecId(v === "self" ? "" : v)}>
                    <SelectTrigger className="w-48" data-testid="payment-sales-exec"><SelectValue placeholder="All" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="self">My Sales</SelectItem>
                      {users.filter(u => u.role === "telecaller" || u.role === "admin").map(u => (
                        <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Period</Label>
                  <Select value={paymentSalesPeriod} onValueChange={setPaymentSalesPeriod}>
                    <SelectTrigger className="w-36" data-testid="payment-sales-period"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="today">Today</SelectItem>
                      <SelectItem value="yesterday">Yesterday</SelectItem>
                      <SelectItem value="week">This Week</SelectItem>
                      <SelectItem value="month">This Month</SelectItem>
                      <SelectItem value="all">All Time</SelectItem>
                      <SelectItem value="custom">Custom Range</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {paymentSalesPeriod === "custom" && (
                  <>
                    <div><Label className="text-xs">From</Label><Input type="date" value={paymentSalesDateFrom} onChange={e => setPaymentSalesDateFrom(e.target.value)} className="w-36" /></div>
                    <div><Label className="text-xs">To</Label><Input type="date" value={paymentSalesDateTo} onChange={e => setPaymentSalesDateTo(e.target.value)} className="w-36" /></div>
                  </>
                )}
                <div className="flex items-center gap-2"><Checkbox id="pExGst" checked={paymentSalesExGst} onCheckedChange={setPaymentSalesExGst} /><Label htmlFor="pExGst" className="text-xs cursor-pointer">Excl. GST</Label></div>
                <div className="flex items-center gap-2"><Checkbox id="pExShip" checked={paymentSalesExShip} onCheckedChange={setPaymentSalesExShip} /><Label htmlFor="pExShip" className="text-xs cursor-pointer">Excl. Shipping</Label></div>
              </div>
            </CardHeader>
            <CardContent>
              {paymentSalesData ? (
                <div className="grid grid-cols-3 gap-4">
                  <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold text-green-700 dark:text-green-400">{paymentSalesData.total_orders}</p><p className="text-xs text-muted-foreground">Orders (Payment Received)</p></CardContent></Card>
                  <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold text-green-700 dark:text-green-400">{"\u20B9"}{paymentSalesData.total_amount?.toLocaleString("en-IN")}</p><p className="text-xs text-muted-foreground">Total Revenue</p></CardContent></Card>
                  <Card><CardContent className="pt-4 text-center"><p className="text-2xl font-bold text-green-700 dark:text-green-400">{"\u20B9"}{paymentSalesData.product_sales?.toLocaleString("en-IN")}</p><p className="text-xs text-muted-foreground">Product Sales</p></CardContent></Card>
                </div>
              ) : <p className="text-center py-4 text-muted-foreground">Select an executive or loading...</p>}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Users Tab */}
        <TabsContent value="users" className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">User Management</CardTitle>
                <Button size="sm" onClick={() => setShowUserDialog(true)} data-testid="add-user-btn"><UserPlus className="w-4 h-4 mr-2" /> Add User</Button>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow>
                  <TableHead className="text-xs">Name</TableHead>
                  <TableHead className="text-xs">Username</TableHead>
                  <TableHead className="text-xs">Role</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Actions</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {users.map(u => (
                    <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                      <TableCell className="font-medium text-sm">{u.name}</TableCell>
                      <TableCell className="text-sm font-mono">{u.username}</TableCell>
                      <TableCell><Badge variant="secondary" className="text-xs">{u.role}</Badge></TableCell>
                      <TableCell><Badge variant={u.active ? "default" : "destructive"} className="text-xs">{u.active ? "Active" : "Inactive"}</Badge></TableCell>
                      <TableCell>
                        {u.username !== "admin" && (
                          <Button variant="ghost" size="icon" onClick={() => toggleUserActive(u)} data-testid={`toggle-user-${u.id}`}>
                            {u.active ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>


        {/* Edit Requests Tab */}
        <TabsContent value="edit-requests" className="space-y-4" data-testid="edit-requests-tab">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Formulation Lock — Edit Requests</CardTitle>
                <Button variant="outline" size="sm" onClick={loadEditPermissions}><RefreshCw className="w-3 h-3 mr-1" /> Refresh</Button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">Orders with formulations are locked. Non-admin users must request permission to edit them.</p>
            </CardHeader>
            <CardContent>
              {editPermissions.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-6">No edit requests</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Order</TableHead>
                      <TableHead className="text-xs">Customer</TableHead>
                      <TableHead className="text-xs">Requested By</TableHead>
                      <TableHead className="text-xs">Reason</TableHead>
                      <TableHead className="text-xs">Date</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {editPermissions.map(p => (
                      <TableRow key={p.id}>
                        <TableCell className="text-sm font-medium"><Link to={`/orders/${p.order_id}`} className="text-primary underline">{p.order_number}</Link></TableCell>
                        <TableCell className="text-sm">{p.customer_name}</TableCell>
                        <TableCell className="text-sm">{p.requested_by} <Badge variant="outline" className="text-xs ml-1">{p.requested_by_role}</Badge></TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-[200px] truncate">{p.reason || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{new Date(p.created_at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</TableCell>
                        <TableCell>
                          <Badge variant={p.status === "pending" ? "default" : p.status === "approved" ? "secondary" : "destructive"} className="text-xs">
                            {p.status === "used" ? "Used" : p.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {p.status === "pending" ? (
                            <div className="flex gap-1">
                              <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => handleEditPermission(p.id, "approve")} data-testid={`approve-perm-${p.id}`}>Approve</Button>
                              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleEditPermission(p.id, "reject")} data-testid={`reject-perm-${p.id}`}>Reject</Button>
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">{p.handled_by ? `by ${p.handled_by}` : "—"}</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Settings Tab */}
        <TabsContent value="settings" className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Formulation Visibility</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">When ON, packaging team can view and edit formulations. Admin always has access. Telecallers never see formulations.</p>
              <Button variant={showFormulation ? "default" : "outline"} onClick={toggleFormulation} data-testid="toggle-formulation-btn">
                {showFormulation ? <Eye className="w-4 h-4 mr-2" /> : <EyeOff className="w-4 h-4 mr-2" />}
                {showFormulation ? "Formulations Visible (for Packaging)" : "Formulations Hidden (for Packaging)"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Packaging Staff</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Input value={newStaffName} onChange={e => setNewStaffName(e.target.value)} placeholder="Staff name" data-testid="new-staff-input" />
                <Button onClick={addStaff} data-testid="add-staff-btn">Add</Button>
              </div>
              <div className="space-y-2">
                {packagingStaff.map(s => (
                  <div key={s.id} className="flex items-center justify-between p-2 rounded border">
                    <span className={`text-sm ${!s.active ? 'text-muted-foreground line-through' : ''}`}>{s.name}</span>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" onClick={() => toggleStaffActive(s)}>
                        {s.active ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => deleteStaff(s)}><Trash2 className="w-3 h-3 text-destructive" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* New User Dialog */}
      <Dialog open={showUserDialog} onOpenChange={setShowUserDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add New User</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Name</Label><Input value={newUser.name} onChange={e => setNewUser({ ...newUser, name: e.target.value })} data-testid="new-user-name" /></div>
            <div><Label>Username</Label><Input value={newUser.username} onChange={e => setNewUser({ ...newUser, username: e.target.value })} data-testid="new-user-username" /></div>
            <div><Label>Password</Label><Input type="password" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })} data-testid="new-user-password" /></div>
            <div><Label>Role</Label>
              <Select value={newUser.role} onValueChange={v => setNewUser({ ...newUser, role: v })}>
                <SelectTrigger data-testid="new-user-role"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="telecaller">Telecaller (Executive)</SelectItem>
                  <SelectItem value="packaging">Packaging</SelectItem>
                  <SelectItem value="dispatch">Dispatch</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="accounts">Accounts</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowUserDialog(false)}>Cancel</Button>
            <Button onClick={createUser} data-testid="save-user-btn">Create User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
