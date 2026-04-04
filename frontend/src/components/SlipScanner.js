import { useState, useRef, useEffect, useCallback } from "react";
import ReactCrop from "react-image-crop";
import "react-image-crop/dist/ReactCrop.css";
import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Upload, Camera, X, ScanBarcode, Loader2, Crop, Check } from "lucide-react";

function getCroppedBlob(imgEl, crop) {
  return new Promise((resolve) => {
    const canvas = document.createElement("canvas");
    const scaleX = imgEl.naturalWidth / imgEl.width;
    const scaleY = imgEl.naturalHeight / imgEl.height;
    canvas.width = crop.width * scaleX;
    canvas.height = crop.height * scaleY;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(imgEl, crop.x * scaleX, crop.y * scaleY, crop.width * scaleX, crop.height * scaleY, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.92);
  });
}

export function SlipScanner({ onBarcodeDetected, slipImages, onSlipImagesChange }) {
  const [uploading, setUploading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [scanning, setScanning] = useState(false);
  // Crop state
  const [cropSrc, setCropSrc] = useState(null);
  const [crop, setCrop] = useState(undefined);
  const [originalFile, setOriginalFile] = useState(null);
  const cropImgRef = useRef(null);

  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const scanIntervalRef = useRef(null);
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  const stopCamera = useCallback(() => {
    if (scanIntervalRef.current) { clearInterval(scanIntervalRef.current); scanIntervalRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (videoRef.current) { videoRef.current.srcObject = null; }
    setCameraActive(false);
    setScanning(false);
  }, []);

  useEffect(() => { return () => stopCamera(); }, [stopCamera]);

  useEffect(() => {
    if (cameraActive && streamRef.current && videoRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [cameraActive]);

  // --- Upload & Scan ---
  const uploadAndScan = async (file) => {
    setUploading(true);
    try {
      const compressed = await compressImage(file);
      const formData = new FormData();
      formData.append("file", compressed);
      const uploadRes = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
      onSlipImagesChange([...(slipImages || []), uploadRes.data.url]);

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

  // --- File / Camera selection → open crop ---
  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOriginalFile(file);
    setCropSrc(URL.createObjectURL(file));
    setCrop(undefined);
    e.target.value = "";
  };

  // --- Crop confirm ---
  const handleCropConfirm = async () => {
    if (!cropImgRef.current) return;
    let fileToUpload = originalFile;
    if (crop && crop.width > 0 && crop.height > 0) {
      const blob = await getCroppedBlob(cropImgRef.current, crop);
      if (blob) fileToUpload = new File([blob], originalFile.name, { type: "image/jpeg" });
    }
    setCropSrc(null);
    setCrop(undefined);
    setOriginalFile(null);
    await uploadAndScan(fileToUpload);
  };

  const handleCropCancel = () => {
    if (cropSrc) URL.revokeObjectURL(cropSrc);
    setCropSrc(null);
    setCrop(undefined);
    setOriginalFile(null);
  };

  // --- Live barcode scan ---
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      streamRef.current = stream;
      setCameraActive(true);
      setScanning(true);
      scanIntervalRef.current = setInterval(() => captureAndScan(), 1500);
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
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob(async (blob) => {
      if (!blob || blob.size < 100) return;
      const fd = new FormData();
      fd.append("file", blob, "scan.jpg");
      try {
        const res = await api.post("/scan-barcode", fd, { headers: { "Content-Type": "multipart/form-data" } });
        if (res.data.found && res.data.code) {
          onBarcodeDetected(res.data.code);
          toast.success(`Barcode scanned: ${res.data.code}`);
          stopCamera();
        }
      } catch {}
    }, "image/jpeg", 0.8);
  };

  const removeSlip = (idx) => { onSlipImagesChange(slipImages.filter((_, i) => i !== idx)); };

  // --- Crop UI (shown as overlay) ---
  if (cropSrc) {
    return (
      <div className="space-y-3" data-testid="slip-crop-ui">
        <p className="text-sm font-medium">Crop the slip image (optional)</p>
        <div className="rounded-lg border overflow-hidden bg-black/5">
          <ReactCrop crop={crop} onChange={(c) => setCrop(c)} keepSelection>
            <img
              ref={cropImgRef}
              src={cropSrc}
              alt="Crop preview"
              style={{ maxHeight: 350, width: "100%", objectFit: "contain" }}
              onLoad={() => {}}
            />
          </ReactCrop>
        </div>
        <div className="flex gap-2">
          <Button type="button" size="sm" onClick={handleCropConfirm} disabled={uploading} data-testid="crop-confirm-btn">
            {uploading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Check className="w-4 h-4 mr-1" />}
            {crop && crop.width > 0 ? "Crop & Upload" : "Upload Without Crop"}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={handleCropCancel} data-testid="crop-cancel-btn">
            <X className="w-4 h-4 mr-1" /> Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleFileSelect} />
        <input type="file" ref={cameraInputRef} className="hidden" accept="image/*" capture="environment" onChange={handleFileSelect} />
        <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploading} data-testid="upload-slip-btn">
          {uploading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Upload className="w-4 h-4 mr-1" />}
          Upload Slip
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => cameraInputRef.current?.click()} disabled={uploading} data-testid="camera-slip-btn">
          <Camera className="w-4 h-4 mr-1" /> Camera
        </Button>
        {!cameraActive ? (
          <Button type="button" variant="outline" size="sm" onClick={startCamera} data-testid="scan-barcode-btn">
            <ScanBarcode className="w-4 h-4 mr-1" /> Scan Barcode
          </Button>
        ) : (
          <Button type="button" variant="destructive" size="sm" onClick={stopCamera} data-testid="stop-scan-btn">
            <X className="w-4 h-4 mr-1" /> Stop Scan
          </Button>
        )}
      </div>

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

      {slipImages?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {slipImages.map((url, i) => (
            <div key={i} className="relative w-16 h-16 rounded border overflow-hidden group">
              <img src={`${backendUrl}${url}`} alt={`Slip ${i + 1}`} className="w-full h-full object-cover" />
              <button type="button" className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity" onClick={() => removeSlip(i)}>
                <X className="w-4 h-4 text-white" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
