import api from "@/lib/api";
import { compressImage } from "@/lib/compressImage";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Compress and upload one photo, retrying on a weak connection.
 * Returns the server URL ("/api/uploads/...") or throws after the last try.
 */
export async function uploadImage(file, { tries = 4 } = {}) {
  const small = await compressImage(file);
  let lastErr;
  for (let i = 0; i < tries; i++) {
    const fd = new FormData();
    fd.append("file", small);
    try {
      const res = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 45000 });
      return res.data.url;
    } catch (e) {
      lastErr = e;
      if (e.response && e.response.status < 500 && e.response.status !== 408) break;   // a real refusal: don't retry
      await sleep(1500 * (i + 1));
    }
  }
  throw lastErr;
}
