import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Mic, MicOff, Loader2, Play, Square, ArrowLeft, Package, Wrench, CalendarDays, X, Check, User, Users, ShoppingBag, ArrowRight } from "lucide-react";

// Shared-phone work screen for packing executives. Task first, people second:
// the order and step are picked once, then everyone doing it types only a
// 4-digit PIN (the PIN itself says who they are). The home screen is a board
// of everything running, so the phone never "belongs" to one person.
const DEVICE_KEY = "work_device_id";
const deviceId = () => {
  try {
    let d = localStorage.getItem(DEVICE_KEY);
    if (!d) { d = Math.random().toString(36).slice(2, 10); localStorage.setItem(DEVICE_KEY, d); }
    return d;
  } catch { return "phone"; }
};

const fmtClock = (iso) => iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "";
const fmtDur = (sec) => {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h} hr ${m} min`;
  if (m) return `${m} min${s ? ` ${s} sec` : ""}`;
  return `${s} sec`;
};
const liveSec = (sess) => (Date.now() - new Date(sess.started_at).getTime()) / 1000;
const taskText = (s) => s.kind === "order" ? `${s.order_number} · ${s.step_label}`
  : s.kind === "amazon" ? `${s.order_number} · Amazon order` : s.note;
const taskKey = (s) => s.kind === "order" ? `o:${s.order_id}:${s.step}`
  : s.kind === "amazon" ? `a:${s.order_id}` : `g:${s.group_id || s.id}`;

// Keypad that fires on the 4th digit. onPin resolves true to close/reset,
// or a string to show as the error and clear the digits.
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

export default function MyWork() {
  const [steps, setSteps] = useState([]);
  const [screen, setScreen] = useState("home");   // home | pickOrder | pickStep | other | who | leave | me
  const [active, setActive] = useState([]);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [orders, setOrders] = useState([]);
  const [q, setQ] = useState("");
  const [order, setOrder] = useState(null);
  const [amazonOrders, setAmazonOrders] = useState([]);
  const [task, setTask] = useState(null);          // {kind: order|amazon|other, order, step, note}
  const [members, setMembers] = useState([]);      // [{name, pin, current}]
  const [note, setNote] = useState("");
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const [pinAsk, setPinAsk] = useState(null);      // {title, hint, remark?, run(pin) -> true | "error"}
  const [remark, setRemark] = useState("");        // optional note typed/spoken while finishing
  const remarkRef = useRef("");
  useEffect(() => { remarkRef.current = remark; }, [remark]);
  const [mine, setMine] = useState(null);          // my-day / my-leave data after PIN
  const [leaveFrom, setLeaveFrom] = useState("");
  const [leaveTo, setLeaveTo] = useState("");
  const [leaveReason, setLeaveReason] = useState("");

  useEffect(() => { api.get("/work/config").then(r => setSteps(r.data.steps)).catch(() => {}); }, []);

  const refresh = useCallback(async () => {
    try { const r = await api.get("/work/active"); setActive(r.data); } catch { /* keep last */ }
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(() => setTick(x => x + 1), 1000);
    const p = setInterval(refresh, 10000);
    return () => { clearInterval(t); clearInterval(p); };
  }, [refresh]);
  void tick;

  const loadOrders = useCallback(async (query) => {
    try { const r = await api.get("/work/orders", { params: { q: query || "" } }); setOrders(r.data); }
    catch { toast.error("Could not load orders"); }
  }, []);
  useEffect(() => {
    if (screen !== "pickOrder") return;
    const t = setTimeout(() => loadOrders(q), 300);
    return () => clearTimeout(t);
  }, [screen, q, loadOrders]);

  const loadAmazon = useCallback(async (query) => {
    try { const r = await api.get("/work/amazon-orders", { params: { q: query || "" } }); setAmazonOrders(r.data); }
    catch { toast.error("Could not load Amazon orders"); }
  }, []);
  useEffect(() => {
    if (screen !== "pickAmazon") return;
    const t = setTimeout(() => loadAmazon(q), 300);
    return () => clearTimeout(t);
  }, [screen, q, loadAmazon]);

  const err = (e, fallback) => e.response?.data?.detail || fallback;
  const identify = async (pin) => (await api.post("/work/pin/identify", { pin, device: deviceId() })).data;

  const goHome = () => { setScreen("home"); setTask(null); setMembers([]); setOrder(null); setNote(""); setQ(""); setMine(null); refresh(); };

  // ── who is doing this: collect PINs ──
  const addMember = useCallback(async (pin) => {
    setBusy(true);
    try {
      const r = await identify(pin);
      setMembers(prev => prev.some(m => m.name === r.name) ? prev : [...prev, { name: r.name, pin, current: r.current }]);
      toast.success(`${r.name} added`);
    } catch (e) { toast.error(err(e, "Wrong PIN")); }
    finally { setBusy(false); }
  }, []);

  const startGroup = async () => {
    setBusy(true);
    try {
      await api.post("/work/start-group", {
        members: members.map(m => ({ name: m.name, pin: m.pin })),
        kind: task.kind, order_id: task.order?.id, step: task.step?.key, note: task.note, device: deviceId(),
      });
      toast.success(`Started for ${members.map(m => m.name).join(", ")}`);
      goHome();
    } catch (e) { toast.error(err(e, "Could not start")); }
    finally { setBusy(false); }
  };

  // ── PIN-confirmed actions from the board ──
  const askDoneOne = (s) => setPinAsk({
    title: `${s.staff}: enter your PIN`, hint: `Finish ${taskText(s)}`, remark: true,
    run: async (pin) => {
      try { await api.post("/work/stop", { name: s.staff, pin, remark: remarkRef.current }); toast.success(`${s.staff} done. Good work!`); refresh(); return true; }
      catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const askDoneAll = (s, names) => setPinAsk({
    title: "Done for all", hint: `Any one of ${names.join(", ")}: enter your PIN`, remark: true,
    run: async (pin) => {
      try {
        const r = await api.post("/work/stop-group", { pin, session_id: s.id, device: deviceId(), remark: remarkRef.current });
        toast.success(`Finished for ${r.data.closed.join(", ")}`); refresh(); return true;
      } catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const nextStepOf = (s) => {
    const i = steps.findIndex(x => x.key === s.step);
    return i >= 0 && i + 1 < steps.length ? steps[i + 1] : null;
  };
  const askNext = (s, names, nxt) => setPinAsk({
    title: `Next: ${nxt.label}`, remark: true,
    hint: names.length > 1 ? `Same people continue. Any one of ${names.join(", ")}: enter your PIN` : `${names[0]}: enter your PIN to continue`,
    run: async (pin) => {
      try {
        const r = await api.post("/work/next-step", { pin, session_id: s.id, device: deviceId(), remark: remarkRef.current });
        toast.success(`${r.data.people.join(", ")}: now ${r.data.step_label}`); refresh(); return true;
      } catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const askStill = (s) => setPinAsk({
    title: `${s.staff}: still working?`, hint: "Enter your PIN to say yes",
    run: async (pin) => {
      try { await api.post("/work/confirm", { name: s.staff, pin }); refresh(); return true; }
      catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const askMe = (next) => setPinAsk({
    title: "Enter your PIN", hint: next === "leave" ? "To see your leave" : "To see your day",
    run: async (pin) => {
      try {
        const who = await identify(pin);
        const [me, lv] = await Promise.all([
          api.get("/work/me", { params: { name: who.name } }),
          api.get("/work/leave/my", { params: { name: who.name } }),
        ]);
        setMine({ name: who.name, pin, me: me.data, leave: lv.data });
        setScreen(next); return true;
      } catch (e) { return err(e, "Wrong PIN"); }
    },
  });
  const sendLeave = () => setPinAsk({
    title: "Enter your PIN", hint: "To send your leave request",
    run: async (pin) => {
      try {
        const who = await identify(pin);
        await api.post("/work/leave/apply", { name: who.name, pin, start_date: leaveFrom, end_date: leaveTo || leaveFrom, reason: leaveReason });
        toast.success(`Leave request sent for ${who.name}`);
        setLeaveFrom(""); setLeaveTo(""); setLeaveReason(""); goHome(); return true;
      } catch (e) { return err(e, "Could not send"); }
    },
  });

  // ── speech to text (Chrome on Android) ──
  const canSpeak = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  const toggleMic = (setter) => {
    if (listening) { recRef.current?.stop(); setListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return toast.error("Speaking is not supported on this phone. Please type.");
    const rec = new SR();
    rec.lang = "en-IN"; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = (ev) => setter(prev => (prev ? prev + " " : "") + ev.results[0][0].transcript);
    rec.onerror = () => { setListening(false); toast.error("Could not hear. Try again or type."); };
    rec.onend = () => setListening(false);
    recRef.current = rec; rec.start(); setListening(true);
  };
  const MicButton = ({ setter, className }) => (
    <Button variant={listening ? "destructive" : "outline"} className={className} onClick={() => toggleMic(setter)} disabled={!canSpeak && !listening}>
      {listening ? <><MicOff className="w-5 h-5 mr-2" /> Stop</> : <><Mic className="w-5 h-5 mr-2" /> Speak</>}
    </Button>
  );

  const pinDialog = (
    <Dialog open={!!pinAsk} onOpenChange={(o) => { if (!o) { setPinAsk(null); setRemark(""); } }}>
      <DialogContent className="max-w-xs">
        <DialogHeader><DialogTitle className="text-xl">{pinAsk?.title}</DialogTitle></DialogHeader>
        {pinAsk?.hint && <p className="text-sm text-muted-foreground -mt-2">{pinAsk.hint}</p>}
        {pinAsk?.remark && (
          <div className="space-y-1">
            <label className="text-sm text-muted-foreground">Note about the work (you can skip this)</label>
            <div className="flex gap-2">
              <textarea className="flex-1 border rounded-lg p-2 text-base min-h-[56px] bg-background" value={remark}
                        onChange={e => setRemark(e.target.value)} placeholder="Example: cleaned 40 diffusers" />
              <Button variant={listening ? "destructive" : "outline"} className="h-14 w-14 shrink-0" onClick={() => toggleMic(setRemark)} disabled={!canSpeak && !listening}>
                {listening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
              </Button>
            </div>
          </div>
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
  );

  const Back = ({ to }) => (
    <Button variant="ghost" onClick={() => (to ? setScreen(to) : goHome())}><ArrowLeft className="w-4 h-4 mr-1" /> Back</Button>
  );

  // ── screen: pick order ──
  if (screen === "pickOrder") {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back />
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

  // ── screen: pick Amazon order (one person does the whole order: no steps) ──
  if (screen === "pickAmazon") {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back />
        <h2 className="text-xl font-bold">Which Amazon order?</h2>
        <Input placeholder="Type AM number or product name" value={q} onChange={e => setQ(e.target.value)} className="h-12 text-lg" />
        <div className="space-y-2">
          {amazonOrders.map(o => {
            const due = o.ship_by ? new Date(o.ship_by) : null;
            const urgent = due && (due.getTime() < Date.now() || due.toDateString() === new Date().toDateString());
            return (
              <button key={o.id} className={`w-full text-left border rounded-lg p-3 hover:bg-accent active:bg-accent ${urgent ? "border-red-400" : ""}`}
                      onClick={() => { setTask({ kind: "amazon", order: o }); setMembers([]); setScreen("who"); }}>
                <div className="flex justify-between items-center">
                  <span className="font-bold text-lg">{o.order_number}</span>
                  {due && <span className={`text-xs ${urgent ? "text-red-600 font-semibold" : "text-muted-foreground"}`}>
                    {urgent ? "SHIP TODAY" : "ship by"} {due.toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</span>}
                </div>
                <div className="text-sm">{o.customer_name}</div>
                {o.working_now?.length > 0 && (
                  <div className="text-xs text-emerald-700 dark:text-emerald-400 mt-1">Now: {o.working_now.join(", ")}</div>
                )}
              </button>
            );
          })}
          {amazonOrders.length === 0 && <p className="text-center text-muted-foreground py-6">No Amazon orders waiting</p>}
        </div>
      </div>
    );
  }

  // ── screen: pick step ──
  if (screen === "pickStep" && order) {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back to="pickOrder" />
        <h2 className="text-xl font-bold">{order.order_number} · {order.customer_name}</h2>
        <p className="text-muted-foreground">What work?</p>
        <div className="grid gap-3">
          {steps.map((st, i) => (
            <Button key={st.key} className="h-16 text-lg justify-start" variant="outline"
                    onClick={() => { setTask({ kind: "order", order, step: st }); setMembers([]); setScreen("who"); }}>
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
        <Back />
        <h2 className="text-xl font-bold">Other work</h2>
        <p className="text-muted-foreground">Say or type what work it is</p>
        <textarea className="w-full border rounded-lg p-3 text-lg min-h-[110px] bg-background" value={note}
                  onChange={e => setNote(e.target.value)} placeholder="Example: cleaning the room, loading the van" />
        <div className="grid grid-cols-2 gap-3">
          <MicButton setter={setNote} className="h-16 text-lg" />
          <Button className="h-16 text-lg" disabled={!note.trim()}
                  onClick={() => { setTask({ kind: "other", note: note.trim() }); setMembers([]); setScreen("who"); }}>
            Next
          </Button>
        </div>
        {!canSpeak && <p className="text-xs text-muted-foreground">Speaking works in Chrome on Android. Otherwise please type.</p>}
      </div>
    );
  }

  // ── screen: who is doing this ──
  if (screen === "who" && task) {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back to={task.kind === "order" ? "pickStep" : task.kind === "amazon" ? "pickAmazon" : "other"} />
        <div className="border rounded-lg p-3 bg-accent/40">
          <p className="text-sm text-muted-foreground">Work</p>
          <p className="text-xl font-bold">{task.kind === "order" ? `${task.order.order_number} · ${task.step.label}`
            : task.kind === "amazon" ? `${task.order.order_number} · Amazon order` : task.note}</p>
          {task.kind !== "other" && <p className="text-sm text-muted-foreground">{task.order.customer_name}</p>}
        </div>
        <h2 className="text-xl font-bold">Who is doing this?</h2>
        <p className="text-muted-foreground -mt-2">Each person: type your PIN. Then press Start.</p>
        <div className="flex flex-wrap gap-2 min-h-[2.5rem]">
          {members.map(m => (
            <span key={m.name} className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-900 rounded-full pl-3 pr-1 py-1 text-base font-medium">
              <Check className="w-4 h-4" /> {m.name}
              <button className="ml-1 rounded-full hover:bg-emerald-200 p-1" onClick={() => setMembers(members.filter(x => x.name !== m.name))}><X className="w-4 h-4" /></button>
            </span>
          ))}
          {members.length === 0 && <span className="text-sm text-muted-foreground py-2">Nobody yet</span>}
        </div>
        {members.filter(m => m.current).map(m => (
          <p key={m.name} className="text-xs text-amber-600">{m.name} is doing {taskText(m.current)} now. That will be finished.</p>
        ))}
        <PinPad onPin={addMember} busy={busy} />
        <Button className="w-full h-16 text-xl" disabled={busy || members.length === 0} onClick={startGroup}>
          <Play className="w-6 h-6 mr-2" /> START{members.length > 1 ? ` for ${members.length} people` : ""}
        </Button>
      </div>
    );
  }

  // ── screen: leave form (PIN asked on send) ──
  if (screen === "leaveForm") {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back />
        <h2 className="text-xl font-bold">Apply for leave</h2>
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
          <MicButton setter={setLeaveReason} className="h-14 text-lg" />
          <Button className="h-14 text-lg" onClick={sendLeave} disabled={!leaveFrom || leaveReason.trim().length < 5}>Send to admin</Button>
        </div>
        <Button variant="outline" className="w-full" onClick={() => askMe("leave")}>See my leave requests</Button>
        {pinDialog}
      </div>
    );
  }

  // ── screen: my leave requests (after PIN) ──
  if (screen === "leave" && mine) {
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back />
        <h2 className="text-xl font-bold">{mine.name}: leave requests</h2>
        {!mine.leave.linked && <p className="text-amber-600">Your name is not linked to the CRM yet. Ask admin.</p>}
        <div className="space-y-2">
          {mine.leave.leaves.map(lv => (
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
          {mine.leave.leaves.length === 0 && <p className="text-sm text-muted-foreground">No leave requests yet.</p>}
        </div>
      </div>
    );
  }

  // ── screen: my day (after PIN) ──
  if (screen === "me" && mine) {
    const att = mine.me.attendance;
    return (
      <div className="max-w-md mx-auto space-y-3 p-2">
        <Back />
        <h2 className="text-xl font-bold">{mine.name}: today</h2>
        {att && (
          <p className="text-sm">
            {!att.linked ? <span className="text-muted-foreground">Attendance not linked - ask admin</span>
              : att.on_leave ? <span className="text-blue-600">You are on leave today</span>
              : att.present ? <span className="text-emerald-600">Present today · in at {String(att.check_in).slice(11, 16)}</span>
              : <span className="text-amber-600">Not punched in yet - please punch attendance</span>}
          </p>
        )}
        <p className="text-muted-foreground">{fmtDur(mine.me.today_total_sec)} work · {mine.me.today_orders} order(s)</p>
        <div className="space-y-1">
          {mine.me.today.map(s => (
            <div key={s.id} className={`text-sm border rounded px-3 py-2 flex justify-between ${s.status === "active" ? "border-emerald-500" : ""}`}>
              <span>
                <span className="font-mono text-muted-foreground">{fmtClock(s.started_at)}{s.ended_at ? `–${fmtClock(s.ended_at)}` : ""}</span>
                {" "}{taskText(s)}
                {s.remark && <span className="block text-xs text-muted-foreground">Note: {s.remark}</span>}
                {s.status === "auto_closed" && <span className="text-amber-600 text-xs ml-1">({s.auto_reason === "punch_out" ? "ended when you punched out" : s.auto_reason === "day_end" ? "ended at 8 PM" : "you forgot DONE"})</span>}
              </span>
              <span className="font-mono">{fmtDur(s.status === "active" ? liveSec(s) : s.duration_sec)}</span>
            </div>
          ))}
          {mine.me.today.length === 0 && <p className="text-sm text-muted-foreground">Nothing yet today.</p>}
        </div>
      </div>
    );
  }

  // ── screen: home board ──
  const groups = [];
  for (const s of active) {
    const k = taskKey(s);
    let g = groups.find(x => x.key === k);
    if (!g) { g = { key: k, rows: [] }; groups.push(g); }
    g.rows.push(s);
  }

  return (
    <div className="max-w-md mx-auto space-y-4 p-2" data-testid="my-work-home">
      <div className="grid grid-cols-2 gap-3">
        <Button className="h-20 text-lg" onClick={() => setScreen("pickOrder")}>
          <Package className="w-6 h-6 mr-2" /> Start order
        </Button>
        <Button className="h-20 text-lg bg-amber-500 hover:bg-amber-600 text-black" onClick={() => setScreen("pickAmazon")} data-testid="mywork-amazon">
          <ShoppingBag className="w-6 h-6 mr-2" /> Amazon order
        </Button>
      </div>
      <Button className="w-full h-16 text-lg" variant="secondary" onClick={() => setScreen("other")}>
        <Wrench className="w-6 h-6 mr-2" /> Other work
      </Button>
      <div className="grid grid-cols-2 gap-3">
        <Button variant="outline" className="h-12" onClick={() => setScreen("leaveForm")}>
          <CalendarDays className="w-5 h-5 mr-2" /> Apply for leave
        </Button>
        <Button variant="outline" className="h-12" onClick={() => askMe("me")}>
          <User className="w-5 h-5 mr-2" /> My day
        </Button>
      </div>

      <h3 className="font-semibold flex items-center gap-2"><Users className="w-4 h-4" /> Working now</h3>
      {groups.length === 0 && <p className="text-muted-foreground text-center py-4">Nobody has started anything.</p>}
      {groups.map(g => {
        const first = g.rows[0];
        const names = g.rows.map(r => r.staff);
        return (
          <Card key={g.key} className="border-emerald-500/60">
            <CardContent className="pt-4 space-y-2">
              <div>
                <p className="text-lg font-bold leading-tight">{taskText(first)}</p>
                {first.kind !== "other" && <p className="text-sm text-muted-foreground">{first.customer_name}</p>}
              </div>
              {g.rows.map(s => (
                <div key={s.id} className="flex items-center justify-between gap-2 border rounded-lg px-3 py-2">
                  <div>
                    <div className="font-semibold">{s.staff}</div>
                    <div className="text-sm font-mono text-emerald-600 dark:text-emerald-400">{fmtDur(liveSec(s))} <span className="text-muted-foreground">· from {fmtClock(s.started_at)}</span></div>
                    {s.needs_confirm && (
                      <button className="text-xs text-amber-600 underline" onClick={() => askStill(s)}>Still working? Tap to say yes</button>
                    )}
                  </div>
                  <Button variant="destructive" className="h-12 px-5 text-base" onClick={() => askDoneOne(s)}>
                    <Square className="w-4 h-4 mr-1" /> DONE
                  </Button>
                </div>
              ))}
              {first.kind === "order" && nextStepOf(first) && (
                <Button className="w-full h-14 text-base" onClick={() => askNext(first, names, nextStepOf(first))} data-testid="mywork-next-step">
                  Next step: {nextStepOf(first).label} <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
              )}
              {g.rows.length > 1 && (
                <Button variant="outline" className="w-full h-12 text-base border-destructive text-destructive" onClick={() => askDoneAll(first, names)}>
                  Done for all ({g.rows.length})
                </Button>
              )}
            </CardContent>
          </Card>
        );
      })}
      {pinDialog}
    </div>
  );
}
