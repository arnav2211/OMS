import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Square } from "lucide-react";

// Thin strip above every page on the packing login: who has work running,
// with a DONE (by PIN) on each, so finishing never needs a trip to another page.
const fmtMin = (iso) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} hr ${m % 60} min`;
};
const taskText = (s) => s.kind === "order" ? `${s.order_number} · ${s.step_label}`
  : s.kind === "amazon" ? `${s.order_number} · Amazon` : (s.note || "").slice(0, 28) + ((s.note || "").length > 28 ? "…" : "");
const taskLink = (s) => s.kind === "order" ? `/orders/${s.order_id}` : s.kind === "amazon" ? `/amazon-orders/${s.order_id}` : "/my-work";

function PinPad({ onPin, busy }) {
  const [pin, setPin] = useState("");
  const firing = useRef(false);
  useEffect(() => {
    if (pin.length !== 4 || firing.current) return;
    firing.current = true;
    Promise.resolve(onPin(pin)).finally(() => { setPin(""); firing.current = false; });
  }, [pin, onPin]);
  const add = (d) => { if (pin.length < 4 && !busy) setPin(pin + d); };
  return (
    <div>
      <div className="text-center text-3xl tracking-[0.5em] h-12 font-mono">
        {busy ? <Loader2 className="w-7 h-7 animate-spin inline" /> : ("•".repeat(pin.length) || <span className="text-base tracking-normal text-muted-foreground">4 digits</span>)}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => (
          <Button key={n} variant="outline" className="h-14 text-2xl" onClick={() => add(String(n))}>{n}</Button>
        ))}
        <span />
        <Button variant="outline" className="h-14 text-2xl" onClick={() => add("0")}>0</Button>
        <Button variant="ghost" className="h-14" onClick={() => setPin("")}>Clear</Button>
      </div>
    </div>
  );
}

export default function WorkingNowBar() {
  const { user } = useAuth();
  const location = useLocation();
  const show = user?.role === "packaging" && location.pathname !== "/my-work";   // My Work already is the board
  const [rows, setRows] = useState([]);
  const [, setTick] = useState(0);
  const [ask, setAsk] = useState(null);
  const [remark, setRemark] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const r = await api.get("/work/active"); setRows(r.data); } catch { /* tracker optional */ }
  }, []);
  useEffect(() => {
    if (!show) return;
    load();
    const p = setInterval(load, 10000);
    const t = setInterval(() => setTick(x => x + 1), 30000);
    return () => { clearInterval(p); clearInterval(t); };
  }, [show, load, location.pathname]);

  if (!show || rows.length === 0) return null;

  const finish = async (pin) => {
    setBusy(true);
    try {
      await api.post("/work/stop", { name: ask.staff, pin, remark });
      toast.success(`${ask.staff} done. Good work!`);
      setAsk(null); setRemark(""); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Wrong PIN"); }
    finally { setBusy(false); }
  };

  return (
    <div className="border-b bg-emerald-50 dark:bg-emerald-950/30 px-3 py-1.5" data-testid="working-now-bar">
      <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap">
        <span className="text-xs font-semibold text-emerald-800 dark:text-emerald-300 shrink-0">Working now</span>
        {rows.map(s => (
          <span key={s.id} className="inline-flex items-center gap-2 bg-background border border-emerald-300 rounded-full pl-3 pr-1 py-0.5 text-sm shrink-0">
            <span className="font-semibold">{s.staff}</span>
            <Link to={taskLink(s)} className="text-muted-foreground hover:underline">{taskText(s)}</Link>
            <span className="font-mono text-xs text-emerald-700 dark:text-emerald-400">{fmtMin(s.started_at)}</span>
            <Button variant="destructive" size="sm" className="h-7 px-3 rounded-full text-xs" onClick={() => { setAsk(s); setRemark(""); }}>
              <Square className="w-3 h-3 mr-1" /> DONE
            </Button>
          </span>
        ))}
      </div>

      <Dialog open={!!ask} onOpenChange={(o) => { if (!o) { setAsk(null); setRemark(""); } }}>
        <DialogContent className="max-w-xs">
          <DialogHeader><DialogTitle className="text-xl">{ask?.staff}: enter your PIN</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground -mt-2">Finish {ask ? taskText(ask) : ""}</p>
          <textarea className="w-full border rounded-lg p-2 text-sm min-h-[48px] bg-background" value={remark}
                    onChange={e => setRemark(e.target.value)} placeholder="Note about the work (you can skip this)" />
          {ask && <PinPad busy={busy} onPin={finish} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
