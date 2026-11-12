import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const ROLES = ["admin", "telecaller", "packaging", "accounts"];

/** Flag an order's stickers as urgent: the media team sees it red, at the top of their list. */
export default function StickerUrgentToggle({ source = "oms", order, className = "" }) {
  const { user } = useAuth();
  const [urgent, setUrgent] = useState(!!order?.sticker_urgent?.on);
  const [by, setBy] = useState(order?.sticker_urgent?.by || "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setUrgent(!!order?.sticker_urgent?.on);
    setBy(order?.sticker_urgent?.by || "");
  }, [order?.id, order?.sticker_urgent?.on, order?.sticker_urgent?.by]);

  if (!order?.id || !ROLES.includes(user?.role)) return null;
  if (["packed", "dispatched", "cancelled"].includes(order.status) && !urgent) return null;

  const toggle = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/sticker-urgent/${source}/${order.id}`, { urgent: !urgent });
      const v = res.data.sticker_urgent;
      setUrgent(!!v?.on);
      setBy(v?.by || "");
      toast.success(v?.on ? "Marked urgent for the media team" : "No longer urgent");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button size="sm" variant={urgent ? "destructive" : "outline"} disabled={busy} onClick={toggle}
      className={className} data-testid="sticker-urgent-toggle"
      title={urgent ? `Urgent for stickers${by ? ` (marked by ${by})` : ""} - click to clear` : "Ask the media team to do this order's stickers first"}>
      <AlertTriangle className="w-4 h-4 mr-1" />
      {urgent ? "Stickers urgent" : "Mark stickers urgent"}
    </Button>
  );
}
