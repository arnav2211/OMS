import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { ArrowLeft, Package, Truck, ClipboardList, Check, MapPin, Phone, Mail, XCircle, Edit, Ban } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const STEPS = [
  { key: "new", label: "Order Placed", icon: ClipboardList },
  { key: "packaging", label: "Packaging", icon: Package },
  { key: "packed", label: "Packed", icon: Package },
  { key: "dispatched", label: "Dispatched", icon: Truck },
];

const STATUS_STYLES = {
  new: "status-new",
  packaging: "status-packaging",
  packed: "status-packed",
  dispatched: "status-dispatched",
  cancelled: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

const PAYMENT_COLORS = {
  unpaid: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
  full: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
};

export default function OrderDetail() {
  const { orderId } = useParams();
  const { user } = useAuth();
  const [order, setOrder] = useState(null);
  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCancelConfirm1, setShowCancelConfirm1] = useState(false);
  const [showCancelConfirm2, setShowCancelConfirm2] = useState(false);
  const [settings, setSettings] = useState({ show_formulation: false });
  const [showPaymentEdit, setShowPaymentEdit] = useState(false);
  const [paymentForm, setPaymentForm] = useState({ payment_status: "unpaid", amount_paid: 0 });
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => { loadOrder(); }, [orderId]);

  const loadOrder = async () => {
    try {
      const [res, settingsRes] = await Promise.all([
        api.get(`/orders/${orderId}`),
        api.get("/settings"),
      ]);
      setOrder(res.data);
      setSettings(settingsRes.data);
      if (res.data.customer_id) {
        const custRes = await api.get(`/customers/${res.data.customer_id}`);
        setCustomer(custRes.data);
      }
    } catch { toast.error("Failed to load order"); }
    finally { setLoading(false); }
  };

  const handleCancel = async () => {
    try {
      await api.put(`/orders/${orderId}/cancel`);
      toast.success("Order cancelled");
      setShowCancelConfirm2(false);
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const handlePaymentUpdate = async () => {
    try {
      const balance = paymentForm.payment_status === "full" ? 0 :
        paymentForm.payment_status === "partial" ? Math.max(0, (order?.grand_total || 0) - paymentForm.amount_paid) : (order?.grand_total || 0);
      await api.put(`/orders/${orderId}`, {
        payment_status: paymentForm.payment_status,
        amount_paid: paymentForm.payment_status === "full" ? order?.grand_total : paymentForm.amount_paid,
        balance_amount: balance,
      });
      toast.success("Payment updated");
      setShowPaymentEdit(false);
      loadOrder();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  if (loading) return <div className="text-center py-12 text-muted-foreground">Loading...</div>;
  if (!order) return <div className="text-center py-12 text-muted-foreground">Order not found</div>;

  const stepIndex = STEPS.findIndex((s) => s.key === order.status);

  return (
    <div className="max-w-5xl mx-auto space-y-6" data-testid="order-detail">
      <div className="flex items-center gap-4">
        <Link to={-1}>
          <Button variant="ghost" size="icon" data-testid="back-btn"><ArrowLeft className="w-5 h-5" /></Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{order.order_number}</h1>
            <Badge variant="secondary" className={`${STATUS_STYLES[order.status]} text-xs uppercase`}>
              {order.status}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Created on {new Date(order.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
            {" by "}{order.telecaller_name}
          </p>
        </div>
        {order.status !== "cancelled" && (user?.role === "admin" || user?.role === "telecaller") && (
          <Button variant="destructive" size="sm" onClick={() => setShowCancelConfirm1(true)} data-testid="cancel-order-btn">
            <Ban className="w-4 h-4 mr-1" /> Cancel Order
          </Button>
        )}
      </div>

      {/* Payment Status Bar */}
      {order.payment_status && (
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-muted-foreground">Payment:</span>
                <Badge variant="secondary" className={`${PAYMENT_COLORS[order.payment_status]} text-xs uppercase`}>
                  {order.payment_status === "partial" ? "Partial Paid" : order.payment_status === "full" ? "Fully Paid" : "Unpaid"}
                </Badge>
                {order.payment_status === "partial" && (
                  <span className="text-sm">
                    Paid: <span className="font-mono font-medium">{"\u20B9"}{(order.amount_paid || 0).toFixed(2)}</span>
                    {" | Balance: "}<span className="font-mono font-medium text-destructive">{"\u20B9"}{(order.balance_amount || 0).toFixed(2)}</span>
                  </span>
                )}
              </div>
              {(user?.role === "admin" || user?.role === "telecaller") && (
                <Button variant="outline" size="sm" onClick={() => {
                  setPaymentForm({ payment_status: order.payment_status || "unpaid", amount_paid: order.amount_paid || 0 });
                  setShowPaymentEdit(true);
                }} data-testid="edit-payment-btn"><Edit className="w-3 h-3 mr-1" /> Edit Payment</Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Progress Tracker */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between px-4">
            {STEPS.map((step, idx) => {
              const Icon = step.icon;
              const status = idx < stepIndex ? "completed" : idx === stepIndex ? "current" : "pending";
              return (
                <div key={step.key} className="flex flex-col items-center relative flex-1">
                  {idx > 0 && (
                    <div
                      className={`absolute top-4 -left-1/2 w-full h-0.5 ${
                        idx <= stepIndex ? "bg-primary" : "bg-muted"
                      }`}
                      style={{ right: "50%", left: "-50%" }}
                    />
                  )}
                  <div className={`progress-step ${status}`}>
                    <div className="step-dot relative z-10">
                      {status === "completed" ? <Check className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                    </div>
                  </div>
                  <p className={`text-xs mt-2 font-medium ${status === "pending" ? "text-muted-foreground" : "text-foreground"}`}>
                    {step.label}
                  </p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Customer Info */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Customer Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="font-medium text-base">{order.customer_name}</p>
            {customer && (
              <>
                {customer.phone_numbers?.length > 0 && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Phone className="w-3.5 h-3.5" />
                    {customer.phone_numbers.join(", ")}
                  </div>
                )}
                {customer.email && (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Mail className="w-3.5 h-3.5" />
                    {customer.email}
                  </div>
                )}
                {customer.gst_no && (
                  <div className="text-muted-foreground">
                    <span className="text-xs uppercase tracking-wider font-medium">GST:</span> {customer.gst_no}
                  </div>
                )}
                <Separator />
                <div>
                  <p className="text-xs uppercase tracking-wider font-medium text-muted-foreground mb-1">Billing Address</p>
                  <p>{customer.billing_address?.address}</p>
                  <p>{customer.billing_address?.city}, {customer.billing_address?.state} - {customer.billing_address?.pincode}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider font-medium text-muted-foreground mb-1">Shipping Address</p>
                  <p>{customer.shipping_address?.address}</p>
                  <p>{customer.shipping_address?.city}, {customer.shipping_address?.state} - {customer.shipping_address?.pincode}</p>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Shipping & Dispatch */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Shipping & Dispatch</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs uppercase tracking-wider font-medium text-muted-foreground">Method</p>
                <p className="capitalize mt-1">{order.shipping_method?.replace("_", " ") || "N/A"}</p>
              </div>
              {order.courier_name && (
                <div>
                  <p className="text-xs uppercase tracking-wider font-medium text-muted-foreground">Courier</p>
                  <p className="mt-1">{order.courier_name}</p>
                </div>
              )}
            </div>
            {order.dispatch?.lr_no && (
              <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
                <p className="text-xs font-medium text-emerald-700 dark:text-emerald-400 uppercase tracking-wider">Dispatch Info</p>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  {order.dispatch.courier_name && <div><span className="text-muted-foreground">Courier:</span> {order.dispatch.courier_name}</div>}
                  {order.dispatch.transporter_name && <div><span className="text-muted-foreground">Transporter:</span> {order.dispatch.transporter_name}</div>}
                  <div><span className="text-muted-foreground">LR No:</span> <span className="font-mono">{order.dispatch.lr_no}</span></div>
                  {order.dispatch.dispatched_by && <div><span className="text-muted-foreground">Dispatched By:</span> {order.dispatch.dispatched_by}</div>}
                  {order.dispatch.dispatched_at && (
                    <div><span className="text-muted-foreground">Date:</span> {new Date(order.dispatch.dispatched_at).toLocaleDateString("en-IN")}</div>
                  )}
                </div>
              </div>
            )}
            {order.purpose && (
              <div>
                <p className="text-xs uppercase tracking-wider font-medium text-muted-foreground">Purpose</p>
                <p className="mt-1">{order.purpose}</p>
              </div>
            )}
            {order.remark && (
              <div>
                <p className="text-xs uppercase tracking-wider font-medium text-muted-foreground">Remarks</p>
                <p className="mt-1">{order.remark}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Order Items */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Order Items</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {order.items?.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 rounded-lg border" data-testid={`detail-item-${idx}`}>
                <div className="flex-1">
                  <p className="font-medium">{item.product_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {item.qty} {item.unit !== "blank" ? item.unit : ""} @ {"\u20B9"}{item.rate?.toFixed(2)}
                  </p>
                  {item.formulation && (user?.role === "admin" || settings.show_formulation) && (
                    <p className="text-xs mt-1 text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded px-2 py-1 inline-block">
                      Formulation: {item.formulation}
                    </p>
                  )}
                </div>
                <div className="text-right">
                  <p className="font-mono font-medium">{"\u20B9"}{item.amount?.toFixed(2)}</p>
                  {item.gst_amount > 0 && (
                    <p className="text-xs text-muted-foreground">+{item.gst_rate}% GST: {"\u20B9"}{item.gst_amount?.toFixed(2)}</p>
                  )}
                </div>
              </div>
            ))}
          </div>

          <Separator className="my-4" />

          <div className="space-y-2 text-sm max-w-xs ml-auto">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span className="font-mono">{"\u20B9"}{order.subtotal?.toFixed(2)}</span>
            </div>
            {order.total_gst > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">GST</span>
                <span className="font-mono">{"\u20B9"}{order.total_gst?.toFixed(2)}</span>
              </div>
            )}
            {order.shipping_charge > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Shipping</span>
                <span className="font-mono">{"\u20B9"}{order.shipping_charge?.toFixed(2)}</span>
              </div>
            )}
            {order.shipping_gst > 0 && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Shipping GST</span>
                <span className="font-mono">{"\u20B9"}{order.shipping_gst?.toFixed(2)}</span>
              </div>
            )}
            <Separator />
            <div className="flex justify-between text-base font-bold">
              <span>Grand Total</span>
              <span className="font-mono">{"\u20B9"}{order.grand_total?.toFixed(2)}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Packaging Images */}
      {(order.packaging?.order_images?.length > 0 || order.packaging?.packed_box_images?.length > 0 || Object.keys(order.packaging?.item_images || {}).length > 0) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Packaging Images</CardTitle>
            {order.packaging?.packed_by && (
              <CardDescription>Packed by: {order.packaging.packed_by}</CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Object.entries(order.packaging?.item_images || {}).map(([idx, urls]) => (
                <div key={idx}>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                    Item {+idx + 1}: {order.items?.[idx]?.product_name}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {urls.map((url, i) => (
                      <a key={i} href={`${backendUrl}${url}`} target="_blank" rel="noreferrer" className="w-24 h-24 rounded-lg border overflow-hidden hover:ring-2 ring-primary transition-shadow">
                        <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                      </a>
                    ))}
                  </div>
                </div>
              ))}
              {order.packaging?.order_images?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Order Images</p>
                  <div className="flex flex-wrap gap-2">
                    {order.packaging.order_images.map((url, i) => (
                      <a key={i} href={`${backendUrl}${url}`} target="_blank" rel="noreferrer" className="w-24 h-24 rounded-lg border overflow-hidden hover:ring-2 ring-primary transition-shadow">
                        <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
              {order.packaging?.packed_box_images?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Packed Box</p>
                  <div className="flex flex-wrap gap-2">
                    {order.packaging.packed_box_images.map((url, i) => (
                      <a key={i} href={`${backendUrl}${url}`} target="_blank" rel="noreferrer" className="w-24 h-24 rounded-lg border overflow-hidden hover:ring-2 ring-primary transition-shadow">
                        <img src={`${backendUrl}${url}`} alt="" className="w-full h-full object-cover" />
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Cancel Confirmation 1 */}
      <Dialog open={showCancelConfirm1} onOpenChange={setShowCancelConfirm1}>
        <DialogContent>
          <DialogHeader><DialogTitle>Cancel Order {order.order_number}?</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Are you sure you want to cancel this order? This action will mark the order as cancelled.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCancelConfirm1(false)}>No, Keep</Button>
            <Button variant="destructive" onClick={() => { setShowCancelConfirm1(false); setShowCancelConfirm2(true); }} data-testid="cancel-confirm-1">Yes, Cancel</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancel Confirmation 2 */}
      <Dialog open={showCancelConfirm2} onOpenChange={setShowCancelConfirm2}>
        <DialogContent>
          <DialogHeader><DialogTitle>Final Confirmation</DialogTitle></DialogHeader>
          <p className="text-sm text-destructive font-medium">This is the final warning. Order {order.order_number} will be permanently cancelled. Are you absolutely sure?</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCancelConfirm2(false)}>Go Back</Button>
            <Button variant="destructive" onClick={handleCancel} data-testid="cancel-confirm-2">Yes, Cancel Order</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Payment Edit Dialog */}
      <Dialog open={showPaymentEdit} onOpenChange={setShowPaymentEdit}>
        <DialogContent>
          <DialogHeader><DialogTitle>Update Payment Status</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Status</Label>
              <Select value={paymentForm.payment_status} onValueChange={v => setPaymentForm(p => ({ ...p, payment_status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="unpaid">Unpaid</SelectItem>
                  <SelectItem value="partial">Partial Paid</SelectItem>
                  <SelectItem value="full">Full Paid</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {paymentForm.payment_status === "partial" && (
              <div>
                <Label>Amount Paid</Label>
                <Input type="number" value={paymentForm.amount_paid || ""} onChange={e => setPaymentForm(p => ({ ...p, amount_paid: +e.target.value }))} />
                <p className="text-xs text-muted-foreground mt-1">Balance: {"\u20B9"}{Math.max(0, (order?.grand_total || 0) - paymentForm.amount_paid).toFixed(2)}</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPaymentEdit(false)}>Cancel</Button>
            <Button onClick={handlePaymentUpdate} data-testid="save-payment-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
