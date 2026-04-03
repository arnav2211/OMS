import { useState, useRef, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Upload, Camera, X, ScanBarcode, Loader2 } from "lucide-react";

export function SlipScanner({ onBarcodeDetected, slipImages, onSlipImagesChange }) {
  const [uploading, setUploading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [scanning, setScanning] = useState(false);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const scanIntervalRef = useRef(null);
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const stopCamera = useCallback(() => {
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
      scanIntervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
    setScanning(false);
  }, []);

  useEffect(() => {
    return () => stopCamera();
  }, [stopCamera]);

  // When cameraActive turns true, connect the stream to the video element
  useEffect(() => {
    if (cameraActive && streamRef.current && videoRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [cameraActive]);

  const uploadAndScan = async (file) => {
    setUploading(true);
    try {
      const compressed = await compressImage(file);
      const formData = new FormData();
      formData.append("file", compressed);
      const uploadRes = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
      onSlipImagesChange([...(slipImages || []), uploadRes.data.url]);

      // Try barcode scan on the original image
      const scanForm = new FormData();
      scanForm.append("file", file);
      const scanRes = await api.post("/scan-barcode", scanForm, { headers: { "Content-Type": "multipart/form-data" } });
      if (scanRes.data.found && scanRes.data.code) {
        onBarcodeDetected(scanRes.data.code);
        toast.success(`Barcode detected: ${scanRes.data.code}`);
      } else {
        toast.info("No barcode found on slip. Enter LR No. manually.");
      }
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadAndScan(file);
    e.target.value = "";
  };

  const handleCameraCapture = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadAndScan(file);
    e.target.value = "";
  };

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      streamRef.current = stream;
      // Set cameraActive first so video element renders, then useEffect connects the stream
      setCameraActive(true);
      setScanning(true);

      scanIntervalRef.current = setInterval(() => {
        captureAndScan();
      }, 1500);
    } catch {
      toast.error("Could not access camera");
      setCameraActive(false);
    }
  };

  const captureAndScan = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    if (video.videoWidth === 0 || video.videoHeight === 0) return;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);
    canvas.toBlob(async (blob) => {
      if (!blob || blob.size < 100) return;
      const formData = new FormData();
      formData.append("file", blob, "scan.jpg");
      try {
        const res = await api.post("/scan-barcode", formData, { headers: { "Content-Type": "multipart/form-data" } });
        if (res.data.found && res.data.code) {
          onBarcodeDetected(res.data.code);
          toast.success(`Barcode scanned: ${res.data.code}`);
          stopCamera();
        }
      } catch { /* silently retry */ }
    }, "image/jpeg", 0.8);
  };

  const removeSlip = (idx) => {
    onSlipImagesChange(slipImages.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleFileUpload} />
        <input type="file" ref={cameraInputRef} className="hidden" accept="image/*" capture="environment" onChange={handleCameraCapture} />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          data-testid="upload-slip-btn"
        >
          {uploading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Upload className="w-4 h-4 mr-1" />}
          Upload Slip
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => cameraInputRef.current?.click()}
          disabled={uploading}
          data-testid="camera-slip-btn"
        >
          <Camera className="w-4 h-4 mr-1" /> Camera
        </Button>
        {!cameraActive ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={startCamera}
            data-testid="scan-barcode-btn"
          >
            <ScanBarcode className="w-4 h-4 mr-1" /> Scan Barcode
          </Button>
        ) : (
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={stopCamera}
            data-testid="stop-scan-btn"
          >
            <X className="w-4 h-4 mr-1" /> Stop Scan
          </Button>
        )}
      </div>

      {/* Camera preview for barcode scanning */}
      {cameraActive && (
        <div className="relative rounded-lg overflow-hidden border bg-black" data-testid="camera-preview">
          <video ref={videoRef} className="w-full max-h-48 object-cover" playsInline muted autoPlay />
          <canvas ref={canvasRef} className="hidden" />
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-3/4 h-1/2 border-2 border-dashed border-green-400 rounded-lg opacity-70" />
          </div>
          {scanning && (
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-black/70 text-white text-xs px-3 py-1 rounded-full flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 animate-spin" /> Scanning...
            </div>
          )}
        </div>
      )}

      {/* Uploaded slip images */}
      {slipImages?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {slipImages.map((url, i) => (
            <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
              <img src={`${backendUrl}${url}`} alt={`Slip ${i + 1}`} className="w-full h-full object-cover" />
              <button
                type="button"
                className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity"
                onClick={() => removeSlip(i)}
              >
                <X className="w-4 h-4 text-white" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
