import { useState, useEffect, useRef, useCallback } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { MapPin, Battery, RefreshCw, Route, Clock, Navigation } from "lucide-react";

const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

// Load Leaflet from CDN once (no API key, OpenStreetMap tiles).
function loadLeaflet() {
  return new Promise((resolve, reject) => {
    if (window.L) return resolve(window.L);
    if (!document.querySelector(`link[href="${LEAFLET_CSS}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = LEAFLET_CSS;
      document.head.appendChild(link);
    }
    let script = document.querySelector(`script[src="${LEAFLET_JS}"]`);
    if (script) {
      script.addEventListener("load", () => resolve(window.L));
      script.addEventListener("error", reject);
      return;
    }
    script = document.createElement("script");
    script.src = LEAFLET_JS;
    script.onload = () => resolve(window.L);
    script.onerror = reject;
    document.body.appendChild(script);
  });
}

function timeAgo(iso) {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const todayIST = () => {
  const now = new Date();
  const ist = new Date(now.getTime() + (330 + now.getTimezoneOffset()) * 60000);
  return ist.toISOString().slice(0, 10);
};

export default function FieldTracking() {
  const [execs, setExecs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [date, setDate] = useState(todayIST());
  const [history, setHistory] = useState(null);
  const [stays, setStays] = useState([]);
  const [live, setLive] = useState(true);
  const [leafletReady, setLeafletReady] = useState(false);

  const mapRef = useRef(null);
  const mapObj = useRef(null);
  const layerRef = useRef(null);
  const liveMarkers = useRef({});

  // Init Leaflet map
  useEffect(() => {
    let cancelled = false;
    loadLeaflet()
      .then((L) => {
        if (cancelled || mapObj.current || !mapRef.current) return;
        const map = L.map(mapRef.current).setView([21.1458, 79.0882], 12); // Nagpur default
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap",
          maxZoom: 19,
        }).addTo(map);
        mapObj.current = map;
        layerRef.current = L.layerGroup().addTo(map);
        setLeafletReady(true);
      })
      .catch(() => toast.error("Could not load map library (needs internet)."));
    return () => {
      cancelled = true;
    };
  }, []);

  const loadExecs = useCallback(async () => {
    try {
      const res = await api.get("/location/executives");
      setExecs(res.data || []);
    } catch {
      toast.error("Failed to load executives");
    }
  }, []);

  useEffect(() => {
    loadExecs();
  }, [loadExecs]);

  // Live polling of everyone's latest fix
  useEffect(() => {
    if (!live) return;
    const t = setInterval(loadExecs, 15000);
    return () => clearInterval(t);
  }, [live, loadExecs]);

  // Draw live markers for all executives
  useEffect(() => {
    if (!leafletReady || !mapObj.current) return;
    const L = window.L;
    Object.values(liveMarkers.current).forEach((m) => mapObj.current.removeLayer(m));
    liveMarkers.current = {};
    execs.forEach((e) => {
      const f = e.last_fix;
      if (!f) return;
      const stale = f.ts && (Date.now() - new Date(f.ts).getTime()) > 5 * 60000;
      const marker = L.circleMarker([f.lat, f.lng], {
        radius: 9,
        color: "#fff",
        weight: 2,
        fillColor: stale ? "#f59e0b" : "#10b981",
        fillOpacity: 1,
      }).bindPopup(
        `<b>${e.name}</b><br/>${timeAgo(f.ts)}${f.battery != null ? ` · 🔋${f.battery}%` : ""}`
      );
      marker.addTo(mapObj.current);
      liveMarkers.current[e.id] = marker;
    });
  }, [execs, leafletReady]);

  const loadHistory = useCallback(
    async (execId, d) => {
      if (!execId) return;
      try {
        const [h, s] = await Promise.all([
          api.get(`/location/history/${execId}?date=${d}`),
          api.get(`/location/staypoints/${execId}?date=${d}`),
        ]);
        setHistory(h.data);
        setStays(s.data.stay_points || []);
        drawTrack(h.data, s.data.stay_points || []);
      } catch {
        toast.error("Failed to load track");
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const drawTrack = (h, staysList) => {
    if (!leafletReady || !mapObj.current || !window.L) return;
    const L = window.L;
    layerRef.current.clearLayers();
    const pts = (h.points || []).map((p) => [p.lat, p.lng]);
    if (pts.length) {
      const line = L.polyline(pts, { color: "#3b82f6", weight: 3, opacity: 0.8 });
      layerRef.current.addLayer(line);
      layerRef.current.addLayer(
        L.marker(pts[0]).bindPopup("Start of day")
      );
      layerRef.current.addLayer(
        L.marker(pts[pts.length - 1]).bindPopup("Latest position")
      );
      mapObj.current.fitBounds(line.getBounds(), { padding: [40, 40] });
    }
    staysList.forEach((s) => {
      layerRef.current.addLayer(
        L.circle([s.lat, s.lng], {
          radius: Math.max(40, Math.min(200, s.duration_min * 2)),
          color: "#ef4444",
          fillColor: "#ef4444",
          fillOpacity: 0.25,
        }).bindPopup(
          `Stayed <b>${s.duration_min} min</b><br/>${new Date(s.arrival).toLocaleTimeString("en-IN")} → ${new Date(
            s.departure
          ).toLocaleTimeString("en-IN")}`
        )
      );
    });
  };

  const selectExec = (e) => {
    setSelected(e);
    loadHistory(e.id, date);
  };

  useEffect(() => {
    if (selected) loadHistory(selected.id, date);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  return (
    <div className="space-y-4" data-testid="field-tracking">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Navigation className="w-6 h-6" /> Field Tracking
        </h1>
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={date}
            max={todayIST()}
            onChange={(e) => setDate(e.target.value)}
            className="w-auto"
          />
          <Button
            variant={live ? "default" : "outline"}
            size="sm"
            onClick={() => setLive((v) => !v)}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${live ? "animate-spin" : ""}`} />
            {live ? "Live" : "Paused"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Executives list */}
        <Card className="lg:col-span-1">
          <CardContent className="p-3 space-y-2 max-h-[70vh] overflow-y-auto">
            {execs.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-6">
                No field executives yet. Create one in Users.
              </p>
            )}
            {execs.map((e) => {
              const f = e.last_fix;
              const stale = f?.ts && Date.now() - new Date(f.ts).getTime() > 5 * 60000;
              return (
                <button
                  key={e.id}
                  onClick={() => selectExec(e)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${
                    selected?.id === e.id ? "border-primary bg-accent" : "border-border hover:bg-accent/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{e.name}</span>
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${
                        !f ? "bg-muted-foreground" : stale ? "bg-amber-500" : "bg-emerald-500"
                      }`}
                    />
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" /> {f ? timeAgo(f.ts) : "no data"}
                    </span>
                    {f?.battery != null && (
                      <span className="flex items-center gap-1">
                        <Battery className="w-3 h-3" /> {f.battery}%
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </CardContent>
        </Card>

        {/* Map + stats */}
        <div className="lg:col-span-3 space-y-4">
          <Card>
            <CardContent className="p-0">
              <div ref={mapRef} style={{ height: "60vh", width: "100%", borderRadius: "0.75rem" }} />
            </CardContent>
          </Card>

          {selected && history && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardContent className="pt-5">
                  <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-wider">
                    <Route className="w-4 h-4" /> Distance
                  </div>
                  <p className="text-2xl font-bold mt-1">{history.distance_km} km</p>
                  <p className="text-xs text-muted-foreground">{history.count} location fixes</p>
                </CardContent>
              </Card>
              <Card className="md:col-span-2">
                <CardContent className="pt-5">
                  <div className="flex items-center gap-2 text-muted-foreground text-xs uppercase tracking-wider mb-2">
                    <Clock className="w-4 h-4" /> Where they stayed most
                  </div>
                  {stays.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No significant stops.</p>
                  ) : (
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {stays.slice(0, 8).map((s, i) => (
                        <div key={i} className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">
                            {new Date(s.arrival).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                            {" – "}
                            {new Date(s.departure).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                          <Badge variant="secondary">{s.duration_min} min</Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
