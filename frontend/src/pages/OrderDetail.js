import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { ArrowLeft, Package, Truck, Edit, Printer, Trash2, FileText, X, Share2 } from "lucide-react";

const STATUS_COLORS = { new: "bg-blue-100 text-blue-800", packaging: "bg-yellow-100 text-yellow-800", packed: "bg-green-100 text-green-800", dispatched: "bg-purple-100 text-purple-800" };
const COURIER_OPTIONS = ["DTDC", "Anjani", "Professional", "India Post"];

export default function OrderDetail() {
  const { orderId: id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  // These are kept for backwards compatibility but no longer used (edit now navigates to /orders/:id/edit)
  // eslint-disable-next-line
  const [showEdit, ] = useState(false);
  // eslint-disable-next-line
  const [editData, ] = useState({});
  const [saving, setSaving] = useState(false);
  const [showPackaging, setShowPackaging] = useState(false);
  const [showDispatch, setShowDispatch] = useState(false);
  const [showFormulation, setShowFormulation] = useState(false);
  const [formulationItems, setFormulationItems] = useState([]);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [dispatchData, setDispatchData] = useState({ courier_name: "", transporter_name: "", lr_no: "", dispatch_type: "" });
  const [previewImage, setPreviewImage] = useState(null);
  const [customerPhone, setCustomerPhone] = useState("");

  useEffect(() => { loadOrder(); }, [id]);

  useEffect(() => {
    if (order?.customer_id) {
      api.get(`/customers/${order.customer_id}`).then(r => {
        const phones = r.data?.phone_numbers || [];
        if (phones.length) setCustomerPhone(phones[0]);
      }).catch(() => {});
    }
  }, [order?.customer_id]);

  const loadOrder = async () => {
    try { const res = await api.get(`/orders/${id}`); setOrder(res.data); }
    catch { toast.error("Order not found"); navigate("/"); }
    finally { setLoading(false); }
  };

  const isDispatched = order?.status === "dispatched";
  const canEditOrder = user?.role === "admin" || (user?.role === "telecaller" && order?.telecaller_id === user?.id);
  const canEditFormulation = user?.role === "admin" || user?.role === "packaging";
  const showFormulations = user?.role === "admin" || user?.role === "packaging";
  const canEditPackaging = ["admin", "packaging"].includes(user?.role) && !isDispatched;
  const canEditDispatch = ["admin", "dispatch"].includes(user?.role);
  const canSharePI = ["admin", "telecaller"].includes(user?.role);
  const canShareImages = ["admin", "telecaller"].includes(user?.role);

  const openEdit = () => {
    if (isDispatched) return toast.error("Cannot edit dispatched order");
    navigate(`/orders/${id}/edit`);
  };

  const openFormulation = () => {
    setFormulationItems(order.items.map(i => ({ product_name: i.product_name, formulation: i.formulation || "" })));
    setShowFormulation(true);
  };

  const saveFormulation = async () => {
    setSaving(true);
    try {
      await api.put(`/orders/${id}/formulation`, { items: formulationItems });
      toast.success("Formulations updated"); setShowFormulation(false); loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const openPackaging = async () => {
    try { const res = await api.get("/packaging-staff"); setPackagingStaff(res.data.filter(s => s.active)); }
    catch { } setShowPackaging(true);
  };

  const savePackaging = async (packData) => {
    setSaving(true);
    try {
      await api.put(`/orders/${id}/packaging`, packData);
      toast.success("Packaging updated"); setShowPackaging(false); loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const openDispatch = () => {
    setDispatchData({ courier_name: order.courier_name || "", transporter_name: order.transporter_name || "", lr_no: "", dispatch_type: order.shipping_method || "" });
    setShowDispatch(true);
  };

  const saveDispatch = async () => {
    setSaving(true);
    try {
      await api.put(`/orders/${id}/dispatch`, dispatchData);
      toast.success("Order dispatched!"); setShowDispatch(false); loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const handlePrint = () => {
    const token = localStorage.getItem("token");
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/orders/${id}/print?token=${token}`, "_blank");
  };

  const deleteOrder = async () => {
    if (deleteConfirmText !== order.order_number) return toast.error("Type the order number to confirm");
    try { await api.delete(`/orders/${id}/delete`); toast.success("Order deleted"); navigate("/orders"); }
    catch (err) { toast.error(err.response?.data?.detail || "Failed"); setShowDeleteConfirm(false); }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>;
  if (!order) return <p className="text-center py-8 text-muted-foreground">Order not found.</p>;

  // Collect all packing image URLs
  const allPackingImageUrls = [];
  if (order.packaging?.item_images) {
    Object.values(order.packaging.item_images).forEach(urls => {
      if (urls?.length) allPackingImageUrls.push(...urls);
    });
  }
  if (order.packaging?.order_images?.length) allPackingImageUrls.push(...order.packaging.order_images);
  if (order.packaging?.packed_box_images?.length) allPackingImageUrls.push(...order.packaging.packed_box_images);

  const sharePackingImages = async () => {
    if (!allPackingImageUrls.length) return toast.error("No packing images to share");
    try {
      const blobs = await Promise.all(
        allPackingImageUrls.map(url => fetch(`${process.env.REACT_APP_BACKEND_URL}${url}`).then(r => r.blob()))
      );
      const files = blobs.map((blob, i) => {
        const ext = blob.type.includes("png") ? "png" : "jpg";
        return new File([blob], `packing-${order.order_number}-${i + 1}.${ext}`, { type: blob.type });
      });

      if (navigator.canShare && navigator.canShare({ files })) {
        await navigator.share({ files, title: `Packing Images - ${order.order_number}` });
      } else {
        // Desktop fallback: download each file
        files.forEach((file, i) => {
          const url = URL.createObjectURL(file);
          const a = document.createElement("a");
          a.href = url;
          a.download = file.name;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        });
        toast.success("Images downloaded. Opening WhatsApp...");
        // Open WhatsApp if customer phone available
        if (customerPhone) {
          const clean = customerPhone.replace(/[^0-9]/g, "");
          const waPhone = clean.startsWith("91") ? clean : `91${clean}`;
          setTimeout(() => window.open(`https://wa.me/${waPhone}`, "_blank"), 500);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") toast.error("Share failed");
    }
  };

  const shareInvoice = async () => {
    if (!order.tax_invoice_url) return toast.error("No invoice to share");
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}${order.tax_invoice_url}`);
      if (!response.ok) throw new Error("Failed to fetch invoice");
      const blob = await response.blob();
      const file = new File([blob], `Invoice-${order.order_number}.pdf`, { type: "application/pdf" });

      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: `Invoice - ${order.order_number}` });
      } else {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success("Invoice downloaded. Opening WhatsApp...");
        if (customerPhone) {
          const clean = customerPhone.replace(/[^0-9]/g, "");
          const waPhone = clean.startsWith("91") ? clean : `91${clean}`;
          setTimeout(() => window.open(`https://wa.me/${waPhone}`, "_blank"), 500);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") toast.error("Share failed");
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-4 sm:space-y-6 px-1 sm:px-0" data-testid="order-detail-page">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}><ArrowLeft className="w-5 h-5" /></Button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">{order.order_number}</h1>
            <Badge className={`${STATUS_COLORS[order.status] || "bg-gray-100"} text-xs mt-1`} data-testid="order-status-badge">{order.status}</Badge>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handlePrint} data-testid="print-order-btn"><Printer className="w-4 h-4 mr-1" /> Print</Button>
          {(canEditOrder || canEditPackaging || canEditDispatch) && !isDispatched && (
            <Button variant="outline" size="sm" onClick={openEdit} data-testid="edit-order-btn"><Edit className="w-4 h-4 mr-1" /> Edit</Button>
          )}
          {canEditFormulation && <Button variant="outline" size="sm" onClick={openFormulation} data-testid="formulation-btn"><FileText className="w-4 h-4 mr-1" /> Formulation</Button>}
          {user?.role === "admin" && <Button variant="destructive" size="sm" onClick={() => setShowDeleteConfirm(true)} data-testid="delete-order-btn"><Trash2 className="w-4 h-4 mr-1" /> Delete</Button>}
        </div>
      </div>

      {isDispatched && <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 text-sm text-purple-800 dark:text-purple-200" data-testid="dispatch-lock-notice">This order has been dispatched. Editing is locked (formulation changes only).</div>}

      {/* Customer Info */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Customer Information</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Customer</span><span className="text-sm font-medium">{order.customer_name}</span></div>
          {order.billing_address && (
            <div className="flex justify-between"><span className="text-sm text-muted-foreground">Billing Address</span><span className="text-sm text-right max-w-[60%]">{order.billing_address.address_line}, {order.billing_address.city}, {order.billing_address.state} - {order.billing_address.pincode}</span></div>
          )}
          {order.shipping_address && (
            <div className="flex justify-between"><span className="text-sm text-muted-foreground">Shipping Address</span><span className="text-sm text-right max-w-[60%]">{order.shipping_address.address_line}, {order.shipping_address.city}, {order.shipping_address.state} - {order.shipping_address.pincode}</span></div>
          )}
          {order.purpose && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Purpose</span><span className="text-sm">{order.purpose}</span></div>}
          {order.mode_of_payment && (
            <div className="flex justify-between"><span className="text-sm text-muted-foreground">Payment Mode</span><span className="text-sm">{order.mode_of_payment}{order.payment_mode_details ? ` (${order.payment_mode_details})` : ""}</span></div>
          )}
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Created</span><span className="text-sm">{new Date(order.created_at).toLocaleString("en-IN")}</span></div>
        </CardContent>
      </Card>

      {/* Items */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Items ({order.items?.length})</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">#</TableHead>
                  <TableHead className="text-xs">Product</TableHead>
                  <TableHead className="text-xs text-right">Qty</TableHead>
                  <TableHead className="text-xs">Unit</TableHead>
                  <TableHead className="text-xs text-right">Rate</TableHead>
                  <TableHead className="text-xs text-right">Amount</TableHead>
                  {order.gst_applicable && <><TableHead className="text-xs text-right">GST%</TableHead><TableHead className="text-xs text-right">GST Amt</TableHead></>}
                  <TableHead className="text-xs text-right">Total</TableHead>
                  {showFormulations && <TableHead className="text-xs">Formulation</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {order.items?.map((item, i) => (
                  <TableRow key={i} data-testid={`order-item-row-${i}`}>
                    <TableCell className="text-sm">{i + 1}</TableCell>
                    <TableCell className="text-sm">
                      {item.product_name}
                      {item.description && <p className="text-xs text-muted-foreground">{item.description}</p>}
                    </TableCell>
                    <TableCell className="text-sm text-right font-mono">{item.qty}</TableCell>
                    <TableCell className="text-sm">{item.unit}</TableCell>
                    <TableCell className="text-sm text-right font-mono">{item.rate?.toFixed(2)}</TableCell>
                    <TableCell className="text-sm text-right font-mono">{item.amount?.toFixed(2)}</TableCell>
                    {order.gst_applicable && (
                      <><TableCell className="text-sm text-right">{item.gst_rate}%</TableCell><TableCell className="text-sm text-right font-mono">{item.gst_amount?.toFixed(2)}</TableCell></>
                    )}
                    <TableCell className="text-sm text-right font-mono font-medium">{item.total?.toFixed(2)}</TableCell>
                    {showFormulations && <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{item.formulation || "-"}</TableCell>}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <Separator />
            <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-mono">{"\u20B9"}{order.subtotal?.toFixed(2)}</span></div>
            {order.gst_applicable && <div className="flex justify-between"><span className="text-muted-foreground">GST</span><span className="font-mono">{"\u20B9"}{order.total_gst?.toFixed(2)}</span></div>}
            {order.shipping_charge > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping</span><span className="font-mono">{"\u20B9"}{order.shipping_charge?.toFixed(2)}</span></div>}
            {order.shipping_gst > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping GST</span><span className="font-mono">{"\u20B9"}{order.shipping_gst?.toFixed(2)}</span></div>}
            <Separator />
            <div className="flex justify-between text-base font-bold"><span>Grand Total</span><span className="font-mono">{"\u20B9"}{order.grand_total}</span></div>
          </div>
        </CardContent>
      </Card>

      {/* Payment */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Payment Details</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Status</span><Badge variant="outline">{order.payment_status}</Badge></div>
          {order.amount_paid > 0 && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Amount Paid</span><span className="text-sm font-mono">{"\u20B9"}{order.amount_paid}</span></div>}
          {order.balance_amount > 0 && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Balance</span><span className="text-sm font-mono text-red-500">{"\u20B9"}{order.balance_amount}</span></div>}
          {order.payment_screenshots?.length > 0 && (
            <div>
              <p className="text-sm font-medium mb-2">Payment Proof</p>
              <div className="flex flex-wrap gap-2" data-testid="payment-proof-images">
                {order.payment_screenshots.map((url, i) => (
                  <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                    <button className="w-full h-full" onClick={() => setPreviewImage(`${process.env.REACT_APP_BACKEND_URL}${url}`)}>
                      <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt={`Payment proof ${i + 1}`} className="w-full h-full object-cover" />
                    </button>
                    {!isDispatched && (canEditOrder) && (
                      <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={async () => {
                          try {
                            await api.delete(`/orders/${id}/images?image_type=payment&image_url=${encodeURIComponent(url)}`);
                            toast.success("Image removed"); loadOrder();
                          } catch { toast.error("Failed to remove"); }
                        }}
                        data-testid={`delete-payment-img-${i}`}>
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tax Invoice */}
      {order.tax_invoice_url && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Tax Invoice</CardTitle>
              <div className="flex gap-2">
                <a href={`${process.env.REACT_APP_BACKEND_URL}${order.tax_invoice_url}`} target="_blank" rel="noopener noreferrer">
                  <Button variant="outline" size="sm" data-testid="view-invoice-btn"><FileText className="w-4 h-4 mr-1" /> View</Button>
                </a>
                {canSharePI && (
                  <Button variant="outline" size="sm" onClick={shareInvoice} data-testid="share-invoice-btn">
                    <Share2 className="w-4 h-4 mr-1 text-green-600" /> Share
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
        </Card>
      )}

      {/* Free Samples */}
      {order.free_samples?.length > 0 && (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Free Samples</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-1" data-testid="free-samples-list">
              {order.free_samples.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-sm p-2 rounded bg-secondary/50">
                  <span className="text-xs font-mono text-muted-foreground">{i + 1}.</span>
                  <span className="font-medium">{s.item_name}</span>
                  {s.description && <span className="text-muted-foreground">- {s.description}</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Packing Images */}
      {(order.packaging?.item_images && Object.keys(order.packaging.item_images).length > 0) || order.packaging?.order_images?.length > 0 || order.packaging?.packed_box_images?.length > 0 ? (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Packing Images</CardTitle>
              {canShareImages && allPackingImageUrls.length > 0 && (
                <Button variant="outline" size="sm" onClick={sharePackingImages} data-testid="share-packing-images-btn">
                  <Share2 className="w-4 h-4 mr-1 text-green-600" /> Share Images
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {order.packaging?.item_images && Object.entries(order.packaging.item_images).map(([key, urls]) => (
              urls?.length > 0 && (
                <div key={key}>
                  <p className="text-xs font-medium text-muted-foreground uppercase mb-2">Item: {key}</p>
                  <div className="flex flex-wrap gap-2">
                    {urls.map((url, i) => (
                      <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                        <button className="w-full h-full" onClick={() => setPreviewImage(`${process.env.REACT_APP_BACKEND_URL}${url}`)}>
                          <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt={`Item ${key}`} className="w-full h-full object-cover" />
                        </button>
                        {!isDispatched && canEditPackaging && (
                          <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={async () => {
                              try {
                                await api.delete(`/orders/${id}/images?image_type=item_image&image_url=${encodeURIComponent(url)}&item_name=${encodeURIComponent(key)}`);
                                toast.success("Image removed"); loadOrder();
                              } catch { toast.error("Failed"); }
                            }}>
                            <X className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )
            ))}
            {order.packaging?.order_images?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase mb-2">Full Order Images</p>
                <div className="flex flex-wrap gap-2">
                  {order.packaging.order_images.map((url, i) => (
                    <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                      <button className="w-full h-full" onClick={() => setPreviewImage(`${process.env.REACT_APP_BACKEND_URL}${url}`)}>
                        <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt={`Order img ${i + 1}`} className="w-full h-full object-cover" />
                      </button>
                      {!isDispatched && canEditPackaging && (
                        <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={async () => { try { await api.delete(`/orders/${id}/images?image_type=order_image&image_url=${encodeURIComponent(url)}`); toast.success("Image removed"); loadOrder(); } catch { toast.error("Failed"); } }}>
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {order.packaging?.packed_box_images?.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase mb-2">Packed Box Images</p>
                <div className="flex flex-wrap gap-2">
                  {order.packaging.packed_box_images.map((url, i) => (
                    <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                      <button className="w-full h-full" onClick={() => setPreviewImage(`${process.env.REACT_APP_BACKEND_URL}${url}`)}>
                        <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt={`Box img ${i + 1}`} className="w-full h-full object-cover" />
                      </button>
                      {!isDispatched && canEditPackaging && (
                        <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={async () => { try { await api.delete(`/orders/${id}/images?image_type=packed_box_image&image_url=${encodeURIComponent(url)}`); toast.success("Image removed"); loadOrder(); } catch { toast.error("Failed"); } }}>
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {/* Packaging, Dispatch, Remark */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Packaging */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Packaging</CardTitle>
              {["admin", "packaging"].includes(user?.role) && order.status !== "dispatched" && (
                <Button variant="outline" size="sm" onClick={openPackaging} data-testid="update-packaging-btn"><Package className="w-4 h-4 mr-1" /> Update</Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {order.packaging?.item_packed_by?.length > 0 && <div><span className="text-muted-foreground">Packed By:</span> {order.packaging.item_packed_by.join(", ")}</div>}
            {order.packaging?.box_packed_by?.length > 0 && <div><span className="text-muted-foreground">Box Packed By:</span> {order.packaging.box_packed_by.join(", ")}</div>}
            {order.packaging?.checked_by?.length > 0 && <div><span className="text-muted-foreground">Checked By:</span> {order.packaging.checked_by.join(", ")}</div>}
            {order.packaging?.packed_at && <div><span className="text-muted-foreground">Packed At:</span> {new Date(order.packaging.packed_at).toLocaleString("en-IN")}</div>}
            {!order.packaging?.packed_at && <p className="text-muted-foreground">Not yet packed.</p>}
          </CardContent>
        </Card>

        {/* Dispatch */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Dispatch</CardTitle>
              {["admin", "dispatch"].includes(user?.role) && order.status === "packed" && (
                <Button variant="outline" size="sm" onClick={openDispatch} data-testid="dispatch-order-btn"><Truck className="w-4 h-4 mr-1" /> Dispatch</Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {order.dispatch?.dispatched_at ? (
              <>
                <div><span className="text-muted-foreground">Dispatched:</span> {new Date(order.dispatch.dispatched_at).toLocaleString("en-IN")}</div>
                {order.dispatch.courier_name && <div><span className="text-muted-foreground">Courier:</span> {order.dispatch.courier_name}</div>}
                {order.dispatch.transporter_name && <div><span className="text-muted-foreground">Transporter:</span> {order.dispatch.transporter_name}</div>}
                {order.dispatch.lr_no && <div><span className="text-muted-foreground">LR No:</span> {order.dispatch.lr_no}</div>}
              </>
            ) : <p className="text-muted-foreground">Not dispatched yet.</p>}
          </CardContent>
        </Card>
      </div>

      {order.remark && (
        <Card>
          <CardContent className="pt-6"><p className="text-sm"><span className="font-medium">Remarks:</span> {order.remark}</p></CardContent>
        </Card>
      )}

      {/* Formulation Dialog */}
      <Dialog open={showFormulation} onOpenChange={setShowFormulation}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Edit Formulations</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {formulationItems.map((item, i) => (
              <div key={i} className="space-y-1">
                <Label className="text-sm font-medium">{item.product_name}</Label>
                <Textarea value={item.formulation} onChange={(e) => {
                  const updated = [...formulationItems];
                  updated[i] = { ...updated[i], formulation: e.target.value };
                  setFormulationItems(updated);
                }} placeholder="Enter formulation..." className="min-h-[80px]" data-testid={`formulation-input-${i}`} />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFormulation(false)}>Cancel</Button>
            <Button onClick={saveFormulation} disabled={saving}>{saving ? "Saving..." : "Save Formulations"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Packaging Dialog - Simplified */}
      <Dialog open={showPackaging} onOpenChange={setShowPackaging}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Update Packaging</DialogTitle></DialogHeader>
          <PackagingForm order={order} staffList={packagingStaff} onSave={savePackaging} onCancel={() => setShowPackaging(false)} saving={saving} />
        </DialogContent>
      </Dialog>

      {/* Dispatch Dialog */}
      <Dialog open={showDispatch} onOpenChange={setShowDispatch}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Dispatch Order</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Dispatch Type</Label>
              <Select value={dispatchData.dispatch_type} onValueChange={(v) => setDispatchData({ ...dispatchData, dispatch_type: v })}>
                <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
                <SelectContent><SelectItem value="courier">Courier</SelectItem><SelectItem value="transport">Transport</SelectItem><SelectItem value="porter">Porter</SelectItem><SelectItem value="self_arranged">Self-Arranged</SelectItem><SelectItem value="office_collection">Office Collection</SelectItem></SelectContent>
              </Select>
            </div>
            {dispatchData.dispatch_type === "courier" && (
              <div><Label>Courier</Label>
                <Select value={dispatchData.courier_name} onValueChange={(v) => setDispatchData({ ...dispatchData, courier_name: v })}>
                  <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>{COURIER_OPTIONS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {dispatchData.dispatch_type === "transport" && (
              <div><Label>Transporter</Label><Input value={dispatchData.transporter_name} onChange={(e) => setDispatchData({ ...dispatchData, transporter_name: e.target.value })} /></div>
            )}
            <div><Label>LR / Tracking No.</Label><Input value={dispatchData.lr_no} onChange={(e) => setDispatchData({ ...dispatchData, lr_no: e.target.value })} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDispatch(false)}>Cancel</Button>
            <Button onClick={saveDispatch} disabled={saving}>{saving ? "Dispatching..." : "Dispatch"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Order</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground mb-2">Type <span className="font-bold text-foreground">{order.order_number}</span> to confirm deletion. This action is permanent.</p>
          <Input value={deleteConfirmText} onChange={(e) => setDeleteConfirmText(e.target.value)} placeholder={order.order_number} data-testid="delete-confirm-input" />
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowDeleteConfirm(false); setDeleteConfirmText(""); }}>Cancel</Button>
            <Button variant="destructive" onClick={deleteOrder} disabled={deleteConfirmText !== order.order_number} data-testid="confirm-delete-order">Delete Permanently</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Image Preview Modal */}
      <Dialog open={!!previewImage} onOpenChange={() => setPreviewImage(null)}>
        <DialogContent className="max-w-3xl p-2">
          <DialogHeader><DialogTitle className="sr-only">Image Preview</DialogTitle></DialogHeader>
          {previewImage && <img src={previewImage} alt="Preview" className="w-full h-auto rounded-lg max-h-[80vh] object-contain" />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PackagingForm({ order, staffList, onSave, onCancel, saving }) {
  const [itemPackedBy, setItemPackedBy] = useState(order.packaging?.item_packed_by || []);
  const [boxPackedBy, setBoxPackedBy] = useState(order.packaging?.box_packed_by || []);
  const [checkedBy, setCheckedBy] = useState(order.packaging?.checked_by || []);

  const toggleStaff = (list, setList, name) => {
    setList(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);
  };

  return (
    <div className="space-y-4">
      {[["Item Packed By", itemPackedBy, setItemPackedBy], ["Box Packed By", boxPackedBy, setBoxPackedBy], ["Checked By", checkedBy, setCheckedBy]].map(([label, list, setter]) => (
        <div key={label}>
          <Label className="text-sm">{label}</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            {staffList.map(s => (
              <Button key={s.id} variant={list.includes(s.name) ? "default" : "outline"} size="sm" onClick={() => toggleStaff(list, setter, s.name)}>
                {s.name}
              </Button>
            ))}
            {staffList.length === 0 && <p className="text-xs text-muted-foreground">No staff configured</p>}
          </div>
        </div>
      ))}
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button onClick={() => onSave({ item_packed_by: itemPackedBy, box_packed_by: boxPackedBy, checked_by: checkedBy })} disabled={saving}>
          {saving ? "Saving..." : "Save Packaging"}
        </Button>
      </DialogFooter>
    </div>
  );
}
