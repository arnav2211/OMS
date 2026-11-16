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

export async function compressImage(file) {
  if (!file?.type?.startsWith("image/")) return file;   // PDFs etc. go as they are
  if (file.size < 150 * 1024) return file;              // already small
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
