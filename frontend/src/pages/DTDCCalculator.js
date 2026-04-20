import { useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Search, Package, Truck, MapPin, Scale, IndianRupee, ArrowRight, Loader2 } from "lucide-react";

export default function DTDCCalculator() {
  const [pincode, setPincode] = useState("");
  const [kg, setKg] = useState("");
  const [grams, setGrams] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCalculate = async () => {
    if (!pincode || pincode.length !== 6) return toast.error("Enter a valid 6-digit pincode");
    const kgVal = parseFloat(kg) || 0;
    const gramsVal = parseFloat(grams) || 0;
    if (kgVal === 0 && gramsVal === 0) return toast.error("Enter package weight");

    setLoading(true);
    try {
      const res = await api.post("/dtdc/calculate", { pincode, kg: kgVal, grams: gramsVal });
      setResult(res.data);
      if (!res.data.serviceable) toast.error(res.data.message);
    } catch {
      toast.error("Calculation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleCalculate();
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight" data-testid="dtdc-page-title">DTDC Servicibilty Check</h1>
        <p className="text-sm text-muted-foreground mt-1">Check serviceability & calculate shipping cost</p>
      </div>

      {/* Input Card */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base flex items-center gap-2"><Package className="w-4 h-4" /> Shipment Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Destination Pincode</Label>
            <div className="relative mt-1">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={pincode}
                onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                onKeyDown={handleKeyDown}
                placeholder="Enter 6-digit pincode"
                className="pl-9"
                data-testid="dtdc-pincode-input"
              />
            </div>
          </div>

          <div>
            <Label>Package Weight</Label>
            <div className="flex gap-3 mt-1">
              <div className="flex-1">
                <div className="relative">
                  <Scale className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    value={kg}
                    onChange={(e) => setKg(e.target.value.replace(/[^\d.]/g, ""))}
                    onKeyDown={handleKeyDown}
                    placeholder="0"
                    className="pl-9"
                    data-testid="dtdc-kg-input"
                  />
                </div>
                <span className="text-xs text-muted-foreground mt-0.5 block">Kilograms</span>
              </div>
              <div className="flex-1">
                <Input
                  value={grams}
                  onChange={(e) => setGrams(e.target.value.replace(/[^\d.]/g, ""))}
                  onKeyDown={handleKeyDown}
                  placeholder="0"
                  data-testid="dtdc-grams-input"
                />
                <span className="text-xs text-muted-foreground mt-0.5 block">Grams</span>
              </div>
            </div>
          </div>

          <Button onClick={handleCalculate} disabled={loading} className="w-full" data-testid="dtdc-calculate-btn">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
            Calculate
          </Button>
        </CardContent>
      </Card>

      {/* Result Card */}
      {result && !result.serviceable && (
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900">
          <CardContent className="pt-6">
            <p className="text-center text-red-600 dark:text-red-400 font-medium" data-testid="dtdc-not-serviceable">
              This pincode is not serviceable by DTDC.
            </p>
          </CardContent>
        </Card>
      )}

      {result && result.serviceable && (
        <Card data-testid="dtdc-result-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Truck className="w-4 h-4" /> Shipping Estimate</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Location Info */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="space-y-0.5">
                <span className="text-xs text-muted-foreground uppercase font-medium">Pincode</span>
                <p className="font-medium" data-testid="dtdc-result-pincode">{result.pincode}</p>
              </div>
              <div className="space-y-0.5">
                <span className="text-xs text-muted-foreground uppercase font-medium">City</span>
                <p className="font-medium" data-testid="dtdc-result-city">{result.city}</p>
              </div>
              <div className="space-y-0.5">
                <span className="text-xs text-muted-foreground uppercase font-medium">State</span>
                <p className="font-medium" data-testid="dtdc-result-state">{result.state}</p>
              </div>
              <div className="space-y-0.5">
                <span className="text-xs text-muted-foreground uppercase font-medium">Category</span>
                <p className="font-medium" data-testid="dtdc-result-category">{result.category}</p>
              </div>
            </div>

            <div className="border-t pt-3">
              <div className="flex items-center justify-between text-sm mb-3">
                <span className="text-muted-foreground">Weight</span>
                <span className="font-medium" data-testid="dtdc-result-weight">{result.total_weight_kg} kg</span>
              </div>
            </div>

            {/* Final Result */}
            <div className="border-t pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground uppercase font-medium">Series</p>
                  <p className="text-lg font-bold mt-0.5" data-testid="dtdc-result-series">{result.series}</p>
                </div>
                <ArrowRight className="w-5 h-5 text-muted-foreground" />
                <div className="text-right">
                  <p className="text-xs text-muted-foreground uppercase font-medium">Final Charge</p>
                  <p className="text-2xl font-bold text-primary mt-0.5" data-testid="dtdc-result-final-charge">
                    {"\u20B9"}{result.final_charge}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Rate Reference */}
      <Card>
        <CardHeader className="pb-3 cursor-pointer" onClick={() => document.getElementById("rate-ref")?.classList.toggle("hidden")}>
          <CardTitle className="text-sm text-muted-foreground flex items-center gap-2">
            <IndianRupee className="w-3.5 h-3.5" /> Rate Reference (tap to toggle)
          </CardTitle>
        </CardHeader>
        <CardContent id="rate-ref" className="hidden">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <p className="font-semibold text-sm mb-2">Ground Express</p>
              <table className="w-full">
                <thead><tr className="border-b"><th className="text-left py-1">Category</th><th className="text-right py-1">Upto 3kg</th><th className="text-right py-1">/kg &gt;3</th></tr></thead>
                <tbody>
                  {[["Within City",77,20],["Within State",93,24],["Within Zone",111,30],["Metros",141,37],["Rest of India",152,41],["Special destination",215,58]].map(([cat,base,per]) => (
                    <tr key={cat} className="border-b border-muted"><td className="py-1">{cat}</td><td className="text-right">{"\u20B9"}{base}</td><td className="text-right">{"\u20B9"}{per}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <p className="font-semibold text-sm mb-2">Standard</p>
              <table className="w-full">
                <thead><tr className="border-b"><th className="text-left py-1">Category</th><th className="text-right py-1">Upto 500g</th><th className="text-right py-1">+500g</th></tr></thead>
                <tbody>
                  {[["Within City",24,16],["Within State",34,20],["Within Zone",37,29],["Metros",63,56],["Rest of India",69,58],["Special destination",98,89]].map(([cat,base,per]) => (
                    <tr key={cat} className="border-b border-muted"><td className="py-1">{cat}</td><td className="text-right">{"\u20B9"}{base}</td><td className="text-right">{"\u20B9"}{per}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
