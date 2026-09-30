import { useState, useEffect, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import api, { API_BASE } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";
import { Loader2, Upload, Download, FileCheck, AlertTriangle, HelpCircle, CheckCircle2, History } from "lucide-react";

const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Plain-language meaning of each finding (mirrors BILL_FLAGS in the backend)
const FLAG_TEXT = {
  WEIGHT: "Charged higher weight than we packed",
  ZONE: "Billed a costlier zone than the pincode is",
  ROV_NOT_ORDERED: "Carrier risk charged without carrier risk",
  ROV_WRONG: "Carrier risk is not 2% of value",
  MATH: "Total / GST doesn't add up",
  DUPLICATE: "Billed twice",
  NOT_IN_OMS: "Not booked from the OMS",
  RETURN: "Return (RTO) of our parcel",
  EXTRA_CHARGE: "Other / COD / ODA charge",
  RATE: "Freight a little above our rate card",
  FUEL: "Fuel % above our fuel table",
  NOT_INSURED: "Carrier risk order, but not insured by DTDC",
  CHILD: "Child piece (no charge)",
  OK: "Matches",
};
const LEVELS = {
  dispute: { label: "Raise with DTDC", cls: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200" },
  check: { label: "Please check", cls: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200" },
  note: { label: "Note", cls: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200" },
  ok: { label: "OK", cls: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200" },
};
const LEVEL_ORDER = ["dispute", "check", "note", "ok"];

export default function DTDCBillCheck() {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [filter, setFilter] = useState("problems");
  const inputRef = useRef(null);

  const loadHistory = useCallback(async () => {
    try {
      const r = await api.get("/dtdc/bill-checks");
      setHistory(r.data || []);
    } catch { /* history is optional */ }
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const run = async () => {
    if (!files.length) return;
    setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const r = await api.post("/dtdc/bill-check", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(r.data);
      setFilter("problems");
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      loadHistory();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not check the bill");
    } finally {
      setBusy(false);
    }
  };

  const open = async (id) => {
    try {
      const r = await api.get(`/dtdc/bill-checks/${id}`);
      setResult(r.data);
      setFilter("problems");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      toast.error("Could not open that check");
    }
  };

  const excel = () => {
    const t = localStorage.getItem("token");
    window.open(`${API_BASE}/dtdc/bill-checks/${result.id}/excel?token=${encodeURIComponent(t || "")}`, "_blank");
  };

  const s = result?.summary;
  const lines = (result?.lines || [])
    .filter((l) => filter === "all" || (filter === "problems" ? ["dispute", "check"].includes(l.level) : l.level === filter))
    .sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level) || (b.extra || 0) - (a.extra || 0));

  return (
    <div className="space-y-5" data-testid="dtdc-bill-check">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><FileCheck className="w-6 h-6" /> DTDC Bill Check</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload the Excel/CSV detail file(s) DTDC sends with the monthly invoice PDFs. Every consignment is checked against
          our packed weight, the pincode zone, carrier risk, fuel, extra charges and the bill arithmetic.
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
            <input ref={inputRef} type="file" multiple accept=".csv,.xlsx,.xls,.pdf" data-testid="bill-files"
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
              className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-2 file:text-sm" />
            <Button onClick={run} disabled={!files.length || busy} data-testid="bill-check-run">
              {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Upload className="w-4 h-4 mr-2" />}
              Check {files.length > 1 ? `${files.length} files` : "bill"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">You can select all accounts' files together (RL1386, RL1387, RL1423). The PDF alone is only a summary, so upload the detail file.</p>
        </CardContent>
      </Card>

      {s && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Card><CardContent className="pt-5">
              <div className="text-xs text-muted-foreground">Billed ({s.lines} lines)</div>
              <div className="text-xl font-bold">{money(s.billed_total)}</div>
            </CardContent></Card>
            <Card className="border-red-300"><CardContent className="pt-5">
              <div className="text-xs text-muted-foreground flex items-center gap-1"><AlertTriangle className="w-3 h-3 text-red-600" /> Raise with DTDC ({s.dispute_count})</div>
              <div className="text-xl font-bold text-red-600" data-testid="bill-dispute-amount">{money(s.dispute_amount)}</div>
            </CardContent></Card>
            <Card className="border-amber-300"><CardContent className="pt-5">
              <div className="text-xs text-muted-foreground flex items-center gap-1"><HelpCircle className="w-3 h-3 text-amber-600" /> Please check ({s.check_count})</div>
              <div className="text-xl font-bold text-amber-600">{money(s.check_amount)}</div>
            </CardContent></Card>
            <Card className="border-green-300"><CardContent className="pt-5">
              <div className="text-xs text-muted-foreground flex items-center gap-1"><CheckCircle2 className="w-3 h-3 text-green-600" /> Matching</div>
              <div className="text-xl font-bold text-green-600">{s.ok_count} lines</div>
            </CardContent></Card>
          </div>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Invoices</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Invoice</TableHead><TableHead>Account</TableHead><TableHead className="text-right">Lines</TableHead>
                  <TableHead className="text-right">Freight</TableHead><TableHead className="text-right">Fuel</TableHead>
                  <TableHead className="text-right">ROV</TableHead><TableHead className="text-right">Other</TableHead>
                  <TableHead className="text-right">GST</TableHead><TableHead className="text-right">Total</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {s.invoices.map((i) => (
                    <TableRow key={i.invoice}>
                      <TableCell className="font-mono text-xs">{i.invoice}</TableCell><TableCell>{i.account}</TableCell>
                      <TableCell className="text-right">{i.lines}</TableCell><TableCell className="text-right">{money(i.basic)}</TableCell>
                      <TableCell className="text-right">{money(i.fuel)} <span className="text-xs text-muted-foreground">({i.fuel_pct}%)</span></TableCell>
                      <TableCell className="text-right">{money(i.rov)}</TableCell><TableCell className="text-right">{money(i.other)}</TableCell>
                      <TableCell className="text-right">{money(i.gst)}</TableCell><TableCell className="text-right font-semibold">{money(i.total)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="text-xs text-muted-foreground mt-2">Match each total with the PDF's "Total" before paying.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between flex-wrap gap-2">
              <CardTitle className="text-base">Consignments</CardTitle>
              <div className="flex gap-1 flex-wrap">
                {[["problems", "Problems"], ["dispute", "Raise"], ["check", "Check"], ["note", "Notes"], ["ok", "OK"], ["all", "All"]].map(([k, lbl]) => (
                  <Button key={k} size="sm" variant={filter === k ? "default" : "outline"} onClick={() => setFilter(k)}>{lbl}</Button>
                ))}
                <Button size="sm" variant="outline" onClick={excel} data-testid="bill-excel"><Download className="w-4 h-4 mr-1" /> Excel</Button>
              </div>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              {lines.length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">Nothing here.</p>
              ) : (
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Status</TableHead><TableHead>Consignment</TableHead><TableHead>Order</TableHead><TableHead>Date / City</TableHead>
                    <TableHead className="text-right">Charged kg</TableHead><TableHead className="text-right">Our kg</TableHead>
                    <TableHead className="text-right">Total</TableHead><TableHead className="text-right">Extra</TableHead><TableHead>What's wrong</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>
                    {lines.map((l) => (
                      <TableRow key={`${l.invoice}-${l.consignment}`}>
                        <TableCell><Badge className={`${LEVELS[l.level].cls} border-0 whitespace-nowrap`}>{LEVELS[l.level].label}</Badge></TableCell>
                        <TableCell className="font-mono text-xs">{l.consignment}<div className="text-muted-foreground">{l.account} · {l.product}</div></TableCell>
                        <TableCell className="text-sm">
                          {l.order_id ? <Link className="text-blue-600 hover:underline" to={`/orders/${l.order_id}`}>{l.order}</Link> : (l.order || "—")}
                          {l.customer && <div className="text-xs text-muted-foreground">{l.customer}</div>}
                        </TableCell>
                        <TableCell className="text-xs whitespace-nowrap">{l.date}<div className="text-muted-foreground">{l.city} · {l.dtdc_zone || l.dtdc_zone_code}</div></TableCell>
                        <TableCell className="text-right">{l.charged_kg}</TableCell>
                        <TableCell className="text-right">{l.our_kg || "—"}</TableCell>
                        <TableCell className="text-right">{money(l.total)}</TableCell>
                        <TableCell className="text-right font-semibold text-red-600">{l.extra ? money(l.extra) : ""}</TableCell>
                        <TableCell className="text-xs min-w-[220px]">
                          {l.flags.filter((f) => f !== "OK").map((f) => <div key={f} className="font-medium">{FLAG_TEXT[f] || f}</div>)}
                          {(l.notes || []).map((n, i) => <div key={i} className="text-muted-foreground">{n}</div>)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              <p className="text-xs text-muted-foreground mt-2">"Extra" is what we were over-billed, including fuel and 18% GST. For lines not booked from the OMS it is the full line total.</p>
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><History className="w-4 h-4" /> Earlier checks</CardTitle></CardHeader>
        <CardContent>
          {history.length === 0 ? <p className="text-sm text-muted-foreground">No bills checked yet.</p> : (
            <div className="space-y-2">
              {history.map((h) => (
                <button key={h.id} onClick={() => open(h.id)}
                  className={`w-full text-left rounded-md border p-3 hover:bg-muted text-sm ${result?.id === h.id ? "border-primary" : ""}`}>
                  <div className="font-medium">{(h.invoices || []).join(", ")}</div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(h.created_at).toLocaleString("en-IN")} by {h.uploaded_by} · billed {money(h.summary?.billed_total)} ·
                    <span className="text-red-600"> raise {money(h.summary?.dispute_amount)}</span> · check {money(h.summary?.check_amount)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
