import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  MapPin, Loader2, CheckCircle2, XCircle, Calculator, Table2,
  TrendingDown, AlertTriangle, RefreshCw,
} from "lucide-react";

const money = (n) =>
  n === null || n === undefined ? "—" : `₹${Number(n).toFixed(2)}`;
const gramsLabel = (g) => (g < 1000 ? `${g} g` : `${g / 1000} kg`);

export default function IndiaPostCalculator() {
  const [status, setStatus] = useState(null);

  // Calculator
  const [pincode, setPincode] = useState("");
  const [weight, setWeight] = useState("");
  const [dims, setDims] = useState({ length: "", breadth: "", height: "" });
  const [insurance, setInsurance] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  // Rate card
  const [card, setCard] = useState(null);
  const [cardLoading, setCardLoading] = useState(false);

  useEffect(() => {
    api.get("/indiapost/status").then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  const calculate = async () => {
    if (!/^\d{6}$/.test(pincode)) return toast.error("Enter a valid 6-digit pincode");
    const w = parseFloat(weight);
    if (!w || w <= 0) return toast.error("Enter a weight greater than zero");
    setLoading(true);
    setResult(null);
    try {
      const res = await api.post("/indiapost/rate", {
        pincode,
        weight_kg: w,
        length: parseFloat(dims.length) || 0,
        breadth: parseFloat(dims.breadth) || 0,
        height: parseFloat(dims.height) || 0,
        insurance: parseFloat(insurance) || 0,
      });
      setResult(res.data);
      if (!res.data.ok) toast.error(res.data.message || "No rate available");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not fetch India Post rates");
    } finally {
      setLoading(false);
    }
  };

  const loadCard = useCallback(async () => {
    setCardLoading(true);
    try {
      const res = await api.post("/indiapost/rate-card", {});
      setCard(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not build the rate card");
    } finally {
      setCardLoading(false);
    }
  }, []);

  const notReady = status && !status.configured;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="indiapost-page-title">
            India Post
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Both contracts are quoted for every shipment — the cheaper one wins.
          </p>
        </div>
        {status?.sandbox && (
          <Badge variant="outline" className="border-amber-500 text-amber-600 shrink-0">
            Sandbox
          </Badge>
        )}
      </div>

      {notReady && (
        <Card className="border-amber-500/50 bg-amber-50/50 dark:bg-amber-950/20">
          <CardContent className="pt-5 flex gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-sm space-y-1">
              <p className="font-medium">India Post contracts are not connected yet.</p>
              <p className="text-muted-foreground">
                Serviceability works without credentials, but rates need the contract
                logins. Register for the sandbox in the India Post customer portal, then
                add the credentials to the server configuration.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="calculator">
        <TabsList>
          <TabsTrigger value="calculator" data-testid="tab-calculator">
            <Calculator className="w-4 h-4 mr-1.5" /> Calculator
          </TabsTrigger>
          <TabsTrigger value="card" data-testid="tab-rate-card">
            <Table2 className="w-4 h-4 mr-1.5" /> Rate card
          </TabsTrigger>
        </TabsList>

        {/* ── Calculator ───────────────────────────────────────────── */}
        <TabsContent value="calculator" className="space-y-4 mt-4">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base flex items-center gap-2">
                <MapPin className="w-4 h-4" /> Shipment
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <Label>Destination pincode</Label>
                  <Input
                    value={pincode}
                    onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    onKeyDown={(e) => e.key === "Enter" && calculate()}
                    placeholder="6-digit pincode"
                    className="mt-1"
                    data-testid="indiapost-pincode"
                  />
                </div>
                <div>
                  <Label>Weight (kg)</Label>
                  <Input
                    value={weight}
                    onChange={(e) => setWeight(e.target.value.replace(/[^\d.]/g, ""))}
                    onKeyDown={(e) => e.key === "Enter" && calculate()}
                    placeholder="e.g. 1.5"
                    className="mt-1"
                    data-testid="indiapost-weight"
                  />
                </div>
                <div>
                  <Label>Insurance value (₹)</Label>
                  <Input
                    value={insurance}
                    onChange={(e) => setInsurance(e.target.value.replace(/[^\d.]/g, ""))}
                    placeholder="optional"
                    className="mt-1"
                    data-testid="indiapost-insurance"
                  />
                </div>
              </div>

              <div>
                <Label className="text-xs text-muted-foreground">
                  Box dimensions in cm — optional, but India Post charges on the greater
                  of actual and volumetric weight, so a quote without them can come in low.
                </Label>
                <div className="grid grid-cols-3 gap-3 mt-1">
                  {["length", "breadth", "height"].map((k) => (
                    <Input
                      key={k}
                      value={dims[k]}
                      onChange={(e) =>
                        setDims({ ...dims, [k]: e.target.value.replace(/[^\d.]/g, "") })
                      }
                      placeholder={k[0].toUpperCase() + k.slice(1)}
                      data-testid={`indiapost-${k}`}
                    />
                  ))}
                </div>
              </div>

              <Button onClick={calculate} disabled={loading} data-testid="indiapost-calculate">
                {loading ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Comparing…</>
                ) : (
                  <><Calculator className="w-4 h-4 mr-2" /> Compare rates</>
                )}
              </Button>
            </CardContent>
          </Card>

          {result && !result.ok && (
            <Card className="border-destructive/50">
              <CardContent className="pt-5 flex gap-3">
                <XCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium">{result.message || "No rate available"}</p>
                  {(result.skipped || []).length > 0 && (
                    <ul className="text-muted-foreground mt-2 space-y-0.5">
                      {result.skipped.map((s, i) => (
                        <li key={i}>{s.product}: {s.reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {result?.ok && (
            <div className="space-y-3">
              <Card className="border-primary/60">
                <CardContent className="pt-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          Cheapest
                        </span>
                      </div>
                      <p className="text-lg font-semibold mt-1">
                        {result.cheapest.product_label}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {result.cheapest.account_label}
                        {result.office?.office_name && ` · via ${result.office.office_name}`}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold" data-testid="indiapost-best-total">
                        {money(result.cheapest.total)}
                      </p>
                      <p className="text-xs text-muted-foreground">incl. GST</p>
                      {result.savings > 0 && (
                        <p className="text-xs text-emerald-600 flex items-center gap-1 justify-end mt-0.5">
                          <TrendingDown className="w-3 h-3" />
                          saves {money(result.savings)}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">All eligible options</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                        <tr>
                          <th className="text-left px-4 py-2">Product</th>
                          <th className="text-right px-4 py-2">Chargeable</th>
                          <th className="text-right px-4 py-2">Base</th>
                          <th className="text-right px-4 py-2">Tax</th>
                          <th className="text-right px-4 py-2">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.quotes.map((q, i) => (
                          <tr key={i} className={`border-t ${i === 0 ? "bg-emerald-50/50 dark:bg-emerald-950/20" : ""}`}>
                            <td className="px-4 py-2">
                              <div className="font-medium">{q.product_label}</div>
                              <div className="text-xs text-muted-foreground">{q.account_label}</div>
                            </td>
                            <td className="text-right px-4 py-2">
                              {gramsLabel(q.chargeable_weight_g)}
                              {q.volumetric_weight_g > q.weight_g && (
                                <div className="text-[10px] text-amber-600">volumetric</div>
                              )}
                            </td>
                            <td className="text-right px-4 py-2">{money(q.base_tariff)}</td>
                            <td className="text-right px-4 py-2">{money(q.tax)}</td>
                            <td className="text-right px-4 py-2 font-semibold">{money(q.total)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              {(result.skipped || []).length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Not eligible: {result.skipped.map((s) => `${s.product} (${s.reason})`).join(", ")}
                </p>
              )}
            </div>
          )}
        </TabsContent>

        {/* ── Rate card ────────────────────────────────────────────── */}
        <TabsContent value="card" className="space-y-4 mt-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-sm text-muted-foreground">
              Live grid across both contracts. The cheaper product is highlighted in each cell.
            </p>
            <Button variant="outline" size="sm" onClick={loadCard} disabled={cardLoading}
                    data-testid="indiapost-build-card">
              {cardLoading ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Building…</>
              ) : (
                <><RefreshCw className="w-4 h-4 mr-2" /> {card ? "Refresh" : "Build rate card"}</>
              )}
            </Button>
          </div>

          {card && (
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs">
                      <tr>
                        <th className="text-left px-3 py-2 sticky left-0 bg-muted/50">Weight</th>
                        {card.columns.map((c) => (
                          <th key={c.pincode} className="px-3 py-2 text-right">
                            <div className="font-semibold">{c.city || c.pincode}</div>
                            <div className="font-normal text-muted-foreground">{c.pincode}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {card.rows.map((row) => (
                        <tr key={row.weight_g} className="border-t">
                          <td className="px-3 py-2 font-medium sticky left-0 bg-background">
                            {gramsLabel(row.weight_g)}
                          </td>
                          {row.cells.map((cell, i) => (
                            <td key={i} className="px-3 py-2 text-right">
                              {cell.ok ? (
                                <>
                                  <div className="font-semibold">{money(cell.total)}</div>
                                  <div className="text-[10px] text-muted-foreground">
                                    {cell.cheapest}
                                  </div>
                                </>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {card && (
            <p className="text-xs text-muted-foreground">
              Quoted from {card.origin_pincode} on{" "}
              {new Date(card.generated_at).toLocaleString("en-IN")}
              {card.sandbox && " · sandbox rates, not your contracted rates"}
            </p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
