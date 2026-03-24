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
import { Upload, RefreshCw, Search, Package } from "lucide-react";

const STATUS_BADGE = {
  new: "bg-blue-100 text-blue-800 border-blue-200",
  packaging: "bg-yellow-100 text-yellow-800 border-yellow-200",
  packed: "bg-purple-100 text-purple-800 border-purple-200",
  dispatched: "bg-green-100 text-green-800 border-green-200",
};

const COURIERS = ["DTDC", "Anjani", "Professional", "India Post"];

export default function AmazonOrders() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [showUpload, setShowUpload] = useState(false);
  const [shipType, setShipType] = useState("easy_ship");
  const [courier, setCourier] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);

  useEffect(() => { loadOrders(); }, []);

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
    if (shipType === "self_ship" && !courier) {
      toast.error("Select a courier for Self Ship");
      e.target.value = "";
      return;
    }
    setUploading(true);
    setUploadResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const params = new URLSearchParams({ ship_type: shipType });
      if (shipType === "self_ship") params.set("courier_name", courier);
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

  const filtered = orders.filter(o => {
    if (statusFilter !== "all" && o.status !== statusFilter) return false;
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
        {isAdmin && (
          <Button onClick={() => { setShowUpload(true); setUploadResult(null); }} data-testid="upload-pdf-btn">
            <Upload className="w-4 h-4 mr-2" /> Upload PDF
          </Button>
        )}
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>}
                {!loading && filtered.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No orders found</TableCell></TableRow>}
                {filtered.map(o => (
                  <TableRow key={o.id} className="cursor-pointer hover:bg-accent/50" data-testid={`am-row-${o.id}`}>
                    <TableCell>
                      <Link to={`/amazon-orders/${o.id}`} className="font-mono text-sm text-primary hover:underline font-medium" data-testid={`am-link-${o.id}`}>{o.am_order_number}</Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{o.amazon_order_id}</TableCell>
                    <TableCell className="text-sm">{o.customer_name}</TableCell>
                    <TableCell className="text-sm font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      {o.shipping_method === "amazon" ? "Amazon" : o.courier_name || "Courier"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={`text-xs capitalize ${STATUS_BADGE[o.status] || ""}`}>{o.status}</Badge>
                    </TableCell>
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
              <Select value={shipType} onValueChange={v => { setShipType(v); setCourier(""); }} data-testid="ship-type-select">
                <SelectTrigger data-testid="ship-type-trigger"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="easy_ship">Easy Ship</SelectItem>
                  <SelectItem value="self_ship">Self Ship</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {shipType === "self_ship" && (
              <div>
                <Label className="text-sm">Courier</Label>
                <Select value={courier} onValueChange={setCourier}>
                  <SelectTrigger data-testid="courier-select"><SelectValue placeholder="Select courier" /></SelectTrigger>
                  <SelectContent>
                    {COURIERS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
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
    </div>
  );
}
