import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { Camera, X, RefreshCw } from "lucide-react";

/**
 * In-app camera for packing photos. It takes a ~1280px frame straight from the live video, so an
 * old phone never has to open its camera app, save a 12 MP photo, then decode and shrink it.
 * Stays open for several shots in a row; each shot is handed to onShot(file) at once.
 * If the browser has no camera access, onUnavailable() is called so the page can fall back.
 */
export default function QuickCamera({ open, title, onShot, onClose, onUnavailable }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [count, setCount] = useState(0);
  const [flash, setFlash] = useState(false);
  const [facing, setFacing] = useState("environment");

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setReady(false);
    setCount(0);
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("no camera api");
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 960 } },
        });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        const v = videoRef.current;
        if (v) {
          v.srcObject = stream;
          v.setAttribute("playsinline", "true");     // iPhone: keep it inline, not full screen
          await v.play().catch(() => {});
          setReady(true);
        }
      } catch {
        if (!cancelled) onUnavailable?.();
      }
    })();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, facing]);

  const shoot = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const scale = Math.min(1, 1280 / Math.max(v.videoWidth, v.videoHeight));
    const w = Math.round(v.videoWidth * scale);
    const h = Math.round(v.videoHeight * scale);
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    c.getContext("2d").drawImage(v, 0, 0, w, h);
    setFlash(true);
    setTimeout(() => setFlash(false), 120);
    c.toBlob((blob) => {
      if (!blob) return;
      onShot(new File([blob], `photo-${Date.now()}.jpg`, { type: "image/jpeg", lastModified: Date.now() }));
      setCount((n) => n + 1);
    }, "image/jpeg", 0.75);
  };

  if (!open) return null;
  // Portal to <body>: a parent dialog's transform would otherwise squeeze this into the dialog box.
  return createPortal(
    <div className="fixed inset-0 z-[100] bg-black flex flex-col" style={{ pointerEvents: "auto" }} data-testid="quick-camera">
      <div className="flex items-center justify-between px-3 py-2 text-white text-sm">
        <span className="truncate">{title || "Photo"}{count ? ` · ${count} taken` : ""}</span>
        <div className="flex items-center gap-2">
          <button onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))} className="p-2" title="Switch camera">
            <RefreshCw className="w-5 h-5" />
          </button>
          <button onClick={onClose} className="p-2" title="Close" data-testid="quick-camera-close">
            <X className="w-6 h-6" />
          </button>
        </div>
      </div>
      <div className="relative flex-1 overflow-hidden">
        <video ref={videoRef} muted playsInline autoPlay className="absolute inset-0 w-full h-full object-contain" />
        {flash && <div className="absolute inset-0 bg-white/70" />}
        {!ready && <div className="absolute inset-0 flex items-center justify-center text-white/80 text-sm">Starting camera...</div>}
      </div>
      <div className="flex items-center justify-center gap-6 py-5">
        <Button variant="secondary" onClick={onClose} data-testid="quick-camera-done">Done</Button>
        <button onClick={shoot} disabled={!ready} data-testid="quick-camera-shoot"
          className="w-16 h-16 rounded-full bg-white border-4 border-white/40 active:scale-95 disabled:opacity-40 flex items-center justify-center">
          <Camera className="w-7 h-7 text-black" />
        </button>
        <span className="w-[64px]" />
      </div>
    </div>,
    document.body,
  );
}
