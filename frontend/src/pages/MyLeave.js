import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { CalendarDays, Loader2 } from "lucide-react";

// Leave requests for OMS logins that are linked to a CRM user (accounts,
// telecallers). The request is written into the CRM, so admin approves it
// there like any other.
const fmtTime = (t) => t ? String(t).slice(11, 16) : "";
const StatusBadge = ({ status }) => {
  if (status === "pending") return <Badge className="bg-amber-100 text-amber-800">Pending</Badge>;
  if (status === "rejected") return <Badge className="bg-red-100 text-red-800">Rejected</Badge>;
  return <Badge className="bg-emerald-100 text-emerald-800">Approved</Badge>;
};

export function AttendanceLine({ att }) {
  if (!att || att.linked === false) return <span className="text-muted-foreground">Not linked to attendance — ask admin</span>;
  if (att.on_leave) return <span className="text-blue-600 dark:text-blue-400 font-medium">On leave today</span>;
  if (att.present) return (
    <span className="text-emerald-600 dark:text-emerald-400 font-medium">
      Present · in {fmtTime(att.check_in)}{att.check_out ? ` · out ${fmtTime(att.check_out)}` : ""}
    </span>
  );
  return <span className="text-amber-600 dark:text-amber-400 font-medium">Not punched in yet{att.leave_pending ? " · leave request pending" : ""}</span>;
};

export default function MyLeave() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const r = await api.get("/leave/my"); setData(r.data); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not load"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const apply = async () => {
    setBusy(true);
    try {
      await api.post("/leave/apply", { start_date: from, end_date: to || from, reason });
      toast.success("Leave request sent to admin");
      setFrom(""); setTo(""); setReason("");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not apply", { duration: 8000 }); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-2xl space-y-4" data-testid="my-leave">
      <h1 className="text-2xl font-bold flex items-center gap-2"><CalendarDays className="w-6 h-6" /> My Leave</h1>
      <Card>
        <CardContent className="pt-4 text-sm">
          <div className="text-muted-foreground mb-1">Today, {user?.name}{data?.crm_name ? ` (CRM: ${data.crm_name})` : ""}</div>
          <AttendanceLine att={data?.attendance ?? (data && !data.linked ? { linked: false } : null)} />
        </CardContent>
      </Card>

      {data?.linked && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Apply for leave</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-xs text-muted-foreground">From</label><Input type="date" value={from} onChange={e => setFrom(e.target.value)} /></div>
              <div><label className="text-xs text-muted-foreground">To</label><Input type="date" value={to} onChange={e => setTo(e.target.value)} placeholder="Same day" /></div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Reason (required)</label>
              <textarea className="w-full border rounded-lg p-2 min-h-[90px] bg-background" value={reason}
                        onChange={e => setReason(e.target.value)} placeholder="Why do you need leave?" />
            </div>
            <Button onClick={apply} disabled={busy || !from || reason.trim().length < 5}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null} Send request
            </Button>
            <p className="text-xs text-muted-foreground">Goes to admin in the CRM as pending. You will see the decision here.</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">My requests</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          {(data?.leaves || []).map(lv => (
            <div key={lv.id} className="border rounded p-2">
              <div className="flex justify-between items-center">
                <span className="font-medium">{lv.start_date}{lv.end_date !== lv.start_date ? ` → ${lv.end_date}` : ""}</span>
                <StatusBadge status={lv.status} />
              </div>
              <div className="text-muted-foreground whitespace-pre-wrap">{lv.reason}</div>
              {lv.decision_note && <div className="text-xs mt-1">Admin: {lv.decision_note}</div>}
            </div>
          ))}
          {data && data.leaves.length === 0 && <p className="text-muted-foreground">No leave requests yet.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
