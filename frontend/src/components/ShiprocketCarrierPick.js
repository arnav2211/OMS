import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Clock, PackageCheck, AlertTriangle } from "lucide-react";

// Shown under the courier dropdown when "Shiprocket" is picked while making or
// editing an order. Quotes Shiprocket's carriers live for the shipping pincode
// and lets the telecaller pick one; booking later preselects that carrier.
// The weight is an estimate typed here - packing's real weight decides the
// final fare, so the booking screen re-quotes and flags a change.
export default function ShiprocketCarrierPick({ pincode, cod = false, declared = 0, value, onChange }) {
  const [weight, setWeight] = useState(value?.weight_kg ? String(value.weight_kg) : "1");
  const [couriers, setCouriers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const timer = useRef(null);

  const pin = String(pincode || "").trim();
  const w = parseFloat(weight);

  useEffect(() => {
    if (!/^\d{6}$/.test(pin)) { setCouriers([]); setMsg(pin ? "Enter a valid shipping pincode first" : "Choose the shipping address first"); return; }
    if (!(w > 0)) { setCouriers([]); setMsg("Enter the approximate weight"); return; }
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setLoading(true);
      setMsg("");
      try {
        const res = await api.get(`/shiprocket/check/${pin}`, { params: { weight: w, cod: !!cod } });
        if (res.data.serviceable) {
          setCouriers(res.data.couriers || []);
          // keep the earlier pick if it is still offered, else fall back to cheapest
          const keep = value && (res.data.couriers || []).find(c => c.courier_id === value.courier_id);
          const pick = keep || res.data.couriers[0];
          if (pick && (!value || value.courier_id !== pick.courier_id || +value.weight_kg !== w || +value.rate !== +pick.rate)) {
            onChange && onChange({ courier_id: pick.courier_id, name: pick.name, rate: pick.rate, etd: pick.etd || "",
                                   weight_kg: w, cod: !!cod, quoted_at: new Date().toISOString() });
          }
        } else {
          setCouriers([]);
          setMsg(res.data.message || "No Shiprocket courier serves this pincode");
          if (value) onChange && onChange(null);
        }
      } catch {
        setMsg("Could not reach Shiprocket right now");
      } finally {
        setLoading(false);
      }
    }, 500);
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pin, w, cod]);

  const pick = (c) => onChange && onChange({ courier_id: c.courier_id, name: c.name, rate: c.rate, etd: c.etd || "",
                                             weight_kg: w, cod: !!cod, quoted_at: new Date().toISOString() });

  return (
    <div className="md:col-span-3 rounded-md border border-violet-300 bg-violet-50/60 dark:bg-violet-950/20 dark:border-violet-800 p-3 space-y-2" data-testid="shiprocket-carrier-pick">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <Label className="text-xs">Approx. weight (kg)</Label>
          <Input type="number" step="0.1" min="0.1" value={weight} onChange={e => setWeight(e.target.value)}
                 className="h-9 w-28 mt-1" data-testid="shiprocket-pick-weight" />
        </div>
        <div className="text-xs text-muted-foreground pb-2">
          Shiprocket carriers for pincode <b>{pin || "—"}</b>{cod ? " · COD" : ""}. Fares include GST and are re-checked at booking with the packed weight.
        </div>
        {loading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground mb-2" />}
      </div>

      {msg && !loading && (
        <p className="text-xs text-amber-700 dark:text-amber-300 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> {msg}</p>
      )}

      {couriers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
          {couriers.map((c, i) => {
            const active = value?.courier_id === c.courier_id;
            return (
              <button key={c.courier_id} type="button" onClick={() => pick(c)} data-testid={`shiprocket-pick-${i}`}
                      className={`text-left rounded-md border px-3 py-2 transition ${active ? "border-violet-600 bg-white dark:bg-violet-900/40 ring-1 ring-violet-500" : "border-border bg-background hover:bg-accent/50"}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium truncate">
                    {c.name}
                    {i === 0 && <Badge className="ml-1.5 bg-emerald-600 text-white text-[10px] px-1 py-0">CHEAPEST</Badge>}
                  </span>
                  <span className="font-mono font-semibold text-sm shrink-0">₹{Number(c.rate).toFixed(0)}</span>
                </div>
                <div className="text-[11px] text-muted-foreground flex flex-wrap gap-x-3 mt-0.5">
                  {c.etd && <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> by {c.etd}</span>}
                  {c.cutoff_time && <span className="flex items-center gap-1"><PackageCheck className="w-3 h-3" /> pickup today if before {c.cutoff_time}</span>}
                  {c.rating ? <span>rating {c.rating}</span> : null}
                </div>
              </button>
            );
          })}
        </div>
      )}
      {value && (
        <p className="text-xs">
          Selected: <b>{value.name}</b> · ₹{Number(value.rate).toFixed(2)} at {value.weight_kg} kg
        </p>
      )}
    </div>
  );
}
