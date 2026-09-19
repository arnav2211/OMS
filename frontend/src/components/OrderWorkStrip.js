import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Play, Square, ArrowRight, Check, X, Timer, UserPlus } from "lucide-react";

// The work tracker, on the order itself: packers start / continue / finish
// their work here by PIN while looking at the items, and admins see who is on
// the order and for how long. My Work stays for other work, leave and the board.
const DO_ROLES = ["packaging", "admin", "dispatch"];
const deviceId = () => {
  try {
    let d = localStorage.getItem("work_device_id");
    if (!d) { d = Math.random().toString(36).slice(2, 10); localStorage.setItem("work_device_id", d); }
    return d;
  } catch { return "phone"; }
};
const fmtClock = (iso) => iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "";
const fmtDur = (sec) => {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h} hr ${m} min`;
  if (m) return `${m} min${sec < 600 && s ? ` ${s} sec` : ""}`;
  return `${s} sec`;
};
const liveSec = (s) => s.status === "active" ? (Date.now() - new Date(s.started_at).getTime()) / 1000 : s.duration_sec;

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

export default function OrderWorkStrip({ kind = "order", orderId, status, onChanged }) {
  const { user } = useAuth();
  const canAct = DO_ROLES.includes(user?.role) && !["dispatched", "cancelled"].includes(status);
  const [data, setData] = useState(null);
  const [steps, setSteps] = useState([]);
  const [hidden, setHidden] = useState(false);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(null);     // step object (or {amazon:true}) being started
  const [members, setMembers] = useState([]);
  const [pinAsk, setPinAsk] = useState(null);         // {title, hint, remark, run}
  const [remark, setRemark] = useState("");
  const remarkRef = useRef("");
  useEffect(() => { remarkRef.current = remark; }, [remark]);

  const load = useCallback(async () => {
    try { const r = await api.get(`/work/order/${orderId}`); setData(r.data); }
    catch (e) { if (e.response?.status === 403) setHidden(true); }
  }, [orderId]);
  useEffect(() => {
    load();
    api.get("/work/config").then(r => setSteps(r.data.steps)).catch(() => {});
    const t = setInterval(() => setTick(x => x + 1), 1000);
    const p = setInterval(load, 10000);
    return () => { clearInterval(t); clearInterval(p); };
  }, [load]);
  void tick;

  if (hidden || !data) return null;
  const err = (e, fb) => e.response?.data?.detail || fb;
  const changed = () => { load(); onChanged?.(); };

  const doneSteps = data.steps || [];
  const active = doneSteps.flatMap(st => st.sessions.filter(s => s.status === "active"));
  const activeStep = doneSteps.find(st => st.active);
  const stepKeys = steps.map(s => s.key);
  const touched = new Set(doneSteps.map(st => st.step));
  // what to offer next: after the running step, else the first step nobody has done
  const nextAfterActive = activeStep && kind === "order"
    ? steps[stepKeys.indexOf(activeStep.step) + 1] || null : null;
  const firstUndone = kind === "order" ? steps.find(s => !touched.has(s.key)) || null : null;

  const addMember = async (pin) => {
    setBusy(true);
    try {
      const r = (await api.post("/work/pin/identify", { pin, device: deviceId() })).data;
      setMembers(prev => prev.some(m => m.name === r.name) ? prev : [...prev, { name: r.name, pin, current: r.current }]);
    } catch (e) { toast.error(err(e, "Wrong PIN")); }
    finally { setBusy(false); }
  };
  const startNow = async () => {
    setBusy(true);
    try {
      await api.post("/work/start-group", {
        members: members.map(m => ({ name: m.name, pin: m.pin })), kind,
        order_id: orderId, step: kind === "order" ? starting.key : undefined, device: deviceId(),
      });
      toast.success(`Started for ${members.map(m => m.name).join(", ")}`);
      setStarting(null); setMembers([]); changed();
    } catch (e) { toast.error(err(e, "Could not start")); }
    finally { setBusy(false); }
  };
  const askDone = (s) => setPinAsk({
    title: `${s.staff}: enter your PIN`, hint: "Finish your work on this order", remark: true,
    run: async (pin) => {
      try { await api.post("/work/stop", { name: s.staff, pin, remark: remarkRef.current }); toast.success(`${s.staff} done`); changed(); return true; }
      catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const askDoneAll = () => setPinAsk({
    title: "Done for all", hint: `Any one of ${active.map(a => a.staff).join(", ")}: enter your PIN`, remark: true,
    run: async (pin) => {
      try { await api.post("/work/stop-group", { pin, session_id: active[0].id, device: deviceId(), remark: remarkRef.current }); changed(); return true; }
      catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const askNext = () => setPinAsk({
    title: `Next: ${nextAfterActive.label}`, remark: true,
    hint: active.length > 1 ? `Same people continue. Any one of ${active.map(a => a.staff).join(", ")}: enter your PIN` : `${active[0].staff}: enter your PIN to continue`,
    run: async (pin) => {
      try {
        const r = await api.post("/work/next-step", { pin, session_id: active[0].id, device: deviceId(), remark: remarkRef.current });
        toast.success(`${r.data.people.join(", ")}: now ${r.data.step_label}`); changed(); return true;
      } catch (e) { return err(e, "Wrong PIN"); }
    },
  });

  const nothingYet = doneSteps.length === 0;
  if (nothingYet && !canAct) return null;      // viewers see the strip once there is something to see

  return (
    <Card className={active.length ? "border-emerald-500" : ""} data-testid="order-work-strip">
      <CardContent className="pt-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="font-semibold flex items-center gap-2"><Timer className="w-4 h-4" /> Packing work</span>
          {data.total_sec > 0 && (
            <span className="text-sm text-muted-foreground">
              Total {fmtDur(doneSteps.reduce((t, st) => t + st.sessions.reduce((x, s) => x + liveSec(s), 0), 0))}
              {data.first_start ? ` · started ${fmtClock(data.first_start)}` : ""}
            </span>
          )}
        </div>

        {/* who did / is doing what */}
        {doneSteps.map(st => (
          <div key={st.step} className={`rounded-lg border px-3 py-2 ${st.active ? "border-emerald-500 bg-emerald-50/60 dark:bg-emerald-950/20" : ""}`}>
            <div className="flex justify-between items-center gap-2">
              <span className="font-medium text-sm">
                {st.active ? <Badge className="bg-emerald-100 text-emerald-800 mr-2">Now</Badge> : <Check className="w-4 h-4 inline text-emerald-600 mr-1" />}
                {st.label}
              </span>
              <span className="font-mono text-sm">{fmtDur(st.sessions.reduce((x, s) => x + liveSec(s), 0))}</span>
            </div>
            <div className="mt-1 space-y-1">
              {st.sessions.map(s => (
                <div key={s.id} className="flex justify-between items-center text-sm gap-2">
                  <span>
                    <span className="font-medium">{s.staff}</span>
                    <span className="text-muted-foreground"> · {fmtClock(s.started_at)}{s.ended_at ? `–${fmtClock(s.ended_at)}` : " → now"} · {fmtDur(liveSec(s))}</span>
                    {s.remark && <span className="block text-xs text-blue-700 dark:text-blue-300">Note: {s.remark}</span>}
                  </span>
                  {s.status === "active" && canAct && (
                    <Button variant="destructive" size="sm" className="h-9 px-4" onClick={() => askDone(s)}>
                      <Square className="w-3.5 h-3.5 mr-1" /> DONE
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
        {nothingYet && <p className="text-sm text-muted-foreground">Nobody has started this order yet.</p>}

        {/* actions */}
        {canAct && (
          <div className="space-y-2">
            {active.length > 0 ? (
              <>
                {nextAfterActive && (
                  <Button className="w-full h-14 text-base" onClick={askNext} data-testid="strip-next">
                    Next: {nextAfterActive.label} <ArrowRight className="w-5 h-5 ml-2" />
                  </Button>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" className="h-11" onClick={() => { setStarting(kind === "order" ? steps.find(x => x.key === activeStep.step) : { amazon: true, label: "Amazon order" }); setMembers([]); }}>
                    <UserPlus className="w-4 h-4 mr-1" /> Join this work
                  </Button>
                  {active.length > 1
                    ? <Button variant="outline" className="h-11 border-destructive text-destructive" onClick={askDoneAll}>Done for all ({active.length})</Button>
                    : <span />}
                </div>
              </>
            ) : kind === "amazon" ? (
              <Button className="w-full h-14 text-base" onClick={() => { setStarting({ amazon: true, label: "Amazon order" }); setMembers([]); }} data-testid="strip-start">
                <Play className="w-5 h-5 mr-2" /> {nothingYet ? "Start this order" : "Continue this order"}
              </Button>
            ) : (
              <>
                {firstUndone && (
                  <Button className="w-full h-14 text-base" onClick={() => { setStarting(firstUndone); setMembers([]); }} data-testid="strip-start">
                    <Play className="w-5 h-5 mr-2" /> Start: {firstUndone.label}
                  </Button>
                )}
                <div className="flex gap-1 flex-wrap items-center">
                  <span className="text-xs text-muted-foreground mr-1">{firstUndone ? "or another step:" : "start a step again:"}</span>
                  {steps.filter(s => s.key !== firstUndone?.key).map(s => (
                    <Button key={s.key} variant="outline" size="sm" className="h-8 text-xs" onClick={() => { setStarting(s); setMembers([]); }}>{s.label}</Button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </CardContent>

      {/* who is doing this: one or more PINs, then START */}
      <Dialog open={!!starting} onOpenChange={(o) => { if (!o) { setStarting(null); setMembers([]); } }}>
        <DialogContent className="max-w-xs">
          <DialogHeader><DialogTitle className="text-xl">{starting?.label}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground -mt-2">Each person doing this: type your PIN. Then press START.</p>
          <div className="flex flex-wrap gap-2 min-h-[2rem]">
            {members.map(m => (
              <span key={m.name} className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-900 rounded-full pl-3 pr-1 py-1 font-medium">
                <Check className="w-4 h-4" /> {m.name}
                <button className="ml-1 rounded-full hover:bg-emerald-200 p-1" onClick={() => setMembers(members.filter(x => x.name !== m.name))}><X className="w-4 h-4" /></button>
              </span>
            ))}
          </div>
          {members.filter(m => m.current && m.current.order_id !== orderId).map(m => (
            <p key={m.name} className="text-xs text-amber-600">{m.name} is on {m.current.order_number || m.current.note} now. That will be finished.</p>
          ))}
          <PinPad onPin={addMember} busy={busy} />
          <Button className="w-full h-14 text-lg" disabled={busy || members.length === 0} onClick={startNow}>
            <Play className="w-5 h-5 mr-2" /> START{members.length > 1 ? ` for ${members.length} people` : ""}
          </Button>
        </DialogContent>
      </Dialog>

      {/* single PIN confirmation with an optional note */}
      <Dialog open={!!pinAsk} onOpenChange={(o) => { if (!o) { setPinAsk(null); setRemark(""); } }}>
        <DialogContent className="max-w-xs">
          <DialogHeader><DialogTitle className="text-xl">{pinAsk?.title}</DialogTitle></DialogHeader>
          {pinAsk?.hint && <p className="text-sm text-muted-foreground -mt-2">{pinAsk.hint}</p>}
          {pinAsk?.remark && (
            <textarea className="w-full border rounded-lg p-2 text-sm min-h-[48px] bg-background" value={remark}
                      onChange={e => setRemark(e.target.value)} placeholder="Note about the work (you can skip this)" />
          )}
          {pinAsk && (
            <PinPad busy={busy} onPin={async (pin) => {
              setBusy(true);
              const res = await pinAsk.run(pin);
              setBusy(false);
              if (res === true) { setPinAsk(null); setRemark(""); } else toast.error(res);
            }} />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
