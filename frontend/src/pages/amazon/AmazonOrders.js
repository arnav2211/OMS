import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Upload, RefreshCw, Search, Package, Trash2 } from "lucide-react";

const STATUS_BADGE = {
  new: "bg-blue-100 text-blue-800 border-blue-200",
  packaging: "bg-yellow-100 text-yellow-800 border-yellow-200",
  packed: "bg-purple-100 text-purple-800 border-purple-200",
  dispatched: "bg-green-100 text-green-800 border-green-200",
  cancelled: "bg-red-100 text-red-800 border-red-200",
};

const COURIERS = ["DTDC", "Anjani", "India Post", "Others"];

export default function AmazonOrders() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [shipTypeFilter, setShipTypeFilter] = useState("all");
  const [showUpload, setShowUpload] = useState(false);
  const [shipType, setShipType] = useState("easy_ship");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

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

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const params = new URLSearchParams({ ship_type: shipType });
      const res = await api.post(`/amazon/upload-pdf?${params}`, form, { headers: { "Content-Type": "multipart/form-data" } });
      setUploadResult(res.data);
      toast.success(`${res.data.created} orders created`);
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (orderId) => {
    try {
      await api.delete(`/amazon/orders/${orderId}`);
      toast.success("Order deleted");
      setDeleteConfirm(null);
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Delete failed"); }
  };

  const filtered = orders.filter(o => {
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
          {isAdmin && (
            <Button onClick={() => { setShowUpload(true); setUploadResult(null); }} data-testid="upload-pdf-btn">
              <Upload className="w-4 h-4 mr-2" /> Upload PDF
            </Button>
          )}
        </div>
      </div>

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
                  <TableRow key={o.id} className="cursor-pointer hover:bg-accent/50" data-testid={`am-row-${o.id}`}>
                    <TableCell>
                      <Link to={`/amazon-orders/${o.id}`} className="font-mono text-sm text-primary hover:underline font-medium" data-testid={`am-link-${o.id}`}>{o.am_order_number}</Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {o.amazon_order_id}
                      {o.source === "sp_api" && (
                        <div className="font-sans mt-0.5 flex gap-1 flex-wrap">
                          {o.easy_ship_status && <Badge variant="outline" className={`text-[10px] ${o.easy_ship_status === "PendingSchedule" ? "border-amber-500 text-amber-600" : ""}`}>{o.easy_ship_status.replace(/([a-z])([A-Z])/g, "$1 $2")}</Badge>}
                          {o.status !== "dispatched" && o.latest_ship_date && <span className="text-[10px]">ship by {new Date(o.latest_ship_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</span>}
                          {o.is_cod && <Badge variant="outline" className="text-[10px]">COD</Badge>}
                          {!o.pdf_enriched && o.ship_type === "self_ship" && <span className="text-[10px] text-amber-600">upload PDF for address</span>}
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

      {/* Upload Dialog */}
      <Dialog open={showUpload} onOpenChange={setShowUpload}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Upload Amazon PDF</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-sm">Ship Type</Label>
              <Select value={shipType} onValueChange={setShipType} data-testid="ship-type-select">
                <SelectTrigger data-testid="ship-type-trigger"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="easy_ship">Easy Ship</SelectItem>
                  <SelectItem value="self_ship">Self Ship</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">PDF File</Label>
              <Input type="file" accept=".pdf" onChange={handleUpload} disabled={uploading} data-testid="pdf-file-input" />
            </div>
            {uploading && <p className="text-sm text-muted-foreground">Parsing PDF...</p>}
            {uploadResult && (
              <div className="p-3 rounded-lg bg-green-50 border border-green-200 text-sm space-y-1" data-testid="upload-result">
                <p className="font-medium text-green-800">{uploadResult.created} orders created</p>
                {uploadResult.duplicates > 0 && (
                  <p className="text-amber-700">{uploadResult.duplicates} duplicates skipped: {uploadResult.duplicate_ids?.join(", ")}</p>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
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
