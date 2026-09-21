import { useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/contexts/AuthContext";
import ShiprocketBookPanel from "@/components/ShiprocketBookPanel";
import { Search, MapPin, Loader2, CheckCircle2, XCircle, AlertTriangle, Truck, Clock, PackageCheck, ClipboardList } from "lucide-react";

// Booking spends wallet money and schedules pickups — mirrors the backend's role gate.
const BOOKING_ROLES = ["admin", "dispatch", "packaging", "accounts"];

export default function ShiprocketChecker() {
  const { user } = useAuth();
  const canSeeBooking = BOOKING_ROLES.includes(user?.role);
  const [pincode, setPincode] = useState("");
  const [weight, setWeight] = useState("1");
  const [cod, setCod] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCheck = async () => {
    if (!pincode || pincode.length !== 6) return toast.error("Enter a valid 6-digit pincode");
    const w = parseFloat(weight);
    if (!Number.isFinite(w) || w <= 0) return toast.error("Enter a valid weight in KG");
    setLoading(true);
    setResult(null);
    try {
      const res = await api.get(`/shiprocket/check/${pincode}`, { params: { weight: w, cod } });
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
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" data-testid="shiprocket-page-title">Shiprocket</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Check serviceability, compare its couriers, and book parcels</p>
      </div>

      <Tabs defaultValue="check" className="w-full">
        <TabsList className="mb-5 mx-auto flex w-fit">
          <TabsTrigger value="check" data-testid="sr-tab-check"><MapPin className="w-4 h-4 mr-2" /> Pincode Check</TabsTrigger>
          {canSeeBooking && (
            <TabsTrigger value="book" data-testid="sr-tab-book"><ClipboardList className="w-4 h-4 mr-2" /> Book Orders</TabsTrigger>
          )}
        </TabsList>

        {canSeeBooking && (
          <TabsContent value="book">
            <ShiprocketBookPanel />
          </TabsContent>
        )}

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
                      <Input value={pincode} onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                        onKeyDown={handleKeyDown} placeholder="Enter 6-digit pincode" inputMode="numeric"
                        className="pl-9 h-11 text-base" data-testid="shiprocket-pincode-input" />
                    </div>
                  </div>
                  <div>
                    <Label>Weight (KG)</Label>
                    <Input type="number" step="0.001" min="0.05" value={weight} onChange={(e) => setWeight(e.target.value)}
                      onKeyDown={handleKeyDown} placeholder="1.5" className="mt-1.5 h-11 text-base" data-testid="shiprocket-weight-input" />
                  </div>
                </div>
                <label className="flex items-center gap-2 cursor-pointer w-fit">
                  <Checkbox checked={cod} onCheckedChange={v => setCod(!!v)} data-testid="shiprocket-cod" />
                  <span className="text-sm">COD order</span>
                </label>
                <Button onClick={handleCheck} disabled={loading} className="w-full h-11 text-base" data-testid="shiprocket-check-btn">
                  {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
                  Check Serviceability
                </Button>
              </CardContent>
            </Card>

            {result && result.configured === false && (
              <Card className="border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900">
                <CardContent className="pt-6 flex items-start gap-2">
                  <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                  <p className="text-amber-700 dark:text-amber-400 text-sm font-medium">{result.message}</p>
                </CardContent>
              </Card>
            )}

            {result && result.configured !== false && !result.serviceable && (
              <Card className="border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900">
                <CardContent className="pt-6 flex items-center justify-center gap-2 text-center">
                  <XCircle className="w-5 h-5 text-red-500" />
                  <p className="text-red-600 dark:text-red-400 font-medium" data-testid="shiprocket-not-serviceable">{result.message}</p>
                </CardContent>
              </Card>
            )}

            {result && result.serviceable && (
              <div className="space-y-3" data-testid="shiprocket-result">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className="border-green-300 bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400 dark:border-green-800 gap-1.5 py-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Serviceable
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    Pincode: {pincode}{result.city ? ` · ${result.city}, ${result.state}` : ""} ({result.count} courier{result.count > 1 ? "s" : ""})
                  </span>
                </div>

                {(result.couriers || []).map((c, i) => (
                  <Card key={c.courier_id} className={i === 0 ? "border-2 border-emerald-500" : ""} data-testid={`shiprocket-rate-${i}`}>
                    <CardContent className="pt-5">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Truck className="w-4 h-4 text-primary" />
                          <span className="font-medium">{c.name}</span>
                          {i === 0 && <Badge className="bg-emerald-600 text-white text-[10px]">CHEAPEST</Badge>}
                          <span className="text-xs text-muted-foreground">
                            · {c.surface ? "Surface" : "Air"}{c.rating ? ` · rating ${c.rating}` : ""}
                          </span>
                        </div>
                        <div className="text-right">
                          <div className="font-mono font-semibold text-base">₹{Number(c.rate).toFixed(2)}</div>
                          <div className="text-[11px] text-muted-foreground">
                            GST included{cod && c.cod_charges ? ` · COD fee ₹${c.cod_charges}` : ""}
                          </div>
                        </div>
                      </div>
                      <div className="mt-2 space-y-1">
                        {c.cutoff_time && (
                          <p className="text-xs flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
                            <PackageCheck className="w-3.5 h-3.5 shrink-0" />
                            <span><b>Pickup:</b> same day if booked before {c.cutoff_time}</span>
                          </p>
                        )}
                        {c.etd && (
                          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                            <Clock className="w-3.5 h-3.5 shrink-0" />
                            <span><b>Expected delivery:</b> {c.etd}{c.days ? ` (${c.days} days)` : ""}</span>
                          </p>
                        )}
                        {c.rto_charges != null && (
                          <p className="text-[11px] text-muted-foreground">If the parcel comes back (RTO): ₹{Number(c.rto_charges).toFixed(2)} extra</p>
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
