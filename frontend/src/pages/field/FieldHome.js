import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MapPin, LogOut, CheckCircle2, AlertTriangle } from "lucide-react";
import api from "@/lib/api";

/**
 * Minimal "on-duty" screen for the field_executive role.
 * While this screen is open it shares the device location with the office.
 * On Android this is a *foreground-only* fallback for quick testing — the
 * native CitSpray app's background service is what provides 24/7 tracking.
 */
export default function FieldHome() {
  const { user, logout } = useAuth();
  const [status, setStatus] = useState("starting"); // starting | active | denied | error
  const [lastSent, setLastSent] = useState(null);
  const [fixCount, setFixCount] = useState(0);
  const watchIdRef = useRef(null);
  const lastSentAtRef = useRef(0);

  const sendPing = useCallback(async (pos) => {
    const now = Date.now();
    // throttle to at most one ping every 10s
    if (now - lastSentAtRef.current < 10000) return;
    lastSentAtRef.current = now;
    const c = pos.coords;
    try {
      await api.post("/location/ping", {
        lat: c.latitude,
        lng: c.longitude,
        accuracy: c.accuracy ?? null,
        altitude: c.altitude ?? null,
        speed: c.speed ?? null,
        heading: c.heading ?? null,
        ts: new Date(pos.timestamp || Date.now()).toISOString(),
      });
      setLastSent(new Date());
      setFixCount((n) => n + 1);
      setStatus("active");
    } catch {
      /* keep trying on next fix */
    }
  }, []);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setStatus("error");
      return;
    }
    watchIdRef.current = navigator.geolocation.watchPosition(
      sendPing,
      (err) => setStatus(err.code === err.PERMISSION_DENIED ? "denied" : "error"),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 }
    );
    return () => {
      if (watchIdRef.current != null) navigator.geolocation.clearWatch(watchIdRef.current);
    };
  }, [sendPing]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background p-6">
      <Card className="w-full max-w-sm">
        <CardContent className="pt-8 pb-6 flex flex-col items-center text-center gap-4">
          <img src="/logo.png" alt="CitSpray" className="h-14 w-14 rounded-xl object-contain" />
          <div>
            <h1 className="text-xl font-bold">CitSpray Field</h1>
            <p className="text-sm text-muted-foreground">{user?.name}</p>
          </div>

          <div className="w-full rounded-xl border border-border p-4 flex items-center gap-3">
            {status === "active" ? (
              <CheckCircle2 className="w-6 h-6 text-emerald-500 shrink-0" />
            ) : status === "denied" || status === "error" ? (
              <AlertTriangle className="w-6 h-6 text-amber-500 shrink-0" />
            ) : (
              <MapPin className="w-6 h-6 text-primary shrink-0 animate-pulse" />
            )}
            <div className="text-left">
              <p className="text-sm font-medium">
                {status === "active" && "You are on duty"}
                {status === "starting" && "Connecting…"}
                {status === "denied" && "Location permission needed"}
                {status === "error" && "Location unavailable"}
              </p>
              <p className="text-xs text-muted-foreground">
                {status === "active" && lastSent
                  ? `Last update ${lastSent.toLocaleTimeString("en-IN")} · ${fixCount} sent`
                  : status === "denied"
                  ? "Please allow location access."
                  : "Keep this screen open."}
              </p>
            </div>
          </div>

          <Button variant="ghost" size="sm" onClick={logout} className="text-muted-foreground">
            <LogOut className="w-4 h-4 mr-2" /> Sign out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
