import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Truck, Send, Eye } from "lucide-react";

export default function DispatchDashboard() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [showDispatch, setShowDispatch] = useState(false);
  const [courierName, setCourierName] = useState("");
  const [transporterName, setTransporterName] = useState("");
  const [lrNo, setLrNo] = useState("");

  useEffect(() => { loadOrders(); }, []);

  const loadOrders = async () => {
    try {
      const res = await api.get("/orders");
      setOrders(res.data.filter((o) => ["packed", "dispatched"].includes(o.status)));
    } catch { } finally { setLoading(false); }
  };

  const openDispatch = (order) => {
    setSelectedOrder(order);
    setCourierName(order.dispatch?.courier_name || "");
    setTransporterName(order.dispatch?.transporter_name || "");
    setLrNo(order.dispatch?.lr_no || "");
    setShowDispatch(true);
  };

  const handleDispatch = async () => {
    if (!selectedOrder) return;
    if (selectedOrder.shipping_method === "office_collection") {
      // No LR needed
    } else if (!courierName && !transporterName) {
      return toast.error("Enter courier or transporter name");
    }
    try {
      await api.put(`/orders/${selectedOrder.id}/dispatch`, {
        courier_name: courierName,
        transporter_name: transporterName,
        lr_no: lrNo,
      });
      toast.success("Order dispatched!");
      setShowDispatch(false);
      loadOrders();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="dispatch-dashboard">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dispatch Queue</h1>
        <p className="text-muted-foreground text-sm mt-1">{orders.filter((o) => o.status === "packed").length} orders ready for dispatch</p>
      </div>

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <p className="text-center py-8 text-muted-foreground">Loading...</p>
          ) : orders.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Truck className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No orders ready for dispatch</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs uppercase tracking-wider">Order #</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Customer</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Shipping</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-xs uppercase tracking-wider">LR No.</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id} data-testid={`dispatch-order-${order.order_number}`}>
                    <TableCell className="font-mono font-medium">{order.order_number}</TableCell>
                    <TableCell>{order.customer_name}</TableCell>
                    <TableCell className="capitalize text-sm">{order.shipping_method?.replace("_", " ")}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className={`status-${order.status} text-xs uppercase`}>
                        {order.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{order.dispatch?.lr_no || "-"}</TableCell>
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
              <div className="text-sm">
                <span className="text-muted-foreground">Shipping Method:</span>{" "}
                <span className="capitalize">{selectedOrder.shipping_method?.replace("_", " ")}</span>
              </div>
              {selectedOrder.shipping_method !== "office_collection" && (
                <>
                  {["courier", "porter"].includes(selectedOrder.shipping_method) && (
                    <div>
                      <Label>Courier Name</Label>
                      <Input value={courierName} onChange={(e) => setCourierName(e.target.value)} placeholder="e.g. BlueDart, DTDC" data-testid="dispatch-courier-input" />
                    </div>
                  )}
                  {selectedOrder.shipping_method === "transport" && (
                    <div>
                      <Label>Transporter Name</Label>
                      <Input value={transporterName} onChange={(e) => setTransporterName(e.target.value)} placeholder="Transporter name" data-testid="dispatch-transporter-input" />
                    </div>
                  )}
                  <div>
                    <Label>LR / Tracking Number</Label>
                    <Input value={lrNo} onChange={(e) => setLrNo(e.target.value)} placeholder="LR / Docket No." data-testid="dispatch-lr-input" />
                  </div>
                </>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDispatch(false)}>Cancel</Button>
            <Button onClick={handleDispatch} data-testid="confirm-dispatch-btn">
              <Truck className="w-4 h-4 mr-1" /> Confirm Dispatch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
