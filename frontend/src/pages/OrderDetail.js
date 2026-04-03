import { useState, useEffect } from "react";
import { ArrowLeft, Package, Truck, Edit, Printer, Trash2, FileText, X, Share2, Copy, ClipboardCopy, History, Upload, Lock } from "lucide-react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
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
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { mobilePrintPdf } from "@/lib/mobilePrint";
import { SlipScanner } from "@/components/SlipScanner";

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
  const [formulationFreeSamples, setFormulationFreeSamples] = useState([]);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [formulationHistory, setFormulationHistory] = useState([]);
  const [formulationVisible, setFormulationVisible] = useState(true);
  const [packagingStaff, setPackagingStaff] = useState([]);
  const [dispatchData, setDispatchData] = useState({ courier_name: "", transporter_name: "", lr_no: "", dispatch_type: "" });
  const [dispatchSlipImages, setDispatchSlipImages] = useState([]);
  const [previewImage, setPreviewImage] = useState(null);
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerGst, setCustomerGst] = useState("");
  const [customerAlias, setCustomerAlias] = useState("");
  const [statusUpdating, setStatusUpdating] = useState(false);

  useEffect(() => { loadOrder(); }, [id]);

  useEffect(() => {
    if (user?.role === "packaging") {
      api.get("/settings").then(r => setFormulationVisible(r.data?.show_formulation || false)).catch(() => {});
    }
  }, [user?.role]);

  useEffect(() => {
    if (order?.customer_id) {
      // Customer data is now enriched in the order response
      const phones = order.customer_phone || [];
      if (phones.length) setCustomerPhone(phones[0]);
      setCustomerGst(order.customer_gst_no || "");
      setCustomerAlias(order.customer_alias || "");
    }
  }, [order?.customer_id, order?.customer_phone, order?.customer_gst_no, order?.customer_alias]);

  const loadOrder = async () => {
    try { const res = await api.get(`/orders/${id}`); setOrder(res.data); }
    catch { toast.error("Order not found"); navigate("/"); }
    finally { setLoading(false); }
  };

  const isDispatched = order?.status === "dispatched";
  const isAdmin = user?.role === "admin";
  const canEditOrder = user?.role === "admin" || (user?.role === "telecaller" && order?.telecaller_id === user?.id);
  const canEditFormulation = user?.role === "admin" || (user?.role === "packaging" && formulationVisible);
  const showFormulations = user?.role === "admin" || (user?.role === "packaging" && formulationVisible);
  const canEditPackaging = user?.role === "admin" || (user?.role === "packaging" && !isDispatched);
  const canEditDispatch = ["admin", "dispatch", "packaging"].includes(user?.role);
  const canSharePI = ["admin", "telecaller"].includes(user?.role);
  const canShareImages = ["admin", "telecaller", "packaging"].includes(user?.role);
  // Telecaller can edit payment on own orders even after dispatch
  const canEditPayment = isAdmin || (user?.role === "telecaller" && order?.telecaller_id === user?.id);

  const openEdit = () => {
    if (isDispatched && !isAdmin) return toast.error("Cannot edit dispatched order");
    navigate(`/orders/${id}/edit`);
  };

  const openFormulation = () => {
    setFormulationItems(order.items.map(i => ({
      product_name: i.product_name, description: i.description || "", formulation: i.formulation || "",
      qty: i.qty, unit: i.unit, amount: i.amount || 0, gst_applicable: order.gst_applicable,
    })));
    setFormulationFreeSamples((order.free_samples || []).map(s => ({
      item_name: s.item_name, description: s.description || "", formulation: s.formulation || "",
    })));
    setShowFormulation(true);
  };

  const loadFormulationHistory = async () => {
    if (!order?.customer_id) return;
    try {
      const res = await api.get(`/orders/formulation-history/${order.customer_id}`);
      setFormulationHistory(res.data);
      setShowHistory(true);
    } catch { toast.error("Failed to load history"); }
  };

  const saveFormulation = async () => {
    setSaving(true);
    try {
      const items = formulationItems.map((item, i) => ({ index: i, formulation: item.formulation }));
      const fsSamples = formulationFreeSamples.map((s, i) => ({ is_free_sample: true, fs_index: i, formulation: s.formulation }));
      await api.put(`/orders/${id}/formulation`, { items: [...items, ...fsSamples] });
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
    const d = order.dispatch || {};
    setDispatchData({
      courier_name: d.courier_name || order.courier_name || "",
      transporter_name: d.transporter_name || order.transporter_name || "",
      lr_no: d.lr_no || "",
      dispatch_type: d.dispatch_type || order.shipping_method || "",
    });
    setDispatchSlipImages(d.dispatch_slip_images || []);
    setShowDispatch(true);
  };

  const saveDispatch = async () => {
    setSaving(true);
    try {
      await api.put(`/orders/${id}/dispatch`, { ...dispatchData, dispatch_slip_images: dispatchSlipImages });
      toast.success("Order dispatched!"); setShowDispatch(false); loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const handlePrint = () => {
    const token = localStorage.getItem("token");
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/orders/${id}/print?token=${token}`;
    const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    fetch(url).then(res => res.blob()).then(blob => {
      if (isMobile) {
        mobilePrintPdf(blob, `${order.order_number || "order"}.pdf`);
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

  const copyToClipboard = (text, label) => {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copied!`)).catch(() => toast.error("Copy failed"));
  };

  const deleteOrder = async () => {
    if (deleteConfirmText !== order.order_number) return toast.error("Type the order number to confirm");
    try { await api.delete(`/orders/${id}`); toast.success("Order deleted"); navigate("/all-orders"); }
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

  const packedBoxImageUrls = order.packaging?.packed_box_images || [];

  const sharePackedBoxImages = async () => {
    const dispatchSlipUrls = order.dispatch?.dispatch_slip_images || [];
    const allUrls = [...packedBoxImageUrls, ...dispatchSlipUrls];
    if (!allUrls.length) return toast.error("No images to share");
    try {
      const blobs = await Promise.all(
        allUrls.map(url => fetch(`${process.env.REACT_APP_BACKEND_URL}${url}`).then(r => r.blob()))
      );
      const files = blobs.map((blob, i) => {
        const ext = blob.type.includes("png") ? "png" : "jpg";
        const label = i < packedBoxImageUrls.length ? `packed-box-${i + 1}` : `dispatch-slip-${i - packedBoxImageUrls.length + 1}`;
        return new File([blob], `${label}-${order.order_number}.${ext}`, { type: blob.type });
      });

      if (navigator.canShare && navigator.canShare({ files })) {
        await navigator.share({ files, title: `Packed Box Images - ${order.order_number}` });
      } else {
        files.forEach((file) => {
          const url = URL.createObjectURL(file);
          const a = document.createElement("a");
          a.href = url;
          a.download = file.name;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        });
        toast.success("Packed box images downloaded. Opening WhatsApp...");
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

  const shareDispatchSlip = async () => {
    const slipUrls = order.dispatch?.dispatch_slip_images || [];
    if (!slipUrls.length) return toast.error("No dispatch slip to share");
    try {
      const blobs = await Promise.all(
        slipUrls.map(url => fetch(`${process.env.REACT_APP_BACKEND_URL}${url}`).then(r => r.blob()))
      );
      const files = blobs.map((blob, i) => {
        const ext = blob.type.includes("png") ? "png" : "jpg";
        return new File([blob], `dispatch-slip-${order.order_number}-${i + 1}.${ext}`, { type: blob.type });
      });
      if (navigator.canShare && navigator.canShare({ files })) {
        await navigator.share({ files, title: `Dispatch Slip - ${order.order_number}` });
      } else {
        files.forEach((file) => {
          const url = URL.createObjectURL(file);
          const a = document.createElement("a");
          a.href = url; a.download = file.name;
          document.body.appendChild(a); a.click();
          document.body.removeChild(a); URL.revokeObjectURL(url);
        });
        toast.success("Dispatch slip downloaded.");
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

  const markPacked = async () => {
    setStatusUpdating(true);
    try {
      await api.put(`/orders/${id}/mark-packed`);
      toast.success("Order marked as Packed");
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setStatusUpdating(false); }
  };

  const undoPacked = async () => {
    setStatusUpdating(true);
    try {
      await api.put(`/orders/${id}/undo-packed`);
      toast.success("Order reverted to Packaging");
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setStatusUpdating(false); }
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
          {order.formulation_locked && <Badge variant="outline" className="text-amber-600 border-amber-300 text-xs"><Lock className="w-3 h-3 mr-1" />Formulation Locked</Badge>}
          {(user?.role === "admin" || user?.role === "telecaller") && (
            <Button variant="outline" size="sm" onClick={() => navigate(`/create-order?duplicate=${id}`)} data-testid="duplicate-order-btn"><Copy className="w-4 h-4 mr-1" /> Duplicate</Button>
          )}
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={openEdit} data-testid="edit-order-btn"><Edit className="w-4 h-4 mr-1" /> Edit</Button>
          )}
          {!isAdmin && (canEditOrder || canEditPackaging || canEditDispatch) && !isDispatched && (
            <Button variant="outline" size="sm" onClick={openEdit} data-testid="edit-order-btn"><Edit className="w-4 h-4 mr-1" /> Edit</Button>
          )}
          {canEditFormulation && <Button variant="outline" size="sm" onClick={openFormulation} data-testid="formulation-btn"><FileText className="w-4 h-4 mr-1" /> Formulation</Button>}
          {canEditFormulation && <Button variant="outline" size="sm" onClick={loadFormulationHistory} data-testid="formulation-history-btn"><History className="w-4 h-4 mr-1" /> History</Button>}
          {["admin", "packaging"].includes(user?.role) && ["new", "packaging"].includes(order.status) && (
            <Button variant="default" size="sm" onClick={markPacked} disabled={statusUpdating} data-testid="mark-packed-btn"><Package className="w-4 h-4 mr-1" /> Mark Packed</Button>
          )}
          {["admin", "packaging"].includes(user?.role) && order.status === "packed" && (
            <Button variant="outline" size="sm" onClick={undoPacked} disabled={statusUpdating} data-testid="undo-packed-btn">Undo Packed</Button>
          )}
          {user?.role === "admin" && <Button variant="destructive" size="sm" onClick={() => setShowDeleteConfirm(true)} data-testid="delete-order-btn"><Trash2 className="w-4 h-4 mr-1" /> Delete</Button>}
          {user?.role === "telecaller" && canEditOrder && !isDispatched && <Button variant="destructive" size="sm" onClick={() => setShowDeleteConfirm(true)} data-testid="delete-order-btn"><Trash2 className="w-4 h-4 mr-1" /> Delete</Button>}
        </div>
      </div>

      {isDispatched && !isAdmin && <div className="p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 text-sm text-purple-800 dark:text-purple-200" data-testid="dispatch-lock-notice">This order has been dispatched. Editing is locked (formulation changes only).</div>}

      {/* Customer Info */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Customer Information</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Customer</span><span className="text-sm font-medium">{order.customer_name}{customerAlias ? <span className="text-muted-foreground font-normal"> ({customerAlias})</span> : ""}</span></div>
          {customerPhone && (
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Phone</span>
              <button className="text-sm font-medium flex items-center gap-1 hover:text-primary transition-colors" onClick={() => copyToClipboard(customerPhone, "Phone number")} data-testid="copy-phone-btn">
                {customerPhone} <ClipboardCopy className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          {customerGst && (
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">GST Number</span>
              <button className="text-sm font-mono font-medium flex items-center gap-1 hover:text-primary transition-colors" onClick={() => copyToClipboard(customerGst, "GST number")} data-testid="copy-gst-btn">
                {customerGst} <ClipboardCopy className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
          {order.billing_address && (
            <div className="flex justify-between items-start gap-4">
              <span className="text-sm text-muted-foreground shrink-0">Billing Address</span>
              <div className="text-sm text-right max-w-[65%] flex items-start gap-1">
                <span className="leading-relaxed whitespace-pre-line break-words">{order.billing_address.address_line}{order.billing_address.city ? `\n${order.billing_address.city}` : ""}{order.billing_address.state ? `, ${order.billing_address.state}` : ""}{order.billing_address.pincode ? ` - ${order.billing_address.pincode}` : ""}</span>
                <button className="shrink-0 mt-0.5 hover:text-primary transition-colors" onClick={() => copyToClipboard(`${order.billing_address.address_line}, ${order.billing_address.city}, ${order.billing_address.state} - ${order.billing_address.pincode}`, "Billing address")} data-testid="copy-billing-address-btn">
                  <ClipboardCopy className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
          {order.shipping_address && (
            <div className="flex justify-between items-start gap-4">
              <span className="text-sm text-muted-foreground shrink-0">Shipping Address</span>
              <div className="text-sm text-right max-w-[65%] flex items-start gap-1">
                <span className="leading-relaxed whitespace-pre-line break-words">{order.shipping_address.address_name ? `${order.shipping_address.address_name}\n` : ""}{order.shipping_address.address_line}{order.shipping_address.city ? `\n${order.shipping_address.city}` : ""}{order.shipping_address.state ? `, ${order.shipping_address.state}` : ""}{order.shipping_address.pincode ? ` - ${order.shipping_address.pincode}` : ""}</span>
                <button className="shrink-0 mt-0.5 hover:text-primary transition-colors" onClick={() => copyToClipboard(`${order.shipping_address.address_line}, ${order.shipping_address.city}, ${order.shipping_address.state} - ${order.shipping_address.pincode}`, "Shipping address")} data-testid="copy-shipping-address-btn">
                  <ClipboardCopy className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
          {order.purpose && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Purpose</span><span className="text-sm">{order.purpose}</span></div>}
          <div className="flex justify-between"><span className="text-sm text-muted-foreground">Created</span><span className="text-sm">{new Date(order.created_at).toLocaleString("en-IN")}</span></div>
        </CardContent>
      </Card>

      {/* Shipping Details */}
      {(order.shipping_method || order.dispatch) && (
        <Card data-testid="shipping-details-card">
          <CardHeader className="pb-3"><CardTitle className="text-base">Shipping Details</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Shipping Method</span>
              <span className="text-sm font-medium capitalize" data-testid="order-shipping-method">{(order.dispatch?.dispatch_type || order.shipping_method || "")?.replace(/_/g, " ")}</span>
            </div>
            {(order.dispatch?.courier_name || order.courier_name) && (
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Courier Name</span>
                <span className="text-sm" data-testid="order-courier-name">{order.dispatch?.courier_name || order.courier_name}</span>
              </div>
            )}
            {(order.dispatch?.transporter_name || order.transporter_name) && (
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Transporter Name</span>
                <span className="text-sm" data-testid="order-transporter-name">{order.dispatch?.transporter_name || order.transporter_name}</span>
              </div>
            )}
            {order.dispatch?.lr_no && (
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">LR No</span>
                <span className="text-sm font-mono" data-testid="order-lr">{order.dispatch.lr_no}</span>
              </div>
            )}
            {order.dispatch?.tracking_number && (
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Tracking Number</span>
                <span className="text-sm font-mono" data-testid="order-tracking">{order.dispatch.tracking_number}</span>
              </div>
            )}
            {order.extra_shipping_details && (
              <div className="flex justify-between items-start">
                <span className="text-sm text-muted-foreground">Extra Details</span>
                <span className="text-sm text-right max-w-[60%]" data-testid="extra-shipping-details">{order.extra_shipping_details}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Items */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Items ({order.items?.length})</CardTitle></CardHeader>
        <CardContent>
            <Table className="min-w-[600px]">
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
          <div className="mt-4 space-y-2 text-sm">
            <Separator />
            <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span className="font-mono">{"\u20B9"}{order.subtotal?.toFixed(2)}</span></div>
            {order.gst_applicable && <div className="flex justify-between"><span className="text-muted-foreground">GST</span><span className="font-mono">{"\u20B9"}{order.total_gst?.toFixed(2)}</span></div>}
            {order.shipping_charge > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping</span><span className="font-mono">{"\u20B9"}{order.shipping_charge?.toFixed(2)}</span></div>}
            {order.shipping_gst > 0 && <div className="flex justify-between"><span className="text-muted-foreground">Shipping GST</span><span className="font-mono">{"\u20B9"}{order.shipping_gst?.toFixed(2)}</span></div>}
            {order.additional_charges?.filter(c => c.amount > 0).map((c, i) => (
              <div key={i}>
                <div className="flex justify-between"><span className="text-muted-foreground">{c.name || "Charge"}</span><span className="font-mono">{"\u20B9"}{c.amount?.toFixed(2)}</span></div>
                {c.gst_amount > 0 && <div className="flex justify-between"><span className="text-muted-foreground">{c.name} GST ({c.gst_percent}%)</span><span className="font-mono">{"\u20B9"}{c.gst_amount?.toFixed(2)}</span></div>}
              </div>
            ))}
            <Separator />
            <div className="flex justify-between text-base font-bold"><span>Grand Total</span><span className="font-mono">{"\u20B9"}{order.grand_total}</span></div>
          </div>
        </CardContent>
      </Card>

      {/* Payment */}
      <PaymentSection order={order} user={user} canEditPayment={canEditPayment} isDispatched={isDispatched} isAdmin={isAdmin} orderId={id} onReload={loadOrder} setPreviewImage={setPreviewImage} />

      {/* Payment Verification */}
      {["admin", "accounts"].includes(user?.role) && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Payment Verification</CardTitle>
              <Badge className={`text-xs ${
                order.payment_check_status === "received" ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" :
                order.payment_check_status === "pending_recheck" ? "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" :
                "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400"
              }`} data-testid="payment-check-badge">
                {order.payment_check_status === "received" ? "Received" : order.payment_check_status === "pending_recheck" ? "Pending Re-check" : "Pending"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Button size="sm" variant={order.payment_check_status === "received" ? "default" : "outline"}
                className={order.payment_check_status === "received" ? "bg-green-600 hover:bg-green-700" : ""}
                onClick={async () => {
                  try { await api.put(`/orders/${id}/payment-check`, { payment_check_status: "received" }); toast.success("Payment marked as received"); loadOrder(); }
                  catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
                }}
                data-testid="mark-received-btn">
                Mark Received
              </Button>
              <Button size="sm" variant={order.payment_check_status === "pending" ? "default" : "outline"}
                className={order.payment_check_status === "pending" ? "bg-yellow-600 hover:bg-yellow-700" : ""}
                onClick={async () => {
                  try { await api.put(`/orders/${id}/payment-check`, { payment_check_status: "pending" }); toast.success("Payment marked as pending"); loadOrder(); }
                  catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
                }}
                data-testid="mark-pending-btn">
                Mark Pending
              </Button>
            </div>
            {order.payment_checked_by && (
              <p className="text-xs text-muted-foreground mt-2">Last checked by: {order.payment_checked_by} on {order.payment_checked_at ? new Date(order.payment_checked_at).toLocaleString("en-IN") : "-"}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Payment Check Status (view only for telecaller) */}
      {user?.role === "telecaller" && order.payment_check_status && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Payment Verification</CardTitle>
              <Badge className={`text-xs ${
                order.payment_check_status === "received" ? "bg-green-100 text-green-800" :
                order.payment_check_status === "pending_recheck" ? "bg-red-100 text-red-800" :
                "bg-yellow-100 text-yellow-800"
              }`}>
                {order.payment_check_status === "received" ? "Received" : order.payment_check_status === "pending_recheck" ? "Pending Re-check" : "Pending"}
              </Badge>
            </div>
          </CardHeader>
        </Card>
      )}

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
                <div key={i} className="text-sm p-2 rounded bg-secondary/50 space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-muted-foreground">{i + 1}.</span>
                    <span className="font-medium">{s.item_name}</span>
                    {s.description && <span className="text-muted-foreground">- {s.description}</span>}
                  </div>
                  {showFormulations && s.formulation && (
                    <p className="text-xs text-amber-600 ml-6">{s.formulation}</p>
                  )}
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
                <div className="flex gap-2 flex-wrap">
                  <Button variant="outline" size="sm" onClick={sharePackingImages} data-testid="share-packing-images-btn">
                    <Share2 className="w-4 h-4 mr-1 text-green-600" /> Share All Images
                  </Button>
                  {(packedBoxImageUrls.length > 0 || order.dispatch?.dispatch_slip_images?.length > 0) && (
                    <Button variant="outline" size="sm" onClick={sharePackedBoxImages} data-testid="share-packed-box-images-btn">
                      <Share2 className="w-4 h-4 mr-1 text-blue-600" /> Share Packed Box Images
                    </Button>
                  )}
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {order.packaging?.item_images && Object.entries(order.packaging.item_images).map(([key, urls]) => (
              urls?.length > 0 && (
                <div key={key}>
                  <p className="text-xs font-medium text-muted-foreground uppercase mb-2">Item: {key.includes("__") ? key.split("__")[0] : key}</p>
                  <div className="flex flex-wrap gap-2">
                    {urls.map((url, i) => (
                      <div key={i} className="relative w-20 h-20 rounded-lg border overflow-hidden group">
                        <button className="w-full h-full" onClick={() => setPreviewImage(`${process.env.REACT_APP_BACKEND_URL}${url}`)}>
                          <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt={`Item ${key}`} className="w-full h-full object-cover" />
                        </button>
                        {canEditPackaging && (
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
                      {canEditPackaging && (
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
                      {canEditPackaging && (
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
              {canEditPackaging && (
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
              {["admin", "dispatch", "packaging"].includes(user?.role) && (order.status === "packed" || order.status === "dispatched") && (
                <Button variant="outline" size="sm" onClick={openDispatch} data-testid="dispatch-order-btn">
                  <Truck className="w-4 h-4 mr-1" /> {order.status === "dispatched" ? "Edit Dispatch" : "Dispatch"}
                </Button>
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
                {order.dispatch.dispatch_slip_images?.length > 0 && (
                  <div className="pt-2">
                    <span className="text-muted-foreground text-xs uppercase font-medium">Dispatch Slip</span>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {order.dispatch.dispatch_slip_images.map((url, i) => (
                        <button key={i} className="w-16 h-16 rounded border overflow-hidden" onClick={() => setPreviewImage(`${process.env.REACT_APP_BACKEND_URL}${url}`)}>
                          <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt={`Slip ${i+1}`} className="w-full h-full object-cover" />
                        </button>
                      ))}
                    </div>
                    {["admin", "telecaller", "packaging", "dispatch"].includes(user?.role) && (
                      <Button variant="outline" size="sm" className="mt-2" onClick={shareDispatchSlip} data-testid="share-dispatch-slip-btn">
                        <Share2 className="w-4 h-4 mr-1 text-blue-600" /> Share Slip
                      </Button>
                    )}
                  </div>
                )}
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
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              Edit Formulations
              <Button variant="ghost" size="sm" onClick={loadFormulationHistory} data-testid="formulation-history-in-edit">
                <History className="w-4 h-4 mr-1" /> History
              </Button>
            </DialogTitle>
            <DialogDescription>Set formulations for order items and free samples.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {formulationItems.map((item, i) => (
              <div key={i} className="space-y-1">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <Label className="text-sm font-medium">{item.product_name}</Label>
                  {item.description && <span className="text-xs text-muted-foreground">— {item.description}</span>}
                  <span className="text-xs text-muted-foreground">Qty: {item.qty} {item.unit}</span>
                  {item.amount > 0 && <span className="text-xs text-muted-foreground">Amt: {"\u20B9"}{item.amount}{item.gst_applicable ? " (excl. GST)" : ""}</span>}
                </div>
                <Textarea value={item.formulation} onChange={(e) => {
                  const updated = [...formulationItems];
                  updated[i] = { ...updated[i], formulation: e.target.value };
                  setFormulationItems(updated);
                }} placeholder="Enter formulation..." className="min-h-[80px]" data-testid={`formulation-input-${i}`} />
              </div>
            ))}
            {formulationFreeSamples.length > 0 && (
              <>
                <Separator />
                <Label className="text-sm font-medium text-muted-foreground">Free Samples</Label>
                {formulationFreeSamples.map((sample, i) => (
                  <div key={`fs-${i}`} className="space-y-1">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                      <Label className="text-sm font-medium">{sample.item_name}</Label>
                      {sample.description && <span className="text-xs text-muted-foreground">{sample.description}</span>}
                      <Badge variant="outline" className="text-xs">Free Sample</Badge>
                    </div>
                    <Textarea value={sample.formulation} onChange={(e) => {
                      const updated = [...formulationFreeSamples];
                      updated[i] = { ...updated[i], formulation: e.target.value };
                      setFormulationFreeSamples(updated);
                    }} placeholder="Enter formulation for free sample..." className="min-h-[80px]" data-testid={`fs-formulation-input-${i}`} />
                  </div>
                ))}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFormulation(false)}>Cancel</Button>
            <Button onClick={saveFormulation} disabled={saving}>{saving ? "Saving..." : "Save Formulations"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Packaging Dialog - Simplified */}
      <Dialog open={showPackaging} onOpenChange={setShowPackaging}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
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
            <div><Label>LR / Tracking No.</Label><Input value={dispatchData.lr_no} onChange={(e) => setDispatchData({ ...dispatchData, lr_no: e.target.value })} data-testid="dispatch-lr-input" /></div>
            <div>
              <Label className="mb-2 block">Courier / Transport Slip</Label>
              <SlipScanner
                onBarcodeDetected={(code) => setDispatchData(prev => ({ ...prev, lr_no: code }))}
                slipImages={dispatchSlipImages}
                onSlipImagesChange={setDispatchSlipImages}
              />
            </div>
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

      {/* Formulation History Dialog */}
      <Dialog open={showHistory} onOpenChange={setShowHistory}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Formulation History</DialogTitle></DialogHeader>
          {formulationHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No formulation history found.</p>
          ) : (
            <div className="space-y-4">
              {formulationHistory.map((h, i) => (
                <div key={i} className="border rounded-lg p-3 space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-medium text-sm">{h.order_number}</span>
                    <span className="text-xs text-muted-foreground">{new Date(h.created_at).toLocaleDateString("en-IN")}</span>
                  </div>
                  {h.items?.filter(it => it.formulation).map((it, j) => (
                    <div key={j} className="border-l-2 border-amber-400 pl-3">
                      <p className="text-sm">{it.product_name} ({it.qty} {it.unit})</p>
                      <p className="text-xs text-amber-600">{it.formulation}</p>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
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

function PaymentSection({ order, user, canEditPayment, isDispatched, isAdmin, orderId, onReload, setPreviewImage }) {
  const [editing, setEditing] = useState(false);
  const [payStatus, setPayStatus] = useState(order.payment_status || "unpaid");
  const [modeOfPayment, setModeOfPayment] = useState(order.mode_of_payment || "");
  const [paymentModeDetails, setPaymentModeDetails] = useState(order.payment_mode_details || "");
  const [amountPaid, setAmountPaid] = useState(order.amount_paid || 0);
  const [screenshots, setScreenshots] = useState(order.payment_screenshots || []);
  const [saving, setSaving] = useState(false);

  const PAYMENT_MODES = ["Cash", "Online", "Other"];
  const grandTotal = order.grand_total || 0;
  const balanceAmount = payStatus === "full" ? 0 : payStatus === "partial" ? Math.max(0, grandTotal - amountPaid) : grandTotal;

  const handleScreenshotUpload = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    for (const file of files) {
      const compressed = await compressImage(file);
      const formData = new FormData();
      formData.append("file", compressed);
      try {
        const res = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
        setScreenshots(prev => [...prev, res.data.url]);
      } catch { toast.error("Upload failed"); }
    }
    e.target.value = "";
  };

  const savePayment = async () => {
    setSaving(true);
    try {
      await api.put(`/orders/${orderId}`, {
        payment_status: payStatus,
        mode_of_payment: modeOfPayment,
        payment_mode_details: paymentModeDetails,
        amount_paid: payStatus === "full" ? grandTotal : amountPaid,
        balance_amount: balanceAmount,
        payment_screenshots: screenshots,
      });
      toast.success("Payment details updated");
      setEditing(false);
      onReload();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed to update"); }
    finally { setSaving(false); }
  };

  if (editing) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Edit Payment Details</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label className="text-sm">Payment Status</Label>
              <Select value={payStatus} onValueChange={setPayStatus}>
                <SelectTrigger data-testid="edit-pay-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="unpaid">Unpaid</SelectItem>
                  <SelectItem value="partial">Partial</SelectItem>
                  <SelectItem value="full">Full</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm">Mode of Payment</Label>
              <Select value={modeOfPayment} onValueChange={setModeOfPayment}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>{PAYMENT_MODES.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {modeOfPayment === "Other" && (
              <div><Label className="text-sm">Payment Details</Label><Input value={paymentModeDetails} onChange={e => setPaymentModeDetails(e.target.value)} /></div>
            )}
          </div>
          {payStatus === "partial" && (
            <div className="grid grid-cols-2 gap-4">
              <div><Label className="text-sm">Amount Paid</Label><Input type="number" value={amountPaid || ""} onChange={e => setAmountPaid(+e.target.value)} data-testid="edit-pay-amount" /></div>
              <div><Label className="text-sm">Balance</Label><Input type="number" value={balanceAmount} readOnly className="bg-muted" /></div>
            </div>
          )}
          <div>
            <Label className="text-sm">Payment Screenshots</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              <label className="cursor-pointer inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90">
                Gallery / Files
                <input type="file" multiple accept="image/*" onChange={handleScreenshotUpload} className="hidden" data-testid="pay-screenshot-input" />
              </label>
              <label className="cursor-pointer inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary text-secondary-foreground hover:bg-secondary/80">
                Camera
                <input type="file" accept="image/*" capture="environment" onChange={handleScreenshotUpload} className="hidden" data-testid="pay-screenshot-camera" />
              </label>
            </div>
            {screenshots.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {screenshots.map((url, i) => (
                  <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
                    <img src={`${process.env.REACT_APP_BACKEND_URL}${url}`} alt="" className="w-full h-full object-cover" />
                    <button className="absolute inset-0 bg-red-500/80 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                      onClick={() => setScreenshots(prev => prev.filter((_, j) => j !== i))}>
                      <X className="w-4 h-4 text-white" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="flex justify-end">
            <Button onClick={savePayment} disabled={saving} data-testid="save-payment-btn">{saving ? "Saving..." : "Save Payment"}</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Payment Details</CardTitle>
          {canEditPayment && (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)} data-testid="edit-payment-btn"><Edit className="w-4 h-4 mr-1" /> Edit</Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex justify-between"><span className="text-sm text-muted-foreground">Status</span><Badge variant="outline">{order.payment_status}</Badge></div>
        {order.mode_of_payment && <div className="flex justify-between"><span className="text-sm text-muted-foreground">Mode</span><span className="text-sm">{order.mode_of_payment}{order.payment_mode_details ? ` (${order.payment_mode_details})` : ""}</span></div>}
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
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PackagingForm({ order, staffList, onSave, onCancel, saving }) {
  const [itemPackedBy, setItemPackedBy] = useState(order.packaging?.item_packed_by || []);
  const [boxPackedBy, setBoxPackedBy] = useState(order.packaging?.box_packed_by || []);
  const [checkedBy, setCheckedBy] = useState(order.packaging?.checked_by || []);
  const [itemImages, setItemImages] = useState(order.packaging?.item_images || {});
  const [orderImages, setOrderImages] = useState(order.packaging?.order_images || []);
  const [packedBoxImages, setPackedBoxImages] = useState(order.packaging?.packed_box_images || []);
  const [uploading, setUploading] = useState(false);

  const toggleStaff = (list, setList, name) => {
    setList(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);
  };

  const uploadImage = async (file, target, itemKey) => {
    const compressed = await compressImage(file);
    const form = new FormData();
    form.append("file", compressed);
    setUploading(true);
    try {
      const res = await api.post("/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      const url = res.data.url;
      if (target === "item" && itemKey) {
        setItemImages(prev => ({ ...prev, [itemKey]: [...(prev[itemKey] || []), url] }));
      } else if (target === "order") {
        setOrderImages(prev => [...prev, url]);
      } else if (target === "packed_box") {
        setPackedBoxImages(prev => [...prev, url]);
      }
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  const removeImage = (target, url, itemKey) => {
    if (target === "item" && itemKey) {
      setItemImages(prev => ({ ...prev, [itemKey]: (prev[itemKey] || []).filter(u => u !== url) }));
    } else if (target === "order") {
      setOrderImages(prev => prev.filter(u => u !== url));
    } else if (target === "packed_box") {
      setPackedBoxImages(prev => prev.filter(u => u !== url));
    }
  };

  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  return (
    <div className="space-y-4">
      {/* Staff Selection */}
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

      <Separator />

      {/* Image Upload Section */}
      <div className="space-y-4">
        <Label className="text-sm font-medium">Packaging Images</Label>

        {/* Item Images */}
        {order.items?.map((item, idx) => {
          const itemKey = `${item.product_name}__${idx}`;
          return (
          <div key={itemKey}>
            <Label className="text-xs font-medium text-muted-foreground uppercase">{item.product_name}</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              {(itemImages[itemKey] || []).map((url, i) => (
                <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
                  <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                  <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => removeImage("item", url, itemKey)}><X className="w-3 h-3" /></button>
                </div>
              ))}
              <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors">
                <Upload className="w-3 h-3 text-muted-foreground" />
                <span className="text-[10px] text-muted-foreground">Files</span>
                <input type="file" accept="image/*" className="sr-only" disabled={uploading}
                  onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "item", itemKey); e.target.value = ""; }} />
              </label>
              <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors bg-secondary/30">
                <Upload className="w-3 h-3 text-muted-foreground" />
                <span className="text-[10px] text-muted-foreground">Camera</span>
                <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading}
                  onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "item", itemKey); e.target.value = ""; }} />
              </label>
            </div>
          </div>
          );
        })}

        {/* Order Images */}
        <div>
          <Label className="text-xs font-medium text-muted-foreground uppercase">Full Order Images</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            {orderImages.map((url, i) => (
              <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
                <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => removeImage("order", url)}><X className="w-3 h-3" /></button>
              </div>
            ))}
            <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors">
              <Upload className="w-3 h-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">Files</span>
              <input type="file" accept="image/*" className="sr-only" disabled={uploading}
                onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "order"); e.target.value = ""; }} />
            </label>
            <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors bg-secondary/30">
              <Upload className="w-3 h-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">Camera</span>
              <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading}
                onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "order"); e.target.value = ""; }} />
            </label>
          </div>
        </div>

        {/* Packed Box Images */}
        <div>
          <Label className="text-xs font-medium text-muted-foreground uppercase">Packed Box Images</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            {packedBoxImages.map((url, i) => (
              <div key={i} className="relative w-16 h-16 rounded-lg border overflow-hidden group">
                <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                <button className="absolute top-0 right-0 bg-red-500 text-white rounded-bl-lg p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => removeImage("packed_box", url)}><X className="w-3 h-3" /></button>
              </div>
            ))}
            <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors">
              <Upload className="w-3 h-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">Files</span>
              <input type="file" accept="image/*" className="sr-only" disabled={uploading}
                onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "packed_box"); e.target.value = ""; }} />
            </label>
            <label className="w-16 h-16 rounded-lg border-2 border-dashed flex flex-col items-center justify-center cursor-pointer hover:bg-accent transition-colors bg-secondary/30">
              <Upload className="w-3 h-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">Camera</span>
              <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={uploading}
                onChange={e => { if (e.target.files[0]) uploadImage(e.target.files[0], "packed_box"); e.target.value = ""; }} />
            </label>
          </div>
        </div>
      </div>

      {uploading && <p className="text-xs text-muted-foreground">Uploading...</p>}

      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button onClick={() => onSave({
          item_packed_by: itemPackedBy, box_packed_by: boxPackedBy, checked_by: checkedBy,
          item_images: itemImages, order_images: orderImages, packed_box_images: packedBoxImages,
        })} disabled={saving || uploading}>
          {saving ? "Saving..." : "Save Packaging"}
        </Button>
      </DialogFooter>
    </div>
  );
}
