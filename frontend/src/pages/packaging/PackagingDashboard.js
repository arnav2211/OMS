import { useState, useEffect, useRef } from "react";
import api, { API_BASE } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { Package, Upload, Camera, Check, Eye, X } from "lucide-react";

export default function PackagingDashboard() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [packedBy, setPackedBy] = useState("");
  const [itemImages, setItemImages] = useState({});
  const [orderImages, setOrderImages] = useState([]);
  const [packedBoxImages, setPackedBoxImages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const [uploadTarget, setUploadTarget] = useState(null);

  useEffect(() => { loadOrders(); }, []);

  const loadOrders = async () => {
    try {
      const res = await api.get("/orders");
      setOrders(res.data.filter((o) => ["new", "packaging"].includes(o.status)));
    } catch { } finally { setLoading(false); }
  };

  const openOrder = (order) => {
    setSelectedOrder(order);
    setPackedBy(order.packaging?.packed_by || "");
    setItemImages(order.packaging?.item_images || {});
    setOrderImages(order.packaging?.order_images || []);
    setPackedBoxImages(order.packaging?.packed_box_images || []);
    setShowDetail(true);
  };

  const handleUpload = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    setUploading(true);
    const urls = [];
    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);
      try {
        const res = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
        urls.push(res.data.url);
      } catch { toast.error("Upload failed"); }
    }
    if (uploadTarget?.type === "item") {
      setItemImages((prev) => ({
        ...prev,
        [uploadTarget.index]: [...(prev[uploadTarget.index] || []), ...urls],
      }));
    } else if (uploadTarget?.type === "order") {
      setOrderImages((prev) => [...prev, ...urls]);
    } else if (uploadTarget?.type === "packed_box") {
      setPackedBoxImages((prev) => [...prev, ...urls]);
    }
    setUploading(false);
    e.target.value = "";
  };

  const triggerUpload = (type, index) => {
    setUploadTarget({ type, index });
    fileInputRef.current?.click();
  };

  const savePackaging = async (markPacked = false) => {
    if (!selectedOrder) return;
    if (markPacked && !packedBy) return toast.error("Enter who packed the order");
    try {
      const payload = {
        item_images: itemImages,
        order_images: orderImages,
        packed_box_images: packedBoxImages,
        packed_by: packedBy,
        status: markPacked ? "packed" : "packaging",
      };
      await api.put(`/orders/${selectedOrder.id}/packaging`, payload);
      toast.success(markPacked ? "Order marked as packed!" : "Packaging updated");
      setShowDetail(false);
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to update");
    }
  };

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <div className="space-y-6" data-testid="packaging-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Packaging Queue</h1>
          <p className="text-muted-foreground text-sm mt-1">{orders.length} orders pending packaging</p>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading...</p>
          ) : orders.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Package className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No orders pending packaging</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Items</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Date</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id} data-testid={`pkg-order-${order.order_number}`}>
                    <TableCell className="font-mono font-medium">{order.order_number}</TableCell>
                    <TableCell>{order.customer_name}</TableCell>
                    <TableCell>{order.items?.length}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`status-${order.status} text-xs uppercase`}>
                        {order.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(order.created_at).toLocaleDateString("en-IN")}
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" onClick={() => openOrder(order)} data-testid={`pkg-view-${order.order_number}`}>
                        <Eye className="w-4 h-4 mr-1" /> Pack
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Pack Order {selectedOrder?.order_number}</DialogTitle>
          </DialogHeader>
          <input type="file" ref={fileInputRef} className="hidden" multiple accept="image/*" onChange={handleUpload} />

          {selectedOrder && (
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">
                Customer: <span className="font-medium text-foreground">{selectedOrder.customer_name}</span>
              </div>

              {/* Items with formulations */}
              <h4 className="text-sm font-semibold">Items</h4>
              {selectedOrder.items?.map((item, idx) => (
                <div key={idx} className="p-3 rounded-lg border space-y-2" data-testid={`pkg-item-${idx}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{item.product_name}</span>
                    <span className="text-sm text-muted-foreground">
                      {item.qty} {item.unit} - {"\u20B9"}{item.total?.toFixed(2)}
                    </span>
                  </div>
                  {item.show_formulation && item.formulation && (
                    <div className="p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                      <p className="text-xs font-medium text-amber-700 dark:text-amber-400">Formulation:</p>
                      <p className="text-sm mt-1 whitespace-pre-wrap">{item.formulation}</p>
                    </div>
                  )}
                  {/* Item images */}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {(itemImages[idx] || []).map((url, i) => (
                      <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
                        <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                        <button
                          className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                          onClick={() => {
                            setItemImages((prev) => ({
                              ...prev,
                              [idx]: prev[idx].filter((_, j) => j !== i),
                            }));
                          }}
                        >
                          <X className="w-4 h-4 text-white" />
                        </button>
                      </div>
                    ))}
                    <button
                      className="w-16 h-16 rounded border-2 border-dashed flex items-center justify-center hover:bg-accent transition-colors"
                      onClick={() => triggerUpload("item", idx)}
                      disabled={uploading}
                      data-testid={`upload-item-img-${idx}`}
                    >
                      <Camera className="w-5 h-5 text-muted-foreground" />
                    </button>
                  </div>
                </div>
              ))}

              <Separator />

              {/* Whole order images */}
              <h4 className="text-sm font-semibold">Whole Order Images</h4>
              <div className="flex flex-wrap gap-2">
                {orderImages.map((url, i) => (
                  <div key={i} className="relative w-20 h-20 rounded border overflow-hidden group">
                    <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                    <button
                      className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                      onClick={() => setOrderImages((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <X className="w-4 h-4 text-white" />
                    </button>
                  </div>
                ))}
                <button
                  className="w-20 h-20 rounded border-2 border-dashed flex items-center justify-center hover:bg-accent transition-colors"
                  onClick={() => triggerUpload("order")}
                  disabled={uploading}
                  data-testid="upload-order-img"
                >
                  <Upload className="w-5 h-5 text-muted-foreground" />
                </button>
              </div>

              {/* Packed box images */}
              <h4 className="text-sm font-semibold">Packed Box Images</h4>
              <div className="flex flex-wrap gap-2">
                {packedBoxImages.map((url, i) => (
                  <div key={i} className="relative w-20 h-20 rounded border overflow-hidden group">
                    <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                    <button
                      className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                      onClick={() => setPackedBoxImages((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <X className="w-4 h-4 text-white" />
                    </button>
                  </div>
                ))}
                <button
                  className="w-20 h-20 rounded border-2 border-dashed flex items-center justify-center hover:bg-accent transition-colors"
                  onClick={() => triggerUpload("packed_box")}
                  disabled={uploading}
                  data-testid="upload-packed-box-img"
                >
                  <Upload className="w-5 h-5 text-muted-foreground" />
                </button>
              </div>

              <Separator />

              <div>
                <Label>Packed By</Label>
                <Input
                  value={packedBy}
                  onChange={(e) => setPackedBy(e.target.value)}
                  placeholder="Name of packer"
                  data-testid="packed-by-input"
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => savePackaging(false)} data-testid="save-packaging-btn">
              Save Progress
            </Button>
            <Button onClick={() => savePackaging(true)} data-testid="mark-packed-btn">
              <Check className="w-4 h-4 mr-1" /> Mark as Packed
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
