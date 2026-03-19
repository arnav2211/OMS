import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { ArrowLeft, Package, Truck, ClipboardList, Check, MapPin, Phone, Mail } from "lucide-react";

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
};

export default function OrderDetail() {
  const { orderId } = useParams();
  const { user } = useAuth();
  const [order, setOrder] = useState(null);
  const [customer, setCustomer] = useState(null);
  const [loading, setLoading] = useState(true);
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => { loadOrder(); }, [orderId]);

  const loadOrder = async () => {
    try {
      const res = await api.get(`/orders/${orderId}`);
      setOrder(res.data);
      if (res.data.customer_id) {
        const custRes = await api.get(`/customers/${res.data.customer_id}`);
        setCustomer(custRes.data);
      }
    } catch { toast.error("Failed to load order"); }
    finally { setLoading(false); }
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
      </div>

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
                  {item.formulation && (user?.role === "admin" || item.show_formulation) && (
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
    </div>
  );
}
