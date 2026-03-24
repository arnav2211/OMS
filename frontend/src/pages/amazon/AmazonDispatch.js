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
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RefreshCw, Truck, Edit2 } from "lucide-react";

const COURIERS = ["DTDC", "Anjani", "Professional", "India Post"];

export default function AmazonDispatch() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  // Easy ship
  const [selectedEasy, setSelectedEasy] = useState(new Set());
  const [dispatching, setDispatching] = useState(false);
  // Self ship
  const [dispatchSelf, setDispatchSelf] = useState(null);
  const [lrNumber, setLrNumber] = useState("");
  const [selfDispatching, setSelfDispatching] = useState(false);
  // Courier edit
  const [editCourier, setEditCourier] = useState(null);
  const [editCourierValue, setEditCourierValue] = useState("");

  useEffect(() => { loadOrders(); }, []);

  const loadOrders = async () => {
    setLoading(true);
    try { const res = await api.get("/amazon/orders"); setOrders(res.data); } catch {} finally { setLoading(false); }
  };

  const easyShipOrders = orders.filter(o => o.ship_type === "easy_ship" && o.status !== "dispatched");
  const selfShipOrders = orders.filter(o => o.ship_type === "self_ship" && o.status !== "dispatched");

  // Easy Ship - bulk dispatch
  const toggleEasySelect = (id) => {
    setSelectedEasy(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  const selectAllEasy = () => {
    if (selectedEasy.size === easyShipOrders.length) setSelectedEasy(new Set());
    else setSelectedEasy(new Set(easyShipOrders.map(o => o.id)));
  };
  const bulkDispatchEasy = async () => {
    if (selectedEasy.size === 0) return toast.error("Select orders to dispatch");
    setDispatching(true);
    try {
      const res = await api.post("/amazon/orders/bulk-dispatch", { order_ids: [...selectedEasy] });
      toast.success(`${res.data.dispatched} orders dispatched`);
      setSelectedEasy(new Set());
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setDispatching(false); }
  };

  // Self Ship - individual dispatch with mandatory LR
  const openSelfDispatch = (order) => { setDispatchSelf(order); setLrNumber(""); };
  const dispatchSelfShip = async () => {
    if (!lrNumber.trim()) return toast.error("LR number is mandatory for self ship");
    setSelfDispatching(true);
    try {
      await api.put(`/amazon/orders/${dispatchSelf.id}/dispatch`, { lr_number: lrNumber.trim() });
      toast.success("Order dispatched");
      setDispatchSelf(null);
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
    finally { setSelfDispatching(false); }
  };

  // Courier edit
  const saveCourier = async () => {
    if (!editCourierValue) return toast.error("Select a courier");
    try {
      await api.put(`/amazon/orders/${editCourier.id}/courier`, { courier_name: editCourierValue });
      toast.success("Courier updated");
      setEditCourier(null);
      loadOrders();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-4" data-testid="amazon-dispatch-page">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Amazon Dispatch</h1>
        <Button variant="outline" size="sm" onClick={loadOrders}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      <Tabs defaultValue="easy_ship">
        <TabsList>
          <TabsTrigger value="easy_ship" data-testid="tab-easy-ship">Easy Ship ({easyShipOrders.length})</TabsTrigger>
          <TabsTrigger value="self_ship" data-testid="tab-self-ship">Self Ship ({selfShipOrders.length})</TabsTrigger>
        </TabsList>

        {/* Easy Ship Tab */}
        <TabsContent value="easy_ship">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-base">Easy Ship Orders — Ready for Dispatch</CardTitle>
                {easyShipOrders.length > 0 && (
                  <Button size="sm" onClick={bulkDispatchEasy} disabled={dispatching || selectedEasy.size === 0} data-testid="bulk-dispatch-easy">
                    <Truck className="w-4 h-4 mr-1" /> Dispatch Selected ({selectedEasy.size})
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">
                        <Checkbox checked={easyShipOrders.length > 0 && selectedEasy.size === easyShipOrders.length} onCheckedChange={selectAllEasy} data-testid="select-all-easy" />
                      </TableHead>
                      <TableHead className="text-xs uppercase">Order</TableHead>
                      <TableHead className="text-xs uppercase">Customer</TableHead>
                      <TableHead className="text-xs uppercase">Amount</TableHead>
                      <TableHead className="text-xs uppercase">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {easyShipOrders.length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No pending Easy Ship orders</TableCell></TableRow>}
                    {easyShipOrders.map(o => (
                      <TableRow key={o.id} data-testid={`easy-row-${o.id}`}>
                        <TableCell>
                          <Checkbox checked={selectedEasy.has(o.id)} onCheckedChange={() => toggleEasySelect(o.id)} />
                        </TableCell>
                        <TableCell>
                          <Link to={`/amazon-orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.am_order_number}</Link>
                        </TableCell>
                        <TableCell className="text-sm">{o.customer_name}</TableCell>
                        <TableCell className="text-sm font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                        <TableCell><Badge variant="outline" className="text-xs capitalize">{o.status}</Badge></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Self Ship Tab */}
        <TabsContent value="self_ship">
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base">Self Ship Orders — Assign Courier & Dispatch</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs uppercase">Order</TableHead>
                      <TableHead className="text-xs uppercase">Customer</TableHead>
                      <TableHead className="text-xs uppercase">Amount</TableHead>
                      <TableHead className="text-xs uppercase">Courier</TableHead>
                      <TableHead className="text-xs uppercase">Status</TableHead>
                      <TableHead className="text-xs uppercase">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selfShipOrders.length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No pending Self Ship orders</TableCell></TableRow>}
                    {selfShipOrders.map(o => (
                      <TableRow key={o.id} data-testid={`self-row-${o.id}`}>
                        <TableCell>
                          <Link to={`/amazon-orders/${o.id}`} className="font-mono text-sm text-primary hover:underline">{o.am_order_number}</Link>
                        </TableCell>
                        <TableCell className="text-sm">{o.customer_name}</TableCell>
                        <TableCell className="text-sm font-mono">{"\u20B9"}{o.grand_total?.toLocaleString("en-IN")}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <span className="text-sm">{o.courier_name || <span className="text-muted-foreground italic">Not set</span>}</span>
                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => { setEditCourier(o); setEditCourierValue(o.courier_name || ""); }} data-testid={`edit-courier-${o.id}`}>
                              <Edit2 className="w-3 h-3" />
                            </Button>
                          </div>
                        </TableCell>
                        <TableCell><Badge variant="outline" className="text-xs capitalize">{o.status}</Badge></TableCell>
                        <TableCell>
                          <Button size="sm" className="text-xs h-7" onClick={() => openSelfDispatch(o)} disabled={!o.courier_name} data-testid={`dispatch-self-${o.id}`}>
                            <Truck className="w-3 h-3 mr-1" /> Dispatch
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Self Ship Dispatch Dialog */}
      <Dialog open={!!dispatchSelf} onOpenChange={() => setDispatchSelf(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Dispatch Self Ship Order</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-sm"><span className="text-muted-foreground">Order:</span> <span className="font-mono font-bold">{dispatchSelf?.am_order_number}</span></div>
            <div className="text-sm"><span className="text-muted-foreground">Courier:</span> <span className="font-medium">{dispatchSelf?.courier_name}</span></div>
            <div>
              <Label className="text-sm">LR Number <span className="text-red-500">*</span></Label>
              <Input value={lrNumber} onChange={e => setLrNumber(e.target.value)} placeholder="Enter LR / Tracking number" data-testid="self-lr-input" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDispatchSelf(null)}>Cancel</Button>
            <Button onClick={dispatchSelfShip} disabled={selfDispatching || !lrNumber.trim()} data-testid="confirm-self-dispatch">
              {selfDispatching ? "Dispatching..." : "Dispatch"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Courier Dialog */}
      <Dialog open={!!editCourier} onOpenChange={() => setEditCourier(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Set Courier — {editCourier?.am_order_number}</DialogTitle></DialogHeader>
          <div>
            <Label className="text-sm">Courier</Label>
            <Select value={editCourierValue} onValueChange={setEditCourierValue}>
              <SelectTrigger data-testid="courier-edit-select"><SelectValue placeholder="Select courier" /></SelectTrigger>
              <SelectContent>
                {COURIERS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditCourier(null)}>Cancel</Button>
            <Button onClick={saveCourier} disabled={!editCourierValue} data-testid="save-courier-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
