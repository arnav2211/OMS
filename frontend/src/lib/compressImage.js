// Image compression before upload: a 3-8 MB camera photo becomes ~50-120 KB.
// Max side 1280px, JPEG quality 0.7.
//
// Fast path: createImageBitmap decodes straight to the target size in native code (no base64
// data URL, no full-size decode in JS), which on the packing team's low-end Android phones is
// several times quicker than the old FileReader -> <img> -> canvas route.

const MAX_SIDE = 1280;
const QUALITY = 0.7;

function toJpegFile(canvas, name) {
  return new Promise((resolve) => {
    canvas.toBlob(
      (blob) => resolve(blob ? new File([blob], (name || "photo").replace(/\.[^.]+$/, "") + ".jpg",
        { type: "image/jpeg", lastModified: Date.now() }) : null),
      "image/jpeg",
      QUALITY,
    );
  });
}

function fit(w, h) {
  const r = Math.min(1, MAX_SIDE / Math.max(w, h));
  return [Math.max(1, Math.round(w * r)), Math.max(1, Math.round(h * r))];
}

async function viaBitmap(file) {
  // one native decode, scaled on the way in (height follows the aspect ratio)
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image", resizeWidth: MAX_SIDE, resizeQuality: "medium" });
  const [w, h] = fit(bmp.width, bmp.height);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  canvas.getContext("2d").drawImage(bmp, 0, 0, w, h);
  bmp.close?.();
  return toJpegFile(canvas, file.name);
}

function viaImage(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);           // no base64 copy of the photo
    const img = new Image();
    img.onload = async () => {
      const [w, h] = fit(img.naturalWidth, img.naturalHeight);
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      resolve(await toJpegFile(canvas, file.name));
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    img.src = url;
  });
}

// Background-thread path: decode, scale and encode in a Web Worker so the page never freezes
// on an old phone while a photo is being shrunk.
const WORKER_SRC = `
self.onmessage = async (e) => {
  const { id, file, max, q } = e.data;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image", resizeWidth: max, resizeQuality: "medium" });
    const r = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const w = Math.max(1, Math.round(bmp.width * r)), h = Math.max(1, Math.round(bmp.height * r));
    const c = new OffscreenCanvas(w, h);
    c.getContext("2d").drawImage(bmp, 0, 0, w, h);
    bmp.close && bmp.close();
    const blob = await c.convertToBlob({ type: "image/jpeg", quality: q });
    self.postMessage({ id, blob });
  } catch (err) {
    self.postMessage({ id, blob: null });
  }
};`;

let worker = null;
let seq = 0;
const waiting = new Map();

function getWorker() {
  if (worker !== null) return worker;
  try {
    if (typeof Worker === "undefined" || typeof OffscreenCanvas === "undefined" || typeof createImageBitmap !== "function") {
      worker = false;
      return worker;
    }
    worker = new Worker(URL.createObjectURL(new Blob([WORKER_SRC], { type: "text/javascript" })));
    worker.onmessage = (e) => {
      const done = waiting.get(e.data.id);
      if (done) { waiting.delete(e.data.id); done(e.data.blob); }
    };
    worker.onerror = () => { worker = false; waiting.forEach((d) => d(null)); waiting.clear(); };
  } catch {
    worker = false;
  }
  return worker;
}

function viaWorker(file) {
  const w = getWorker();
  if (!w) return Promise.resolve(null);
  return new Promise((resolve) => {
    const id = ++seq;
    const timer = setTimeout(() => { waiting.delete(id); resolve(null); }, 20000);
    waiting.set(id, (blob) => {
      clearTimeout(timer);
      resolve(blob ? new File([blob], (file.name || "photo").replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg", lastModified: Date.now() }) : null);
    });
    w.postMessage({ id, file, max: MAX_SIDE, q: QUALITY });
  });
}

export async function compressImage(file) {
  if (!file?.type?.startsWith("image/")) return file;   // PDFs etc. go as they are
  if (file.size < 150 * 1024) return file;              // already small (e.g. in-app camera shots)
  try {
    const out = await viaWorker(file);
    if (out) return out;
  } catch { /* fall back to the page thread */ }
  try {
    if (typeof createImageBitmap === "function") {
      const out = await viaBitmap(file);
      if (out) return out;
    }
  } catch { /* older browser or odd format: fall through */ }
  try {
    const out = await viaImage(file);
    if (out && out.size < file.size) return out;
  } catch { /* keep the original */ }
  return file;
}
