import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Trophy, Crown, Medal, Flame, TrendingUp, Sparkles, Target, Users } from "lucide-react";

const inr = (n) => `₹${Math.round(Number(n || 0)).toLocaleString("en-IN")}`;
const PERIODS = [["today", "Today"], ["week", "This Week"], ["month", "This Month"]];

// Gold / silver / bronze for the podium
const PODIUM = {
  1: { ring: "ring-amber-400", bg: "from-amber-300 to-yellow-500", text: "text-amber-900", height: "h-28", icon: Crown },
  2: { ring: "ring-slate-300", bg: "from-slate-200 to-slate-400", text: "text-slate-800", height: "h-20", icon: Medal },
  3: { ring: "ring-orange-400", bg: "from-orange-300 to-amber-600", text: "text-orange-950", height: "h-14", icon: Medal },
};

function Confetti() {
  const pieces = useMemo(() => Array.from({ length: 36 }, (_, i) => ({
    left: Math.random() * 100, delay: Math.random() * 1.2, dur: 2.2 + Math.random() * 1.6,
    color: ["#f59e0b", "#ef4444", "#10b981", "#3b82f6", "#a855f7", "#ec4899"][i % 6], rot: Math.random() * 360,
  })), []);
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <style>{`@keyframes lb-fall{0%{transform:translateY(-20px) rotate(0)}100%{transform:translateY(260px) rotate(540deg);opacity:0}}`}</style>
      {pieces.map((p, i) => (
        <span key={i} className="absolute top-0 block h-2 w-1.5 rounded-sm"
          style={{ left: `${p.left}%`, background: p.color, transform: `rotate(${p.rot}deg)`,
                   animation: `lb-fall ${p.dur}s ${p.delay}s ease-in 2 both` }} />
      ))}
    </div>
  );
}

function Avatar({ name, size = "w-12 h-12", ring = "" }) {
  const initials = (name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
  return (
    <div className={`${size} ${ring} ring-4 rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white font-bold flex items-center justify-center shadow-lg`}>
      {initials}
    </div>
  );
}

export default function SalesLeaderboard() {
  const [period, setPeriod] = useState(() => {
    try { return localStorage.getItem("lb-period") || "month"; } catch { return "month"; }
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try { localStorage.setItem("lb-period", period); } catch { /* optional */ }
    let alive = true;
    setLoading(true);
    api.get("/leaderboard", { params: { period } })
      .then(r => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [period]);

  const board = data?.board || [];
  const me = data?.me;
  const top3 = board.slice(0, 3);
  const isChamp = me && me.rank === 1 && me.sales > 0;
  const above = me && me.rank > 1 ? board[me.rank - 2] : null;
  const podiumOrder = [top3[1], top3[0], top3[2]].filter(Boolean);

  return (
    <Card className="overflow-hidden border-0 shadow-xl" data-testid="sales-leaderboard">
      {/* Header */}
      <div className="relative bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 px-4 sm:px-6 py-4 text-white">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-white/15 p-2"><Trophy className="w-6 h-6 text-amber-300" /></div>
            <div>
              <h2 className="text-lg sm:text-xl font-bold tracking-tight">Sales Champions</h2>
              <p className="text-xs text-white/80">
                {data ? <>Team: {inr(data.team_sales)} · {data.team_orders} orders {data.period === "month" && <>· {data.days_left_in_month} days left in {data.label}</>}</> : "Loading..."}
              </p>
            </div>
          </div>
          <div className="flex rounded-lg bg-white/15 p-1 self-start">
            {PERIODS.map(([k, l]) => (
              <button key={k} onClick={() => setPeriod(k)} data-testid={`lb-period-${k}`}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition ${period === k ? "bg-white text-violet-700 shadow" : "text-white/90 hover:bg-white/10"}`}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      <CardContent className="p-4 sm:p-6 space-y-6">
        {loading && !data ? <p className="text-sm text-muted-foreground text-center py-8">Loading the leaderboard...</p> : !board.length ? (
          <p className="text-sm text-muted-foreground text-center py-8">No sales executives yet.</p>
        ) : (
          <>
            {/* Personal message */}
            {me && (
              <div className={`relative overflow-hidden rounded-2xl p-4 sm:p-5 ${isChamp
                ? "bg-gradient-to-br from-amber-100 via-yellow-50 to-orange-100 dark:from-amber-950/60 dark:via-yellow-950/40 dark:to-orange-950/50 border border-amber-300"
                : "bg-gradient-to-br from-indigo-50 to-fuchsia-50 dark:from-indigo-950/50 dark:to-fuchsia-950/40 border border-indigo-200 dark:border-indigo-800"}`}
                data-testid="lb-my-card">
                {isChamp && <Confetti />}
                <div className="relative flex items-start gap-4">
                  <div className={`shrink-0 rounded-2xl w-16 h-16 flex flex-col items-center justify-center font-black shadow-md ${isChamp ? "bg-gradient-to-br from-amber-300 to-yellow-500 text-amber-950" : "bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-300"}`}>
                    {isChamp ? <Crown className="w-7 h-7" /> : <span className="text-2xl">#{me.rank}</span>}
                    <span className="text-[10px] font-semibold uppercase tracking-wide">{isChamp ? "No. 1" : `of ${board.length}`}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-sm font-bold">
                      {isChamp ? <><Sparkles className="w-4 h-4 text-amber-500" /> You're the champion {data.period === "today" ? "today" : data.period === "week" ? "this week" : `of ${data.label}`}!</>
                        : me.sales > 0 ? <><Flame className="w-4 h-4 text-orange-500" /> You're climbing, keep going!</>
                        : <><Target className="w-4 h-4 text-indigo-500" /> Your first sale is one call away</>}
                    </div>
                    <p className="mt-1.5 text-[15px] leading-relaxed" data-testid="lb-message">{data.message}</p>
                    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                      <span><b className="text-foreground">{inr(me.sales)}</b> sales</span>
                      <span><b className="text-foreground">{me.orders}</b> orders</span>
                      {me.avg_order > 0 && <span><b className="text-foreground">{inr(me.avg_order)}</b> avg order</span>}
                      {isChamp && me.lead > 0 && <span className="text-amber-700 dark:text-amber-400 font-semibold">Leading by {inr(me.lead)}</span>}
                    </div>
                    {above && (
                      <div className="mt-3">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="font-semibold"><TrendingUp className="inline w-3.5 h-3.5 mr-1 text-emerald-600" />{inr(me.gap)} to overtake {above.name.split(" ")[0]}</span>
                          <span className="text-muted-foreground">#{above.rank}</span>
                        </div>
                        <div className="h-2.5 rounded-full bg-white/70 dark:bg-slate-800 overflow-hidden">
                          <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-500 transition-all duration-700"
                            style={{ width: `${above.sales ? Math.min(100, (100 * me.sales) / above.sales) : 0}%` }} />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Podium */}
            {top3[0]?.sales > 0 && (
              <div className="flex items-end justify-center gap-3 sm:gap-6 pt-2">
                {podiumOrder.map(p => {
                  const st = PODIUM[p.rank];
                  const Icon = st.icon;
                  return (
                    <div key={p.id} className="flex flex-col items-center w-24 sm:w-32">
                      {p.rank === 1 && <Crown className="w-7 h-7 text-amber-400 drop-shadow mb-1 animate-bounce" />}
                      <Avatar name={p.name} size={p.rank === 1 ? "w-16 h-16 text-lg" : "w-12 h-12 text-sm"} ring={st.ring} />
                      <div className={`mt-2 text-sm font-bold text-center truncate max-w-full ${p.is_me ? "text-violet-600 dark:text-violet-400" : ""}`}>
                        {p.name.split(" ")[0]}{p.is_me && " (you)"}
                      </div>
                      <div className="text-xs text-muted-foreground">{inr(p.sales)}</div>
                      <div className={`mt-2 w-full ${st.height} rounded-t-xl bg-gradient-to-b ${st.bg} ${st.text} flex flex-col items-center justify-start pt-2 shadow-inner`}>
                        <Icon className="w-5 h-5" />
                        <span className="text-xl font-black">{p.rank}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Full ranking */}
            <div className="space-y-2">
              {board.map(b => (
                <div key={b.id} data-testid={`lb-row-${b.rank}`}
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition ${b.is_me ? "bg-violet-50 dark:bg-violet-950/40 ring-2 ring-violet-400" : "bg-muted/40 hover:bg-muted"}`}>
                  <div className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-sm font-black ${
                    b.rank === 1 && b.sales > 0 ? "bg-amber-400 text-amber-950" : b.rank === 2 && b.sales > 0 ? "bg-slate-300 text-slate-800" : b.rank === 3 && b.sales > 0 ? "bg-orange-400 text-orange-950" : "bg-background text-muted-foreground border"}`}>
                    {b.rank}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-sm truncate">{b.name}{b.is_me && <span className="ml-1.5 text-[10px] font-bold uppercase text-violet-600 dark:text-violet-400">you</span>}</span>
                      <span className="font-mono text-sm font-bold">{inr(b.sales)}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1.5 flex-1 rounded-full bg-background overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all duration-700" style={{ width: `${b.pct_of_leader}%` }} />
                      </div>
                      <span className="text-[11px] text-muted-foreground whitespace-nowrap"><Users className="inline w-3 h-3 mr-0.5" />{b.orders} orders</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground text-center">Ranked on product sales (before GST, shipping and charges) of orders not cancelled.</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
