import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Mic, MicOff, Loader2, Play, Square, ArrowLeft, UserCircle, Package, Wrench, CalendarDays } from "lucide-react";

// Shared-phone work screen for packing executives. Deliberately simple:
// big buttons, short words, one thing at a time. Identity is name + PIN kept
// in sessionStorage for this tab only, so switching person is one tap.
const ID_KEY = "work_identity";
const loadIdentity = () => {
  try { return JSON.parse(sessionStorage.getItem(ID_KEY) || "null"); } catch { return null; }
};

const fmtClock = (iso) => iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "";
const fmtDur = (sec) => {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h} hr ${m} min`;
  if (m) return `${m} min${s ? ` ${s} sec` : ""}`;
  return `${s} sec`;
};
const liveSec = (sess) => sess ? (Date.now() - new Date(sess.started_at).getTime()) / 1000 : 0;

export default function MyWork() {
  const [identity, setIdentity] = useState(loadIdentity);
  const [staff, setStaff] = useState([]);
  const [steps, setSteps] = useState([]);
  const [screen, setScreen] = useState("home");   // home | pickOrder | pickStep | other
  const [me, setMe] = useState(null);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [pendingName, setPendingName] = useState(null);
  const [pin, setPin] = useState("");
  const [orders, setOrders] = useState([]);
  const [q, setQ] = useState("");
  const [order, setOrder] = useState(null);
  const [note, setNote] = useState("");
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const [leaveInfo, setLeaveInfo] = useState(null);
  const [leaveFrom, setLeaveFrom] = useState("");
  const [leaveTo, setLeaveTo] = useState("");
  const [leaveReason, setLeaveReason] = useState("");

  const loadLeaves = useCallback(async () => {
    if (!identity) return;
    try { const r = await api.get("/work/leave/my", { params: { name: identity.name } }); setLeaveInfo(r.data); }
    catch { /* ignore */ }
  }, [identity]);
  useEffect(() => { if (screen === "leave") loadLeaves(); }, [screen, loadLeaves]);

  const applyLeave = async () => {
    setBusy(true);
    try {
      await api.post("/work/leave/apply", { name: identity.name, pin: identity.pin,
        start_date: leaveFrom, end_date: leaveTo || leaveFrom, reason: leaveReason });
      toast.success("Leave request sent to admin");
      setLeaveFrom(""); setLeaveTo(""); setLeaveReason("");
      loadLeaves();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not send", { duration: 8000 }); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    api.get("/work/staff").then(r => setStaff(r.data)).catch(() => {});
    api.get("/work/config").then(r => setSteps(r.data.steps)).catch(() => {});
  }, []);

  const refreshMe = useCallback(async () => {
    if (!identity) return;
    try {
      const r = await api.get("/work/me", { params: { name: identity.name } });
      setMe(r.data);
    } catch { /* keep last */ }
  }, [identity]);

  useEffect(() => { refreshMe(); }, [refreshMe]);
  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), 1000);
    const p = setInterval(refreshMe, 15000);
    return () => { clearInterval(t); clearInterval(p); };
  }, [refreshMe]);

  const loadOrders = useCallback(async (query) => {
    try {
      const r = await api.get("/work/orders", { params: { q: query || "" } });
      setOrders(r.data);
    } catch (e) { toast.error("Could not load orders"); }
  }, []);
  useEffect(() => {
    if (screen !== "pickOrder") return;
    const t = setTimeout(() => loadOrders(q), 300);
    return () => clearTimeout(t);
  }, [screen, q, loadOrders]);

  // ── identity ──
  const choosePerson = (name) => { setPendingName(name); setPin(""); };
  // `silent` is the automatic try at 4 digits for a PIN of unknown length: a
  // miss keeps the digits so a longer PIN can still be finished with OK.
  const submitPin = async (value = pin, silent = false) => {
    if (value.length < 4 || busy) return;
    setBusy(true);
    try {
      await api.post("/work/pin/check", { name: pendingName, pin: value });
      const id = { name: pendingName, pin: value };
      sessionStorage.setItem(ID_KEY, JSON.stringify(id));
      setIdentity(id); setPendingName(null); setPin(""); setScreen("home");
    } catch (e) {
      if (!silent) {
        toast.error(e.response?.data?.detail || "Wrong PIN");
        setPin("");
      }
    } finally { setBusy(false); }
  };

  // No OK tap needed: the PIN checks itself the moment the last digit is in.
  useEffect(() => {
    if (!pendingName || pin.length < 4) return;
    const len = staff.find(s => s.name === pendingName)?.pin_len;
    if (len) { if (pin.length === len) submitPin(pin, false); }
    else if (pin.length === 4) submitPin(pin, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pin, pendingName]);
  const switchPerson = () => {
    sessionStorage.removeItem(ID_KEY);
    setIdentity(null); setMe(null); setScreen("home");
  };

  // ── actions ──
  const start = async (payload) => {
    setBusy(true);
    try {
      await api.post("/work/start", { name: identity.name, pin: identity.pin, ...payload });
      toast.success("Started");
      setScreen("home"); setOrder(null); setNote(""); setQ("");
      await refreshMe();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(d || "Could not start");
      if (e.response?.status === 403) switchPerson();
    } finally { setBusy(false); }
  };
  const stop = async () => {
    setBusy(true);
    try {
      await api.post("/work/stop", { name: identity.name, pin: identity.pin });
      toast.success("Done. Good work!");
      await refreshMe();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not stop"); }
    finally { setBusy(false); }
  };
  const confirmStill = async () => {
    try { await api.post("/work/confirm", { name: identity.name, pin: identity.pin }); await refreshMe(); }
    catch (e) { toast.error("Could not confirm"); }
  };

  // ── speech to text (Chrome on Android) ──
  const canSpeak = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  const toggleMic = (setter = setNote) => {
    if (listening) { recRef.current?.stop(); setListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return toast.error("Speaking is not supported on this phone. Please type.");
    const rec = new SR();
    rec.lang = "en-IN"; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = (ev) => {
      const text = ev.results[0][0].transcript;
      setter(prev => (prev ? prev + " " : "") + text);
    };
    rec.onerror = () => { setListening(false); toast.error("Could not hear. Try again or type."); };
    rec.onend = () => setListening(false);
    recRef.current = rec; rec.start(); setListening(true);
  };

  const active = me?.active;
  const activeSec = active ? liveSec(active) : 0;
  void tick;

  // ── screen: who are you ──
  if (!identity) {
    return (
      <div className="max-w-md mx-auto space-y-4 p-2" data-testid="my-work">
        <h1 className="text-2xl font-bold text-center">Who are you?</h1>
        <p className="text-center text-muted-foreground">Tap your name</p>
        <div className="grid grid-cols-2 gap-3">
          {staff.map(s => (
            <Button key={s.name} className="h-20 text-xl" variant={pendingName === s.name ? "default" : "outline"}
                    onClick={() => choosePerson(s.name)} disabled={!s.has_pin}>
              <UserCircle className="w-6 h-6 mr-2" /> {s.name}
            </Button>
          ))}
        </div>
        {staff.some(s => !s.has_pin) && (
          <p className="text-xs text-center text-muted-foreground">Grey names have no PIN yet. Ask admin.</p>
        )}
        <Dialog open={!!pendingName} onOpenChange={(o) => !o && setPendingName(null)}>
          <DialogContent className="max-w-xs">
            <DialogHeader><DialogTitle className="text-xl">Hello {pendingName}. Enter your PIN</DialogTitle></DialogHeader>
            <div className="text-center text-3xl tracking-[0.5em] h-12 font-mono">{"•".repeat(pin.length) || " "}</div>
            <div className="grid grid-cols-3 gap-2">
              {[1,2,3,4,5,6,7,8,9].map(n => (
                <Button key={n} variant="outline" className="h-14 text-2xl" onClick={() => pin.length < 6 && setPin(pin + n)}>{n}</Button>
              ))}
              <Button variant="ghost" className="h-14" onClick={() => setPin("")}>Clear</Button>
              <Button variant="outline" className="h-14 text-2xl" onClick={() => pin.length < 6 && setPin(pin + "0")}>0</Button>
              <Button className="h-14 text-lg" onClick={() => submitPin(pin, false)} disabled={busy || pin.length < 4}>
                {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : "OK"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ── screen: pick order ──
  if (screen === "pickOrder") {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Button variant="ghost" onClick={() => setScreen("home")}><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        <h2 className="text-xl font-bold">Which order?</h2>
        <Input placeholder="Type order number or customer name" value={q} onChange={e => setQ(e.target.value)} className="h-12 text-lg" autoFocus />
        <div className="space-y-2">
          {orders.map(o => (
            <button key={o.id} className="w-full text-left border rounded-lg p-3 hover:bg-accent active:bg-accent"
                    onClick={() => { setOrder(o); setScreen("pickStep"); }}>
              <div className="flex justify-between items-center">
                <span className="font-bold text-lg">{o.order_number}</span>
                <span className="text-xs text-muted-foreground">{o.items_count} item(s){o.weight_kg ? ` · ${o.weight_kg} kg` : ""}</span>
              </div>
              <div className="text-sm">{o.customer_name}{o.city ? ` · ${o.city}` : ""}</div>
              {o.working_now?.length > 0 && (
                <div className="text-xs text-emerald-700 dark:text-emerald-400 mt-1">Now: {o.working_now.join(", ")}</div>
              )}
            </button>
          ))}
          {orders.length === 0 && <p className="text-center text-muted-foreground py-6">No orders found</p>}
        </div>
      </div>
    );
  }

  // ── screen: pick step ──
  if (screen === "pickStep" && order) {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Button variant="ghost" onClick={() => setScreen("pickOrder")}><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        <h2 className="text-xl font-bold">{order.order_number} · {order.customer_name}</h2>
        <p className="text-muted-foreground">What will you do?</p>
        <div className="grid gap-3">
          {steps.map((st, i) => (
            <Button key={st.key} className="h-16 text-lg justify-start" variant="outline" disabled={busy}
                    onClick={() => start({ kind: "order", order_id: order.id, step: st.key })}>
              <span className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center mr-3">{i + 1}</span>
              {st.label}
            </Button>
          ))}
        </div>
      </div>
    );
  }

  // ── screen: other work ──
  if (screen === "other") {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Button variant="ghost" onClick={() => setScreen("home")}><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        <h2 className="text-xl font-bold">Other work</h2>
        <p className="text-muted-foreground">Say or type what you are doing</p>
        <textarea className="w-full border rounded-lg p-3 text-lg min-h-[110px] bg-background" value={note}
                  onChange={e => setNote(e.target.value)} placeholder="Example: cleaning the room, loading the van" />
        <div className="grid grid-cols-2 gap-3">
          <Button variant={listening ? "destructive" : "outline"} className="h-16 text-lg" onClick={() => toggleMic(setNote)} disabled={!canSpeak && !listening}>
            {listening ? <><MicOff className="w-6 h-6 mr-2" /> Stop</> : <><Mic className="w-6 h-6 mr-2" /> Speak</>}
          </Button>
          <Button className="h-16 text-lg" disabled={busy || !note.trim()} onClick={() => start({ kind: "other", note })}>
            <Play className="w-6 h-6 mr-2" /> Start
          </Button>
        </div>
        {!canSpeak && <p className="text-xs text-muted-foreground">Speaking works in Chrome on Android. Otherwise please type.</p>}
      </div>
    );
  }

  // ── screen: leave ──
  if (screen === "leave") {
    const att = leaveInfo?.attendance;
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Button variant="ghost" onClick={() => setScreen("home")}><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
        <h2 className="text-xl font-bold">Leave</h2>
        {leaveInfo && !leaveInfo.linked && (
          <p className="text-amber-600">Your name is not linked to the CRM yet. Ask admin.</p>
        )}
        {leaveInfo?.linked && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-sm text-muted-foreground">From date</label>
                <Input type="date" className="h-12 text-lg" value={leaveFrom} onChange={e => setLeaveFrom(e.target.value)} /></div>
              <div><label className="text-sm text-muted-foreground">To date</label>
                <Input type="date" className="h-12 text-lg" value={leaveTo} onChange={e => setLeaveTo(e.target.value)} /></div>
            </div>
            <p className="text-xs text-muted-foreground">One day only? Fill "From date" and leave "To date" empty.</p>
            <label className="text-sm text-muted-foreground">Why do you need leave?</label>
            <textarea className="w-full border rounded-lg p-3 text-lg min-h-[100px] bg-background" value={leaveReason}
                      onChange={e => setLeaveReason(e.target.value)} placeholder="Example: not well, family function" />
            <div className="grid grid-cols-2 gap-3">
              <Button variant={listening ? "destructive" : "outline"} className="h-14 text-lg" onClick={() => toggleMic(setLeaveReason)} disabled={!canSpeak && !listening}>
                {listening ? <><MicOff className="w-5 h-5 mr-2" /> Stop</> : <><Mic className="w-5 h-5 mr-2" /> Speak</>}
              </Button>
              <Button className="h-14 text-lg" onClick={applyLeave} disabled={busy || !leaveFrom || leaveReason.trim().length < 5}>
                {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : "Send to admin"}
              </Button>
            </div>
            {att && <p className="text-sm">Today: {att.on_leave ? "on leave" : att.present ? `present since ${String(att.check_in).slice(11, 16)}` : "not punched in"}</p>}
          </>
        )}
        <h3 className="font-semibold pt-2">My leave requests</h3>
        <div className="space-y-2">
          {(leaveInfo?.leaves || []).map(lv => (
            <div key={lv.id} className="border rounded p-2 text-sm">
              <div className="flex justify-between">
                <span className="font-medium">{lv.start_date}{lv.end_date !== lv.start_date ? ` to ${lv.end_date}` : ""}</span>
                <span className={lv.status === "pending" ? "text-amber-600" : lv.status === "rejected" ? "text-red-600" : "text-emerald-600"}>
                  {lv.status === "pending" ? "Waiting" : lv.status === "rejected" ? "Not approved" : "Approved"}
                </span>
              </div>
              <div className="text-muted-foreground">{lv.reason}</div>
            </div>
          ))}
          {leaveInfo && leaveInfo.leaves.length === 0 && <p className="text-sm text-muted-foreground">No leave requests yet.</p>}
        </div>
      </div>
    );
  }

  // ── screen: home ──
  const att = me?.attendance;
  return (
    <div className="max-w-md mx-auto space-y-4 p-2" data-testid="my-work-home">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Hi {identity.name}</h1>
        <Button variant="ghost" size="sm" onClick={switchPerson}>Not you? Switch</Button>
      </div>
      {att && (
        <p className="text-sm">
          {!att.linked ? <span className="text-muted-foreground">Attendance not linked - ask admin</span>
            : att.on_leave ? <span className="text-blue-600 dark:text-blue-400">You are on leave today</span>
            : att.present ? <span className="text-emerald-600 dark:text-emerald-400">Present today · in at {String(att.check_in).slice(11, 16)}</span>
            : <span className="text-amber-600 dark:text-amber-400">Not punched in yet - please punch attendance</span>}
        </p>
      )}

      <Card className={active ? "border-emerald-500" : ""}>
        <CardContent className="pt-5 space-y-3">
          {active ? (
            <>
              <p className="text-sm text-muted-foreground">You are doing</p>
              <p className="text-2xl font-bold">
                {active.kind === "order" ? `${active.order_number} · ${active.step_label}` : active.note}
              </p>
              {active.kind === "order" && <p className="text-muted-foreground">{active.customer_name}</p>}
              <p className="text-4xl font-mono font-bold text-emerald-600 dark:text-emerald-400">{fmtDur(activeSec)}</p>
              <p className="text-xs text-muted-foreground">Started at {fmtClock(active.started_at)}</p>
              <Button className="w-full h-16 text-xl" variant="destructive" onClick={stop} disabled={busy}>
                {busy ? <Loader2 className="w-6 h-6 animate-spin" /> : <><Square className="w-6 h-6 mr-2" /> DONE</>}
              </Button>
            </>
          ) : (
            <p className="text-lg text-center text-muted-foreground py-2">You are free. Start something below.</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Button className="h-20 text-lg" onClick={() => setScreen("pickOrder")} disabled={busy}>
          <Package className="w-6 h-6 mr-2" /> {active ? "Next order" : "Start order"}
        </Button>
        <Button className="h-20 text-lg" variant="secondary" onClick={() => setScreen("other")} disabled={busy}>
          <Wrench className="w-6 h-6 mr-2" /> Other work
        </Button>
      </div>
      <Button variant="outline" className="w-full h-12 text-base" onClick={() => setScreen("leave")}>
        <CalendarDays className="w-5 h-5 mr-2" /> Apply for leave
      </Button>

      <div>
        <div className="flex justify-between items-baseline mb-2">
          <h3 className="font-semibold">Today</h3>
          <span className="text-sm text-muted-foreground">
            {fmtDur(me?.today_total_sec)} · {me?.today_orders || 0} order(s)
          </span>
        </div>
        <div className="space-y-1">
          {(me?.today || []).map(s => (
            <div key={s.id} className={`text-sm border rounded px-3 py-2 flex justify-between ${s.status === "active" ? "border-emerald-500" : ""}`}>
              <span>
                <span className="font-mono text-muted-foreground">{fmtClock(s.started_at)}{s.ended_at ? `–${fmtClock(s.ended_at)}` : ""}</span>
                {" "}{s.kind === "order" ? `${s.order_number} · ${s.step_label}` : s.note}
                {s.status === "auto_closed" && <span className="text-amber-600 text-xs ml-1">(you forgot DONE)</span>}
              </span>
              <span className="font-mono">{fmtDur(s.status === "active" ? liveSec(s) : s.duration_sec)}</span>
            </div>
          ))}
          {(!me?.today || me.today.length === 0) && <p className="text-sm text-muted-foreground">Nothing yet today.</p>}
        </div>
      </div>

      <Dialog open={!!active?.needs_confirm}>
        <DialogContent className="max-w-xs" onPointerDownOutside={e => e.preventDefault()}>
          <DialogHeader><DialogTitle className="text-xl">Still working?</DialogTitle></DialogHeader>
          <p className="text-lg">{active?.kind === "order" ? `${active.order_number} · ${active.step_label}` : active?.note}</p>
          <p className="text-sm text-muted-foreground">Running for {fmtDur(activeSec)}. If you do not answer, it will be closed and marked.</p>
          <div className="grid grid-cols-2 gap-2">
            <Button className="h-14 text-lg" onClick={confirmStill}>Yes, still working</Button>
            <Button className="h-14 text-lg" variant="destructive" onClick={stop}>No, finished</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
