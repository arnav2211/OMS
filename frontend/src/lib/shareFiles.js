// Share order photos / slips to WhatsApp etc. through the phone's share sheet.
//
// Phones only allow navigator.share() for a few seconds after the tap. Downloading many photos
// first used that time up, so the share was refused ("Share failed"). Files are now fetched once,
// kept in memory, and prefetched when the order opens, so the tap shares at once. If the browser
// still refuses, the files are ready and the next tap shares immediately.

const BASE = process.env.REACT_APP_BACKEND_URL || "";
const cache = new Map();   // url -> Promise<Blob>

function fetchBlob(url) {
  if (!cache.has(url)) {
    const p = fetch(url.startsWith("http") ? url : `${BASE}${url}`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
      .catch((e) => { cache.delete(url); throw e; });
    cache.set(url, p);
  }
  return cache.get(url);
}

export function prefetchFiles(urls) {
  (urls || []).forEach((u) => { if (u) fetchBlob(u).catch(() => {}); });
}

function extFor(type) {
  const t = type || "";
  return t.includes("pdf") ? "pdf" : t.includes("png") ? "png" : t.includes("webp") ? "webp" : "jpg";
}

function download(files) {
  files.forEach((file) => {
    const url = URL.createObjectURL(file);
    const a = document.createElement("a");
    a.href = url; a.download = file.name;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  });
}

/**
 * items: [{ url, name }] (name without extension). Returns "shared" | "downloaded" | "retry" | "cancelled".
 * toast: the sonner toast object. phone: optional customer phone for the WhatsApp fallback.
 */
export async function shareFiles({ items, title, toast, phone }) {
  if (!items?.length) return "none";
  const blobs = await Promise.allSettled(items.map((it) => fetchBlob(it.url)));
  const files = [];
  blobs.forEach((b, i) => {
    if (b.status !== "fulfilled") return;
    const type = b.value.type || "image/jpeg";
    files.push(new File([b.value], `${items[i].name}.${extFor(type)}`, { type }));
  });
  const failed = items.length - files.length;
  if (!files.length) { toast.error("Could not load the files - check the internet and try again"); return "error"; }
  if (failed) toast.warning(`${failed} file(s) could not load and were left out`);

  if (navigator.canShare && navigator.canShare({ files })) {
    try {
      await navigator.share({ files, title });
      return "shared";
    } catch (err) {
      if (err?.name === "AbortError") return "cancelled";
      if (err?.name === "NotAllowedError") {
        // The tap "expired" while the files loaded. They are cached now: the next tap is instant.
        toast.info("Files are ready - tap Share again", { duration: 6000 });
        return "retry";
      }
      // Some phones refuse very large batches: share in groups of 10 instead.
      if (files.length > 10) {
        try {
          await navigator.share({ files: files.slice(0, 10), title });
          toast.info(`Shared the first 10. Downloading the other ${files.length - 10}...`);
          download(files.slice(10));
          return "shared";
        } catch (e2) {
          if (e2?.name === "AbortError") return "cancelled";
        }
      }
    }
  }
  download(files);
  toast.success(`${files.length} file(s) downloaded${phone ? ". Opening WhatsApp..." : ""}`);
  if (phone) {
    const clean = String(phone).replace(/[^0-9]/g, "");
    const waPhone = clean.startsWith("91") ? clean : `91${clean}`;
    setTimeout(() => window.open(`https://wa.me/${waPhone}`, "_blank"), 500);
  }
  return "downloaded";
}
