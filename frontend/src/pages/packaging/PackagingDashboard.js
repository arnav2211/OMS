import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { mobilePrintPdf } from "@/lib/mobilePrint";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { Package, Upload, Camera, Check, Eye, X, Printer, History } from "lucide-react";

function MultiSelect({ label, options, value, onChange, testId }) {
  return (
    <div>
      <Label className="text-sm font-medium">{label} *</Label>
      <div className="flex flex-wrap gap-2 mt-1">
        {options.map((opt) => {
          const selected = value.includes(opt.name);
          return (
            <button
              key={opt.id}
              type="button"
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                selected
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-secondary text-secondary-foreground border-border hover:bg-accent"
              }`}
              onClick={() => {
                if (selected) onChange(value.filter((v) => v !== opt.name));
                else onChange([...value, opt.name]);
              }}
              data-testid={`${testId}-${opt.name}`}
            >
              {opt.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function PackagingDashboard() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [itemPackedBy, setItemPackedBy] = useState([]);
  const [boxPackedBy, setBoxPackedBy] = useState([]);
  const [checkedBy, setCheckedBy] = useState([]);
  const [itemImages, setItemImages] = useState({});
  const [orderImages, setOrderImages] = useState([]);
  const [packedBoxImages, setPackedBoxImages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const [uploadTarget, setUploadTarget] = useState(null);
  const [formulationVisible, setFormulationVisible] = useState(false);
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [formulationHistory, setFormulationHistory] = useState([]);

  useEffect(() => { loadOrders(); loadSettings(); loadStaff(); }, []);

  const loadSettings = async () => {
    try {
      const res = await api.get("/settings");
      setFormulationVisible(res.data?.show_formulation || false);
    } catch {}
  };

  const loadStaff = async () => {
    try {
      const res = await api.get("/packaging-staff");
      setPackagingStaff(res.data);
    } catch {}
  };

  const loadOrders = async () => {
    try {
      const res = await api.get("/orders");
      setOrders(res.data.filter((o) => ["new", "packaging"].includes(o.status)));
    } catch { } finally { setLoading(false); }
  };

  const openOrder = (order) => {
    setSelectedOrder(order);
    setItemPackedBy(order.packaging?.item_packed_by || []);
    setBoxPackedBy(order.packaging?.box_packed_by || []);
    setCheckedBy(order.packaging?.checked_by || []);
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
      const compressed = await compressImage(file);
      const formData = new FormData();
      formData.append("file", compressed);
      try {
        const res = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
        urls.push(res.data.url);
      } catch { toast.error("Upload failed"); }
    }
    if (uploadTarget?.type === "item") {
      setItemImages((prev) => ({ ...prev, [uploadTarget.index]: [...(prev[uploadTarget.index] || []), ...urls] }));
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

  const triggerCameraUpload = (type, index) => {
    setUploadTarget({ type, index });
    document.getElementById("pkg-camera-input")?.click();
  };

  const savePackaging = async (markPacked = false) => {
    if (!selectedOrder) return;
    if (markPacked) {
      if (!itemPackedBy.length) return toast.error("Select who packed the items");
      if (!boxPackedBy.length) return toast.error("Select who packed the box");
      if (!checkedBy.length) return toast.error("Select who checked the order");
    }
    try {
      const payload = {
        item_images: itemImages,
        order_images: orderImages,
        packed_box_images: packedBoxImages,
        item_packed_by: itemPackedBy,
        box_packed_by: boxPackedBy,
        checked_by: checkedBy,
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

  const loadFormulationHistory = async (customerId) => {
    try {
      const res = await api.get(`/orders/formulation-history/${customerId}`);
      setFormulationHistory(res.data);
      setShowHistory(true);
    } catch { toast.error("Failed to load history"); }
  };

  const backendUrl = process.env.REACT_APP_BACKEND_URL;
  const handlePrint = (orderId) => {
    const token = localStorage.getItem("token");
    const url = `${backendUrl}/api/orders/${orderId}/print?token=${token}`;
    const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    fetch(url).then(res => res.blob()).then(blob => {
      if (isMobile) {
        mobilePrintPdf(blob);
      } else {
        const blobUrl = URL.createObjectURL(blob);
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
    }).catch(() => { window.open(url, "_blank"); });
  };

  return (
    <div className="space-y-6" data-testid="packaging-dashboard">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Packaging Queue</h1>
          <p className="text-muted-foreground text-sm mt-1">{orders.length} orders pending packaging</p>
        </div>
      </div>

      <Card>
        <CardContent className="pt-6 overflow-x-auto">
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
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Items</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">Date</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id} data-testid={`pkg-order-${order.order_number}`}>
                    <TableCell className="font-mono font-medium text-sm">
                      <Link to={`/orders/${order.id}`} className="text-primary hover:underline" data-testid={`pkg-order-link-${order.order_number}`}>{order.order_number}</Link>
                    </TableCell>
                    <TableCell className="text-sm">{order.customer_name}</TableCell>
                    <TableCell className="hidden sm:table-cell">{order.items?.length}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`status-${order.status} text-xs uppercase`}>{order.status}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">
                      {new Date(order.created_at).toLocaleDateString("en-IN")}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" onClick={() => handlePrint(order.id)} data-testid={`pkg-print-${order.order_number}`}>
                          <Printer className="w-4 h-4" />
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => openOrder(order)} data-testid={`pkg-view-${order.order_number}`}>
                          <Eye className="w-4 h-4 mr-1" /> Pack
                        </Button>
                      </div>
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
            <DialogTitle className="flex items-center gap-2">
              Pack Order {selectedOrder?.order_number}
              {selectedOrder && formulationVisible && (
                <Button variant="ghost" size="sm" onClick={() => loadFormulationHistory(selectedOrder.customer_id)} data-testid="view-formulation-history">
                  <History className="w-4 h-4 mr-1" /> History
                </Button>
              )}
            </DialogTitle>
          </DialogHeader>
          <input type="file" ref={fileInputRef} className="hidden" multiple accept="image/*" onChange={handleUpload} />
          <input type="file" className="hidden" accept="image/*" capture="environment" onChange={handleUpload} ref={el => { if (el) el.dataset.camera = "true"; }} id="pkg-camera-input" />

          {selectedOrder && (
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">
                Customer: <span className="font-medium text-foreground">{selectedOrder.customer_name}</span>
              </div>

              {/* Items with formulations */}
              <h4 className="text-sm font-semibold">Items</h4>
              {selectedOrder.items?.map((item, idx) => (
                <div key={idx} className="p-3 rounded-lg border space-y-2" data-testid={`pkg-item-${idx}`}>
                  <div className="flex items-center justify-between flex-wrap gap-1">
                    <span className="font-medium text-sm">{item.product_name}</span>
                    <span className="text-sm text-muted-foreground">
                      {item.qty} {item.unit} - {"\u20B9"}{item.total?.toFixed(2)}
                    </span>
                  </div>
                  {formulationVisible && item.formulation && (
                    <div className="p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                      <p className="text-xs font-medium text-amber-700 dark:text-amber-400">Formulation:</p>
                      <p className="text-sm mt-1 whitespace-pre-wrap">{item.formulation}</p>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {(itemImages[idx] || []).map((url, i) => (
                      <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
                        <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                        <button
                          className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                          onClick={() => setItemImages((prev) => ({ ...prev, [idx]: prev[idx].filter((_, j) => j !== i) }))}
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
                      title="Gallery / Files"
                    >
                      <Upload className="w-5 h-5 text-muted-foreground" />
                    </button>
                    <button
                      className="w-16 h-16 rounded border-2 border-dashed flex items-center justify-center hover:bg-accent transition-colors"
                      onClick={() => triggerCameraUpload("item", idx)}
                      disabled={uploading}
                      data-testid={`camera-item-img-${idx}`}
                      title="Camera"
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
                    <button className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity" onClick={() => setOrderImages((prev) => prev.filter((_, j) => j !== i))}>
                      <X className="w-4 h-4 text-white" />
                    </button>
                  </div>
                ))}
                <button className="w-20 h-20 rounded border-2 border-dashed flex flex-col items-center justify-center hover:bg-accent transition-colors" onClick={() => triggerUpload("order")} disabled={uploading} data-testid="upload-order-img" title="Gallery / Files">
                  <Upload className="w-5 h-5 text-muted-foreground" />
                  <span className="text-[10px] text-muted-foreground">Files</span>
                </button>
                <button className="w-20 h-20 rounded border-2 border-dashed flex flex-col items-center justify-center hover:bg-accent transition-colors" onClick={() => triggerCameraUpload("order")} disabled={uploading} data-testid="camera-order-img" title="Camera">
                  <Camera className="w-5 h-5 text-muted-foreground" />
                  <span className="text-[10px] text-muted-foreground">Camera</span>
                </button>
              </div>

              {/* Packed box images */}
              <h4 className="text-sm font-semibold">Packed Box Images</h4>
              <div className="flex flex-wrap gap-2">
                {packedBoxImages.map((url, i) => (
                  <div key={i} className="relative w-20 h-20 rounded border overflow-hidden group">
                    <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                    <button className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity" onClick={() => setPackedBoxImages((prev) => prev.filter((_, j) => j !== i))}>
                      <X className="w-4 h-4 text-white" />
                    </button>
                  </div>
                ))}
                <button className="w-20 h-20 rounded border-2 border-dashed flex flex-col items-center justify-center hover:bg-accent transition-colors" onClick={() => triggerUpload("packed_box")} disabled={uploading} data-testid="upload-packed-box-img" title="Gallery / Files">
                  <Upload className="w-5 h-5 text-muted-foreground" />
                  <span className="text-[10px] text-muted-foreground">Files</span>
                </button>
                <button className="w-20 h-20 rounded border-2 border-dashed flex flex-col items-center justify-center hover:bg-accent transition-colors" onClick={() => triggerCameraUpload("packed_box")} disabled={uploading} data-testid="camera-packed-box-img" title="Camera">
                  <Camera className="w-5 h-5 text-muted-foreground" />
                  <span className="text-[10px] text-muted-foreground">Camera</span>
                </button>
              </div>

              <Separator />

              {/* Three mandatory multi-select fields */}
              <MultiSelect label="Item Packed By" options={packagingStaff} value={itemPackedBy} onChange={setItemPackedBy} testId="item-packed-by" />
              <MultiSelect label="Box Packed By" options={packagingStaff} value={boxPackedBy} onChange={setBoxPackedBy} testId="box-packed-by" />
              <MultiSelect label="Checked By" options={packagingStaff} value={checkedBy} onChange={setCheckedBy} testId="checked-by" />
            </div>
          )}

          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button variant="outline" onClick={() => savePackaging(false)} data-testid="save-packaging-btn">Save Progress</Button>
            <Button onClick={() => savePackaging(true)} data-testid="mark-packed-btn">
              <Check className="w-4 h-4 mr-1" /> Mark as Packed
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Formulation History Dialog */}
      <Dialog open={showHistory} onOpenChange={setShowHistory}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Formulation History</DialogTitle>
          </DialogHeader>
          {formulationHistory.length === 0 ? (
            <p className="text-center py-6 text-muted-foreground">No previous formulations found for this customer.</p>
          ) : (
            <div className="space-y-4">
              {formulationHistory.map((h, i) => (
                <div key={i} className="p-3 rounded-lg border space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm font-medium">{h.order_number}</span>
                    <span className="text-xs text-muted-foreground">{new Date(h.created_at).toLocaleDateString("en-IN")}</span>
                  </div>
                  {h.items.map((item, j) => (
                    <div key={j} className="pl-3 border-l-2 border-amber-300">
                      <p className="text-sm font-medium">{item.product_name} ({item.qty} {item.unit})</p>
                      <p className="text-xs text-amber-700 dark:text-amber-400 mt-1 whitespace-pre-wrap">{item.formulation}</p>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
