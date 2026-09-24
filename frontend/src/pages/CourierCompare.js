import { useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import CarrierRiskCalculator from "@/components/CarrierRiskCalculator";
import { Loader2, Scale, Trophy, AlertTriangle, XCircle, ShieldCheck, Phone, PackageCheck, Clock, IndianRupee } from "lucide-react";

// One pincode + weight -> DTDC, Anjani, Amazon Shipping and Shiprocket side by
// side, all on the same basis (what we pay, GST included), cheapest on top.
const CARRIER_STYLE = {
  "DTDC": "bg-red-100 text-red-800",
  "Anjani": "bg-orange-100 text-orange-800",
  "Amazon Shipping": "bg-amber-100 text-amber-900",
  "Shiprocket": "bg-violet-100 text-violet-800",
  "Delhivery": "bg-teal-100 text-teal-800",
  "Delhivery B2B": "bg-cyan-100 text-cyan-900",
};

// Anjani serves a pincode area by area, and each area has its own delivery type.
const AREA_GROUPS = [
  ["normal", "Normal delivery", "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"],
  ["restricted", "Restricted / special delivery — confirm first", "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200"],
  ["unknown", "Unknown type — confirm with Anjani", "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100"],
  ["documents", "Documents only — no parcels", "bg-red-100 text-red-800 line-through dark:bg-red-950/50 dark:text-red-300"],
  ["none", "NOT serviceable", "bg-red-100 text-red-800 line-through dark:bg-red-950/50 dark:text-red-300"],
];

function AnjaniAreas({ areas }) {
  if (!areas?.length) return null;
  return (
    <div className="mt-2 space-y-2">
      {AREA_GROUPS.map(([kind, title, cls]) => {
        const rows = areas.filter(a => a.kind === kind);
        if (!rows.length) return null;
        return (
          <div key={kind} data-testid={`anjani-areas-${kind}`}>
            <p className="text-xs font-semibold mb-1">{title} ({rows.length})</p>
            <div className="flex flex-wrap gap-1">
              {rows.map(a => <Badge key={a.name} className={`font-normal text-xs ${cls}`} title={a.center}>{a.name}</Badge>)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AnjaniCenters({ centers }) {
  if (!centers?.length) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer font-semibold">Anjani centres here ({centers.length}) — phone numbers</summary>
      <div className="mt-1.5 space-y-1.5">
        {centers.map((c, i) => (
          <div key={i} className="rounded border border-border/70 bg-background/60 p-2">
            <div className="font-medium">{c.name}{c.franchise ? ` · ${c.franchise}` : ""}</div>
            {c.address && <div className="text-muted-foreground">{c.address}</div>}
            <div className="flex flex-wrap gap-x-3 mt-0.5">
              {(c.phones || []).map(ph => (
                <a key={ph} href={`tel:${ph}`} className="flex items-center gap-1 text-primary"><Phone className="w-3 h-3" /> {ph}</a>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

export default function CourierCompare() {
  const [pincode, setPincode] = useState("");
  const [weight, setWeight] = useState("");
  const [cod, setCod] = useState(false);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);

  const check = async (e) => {
    e?.preventDefault();
    if (!/^\d{6}$/.test(pincode.trim())) return toast.error("Enter a 6-digit pincode");
    if (!(parseFloat(weight) > 0)) return toast.error("Enter the weight in kg");
    setLoading(true);
    try {
      const r = await api.get("/rates/compare", { params: { pincode: pincode.trim(), weight: parseFloat(weight), cod } });
      setRes(r.data);
    } catch (err) { toast.error(err.response?.data?.detail || "Could not compare right now"); }
    finally { setLoading(false); }
  };

  const priced = (res?.options || []).filter(o => o.serviceable && o.total);
  const others = (res?.options || []).filter(o => !(o.serviceable && o.total));

  return (
    <div className="max-w-3xl space-y-4" data-testid="courier-compare">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Scale className="w-6 h-6" /> Compare Couriers</h1>
        <p className="text-sm text-muted-foreground">DTDC, Anjani, Amazon Shipping, Shiprocket, Delhivery and Delhivery B2B (transport) together, cheapest first.</p>
      </div>

      <Tabs defaultValue="compare" className="space-y-4">
        <TabsList>
          <TabsTrigger value="compare" data-testid="compare-tab-rates"><Scale className="w-4 h-4 mr-2" /> Rates &amp; Service</TabsTrigger>
          <TabsTrigger value="risk" data-testid="compare-tab-risk"><ShieldCheck className="w-4 h-4 mr-2" /> Carrier Risk</TabsTrigger>
        </TabsList>
        <TabsContent value="risk" className="mt-0 max-w-xl"><CarrierRiskCalculator /></TabsContent>
        <TabsContent value="compare" className="mt-0 space-y-4">

      <Card>
        <CardContent className="pt-5">
          <form onSubmit={check} className="flex flex-wrap items-end gap-3">
            <div>
              <Label className="text-sm">Pincode</Label>
              <Input value={pincode} onChange={e => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="440025"
                     inputMode="numeric" className="w-36 h-11 text-lg" data-testid="compare-pincode" />
            </div>
            <div>
              <Label className="text-sm">Weight (kg)</Label>
              <Input value={weight} onChange={e => setWeight(e.target.value)} type="number" step="0.001" min="0" placeholder="2.5"
                     className="w-32 h-11 text-lg" data-testid="compare-weight" />
            </div>
            <label className="flex items-center gap-2 h-11 cursor-pointer">
              <Checkbox checked={cod} onCheckedChange={v => setCod(!!v)} /> <span className="text-sm">COD order</span>
            </label>
            <Button type="submit" className="h-11 px-6" disabled={loading} data-testid="compare-go">
              {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null} Compare
            </Button>
          </form>
        </CardContent>
      </Card>

      {res && (
        <>
          <p className="text-sm text-muted-foreground">
            {res.city ? `${res.city}, ${res.state} · ` : ""}{res.pincode} · {res.weight_kg} kg{res.cod ? " · COD" : ""} · {res.basis}
          </p>

          {priced.length === 0 && (
            <Card className="border-red-300"><CardContent className="pt-5 text-red-600 font-medium">No courier could be priced for this pincode.</CardContent></Card>
          )}

          <div className="space-y-2">
            {priced.map((o, i) => (
              <Card key={i} className={o.cheapest ? "border-2 border-emerald-500 bg-emerald-50/60 dark:bg-emerald-950/20" : ""} data-testid={`compare-row-${i}`}>
                <CardContent className="py-3">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        {o.cheapest && <Badge className="bg-emerald-600 text-white"><Trophy className="w-3 h-3 mr-1" /> CHEAPEST</Badge>}
                        <Badge className={CARRIER_STYLE[o.carrier] || ""}>{o.carrier}</Badge>
                        <span className="font-medium">{o.service}</span>
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {[o.gst_note, o.note].filter(Boolean).join(" · ")}
                      </div>
                      {(o.pickup || o.eta) && (
                        <div className="text-xs mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                          {o.pickup && <span className="flex items-center gap-1 text-emerald-700 dark:text-emerald-400"><PackageCheck className="w-3 h-3" /> Pickup: {o.pickup}</span>}
                          {o.eta && <span className="flex items-center gap-1 text-muted-foreground"><Clock className="w-3 h-3" /> Delivery by: {o.eta}</span>}
                        </div>
                      )}
                      {o.rto_charges != null && <div className="text-[11px] text-muted-foreground mt-0.5">If it comes back (RTO): {"₹"}{Number(o.rto_charges).toFixed(0)} extra</div>}
                    </div>
                    <div className="text-right">
                      <div className={`font-mono font-bold ${o.cheapest ? "text-2xl text-emerald-700 dark:text-emerald-400" : "text-xl"}`}>{"₹"}{o.total.toFixed(2)}</div>
                      <div className="text-[11px] text-muted-foreground">our cost</div>
                      {i > 0 && <div className="text-xs text-muted-foreground">+{"₹"}{(o.total - priced[0].total).toFixed(0)} vs cheapest</div>}
                      {o.charge_customer != null && (
                        <div className="mt-1 inline-flex items-center gap-1 rounded-md bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200 px-2 py-0.5 text-xs font-semibold" data-testid="compare-charge-customer">
                          <IndianRupee className="w-3 h-3" /> Charge customer {"₹"}{o.charge_customer}
                        </div>
                      )}
                    </div>
                  </div>
                  {o.warning && (
                    <div className="mt-2 rounded-md border border-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2 text-sm">
                      <div className="flex items-start gap-2 text-amber-800 dark:text-amber-300 font-medium">
                        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> {o.warning}
                      </div>
                      <AnjaniAreas areas={o.areas} />
                      <AnjaniCenters centers={o.centers} />
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          {others.length > 0 && (
            <Card>
              <CardContent className="py-3 space-y-1">
                <p className="text-xs uppercase text-muted-foreground font-medium">Not available</p>
                {others.map((o, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm flex-wrap">
                    <XCircle className={`w-4 h-4 shrink-0 ${o.serviceable === false ? "text-red-500" : "text-muted-foreground"}`} />
                    <Badge variant="outline">{o.carrier}</Badge>
                    <span className="text-muted-foreground">{o.note || "Not serviceable"}</span>
                    {o.areas?.length > 0 && <div className="basis-full pl-6"><AnjaniAreas areas={o.areas} /></div>}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
