import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { TrendingUp, Search, Eye } from "lucide-react";
import { Link } from "react-router-dom";

export default function ItemAnalytics() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedItem, setSelectedItem] = useState(null);
  const [showDetail, setShowDetail] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await api.get(`/reports/item-sales?${params.toString()}`);
      setItems(res.data);
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => { loadData(); }, [dateFrom, dateTo]);

  const openDetail = (item) => { setSelectedItem(item); setShowDetail(true); };

  return (
    <div className="space-y-6" data-testid="item-analytics">
      <h1 className="text-2xl font-bold tracking-tight">Item Sales Analytics</h1>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-end gap-3">
            <div><Label className="text-xs">From</Label><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} data-testid="item-date-from" /></div>
            <div><Label className="text-xs">To</Label><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} data-testid="item-date-to" /></div>
            <Button variant="outline" size="sm" onClick={() => { setDateFrom(""); setDateTo(""); }} data-testid="item-clear-filter">Clear</Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? <p className="text-center py-8 text-muted-foreground">Loading...</p> : items.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground"><TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>No item sales data</p></div>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead className="text-xs uppercase">#</TableHead>
                <TableHead className="text-xs uppercase">Product Name</TableHead>
                <TableHead className="text-xs uppercase">Total Qty</TableHead>
                <TableHead className="text-xs uppercase">Total Sales</TableHead>
                <TableHead className="text-xs uppercase">Orders</TableHead>
                <TableHead></TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {items.map((item, idx) => (
                  <TableRow key={idx} data-testid={`item-row-${idx}`}>
                    <TableCell className="text-muted-foreground">{idx + 1}</TableCell>
                    <TableCell className="font-medium">{item.product_name}</TableCell>
                    <TableCell>{item.total_qty}</TableCell>
                    <TableCell className="font-mono">{"\u20B9"}{item.total_amount?.toLocaleString("en-IN")}</TableCell>
                    <TableCell>{item.order_count}</TableCell>
                    <TableCell><Button variant="ghost" size="icon" onClick={() => openDetail(item)} data-testid={`item-detail-${idx}`}><Eye className="w-4 h-4" /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{selectedItem?.product_name} - Purchase History</DialogTitle></DialogHeader>
          {selectedItem && (
            <Table>
              <TableHeader><TableRow>
                <TableHead className="text-xs uppercase">Order #</TableHead>
                <TableHead className="text-xs uppercase">Customer</TableHead>
                <TableHead className="text-xs uppercase">Qty</TableHead>
                <TableHead className="text-xs uppercase">Amount</TableHead>
                <TableHead className="text-xs uppercase">Date</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {selectedItem.orders?.map((o, i) => (
                  <TableRow key={i}>
                    <TableCell><Link to={`/orders/${o.order_id}`} className="text-primary hover:underline font-mono">{o.order_number}</Link></TableCell>
                    <TableCell>{o.customer_name}</TableCell>
                    <TableCell>{o.qty}</TableCell>
                    <TableCell className="font-mono">{"\u20B9"}{o.amount?.toFixed(2)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{o.date ? new Date(o.date).toLocaleDateString("en-IN") : "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
