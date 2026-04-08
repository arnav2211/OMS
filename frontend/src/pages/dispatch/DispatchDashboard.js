import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Truck, Send, Eye, Search, ExternalLink } from "lucide-react";
import { SlipScanner } from "@/components/SlipScanner";
import { validateLrNumber, extractPorterLink, COURIER_LR_PATTERNS } from "@/lib/courierTracking";

const COURIER_OPTIONS = ["DTDC", "Anjani", "Professional", "India Post"];

export default function DispatchDashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showDispatch, setShowDispatch] = useState(false);
  const [courierName, setCourierName] = useState("");
  const [transporterName, setTransporterName] = useState("");
  const [lrNo, setLrNo] = useState("");
  const [dispatchSlipImages, setDispatchSlipImages] = useState([]);
  const [editShippingMethod, setEditShippingMethod] = useState("");
  const [dispSearch, setDispSearch] = useState("");
  const [lrValidationError, setLrValidationError] = useState("");
  const [porterPasteText, setPorterPasteText] = useState("");
  const [porterLink, setPorterLink] = useState("");

  useEffect(() => { loadOrders(); }, []);

  const loadOrders = async () => {
    try {
      const packedRes = await api.get("/orders?status=packed&page_size=200");
      const dispRes = await api.get("/orders?status=dispatched&page_size=200");
      const allOrders = [...(packedRes.data.orders || []), ...(dispRes.data.orders || [])];
      setOrders(allOrders);
    } catch { } finally { setLoading(false); }
  };

  const SHIPPING_METHODS = [
    { value: "transport", label: "Transport" },
    { value: "courier", label: "Courier" },
    { value: "porter", label: "Porter" },
    { value: "self_arranged", label: "Self-Arranged" },
    { value: "office_collection", label: "Office Collection" },
  ];

  const openDispatch = (order) => {
    setSelectedOrder(order);
    setEditShippingMethod(order.shipping_method || "");
    setCourierName(order.dispatch?.courier_name || order.courier_name || "");
    setTransporterName(order.dispatch?.transporter_name || order.transporter_name || "");
    setLrNo(order.dispatch?.lr_no || "");
    setDispatchSlipImages(order.dispatch?.dispatch_slip_images || []);
    setLrValidationError("");
    setPorterPasteText(order.dispatch?.porter_link || "");
    setPorterLink(order.dispatch?.porter_link || "");
    setShowDispatch(true);
  };

  const handleDispatch = async () => {
    if (!selectedOrder) return;
    const method = editShippingMethod || selectedOrder.shipping_method;

    // Mandatory LR for courier and transport
    if ((method === "courier" || method === "transport") && !lrNo.trim()) {
      return toast.error("LR / Tracking Number is mandatory for " + (method === "courier" ? "Courier" : "Transport") + " dispatch");
    }

    // For courier: must select courier
    if (method === "courier" && !courierName) {
      return toast.error("Select a courier");
    }

    // Courier-specific regex validation
    if (method === "courier" && courierName && lrNo.trim()) {
      const validation = validateLrNumber(courierName, lrNo);
      if (!validation.valid) {
        setLrValidationError(validation.message);
        return toast.error(validation.message);
      }
    }

    try {
      const payload = {
        courier_name: courierName,
        transporter_name: transporterName,
        lr_no: lrNo,
        dispatch_type: method,
        shipping_method: method,
        dispatch_slip_images: dispatchSlipImages,
      };
      if (method === "porter" && porterLink) {
        payload.porter_link = porterLink;
      }
      await api.put(`/orders/${selectedOrder.id}/dispatch`, payload);
      toast.success("Order dispatched!");
      setShowDispatch(false);
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const handleUpdateShipping = async () => {
    if (!selectedOrder) return;
    try {
      await api.put(`/orders/${selectedOrder.id}/shipping-method`, {
        shipping_method: editShippingMethod,
        courier_name: courierName,
        transporter_name: transporterName,
      });
      toast.success("Shipping method updated!");
      setShowDispatch(false);
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  const getShippingLabel = (method) => {
    const labels = {
      transport: "Transport",
      courier: "Courier",
      porter: "Porter",
      self_arranged: "Self-Arranged",
      office_collection: "Office Collection",
    };
    return labels[method] || method;
  };

  return (
    <div className="space-y-6" data-testid="dispatch-dashboard">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Dispatch Queue</h1>
        <p className="text-muted-foreground text-sm mt-1">{orders.filter((o) => o.status === "packed").length} orders ready for dispatch</p>
      </div>

      <Card>
        <CardContent className="pt-6 overflow-x-auto">
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading...</p>
          ) : orders.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Truck className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No orders ready for dispatch</p>
            </div>
          ) : (() => {
            const q = dispSearch.toLowerCase();
            const filtered = q ? orders.filter(o =>
              o.order_number?.toLowerCase().includes(q) ||
              o.customer_name?.toLowerCase().includes(q) ||
              o.customer_phone?.some?.(p => p.includes(q)) ||
              o.customer_gst_no?.toLowerCase().includes(q) ||
              o.customer_alias?.toLowerCase().includes(q)
            ) : orders;
            return (
            <>
            <div className="mb-4 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input placeholder="Search by order #, customer, phone, GST, alias..." className="pl-9 max-w-sm" value={dispSearch} onChange={e => setDispSearch(e.target.value)} data-testid="dispatch-search" />
            </div>
            {filtered.length === 0 ? <p className="text-center py-8 text-muted-foreground">No results for "{dispSearch}"</p> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Shipping</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider hidden sm:table-cell">LR No.</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((order) => (
                  <TableRow key={order.id} data-testid={`dispatch-order-${order.order_number}`}>
                    <TableCell className="font-mono font-medium text-sm">
                      <Link to={`/orders/${order.id}`} className="text-primary hover:underline" data-testid={`dispatch-order-link-${order.order_number}`}>{order.order_number}</Link>
                    </TableCell>
                    <TableCell className="text-sm">{order.customer_name}{order.customer_alias ? <span className="text-xs text-muted-foreground ml-1">({order.customer_alias})</span> : ""}</TableCell>
                    <TableCell className="text-sm">{getShippingLabel(order.shipping_method)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`status-${order.status} text-xs uppercase`}>{order.status}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm hidden sm:table-cell">{order.dispatch?.lr_no || "-"}</TableCell>
                    <TableCell className="flex gap-1">
                      <Button variant="outline" size="sm" onClick={() => openDispatch(order)} data-testid={`dispatch-btn-${order.order_number}`}>
                        <Send className="w-3 h-3 mr-1" /> {order.status === "dispatched" ? "Edit" : "Dispatch"}
                      </Button>
                      <Link to={`/orders/${order.id}`}>
                        <Button variant="ghost" size="icon"><Eye className="w-4 h-4" /></Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            )}
            </>
            ); })()}
        </CardContent>
      </Card>

      <Dialog open={showDispatch} onOpenChange={setShowDispatch}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dispatch {selectedOrder?.order_number}</DialogTitle>
          </DialogHeader>
          {selectedOrder && (
            <div className="space-y-4">
              <div className="text-sm">
                <span className="text-muted-foreground">Customer:</span> {selectedOrder.customer_name}
              </div>

              {/* Editable shipping method */}
              <div>
                <Label>Shipping Method</Label>
                <Select value={editShippingMethod} onValueChange={(v) => { setEditShippingMethod(v); setLrValidationError(""); }}>
                  <SelectTrigger data-testid="dispatch-shipping-method-select"><SelectValue placeholder="Select method" /></SelectTrigger>
                  <SelectContent>
                    {SHIPPING_METHODS.map(m => (
                      <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Courier dispatch */}
              {editShippingMethod === "courier" && (
                <div>
                  <Label>Courier <span className="text-red-500">*</span></Label>
                  <Select value={courierName} onValueChange={(v) => { setCourierName(v); setLrValidationError(""); }}>
                    <SelectTrigger data-testid="dispatch-courier-select"><SelectValue placeholder="Select courier" /></SelectTrigger>
                    <SelectContent>
                      {COURIER_OPTIONS.map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Transport dispatch */}
              {editShippingMethod === "transport" && (
                <div>
                  <Label>Transporter Name</Label>
                  <Input
                    value={transporterName}
                    onChange={(e) => setTransporterName(e.target.value)}
                    placeholder="Transporter name"
                    data-testid="dispatch-transporter-input"
                  />
                </div>
              )}

              {/* LR/Tracking field for Courier + Transport */}
              {(editShippingMethod === "courier" || editShippingMethod === "transport") && (
                <>
                  <div>
                    <Label>LR / Tracking No. <span className="text-red-500">*</span></Label>
                    <Input
                      value={lrNo}
                      onChange={(e) => { setLrNo(e.target.value); setLrValidationError(""); }}
                      className={lrValidationError ? "border-red-500" : ""}
                      placeholder={editShippingMethod === "courier" && courierName
                        ? `Format: ${COURIER_LR_PATTERNS[courierName]?.label || "Enter tracking number"}`
                        : "LR / Docket No."}
                      data-testid="dispatch-lr-input"
                    />
                    {lrValidationError && <p className="text-xs text-red-500 mt-1" data-testid="lr-validation-error">{lrValidationError}</p>}
                  </div>
                  <div>
                    <Label className="mb-2 block">{editShippingMethod === "courier" ? "Courier" : "Transport"} Slip</Label>
                    <SlipScanner
                      onBarcodeDetected={(code) => { setLrNo(code); setLrValidationError(""); }}
                      slipImages={dispatchSlipImages}
                      onSlipImagesChange={setDispatchSlipImages}
                    />
                  </div>
                </>
              )}

              {/* Porter: link extraction */}
              {editShippingMethod === "porter" && (
                <div>
                  <Label>Porter Tracking Link / Message</Label>
                  <Textarea
                    value={porterPasteText}
                    onChange={(e) => {
                      const text = e.target.value;
                      setPorterPasteText(text);
                      const link = extractPorterLink(text);
                      setPorterLink(link || "");
                    }}
                    placeholder="Paste Porter message or tracking link here..."
                    className="min-h-[80px]"
                    data-testid="porter-link-input"
                  />
                  {porterLink && (
                    <p className="text-xs text-green-600 mt-1 flex items-center gap-1" data-testid="porter-link-extracted">
                      <ExternalLink className="w-3 h-3" /> Extracted: <a href={porterLink} target="_blank" rel="noopener noreferrer" className="underline truncate max-w-[250px]">{porterLink}</a>
                    </p>
                  )}
                  {porterPasteText && !porterLink && (
                    <p className="text-xs text-amber-600 mt-1">No porter.in link found in pasted text</p>
                  )}
                </div>
              )}

              {/* Self-arranged / Office Collection */}
              {["self_arranged", "office_collection"].includes(editShippingMethod) && (
                <p className="text-sm text-muted-foreground p-3 rounded bg-secondary">
                  No LR number or courier details required for {getShippingLabel(editShippingMethod)}.
                  Click dispatch to mark as dispatched.
                </p>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDispatch(false)}>Cancel</Button>
            {selectedOrder?.status === "dispatched" ? (
              <Button onClick={handleUpdateShipping} data-testid="update-shipping-btn">
                <Truck className="w-4 h-4 mr-1" /> Update Shipping
              </Button>
            ) : (
              <Button onClick={handleDispatch} data-testid="confirm-dispatch-btn">
                <Truck className="w-4 h-4 mr-1" /> Confirm Dispatch
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
