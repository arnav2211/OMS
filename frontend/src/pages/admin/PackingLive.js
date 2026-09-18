import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { RefreshCw, Activity, AlertTriangle, Clock } from "lucide-react";

// Live board for the packing tracker. Polls every 10 s on the "Now" tab.
const fmtClock = (iso) => iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—";
const fmtDur = (sec) => {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m} min`;
  return `${sec} sec`;
};
const liveSec = (s) => s.status === "active" ? (Date.now() - new Date(s.started_at).getTime()) / 1000 : s.duration_sec;
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const daysAgo = (n) => {
  const d = new Date(); d.setDate(d.getDate() - n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const StatusBadge = ({ s }) => {
  if (s.status === "active") return <Badge className="bg-emerald-100 text-emerald-800">Now</Badge>;
  if (s.status === "auto_closed") return <Badge className="bg-amber-100 text-amber-800">Forgot DONE</Badge>;
  return null;
};

const what = (s) => s.kind === "order"
  ? <><Link to={`/orders/${s.order_id}`} className="font-semibold hover:underline">{s.order_number}</Link> · {s.step_label}<span className="text-muted-foreground"> · {s.customer_name}</span></>
  : <span className="italic">{s.note}</span>;

export default function PackingLive() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState("now");
  const [live, setLive] = useState(null);
  const [tick, setTick] = useState(0);
  const [loading, setLoading] = useState(false);
  const [day, setDay] = useState(null);
  const [date, setDate] = useState(todayIso());
  const [staffFilter, setStaffFilter] = useState("");
  const [orderDetail, setOrderDetail] = useState(null);
  const [report, setReport] = useState(null);
  const [from, setFrom] = useState(daysAgo(6));
  const [to, setTo] = useState(todayIso());
  const [staff, setStaff] = useState([]);
  const [pins, setPins] = useState({});

  const loadLive = useCallback(async () => {
    try { const r = await api.get("/work/live"); setLive(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not load"); }
  }, []);
  const loadDay = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get("/work/day", { params: { date, staff: staffFilter } }); setDay(r.data); }
    catch (e) { toast.error("Could not load day"); }
    finally { setLoading(false); }
  }, [date, staffFilter]);
  const loadReport = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get("/work/report", { params: { from_date: from, to_date: to } }); setReport(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not load report"); }
    finally { setLoading(false); }
  }, [from, to]);
  const loadStaff = useCallback(async () => {
    try { const r = await api.get("/work/staff"); setStaff(r.data); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadLive(); loadStaff(); }, [loadLive, loadStaff]);
  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), 1000);
    const p = setInterval(() => { if (tab === "now" || tab === "orders") loadLive(); }, 10000);
    return () => { clearInterval(t); clearInterval(p); };
  }, [tab, loadLive]);
  useEffect(() => { if (tab === "day") loadDay(); }, [tab, loadDay]);
  useEffect(() => { if (tab === "report") loadReport(); }, [tab, loadReport]);
  void tick;

  const openOrder = async (o) => {
    try { const r = await api.get(`/work/order/${o.order_id}`); setOrderDetail({ ...o, detail: r.data }); }
    catch { toast.error("Could not load order"); }
  };
  const setPin = async (name) => {
    const pin = (pins[name] || "").trim();
    if (!/^\d{4,6}$/.test(pin)) return toast.error("PIN must be 4 to 6 digits");
    try {
      await api.put("/work/pin", { name, pin });
      toast.success(`PIN set for ${name}`);
      setPins(p => ({ ...p, [name]: "" }));
      loadStaff();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not set PIN"); }
  };

  const tabs = [["now", "Now"], ["orders", "Orders today"], ["day", "Day timeline"], ["report", "Report"]];
  if (isAdmin) tabs.push(["pins", "PINs"]);

  return (
    <div className="space-y-4" data-testid="packing-live">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Activity className="w-6 h-6" /> Packing Live</h1>
          <p className="text-sm text-muted-foreground">Who is doing what, right now and through the day. Updates every 10 seconds.</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadLive}><RefreshCw className="w-4 h-4" /></Button>
      </div>

      <div className="flex gap-1 flex-wrap">
        {tabs.map(([k, l]) => (
          <Button key={k} size="sm" variant={tab === k ? "default" : "outline"} onClick={() => setTab(k)}>{l}</Button>
        ))}
      </div>

      {tab === "now" && live && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {live.people.map(p => {
            const cur = p.current;
            return (
              <Card key={p.staff} className={cur ? "border-emerald-500" : ""}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex justify-between items-center text-base">
                    <span>{p.staff}</span>
                    {cur ? <Badge className="bg-emerald-100 text-emerald-800">Working</Badge> : <Badge variant="outline">Free</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {cur ? (
                    <>
                      <div>{what(cur)}</div>
                      <div className="text-2xl font-mono font-bold text-emerald-600 dark:text-emerald-400">{fmtDur(liveSec(cur))}</div>
                      <div className="text-xs text-muted-foreground">since {fmtClock(cur.started_at)}
                        {cur.needs_confirm && <span className="text-amber-600 ml-2"><AlertTriangle className="w-3 h-3 inline" /> not confirmed</span>}
                      </div>
                    </>
                  ) : (
                    <div className="text-muted-foreground">
                      {p.last_end ? `Last activity ended ${fmtClock(p.last_end)}` : "Nothing started today"}
                    </div>
                  )}
                  <div className="border-t pt-2 grid grid-cols-3 gap-1 text-xs">
                    <div><div className="text-muted-foreground">Today</div><div className="font-semibold">{fmtDur(p.total_sec + (cur ? liveSec(cur) - cur.duration_sec : 0))}</div></div>
                    <div><div className="text-muted-foreground">Orders</div><div className="font-semibold">{p.orders_count}</div></div>
                    <div><div className="text-muted-foreground">Other</div><div className="font-semibold">{fmtDur(p.other_sec)}</div></div>
                  </div>
                  {p.auto_closed > 0 && <div className="text-xs text-amber-600">{p.auto_closed}× forgot to press DONE</div>}
                  {p.first_start && <div className="text-xs text-muted-foreground">First start {fmtClock(p.first_start)}</div>}
                </CardContent>
              </Card>
            );
          })}
          {live.people.length === 0 && <p className="text-muted-foreground">No packing staff configured.</p>}
        </div>
      )}

      {tab === "orders" && live && (
        <Card>
          <CardContent className="pt-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Order</TableHead><TableHead>Customer</TableHead>
                  <TableHead>Steps (who · time)</TableHead>
                  <TableHead>Started</TableHead><TableHead className="text-right">Total work</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {live.orders.map(o => (
                  <TableRow key={o.order_id} className={`cursor-pointer ${o.active ? "bg-emerald-50 dark:bg-emerald-950/30" : ""}`} onClick={() => openOrder(o)}>
                    <TableCell className="font-semibold">{o.order_number}</TableCell>
                    <TableCell>{o.customer_name}</TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {o.steps.map(st => (
                          <Badge key={st.step} variant={st.active ? "default" : "outline"} className="font-normal">
                            {st.label}: {st.people.join(", ")} · {fmtDur(st.total_sec)}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>{fmtClock(o.first_start)}</TableCell>
                    <TableCell className="text-right font-mono">{fmtDur(o.total_sec)}</TableCell>
                  </TableRow>
                ))}
                {live.orders.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">No order work yet today</TableCell></TableRow>}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {tab === "day" && (
        <div className="space-y-3">
          <div className="flex gap-2 flex-wrap items-end">
            <div><label className="text-xs text-muted-foreground">Date</label><Input type="date" value={date} onChange={e => setDate(e.target.value)} className="w-44" /></div>
            <div>
              <label className="text-xs text-muted-foreground">Person</label>
              <select className="block border rounded h-10 px-2 bg-background" value={staffFilter} onChange={e => setStaffFilter(e.target.value)}>
                <option value="">Everyone</option>
                {staff.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
              </select>
            </div>
            <Button variant="outline" size="sm" onClick={loadDay} disabled={loading}>Refresh</Button>
          </div>
          {day?.timelines.map(t => (
            <Card key={t.staff}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex justify-between flex-wrap gap-2">
                  <span>{t.staff}</span>
                  <span className="text-sm font-normal text-muted-foreground">
                    {fmtClock(t.summary.first_start)} → {fmtClock(t.summary.last_end)} · work {fmtDur(t.summary.total_sec)} · {t.summary.orders_count} orders · other {fmtDur(t.summary.other_sec)}
                    {t.summary.auto_closed > 0 && <span className="text-amber-600"> · {t.summary.auto_closed}× forgot DONE</span>}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {t.items.map((it, i) => it.gap ? (
                  <div key={i} className="flex justify-between text-muted-foreground italic px-2">
                    <span><Clock className="w-3 h-3 inline mr-1" />no activity {fmtClock(it.from)}–{fmtClock(it.to)}</span>
                    <span className="font-mono">{fmtDur(it.duration_sec)}</span>
                  </div>
                ) : (
                  <div key={it.id} className={`flex justify-between items-center border rounded px-2 py-1 ${it.status === "active" ? "border-emerald-500" : ""}`}>
                    <span><span className="font-mono text-muted-foreground mr-2">{fmtClock(it.started_at)}–{it.ended_at ? fmtClock(it.ended_at) : "now"}</span>{what(it)} <StatusBadge s={it} /></span>
                    <span className="font-mono">{fmtDur(liveSec(it))}</span>
                  </div>
                ))}
                {t.items.length === 0 && <p className="text-muted-foreground">Nothing recorded.</p>}
              </CardContent>
            </Card>
          ))}
          {day && day.timelines.length === 0 && <p className="text-muted-foreground">No work recorded on {day.day}.</p>}
        </div>
      )}

      {tab === "report" && (
        <div className="space-y-3">
          <div className="flex gap-2 flex-wrap items-end">
            <div><label className="text-xs text-muted-foreground">From</label><Input type="date" value={from} onChange={e => setFrom(e.target.value)} className="w-44" /></div>
            <div><label className="text-xs text-muted-foreground">To</label><Input type="date" value={to} onChange={e => setTo(e.target.value)} className="w-44" /></div>
            <Button variant="outline" size="sm" onClick={loadReport} disabled={loading}>Refresh</Button>
          </div>
          <Card>
            <CardContent className="pt-4 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Day</TableHead><TableHead>Person</TableHead><TableHead>First start</TableHead><TableHead>Last end</TableHead>
                    <TableHead className="text-right">Order work</TableHead><TableHead className="text-right">Other work</TableHead>
                    <TableHead className="text-right">Orders</TableHead><TableHead className="text-right">Forgot DONE</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(report?.rows || []).map((r, i) => (
                    <TableRow key={i}>
                      <TableCell>{r.day}</TableCell><TableCell className="font-semibold">{r.staff}</TableCell>
                      <TableCell>{fmtClock(r.first_start)}</TableCell><TableCell>{fmtClock(r.last_end)}</TableCell>
                      <TableCell className="text-right font-mono">{fmtDur(r.order_sec)}</TableCell>
                      <TableCell className="text-right font-mono">{fmtDur(r.other_sec)}</TableCell>
                      <TableCell className="text-right">{r.orders_count}</TableCell>
                      <TableCell className="text-right">{r.auto_closed || ""}</TableCell>
                    </TableRow>
                  ))}
                  {report && report.rows.length === 0 && <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground">No work in this range</TableCell></TableRow>}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "pins" && isAdmin && (
        <Card>
          <CardHeader><CardTitle className="text-base">Executive PINs</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-muted-foreground">Each executive needs a 4–6 digit PIN to start work on the shared phones. Names come from Packaging Staff in Settings.</p>
            {staff.map(s => (
              <div key={s.name} className="flex items-center gap-2 flex-wrap">
                <span className="w-40 font-medium">{s.name}</span>
                {s.has_pin ? <Badge className="bg-emerald-100 text-emerald-800">PIN set</Badge> : <Badge variant="outline">No PIN</Badge>}
                <Input className="w-32" placeholder="New PIN" inputMode="numeric" value={pins[s.name] || ""}
                       onChange={e => setPins(p => ({ ...p, [s.name]: e.target.value.replace(/\D/g, "").slice(0, 6) }))} />
                <Button size="sm" onClick={() => setPin(s.name)}>{s.has_pin ? "Reset" : "Set"}</Button>
              </div>
            ))}
            {staff.length === 0 && <p className="text-muted-foreground">No packaging staff configured yet.</p>}
          </CardContent>
        </Card>
      )}

      <Dialog open={!!orderDetail} onOpenChange={(o) => !o && setOrderDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{orderDetail?.order_number} · {orderDetail?.customer_name}</DialogTitle></DialogHeader>
          {orderDetail?.detail && (
            <div className="space-y-3 text-sm">
              <div className="text-muted-foreground">
                Started {fmtClock(orderDetail.detail.first_start)} · {orderDetail.detail.last_end ? `last step ended ${fmtClock(orderDetail.detail.last_end)}` : "still in progress"} · total work {fmtDur(orderDetail.detail.total_sec)}
              </div>
              {orderDetail.detail.steps.map(st => (
                <div key={st.step} className="border rounded p-2">
                  <div className="flex justify-between font-semibold">
                    <span>{st.label} {st.active && <Badge className="bg-emerald-100 text-emerald-800 ml-1">Now</Badge>}</span>
                    <span className="font-mono">{fmtDur(st.total_sec)}</span>
                  </div>
                  <div className="text-muted-foreground">{st.people.join(", ")} · {fmtClock(st.first_start)} → {st.last_end ? fmtClock(st.last_end) : "now"}</div>
                  <div className="mt-1 space-y-0.5">
                    {st.sessions.map(s => (
                      <div key={s.id} className="flex justify-between text-xs">
                        <span>{s.staff} · {fmtClock(s.started_at)}–{s.ended_at ? fmtClock(s.ended_at) : "now"} <StatusBadge s={s} /></span>
                        <span className="font-mono">{fmtDur(liveSec(s))}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {orderDetail.detail.steps.length === 0 && <p className="text-muted-foreground">No work recorded for this order.</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
