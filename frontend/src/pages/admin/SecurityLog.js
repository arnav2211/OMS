import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";
import { ShieldCheck, RefreshCw } from "lucide-react";

// Admin review screen for the security log: logins, lockouts, buyer-data
// access and deletions. Reviewed weekly; entries are kept for 400 days.
const LABELS = {
  login_ok: ["Login", "bg-emerald-100 text-emerald-800"],
  login_failed: ["Wrong password", "bg-amber-100 text-amber-800"],
  login_blocked: ["Login blocked", "bg-red-100 text-red-800"],
  password_changed: ["Password changed", "bg-blue-100 text-blue-800"],
  pii_view: ["Buyer details viewed", "bg-purple-100 text-purple-800"],
  pii_list: ["Buyer list viewed", "bg-purple-100 text-purple-800"],
  pii_bulk_alert: ["Unusual buyer-data access", "bg-red-100 text-red-800"],
  pii_purged: ["Buyer details deleted (30 days)", "bg-slate-100 text-slate-800"],
  log_reviewed: ["Log reviewed", "bg-emerald-100 text-emerald-800"],
};
const FILTERS = [["", "Everything"], ["login_failed", "Wrong passwords"], ["login_blocked", "Blocked logins"],
  ["pii_view", "Buyer details viewed"], ["pii_bulk_alert", "Unusual access"], ["pii_purged", "Deletions"], ["log_reviewed", "Reviews"]];

export default function SecurityLog() {
  const [rows, setRows] = useState([]);
  const [encOn, setEncOn] = useState(null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/security/log", { params: { event: filter, limit: 500 } });
      setRows(r.data.rows); setEncOn(r.data.encryption_configured);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not load"); }
    finally { setLoading(false); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const markReviewed = async () => {
    try { await api.post("/security/log/reviewed"); toast.success("Review recorded"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not record"); }
  };
  const detail = (r) => [r.username && `user ${r.username}`, r.role, r.ip && `from ${r.ip}`, r.order, r.count != null && `${r.count} record(s)`,
    r.password_expired && "password older than 365 days", r.by && `by ${r.by}`].filter(Boolean).join(" · ");

  return (
    <div className="space-y-4" data-testid="security-log">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><ShieldCheck className="w-6 h-6" /> Security Log</h1>
          <p className="text-sm text-muted-foreground">
            Logins, lockouts and every access to Amazon buyer details. Kept 400 days. Review it at least every two weeks and press "Mark reviewed".
            {encOn != null && <span className="ml-2">{encOn ? "Buyer-data encryption: ON" : "Buyer-data encryption: NOT configured"}</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}><RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /></Button>
          <Button size="sm" onClick={markReviewed} data-testid="security-mark-reviewed">Mark reviewed</Button>
        </div>
      </div>
      <div className="flex gap-1 flex-wrap">
        {FILTERS.map(([k, l]) => <Button key={k} size="sm" variant={filter === k ? "default" : "outline"} onClick={() => setFilter(k)}>{l}</Button>)}
      </div>
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>When</TableHead><TableHead>Event</TableHead><TableHead>Details</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((r, i) => (
                <TableRow key={i}>
                  <TableCell className="whitespace-nowrap text-sm font-mono">{new Date(r.at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</TableCell>
                  <TableCell><Badge className={(LABELS[r.event] || [])[1] || ""}>{(LABELS[r.event] || [r.event])[0]}</Badge></TableCell>
                  <TableCell className="text-sm">{detail(r)}</TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground py-8">Nothing recorded</TableCell></TableRow>}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
