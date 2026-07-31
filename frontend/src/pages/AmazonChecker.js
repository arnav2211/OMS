import { useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import AmazonBookPanel from "@/components/AmazonBookPanel";
import { Search, MapPin, Loader2, CheckCircle2, XCircle, AlertTriangle, Truck, Clock, PackageCheck, ClipboardList } from "lucide-react";

const fmtWindow = (w) => {
  if (!w?.start && !w?.end) return null;
  const opts = { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" };
  const s = w.start ? new Date(w.start).toLocaleString("en-IN", opts) : null;
  const e = w.end ? new Date(w.end).toLocaleString("en-IN", opts) : null;
  return s && e ? `${s} — ${e}` : (s || e);
};

export default function AmazonChecker() {
  const [pincode, setPincode] = useState("");
  const [weight, setWeight] = useState("1");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCheck = async () => {
    if (!pincode || pincode.length !== 6) return toast.error("Enter a valid 6-digit pincode");
    const w = parseFloat(weight);
    if (!Number.isFinite(w) || w <= 0) return toast.error("Enter a valid weight in KG");
    setLoading(true);
    setResult(null);
    try {
      const res = await api.get(`/amazon/check/${pincode}?weight=${w}`);
      setResult(res.data);
      if (res.data.configured === false) toast.warning(res.data.message);
      else if (!res.data.serviceable) toast.error(res.data.message);
    } catch {
      toast.error("Unable to check serviceability right now. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => { if (e.key === "Enter") handleCheck(); };

  return (
    <div className="w-full max-w-5xl mx-auto space-y-6 px-1">
      <div className="text-center">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" data-testid="amazon-page-title">Amazon Shipping</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Check serviceability, get live rates, and book parcels</p>
      </div>

      <Tabs defaultValue="check" className="w-full">
        <TabsList className="mb-5 mx-auto flex w-fit">
          <TabsTrigger value="check" data-testid="amz-tab-check"><MapPin className="w-4 h-4 mr-2" /> Pincode Check</TabsTrigger>
          <TabsTrigger value="book" data-testid="amz-tab-book"><ClipboardList className="w-4 h-4 mr-2" /> Book Orders</TabsTrigger>
        </TabsList>

        <TabsContent value="book">
          <AmazonBookPanel />
        </TabsContent>

        <TabsContent value="check">
        <div className="w-full max-w-2xl mx-auto space-y-5">
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base flex items-center gap-2"><MapPin className="w-4 h-4" /> Enter Pincode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <Label>Destination Pincode</Label>
              <div className="relative mt-1.5">
                <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  value={pincode}
                  onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  onKeyDown={handleKeyDown}
                  placeholder="Enter 6-digit pincode"
                  className="pl-9 h-11 text-base"
                  data-testid="amazon-pincode-input"
                />
              </div>
            </div>
            <div>
              <Label>Weight (KG)</Label>
              <Input
                type="number" step="0.001" min="0.1"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="1.5"
                className="mt-1.5 h-11 text-base"
                data-testid="amazon-weight-input"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground -mt-1">Rates depend on weight — enter the actual parcel weight.</p>
          <Button onClick={handleCheck} disabled={loading} className="w-full h-11 text-base" data-testid="amazon-check-btn">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
            Check Serviceability
          </Button>
        </CardContent>
      </Card>

      {/* Not configured yet */}
      {result && result.configured === false && (
        <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900">
          <CardContent className="pt-6 flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-amber-700 dark:text-amber-400 text-sm font-medium" data-testid="amazon-not-configured">{result.message}</p>
          </CardContent>
        </Card>
      )}

      {/* Not Serviceable */}
      {result && result.configured !== false && !result.serviceable && (
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900">
          <CardContent className="pt-6 flex flex-col items-center justify-center gap-1 text-center">
            <div className="flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" />
              <p className="text-red-600 dark:text-red-400 font-medium" data-testid="amazon-not-serviceable">{result.message}</p>
            </div>
            {result.detail && <p className="text-xs text-red-500/80 mt-1 break-all">{result.detail}</p>}
          </CardContent>
        </Card>
      )}

      {/* Serviceable */}
      {result && result.serviceable && (
        <div className="space-y-4" data-testid="amazon-result">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="border-green-300 bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400 dark:border-green-800 gap-1.5 py-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> Serviceable
            </Badge>
            <span className="text-sm text-muted-foreground">
              Pincode: {pincode}{result.city ? ` · ${result.city}, ${result.state}` : ""}
            </span>
            {result.count != null && <span className="text-sm text-muted-foreground">({result.count} service{result.count > 1 ? "s" : ""})</span>}
          </div>

          {(result.rates || []).map((r, i) => (
            <Card key={i} data-testid={`amazon-rate-${i}`}>
              <CardContent className="pt-5">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <Truck className="w-4 h-4 text-primary" />
                    <span className="font-medium">{r.service}</span>
                    {r.carrier && <span className="text-xs text-muted-foreground">· {r.carrier}</span>}
                  </div>
                  {r.amount != null && (
                    <span className="font-mono font-semibold">
                      {r.currency === "INR" || !r.currency ? "₹" : `${r.currency} `}{r.amount}
                    </span>
                  )}
                </div>
                <div className="mt-2 space-y-1">
                  {fmtWindow(r.promise?.pickupWindow) && (
                    <p className="text-xs flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400" data-testid="amazon-pickup-window">
                      <PackageCheck className="w-3.5 h-3.5 shrink-0" />
                      <span><b>Pickup:</b> {fmtWindow(r.promise.pickupWindow)}</span>
                    </p>
                  )}
                  {fmtWindow(r.promise?.deliveryWindow) && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 shrink-0" />
                      <span><b>Delivery:</b> {fmtWindow(r.promise.deliveryWindow)}</span>
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
        </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
