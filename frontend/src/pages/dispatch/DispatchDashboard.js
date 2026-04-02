import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Truck, Send, Eye, Search } from "lucide-react";

const COURIER_OPTIONS = ["DTDC", "Anjani", "Professional", "India Post"];
const NO_LR_METHODS = ["porter", "self_arranged", "office_collection"];

export default function DispatchDashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showDispatch, setShowDispatch] = useState(false);
  const [courierName, setCourierName] = useState("");
  const [transporterName, setTransporterName] = useState("");
  const [lrNo, setLrNo] = useState("");
  const [editShippingMethod, setEditShippingMethod] = useState("");
  const [dispSearch, setDispSearch] = useState("");

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
    setShowDispatch(true);
  };

  const handleDispatch = async () => {
    if (!selectedOrder) return;
    const method = editShippingMethod || selectedOrder.shipping_method;

    // For transport: LR is mandatory for dispatch/packaging
    if (method === "transport" && ["dispatch", "packaging"].includes(user?.role) && !lrNo) {
      return toast.error("LR Number is mandatory for transport dispatch");
    }

    // For courier: must select courier
    if (method === "courier" && !courierName) {
      return toast.error("Select a courier");
    }

    try {
      await api.put(`/orders/${selectedOrder.id}/dispatch`, {
        courier_name: courierName,
        transporter_name: transporterName,
        lr_no: lrNo,
        dispatch_type: method,
        shipping_method: method,
      });
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
                <Select value={editShippingMethod} onValueChange={setEditShippingMethod}>
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
                  <Label>Courier *</Label>
                  <Select value={courierName} onValueChange={setCourierName}>
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
                <>
                  <div>
                    <Label>Transporter Name</Label>
                    <Input
                      value={transporterName}
                      onChange={(e) => setTransporterName(e.target.value)}
                      placeholder="Transporter name"
                      data-testid="dispatch-transporter-input"
                    />
                  </div>
                  <div>
                    <Label>LR Number {["dispatch", "packaging"].includes(user?.role) ? "*" : ""}</Label>
                    <Input
                      value={lrNo}
                      onChange={(e) => setLrNo(e.target.value)}
                      placeholder="LR / Docket No."
                      data-testid="dispatch-lr-input"
                    />
                  </div>
                </>
              )}

              {/* For courier, also show LR field */}
              {editShippingMethod === "courier" && (
                <div>
                  <Label>Tracking Number</Label>
                  <Input
                    value={lrNo}
                    onChange={(e) => setLrNo(e.target.value)}
                    placeholder="Tracking No."
                    data-testid="dispatch-tracking-input"
                  />
                </div>
              )}

              {/* Porter / Self-arranged / Office Collection: just dispatch */}
              {NO_LR_METHODS.includes(editShippingMethod) && (
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
