import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { RefreshCw, Search, Trash2 } from "lucide-react";
import { COURIER_DROPDOWN } from "@/lib/courierTracking";


// Ship-by urgency from Amazon's latest ship date: "overdue", "today" or "".
const shipByUrgency = (o) => {
  if (!o?.latest_ship_date || ["dispatched", "cancelled"].includes(o.status)) return "";
  const d = new Date(o.latest_ship_date);
  if (d.getTime() < Date.now()) return "overdue";
  return d.toDateString() === new Date().toDateString() ? "today" : "";
};
const shipByLabel = (o) => o?.latest_ship_date
  ? new Date(o.latest_ship_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) : "";

const STATUS_BADGE = {
  new: "bg-blue-100 text-blue-800 border-blue-200",
  packaging: "bg-yellow-100 text-yellow-800 border-yellow-200",
  packed: "bg-purple-100 text-purple-800 border-purple-200",
  dispatched: "bg-green-100 text-green-800 border-green-200",
  cancelled: "bg-red-100 text-red-800 border-red-200",
};

const COURIERS = COURIER_DROPDOWN;

export default function AmazonOrders() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [shipTypeFilter, setShipTypeFilter] = useState("all");
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [pickupView, setPickupView] = useState("");      // "", "today", "pickup", "schedule"

  useEffect(() => { loadOrders(); }, []);

  const [sp, setSp] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const loadSp = async () => { try { const r = await api.get("/amazon/sp/status"); setSp(r.data); } catch { /* optional */ } };
  const syncAmazon = async () => {
    setSyncing(true);
    try {
      const r = await api.post("/amazon/sp/sync");
      const d = r.data;
      toast.success(`Amazon: ${d.created.length} new, ${d.dispatched.length} dispatched, ${d.cancelled.length} cancelled`);
      loadOrders(); loadSp();
    } catch (e) { toast.error(e.response?.data?.detail || "Amazon sync failed"); }
    finally { setSyncing(false); }
  };
  useEffect(() => { loadSp(); }, []);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const res = await api.get("/amazon/orders");
      setOrders(res.data);
    } catch { } finally { setLoading(false); }
  };

  const handleDelete = async (orderId) => {
    try {
      await api.delete(`/amazon/orders/${orderId}`);
      toast.success("Order deleted");
      setDeleteConfirm(null);
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Delete failed"); }
  };

  // Pickup counters, from Amazon's own Easy Ship state and ship-by date.
  const live = orders.filter(o => !["dispatched", "cancelled"].includes(o.status));
  const dueByToday = (o) => {
    if (!o.latest_ship_date) return false;
    const d = new Date(o.latest_ship_date), end = new Date();
    end.setHours(23, 59, 59, 999);
    return d.getTime() <= end.getTime();          // today, or already missed
  };
  const pendingPickup = live.filter(o => o.easy_ship_status === "PendingPickUp");
  const pickupToday = pendingPickup.filter(dueByToday);
  const toSchedule = live.filter(o => o.easy_ship_status === "PendingSchedule");
  const PICKUP_VIEWS = { pickup: pendingPickup, today: pickupToday, schedule: toSchedule };

  const filtered = orders.filter(o => {
    if (pickupView && !PICKUP_VIEWS[pickupView].some(x => x.id === o.id)) return false;
    if (statusFilter !== "all" && o.status !== statusFilter) return false;
    if (shipTypeFilter !== "all" && o.ship_type !== shipTypeFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return o.am_order_number?.toLowerCase().includes(q) || o.amazon_order_id?.toLowerCase().includes(q) || o.customer_name?.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div className="space-y-4" data-testid="amazon-orders-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-bold">Amazon Orders</h1>
        <div className="flex items-center gap-2 flex-wrap">
          {sp?.configured && (
            <span className="text-xs text-muted-foreground">
              Amazon sync: {sp.last_run ? new Date(sp.last_run).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "not yet"}
              {sp.pending_schedule > 0 && <span className="ml-2 text-amber-600 font-medium">{sp.pending_schedule} to schedule pickup</span>}
              {sp.last_error && <span className="ml-2 text-red-600">sync error</span>}
            </span>
          )}
          {sp?.configured && (
            <Button variant="outline" onClick={syncAmazon} disabled={syncing} data-testid="amazon-sync-btn">
              <RefreshCw className={`w-4 h-4 mr-2 ${syncing ? "animate-spin" : ""}`} /> Sync from Amazon
            </Button>
          )}
        </div>
      </div>

      {/* Pickup counters: tap one to see just those orders */}
      {sp?.configured && (
        <div className="grid grid-cols-3 gap-2 max-w-2xl" data-testid="amazon-pickup-counters">
          {[
            ["today", "Pickup due today", pickupToday.length, "text-red-600", "border-red-400 bg-red-50 dark:bg-red-950/30", "ship-by today or missed"],
            ["pickup", "Pending pickup (all)", pendingPickup.length, "text-amber-600", "border-amber-400 bg-amber-50 dark:bg-amber-950/30", "scheduled, not collected yet"],
            ["schedule", "To schedule", toSchedule.length, "text-blue-600", "border-blue-400 bg-blue-50 dark:bg-blue-950/30", "pickup not booked yet"],
          ].map(([key, label, n, numCls, activeCls, hint]) => (
            <button key={key} onClick={() => setPickupView(pickupView === key ? "" : key)}
                    className={`text-left rounded-lg border p-3 transition-colors ${pickupView === key ? activeCls : "hover:bg-accent/50"}`}
                    data-testid={`amazon-count-${key}`}>
              <div className={`text-3xl font-bold font-mono ${n > 0 ? numCls : "text-muted-foreground"}`}>{n}</div>
              <div className="text-sm font-medium leading-tight">{label}</div>
              <div className="text-[11px] text-muted-foreground">{hint}</div>
            </button>
          ))}
        </div>
      )}
      {pickupView && (
        <p className="text-xs text-muted-foreground">
          Showing only these orders. <button className="underline" onClick={() => setPickupView("")}>Show all</button>
        </p>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search orders..." value={search} onChange={e => setSearch(e.target.value)} className="pl-8 h-9" data-testid="amazon-search" />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-32 h-9" data-testid="amazon-status-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="packaging">Packaging</SelectItem>
            <SelectItem value="packed">Packed</SelectItem>
            <SelectItem value="dispatched">Dispatched</SelectItem>
          </SelectContent>
        </Select>
        <Select value={shipTypeFilter} onValueChange={setShipTypeFilter}>
          <SelectTrigger className="w-32 h-9" data-testid="amazon-ship-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="easy_ship">Easy Ship</SelectItem>
            <SelectItem value="self_ship">Self Ship</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={loadOrders}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      {/* Orders Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase whitespace-nowrap">AM Order</TableHead>
                  <TableHead className="text-xs uppercase whitespace-nowrap">Amazon Order ID</TableHead>
                  <TableHead className="text-xs uppercase whitespace-nowrap">Customer</TableHead>
                  <TableHead className="text-xs uppercase whitespace-nowrap">Amount</TableHead>
                  <TableHead className="text-xs uppercase whitespace-nowrap">Shipping</TableHead>
                  <TableHead className="text-xs uppercase whitespace-nowrap">Status</TableHead>
                  {isAdmin && <TableHead className="text-xs uppercase whitespace-nowrap">Action</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>}
                {!loading && filtered.length === 0 && <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No orders found</TableCell></TableRow>}
                {filtered.map(o => (
                  <TableRow key={o.id} className={`cursor-pointer hover:bg-accent/50 ${shipByUrgency(o) ? "bg-red-50 dark:bg-red-950/30" : ""}`} data-testid={`am-row-${o.id}`}>
                    <TableCell>
                      <Link to={`/amazon-orders/${o.id}`} className="font-mono text-sm text-primary hover:underline font-medium" data-testid={`am-link-${o.id}`}>{o.am_order_number}</Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {o.amazon_order_id}
                      {o.source === "sp_api" && (
                        <div className="font-sans mt-0.5 flex gap-1 flex-wrap">
                          {o.easy_ship_status && <Badge variant="outline" className={`text-[10px] ${o.easy_ship_status === "PendingSchedule" ? "border-amber-500 text-amber-600" : ""}`}>{o.easy_ship_status.replace(/([a-z])([A-Z])/g, "$1 $2")}</Badge>}
                          {!["dispatched", "cancelled"].includes(o.status) && o.latest_ship_date && (
                            <span className={`text-[10px] ${shipByUrgency(o) ? "text-red-600 font-semibold" : ""}`}>
                              {shipByUrgency(o) === "overdue" ? "SHIP-BY MISSED " : shipByUrgency(o) === "today" ? "SHIP TODAY " : "ship by "}{shipByLabel(o)}
                            </span>
                          )}
                          {o.is_cod && <Badge variant="outline" className="text-[10px]">COD</Badge>}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{o.customer_name}</TableCell>
                    <TableCell className="text-sm font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      {o.shipping_method === "amazon" ? "Amazon" : o.courier_name || "Courier"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-xs capitalize ${STATUS_BADGE[o.status] || ""}`}>{o.status}</Badge>
                    </TableCell>
                    {isAdmin && (
                      <TableCell>
                        {o.status !== "dispatched" && (
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500 hover:text-red-700 hover:bg-red-50"
                            onClick={(e) => { e.stopPropagation(); setDeleteConfirm(o); }} data-testid={`am-delete-${o.id}`}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Delete Order</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <p className="text-sm">Are you sure you want to delete <span className="font-mono font-bold">{deleteConfirm?.am_order_number}</span>?</p>
            <p className="text-sm text-muted-foreground">Amazon Order: {deleteConfirm?.amazon_order_id}</p>
            <p className="text-sm text-muted-foreground">Customer: {deleteConfirm?.customer_name}</p>
            <p className="text-sm text-destructive font-medium">This action cannot be undone.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => handleDelete(deleteConfirm?.id)} data-testid="confirm-delete-am">Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
