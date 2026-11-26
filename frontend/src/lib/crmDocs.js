import axios from "axios";

// Product Documents live in the CRM (one library for the CRM and the OMS).
// The OMS media team / OMS admin use it from here with their OMS login: the CRM
// accepts an OMS login for the documents API only.
const CRM_URL = (process.env.REACT_APP_CRM_URL || "https://crm.mangalamagro.in").replace(/\/$/, "");

export const crm = axios.create({ baseURL: `${CRM_URL}/api` });
crm.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function errMsg(e, fallback = "Something went wrong") {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && d.message) return d.message;
  return fallback;
}

// View / download through a short-lived signed link from the CRM.
export async function openDoc(id, { download = false } = {}) {
  const w = window.open("", "_blank");
  try {
    const { data } = await crm.post(`/docs/documents/${id}/link`, null, { params: { download } });
    const url = data.abs_url || `${CRM_URL}${data.url}`;
    if (w) w.location.href = url; else window.location.href = url;
  } catch (e) {
    if (w) w.close();
    throw e;
  }
}

export function openBlob(blob, downloadName) {
  const url = URL.createObjectURL(blob);
  if (downloadName) {
    const a = document.createElement("a");
    a.href = url; a.download = downloadName;
    document.body.appendChild(a); a.click(); a.remove();
  } else {
    window.open(url, "_blank", "noopener");
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export const KIND_ORDER = ["coa", "gcms", "tds", "msds", "ifra", "spec", "other"];
export const KIND_COLORS = {
  coa: "bg-[#002FA7] text-white", gcms: "bg-[#7C3AED] text-white", tds: "bg-[#0F766E] text-white",
  msds: "bg-[#B45309] text-white", ifra: "bg-[#BE185D] text-white", spec: "bg-gray-700 text-white", other: "bg-muted text-foreground",
};
