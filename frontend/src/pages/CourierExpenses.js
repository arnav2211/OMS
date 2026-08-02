import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, RefreshCw, Fuel, IndianRupee, Package, Plus, Trash2, Download } from "lucide-react";

const money = (n) => (n == null ? "—" : `₹${Number(n).toFixed(2)}`);
const monthOptions = () => {
  const out = [];
  const now = new Date();
  for (let i = 0; i < 14; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    if (d < new Date(2026, 7, 1)) break;      // expenses start Aug 2026
    const from = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
    const end = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    const to = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-${String(end.getDate()).padStart(2, "0")}`;
    out.push({ label: d.toLocaleString("en-IN", { month: "long", year: "numeric" }), from, to });
  }
  return out;
};

export default function CourierExpenses() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const months = monthOptions();
  const [mode, setMode] = useState("month");
  const [monthIdx, setMonthIdx] = useState(0);
  const [from, setFrom] = useState(months[0]?.from || "2026-08-01");
  const [to, setTo] = useState(months[0]?.to || "");
  const [courier, setCourier] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // fuel surcharge editor
  const [showFuel, setShowFuel] = useState(false);
  const [fuelFrom, setFuelFrom] = useState("");
  const [fuelPct, setFuelPct] = useState("");
  const [savingFuel, setSavingFuel] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ date_from: from, date_to: to, courier });
      const res = await api.get(`/courier-expenses?${p}`);
      setData(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to load expenses");
    } finally {
      setLoading(false);
    }
  }, [from, to, courier]);

  useEffect(() => { load(); }, [load]);

  const pickMonth = (idx) => {
    const m = months[idx];
    if (!m) return;
    setMonthIdx(idx); setFrom(m.from); setTo(m.to);
  };

  const saveFuel = async () => {
    if (!fuelFrom || fuelPct === "") return toast.error("Enter the date and percentage");
    setSavingFuel(true);
    try {
      await api.post("/courier-expenses/fuel-surcharges", {
        from_date: fuelFrom, percent: parseFloat(fuelPct),
      });
      toast.success("Fuel surcharge saved");
      setFuelFrom(""); setFuelPct("");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save");
    } finally { setSavingFuel(false); }
  };

  const deleteFuel = async (id) => {
    if (id === "default") return toast.error("The default rate cannot be deleted");
    try {
      await api.delete(`/courier-expenses/fuel-surcharges/${id}`);
      toast.success("Removed"); load();
    } catch (err) { toast.error(err.response?.data?.detail || "Failed"); }
  };

  const exportCsv = () => {
    if (!data?.rows?.length) return toast.error("Nothing to export");
    const head = ["Date", "Order", "Customer", "Courier", "Service", "Zone", "Weight(kg)",
                  "Boxes", "Base", "Fuel%", "Fuel", "GST", "Total"];
    const lines = [head.join(",")].concat(data.rows.map(r => [
      r.date, r.order_number, `"${(r.customer_name || "").replace(/"/g, "'")}"`, r.courier,
      r.service || "", r.zone || "", r.weight_kg, r.num_boxes,
      r.base, r.fuel_percent, r.fuel, r.gst, r.total,
    ].join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `courier-expenses-${data.date_from}-to-${data.date_to}.csv`;
    a.click();
  };

  const summary = data?.summary || {};

  return (
    <div className="space-y-5" data-testid="courier-expenses">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Courier Expenses</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            What we owe DTDC and Anjani, from 01 Aug 2026 onwards
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowFuel(true)} data-testid="fuel-btn">
            <Fuel className="w-4 h-4 mr-1" /> Fuel Surcharge
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download className="w-4 h-4 mr-1" /> CSV
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Period picker */}
      <Card>
        <CardContent className="pt-5 flex flex-wrap items-end gap-3">
          <div>
            <Label className="text-xs">View</Label>
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger className="w-36 mt-1" data-testid="expense-mode"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="month">Monthly</SelectItem>
                <SelectItem value="custom">Custom dates</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {mode === "month" ? (
            <div>
              <Label className="text-xs">Month</Label>
              <Select value={String(monthIdx)} onValueChange={(v) => pickMonth(Number(v))}>
                <SelectTrigger className="w-48 mt-1" data-testid="expense-month"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {months.map((m, i) => <SelectItem key={m.from} value={String(i)}>{m.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <>
              <div>
                <Label className="text-xs">From</Label>
                <Input type="date" value={from} onChange={e => setFrom(e.target.value)} className="mt-1 w-40" data-testid="expense-from" />
              </div>
              <div>
                <Label className="text-xs">To</Label>
                <Input type="date" value={to} onChange={e => setTo(e.target.value)} className="mt-1 w-40" data-testid="expense-to" />
              </div>
            </>
          )}
          <div>
            <Label className="text-xs">Courier</Label>
            <Select value={courier} onValueChange={setCourier}>
              <SelectTrigger className="w-36 mt-1" data-testid="expense-courier"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="dtdc">DTDC</SelectItem>
                <SelectItem value="anjani">Anjani</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Totals */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {["DTDC", "Anjani"].map(cn => {
          const s = summary[cn];
          return (
            <Card key={cn}>
              <CardContent className="pt-5">
                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                  <Package className="w-4 h-4" /> {cn}
                </div>
                <p className="text-2xl font-bold mt-1 font-mono" data-testid={`total-${cn.toLowerCase()}`}>
                  {money(s?.total || 0)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {s?.shipments || 0} shipment(s) · {s?.weight_kg || 0} kg
                  {cn === "DTDC" && s ? ` · base ${money(s.base)} + fuel ${money(s.fuel)} + GST ${money(s.gst)}` : ""}
                </p>
              </CardContent>
            </Card>
          );
        })}
        <Card className="border-primary/40">
          <CardContent className="pt-5">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
              <IndianRupee className="w-4 h-4" /> Grand Total
            </div>
            <p className="text-2xl font-bold mt-1 font-mono text-primary" data-testid="grand-total">
              {money(data?.grand_total || 0)}
            </p>
            <p className="text-xs text-muted-foreground">{data?.count || 0} shipment(s) in period</p>
          </CardContent>
        </Card>
      </div>

      {/* Detail */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Shipment detail</CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
          ) : (
            <Table className="min-w-[1000px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="whitespace-nowrap">Date</TableHead>
                  <TableHead className="whitespace-nowrap">Order</TableHead>
                  <TableHead className="whitespace-nowrap">Customer</TableHead>
                  <TableHead className="whitespace-nowrap">Courier</TableHead>
                  <TableHead className="whitespace-nowrap">Service / Zone</TableHead>
                  <TableHead className="whitespace-nowrap text-right">Wt</TableHead>
                  <TableHead className="whitespace-nowrap text-right">Base</TableHead>
                  <TableHead className="whitespace-nowrap text-right">Fuel</TableHead>
                  <TableHead className="whitespace-nowrap text-right">GST</TableHead>
                  <TableHead className="whitespace-nowrap text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(data?.rows || []).length === 0 && (
                  <TableRow><TableCell colSpan={10} className="text-center text-muted-foreground py-10">
                    No courier shipments with a weight in this period.
                  </TableCell></TableRow>
                )}
                {(data?.rows || []).map(r => (
                  <TableRow key={r.order_id} data-testid={`expense-row-${r.order_id}`}>
                    <TableCell className="text-sm whitespace-nowrap">{r.date}</TableCell>
                    <TableCell className="font-mono text-sm">{r.order_number}</TableCell>
                    <TableCell className="text-sm max-w-[180px] truncate">{r.customer_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">{r.courier}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {r.error ? <span className="text-red-600">{r.error}</span> : (
                        <>{r.service}<br /><span className="text-muted-foreground">{r.zone}</span></>
                      )}
                    </TableCell>
                    <TableCell className="text-sm font-mono text-right whitespace-nowrap">{r.weight_kg}</TableCell>
                    <TableCell className="text-sm font-mono text-right">{money(r.base)}</TableCell>
                    <TableCell className="text-sm font-mono text-right">
                      {r.courier === "DTDC" ? <>{money(r.fuel)}<span className="text-[10px] text-muted-foreground ml-1">{r.fuel_percent}%</span></> : "—"}
                    </TableCell>
                    <TableCell className="text-sm font-mono text-right">{r.courier === "DTDC" ? money(r.gst) : "—"}</TableCell>
                    <TableCell className="text-sm font-mono text-right font-semibold">{money(r.total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Fuel surcharge periods */}
      <Dialog open={showFuel} onOpenChange={setShowFuel}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Fuel Surcharge (DTDC)</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">
            Applied to the base freight before GST. Each entry applies from its date until the next one.
          </p>
          <div className="space-y-2 max-h-56 overflow-y-auto">
            {(data?.fuel_surcharges || []).map(f => (
              <div key={f.id} className="flex items-center justify-between border rounded-lg px-3 py-2">
                <div className="text-sm">
                  <span className="font-medium">{f.percent}%</span>
                  <span className="text-muted-foreground ml-2">from {f.from_date}</span>
                  {f.note ? <span className="text-xs text-muted-foreground ml-2">({f.note})</span> : null}
                </div>
                {isAdmin && f.id !== "default" && (
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => deleteFuel(f.id)}>
                    <Trash2 className="w-3.5 h-3.5 text-destructive" />
                  </Button>
                )}
              </div>
            ))}
          </div>
          {isAdmin && (
            <div className="flex items-end gap-2 border-t pt-3">
              <div className="flex-1">
                <Label className="text-xs">Effective from</Label>
                <Input type="date" value={fuelFrom} onChange={e => setFuelFrom(e.target.value)} className="mt-1" data-testid="fuel-date" />
              </div>
              <div className="w-28">
                <Label className="text-xs">Percent</Label>
                <Input type="number" step="0.01" min="0" max="100" value={fuelPct}
                  onChange={e => setFuelPct(e.target.value)} placeholder="15" className="mt-1" data-testid="fuel-pct" />
              </div>
              <Button onClick={saveFuel} disabled={savingFuel} data-testid="fuel-save">
                {savingFuel ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              </Button>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFuel(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
