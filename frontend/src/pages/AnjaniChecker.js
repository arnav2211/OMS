import { useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Search, MapPin, Building2, Map, Phone, Mail, Loader2, CheckCircle2, XCircle } from "lucide-react";

const DELIVERY_TYPE_MAP = { "1": "Normal Delivery", "2": "Restricted / Special Delivery", "3": "Documents Only" };

export default function AnjaniChecker() {
  const [pincode, setPincode] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCheck = async () => {
    if (!pincode || pincode.length !== 6) return toast.error("Enter a valid 6-digit pincode");
    setLoading(true);
    setResult(null);
    try {
      const res = await api.get(`/anjani/check/${pincode}`);
      setResult(res.data);
      if (!res.data.serviceable) toast.error(res.data.message);
    } catch {
      toast.error("Unable to check serviceability right now. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => { if (e.key === "Enter") handleCheck(); };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight" data-testid="anjani-page-title">Shree Anjani Serviceability</h1>
        <p className="text-sm text-muted-foreground mt-1">Check if a pincode is serviceable by Shree Anjani Courier</p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base flex items-center gap-2"><MapPin className="w-4 h-4" /> Enter Pincode</CardTitle>
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
                data-testid="anjani-pincode-input"
              />
            </div>
          </div>
          <Button onClick={handleCheck} disabled={loading} className="w-full" data-testid="anjani-check-btn">
            {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
            Check Serviceability
          </Button>
        </CardContent>
      </Card>

      {/* Not Serviceable */}
      {result && !result.serviceable && (
        <Card className="border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900">
          <CardContent className="pt-6 flex items-center justify-center gap-2">
            <XCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-600 dark:text-red-400 font-medium" data-testid="anjani-not-serviceable">{result.message}</p>
          </CardContent>
        </Card>
      )}

      {/* Serviceable */}
      {result && result.serviceable && (
        <div className="space-y-4" data-testid="anjani-result">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-green-300 bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400 dark:border-green-800 gap-1.5 py-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> Serviceable
            </Badge>
            <span className="text-sm text-muted-foreground">Pincode: {pincode}</span>
            <span className="text-sm text-muted-foreground">({result.centers.length} center{result.centers.length > 1 ? "s" : ""})</span>
          </div>

          {result.centers.map((center, ci) => (
            <Card key={ci} data-testid={`anjani-center-${ci}`}>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Building2 className="w-4 h-4" /> {center.centerName}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Center Details */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                  <InfoField label="Center Code" value={center.centerCode} />
                  <InfoField label="Branch Type" value={center.branchType} />
                  <InfoField label="Franchise" value={center.franchiseName} />
                  <InfoField label="Is Cargo" value={center.isCargo ? "Yes" : "No"} />
                  <InfoField label="Active" value={center.isActive ? "Yes" : "No"} />
                </div>

                {/* Address */}
                {center.address && (
                  <div className="border-t pt-3">
                    <p className="text-xs text-muted-foreground uppercase font-medium mb-2 flex items-center gap-1"><MapPin className="w-3 h-3" /> Center Address</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                      {center.address.address1 && <InfoField label="Address 1" value={center.address.address1} span />}
                      {center.address.address2 && <InfoField label="Address 2" value={center.address.address2} span />}
                      {center.address.city && <InfoField label="City" value={center.address.city} />}
                      {center.address.pinCode && <InfoField label="Pin Code" value={center.address.pinCode} />}
                      {center.address.mobile && <InfoField label="Mobile" value={center.address.mobile} icon={<Phone className="w-3 h-3" />} />}
                      {center.address.phoneNumber && center.address.phoneNumber !== center.address.mobile && <InfoField label="Phone" value={center.address.phoneNumber} icon={<Phone className="w-3 h-3" />} />}
                      {center.address.email && <InfoField label="Email" value={center.address.email} icon={<Mail className="w-3 h-3" />} />}
                    </div>
                  </div>
                )}

                {/* Hub Details */}
                {center.hub && (
                  <div className="border-t pt-3">
                    <p className="text-xs text-muted-foreground uppercase font-medium mb-2 flex items-center gap-1"><Building2 className="w-3 h-3" /> Hub Details</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                      <InfoField label="Hub Name" value={center.hub.centerName} span />
                      <InfoField label="Hub Code" value={center.hub.centerCode} />
                      <InfoField label="Hub Type" value={center.hub.branchType} />
                      {center.hub.address && (
                        <>
                          {center.hub.address.address1 && <InfoField label="Hub Address" value={[center.hub.address.address1, center.hub.address.address2].filter(Boolean).join(", ")} span />}
                          {center.hub.address.city && <InfoField label="Hub City" value={center.hub.address.city} />}
                          {center.hub.address.mobile && <InfoField label="Hub Mobile" value={center.hub.address.mobile} icon={<Phone className="w-3 h-3" />} />}
                          {center.hub.address.phoneNumber && center.hub.address.phoneNumber !== center.hub.address.mobile && <InfoField label="Hub Phone" value={center.hub.address.phoneNumber} icon={<Phone className="w-3 h-3" />} />}
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Serviceable Areas */}
                {center.areas?.length > 0 && (
                  <div className="border-t pt-3">
                    <p className="text-xs text-muted-foreground uppercase font-medium mb-2 flex items-center gap-1"><Map className="w-3 h-3" /> Serviceable Areas ({center.areas.length})</p>
                    <div className="flex flex-wrap gap-1.5">
                      {center.areas.map((area, ai) => (
                        <Badge key={ai} variant="secondary" className="text-xs font-normal gap-1" data-testid={`anjani-area-${ci}-${ai}`}>
                          {area.areaName}
                          <span className="text-[10px] text-muted-foreground">
                            ({DELIVERY_TYPE_MAP[area.deliveryType] || `Type ${area.deliveryType}`})
                          </span>
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function InfoField({ label, value, icon, span }) {
  if (!value) return null;
  return (
    <div className={span ? "col-span-2 sm:col-span-3" : ""}>
      <span className="text-xs text-muted-foreground uppercase font-medium">{label}</span>
      <p className="font-medium flex items-center gap-1 mt-0.5">{icon}{value}</p>
    </div>
  );
}
