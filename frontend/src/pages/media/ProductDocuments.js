import React, { useCallback, useEffect, useRef, useState } from "react";
import { Copy, Download, Eye, FileText, FlaskConical, Lock, Pencil, Plus, Search, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { crm as api, errMsg } from "@/lib/crmDocs";
import { openDoc, KIND_ORDER, KIND_COLORS } from "@/lib/crmDocs";
import CoaMaker from "@/components/CoaMaker";

/* Product Documents: one page per oil with its COAs, GCMS, TDS, MSDS ...
   Everyone can search, view and download; the admin and the media team can add,
   edit and delete. Documents marked "Only system admin" are hidden from others. */

const inp = "border border-input px-2 py-1.5 text-sm outline-none focus:border-[#002FA7]";

export default function ProductDocuments() {
  const [meta, setMeta] = useState({ kinds: {}, can_edit: false, is_admin: false });
  const [q, setQ] = useState("");
  const [products, setProducts] = useState([]);
  const [allProducts, setAllProducts] = useState([]);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [maker, setMaker] = useState(null);       // {existing?, duplicateOf?}
  const [upload, setUpload] = useState(false);
  const [newOil, setNewOil] = useState(false);

  const loadProducts = useCallback(async (query) => {
    try {
      const { data } = await api.get("/docs/products", { params: { q: query || "" } });
      setProducts(data.products || []);
      if (!query) setAllProducts(data.products || []);
    } catch (e) { toast.error(errMsg(e, "Could not load documents")); }
  }, []);

  const loadDetail = useCallback(async (pid) => {
    if (!pid) { setDetail(null); return; }
    try {
      const { data } = await api.get(`/docs/products/${pid}`);
      setDetail(data);
    } catch (e) { toast.error(errMsg(e, "Could not load")); }
  }, []);

  useEffect(() => {
    api.get("/docs/meta").then(({ data }) => setMeta(data)).catch(() => {});
    loadProducts("");
  }, [loadProducts]);
  useEffect(() => { const t = setTimeout(() => loadProducts(q), 250); return () => clearTimeout(t); }, [q, loadProducts]);
  useEffect(() => { loadDetail(sel); }, [sel, loadDetail]);

  const refresh = (pid) => { loadProducts(q); loadProducts(""); if (pid) { setSel(pid); loadDetail(pid); } };

  const del = async (d) => {
    if (!window.confirm(`Delete "${d.title}"?`)) return;
    try { await api.delete(`/docs/documents/${d.id}`); toast.success("Deleted"); refresh(sel); }
    catch (e) { toast.error(errMsg(e, "Delete failed")); }
  };

  const docs = detail?.documents || [];
  const grouped = KIND_ORDER.map((k) => [k, docs.filter((d) => (d.kind || "other") === k)]).filter(([, l]) => l.length);

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col md:flex-row min-h-0 border border-border rounded-lg overflow-hidden bg-card" data-testid="documents-page">
      {/* Oils */}
      <div className={`md:w-80 border-r border-border flex flex-col min-h-0 ${sel ? "hidden md:flex" : "flex"} flex-1 md:flex-none`}>
        <div className="p-3 border-b border-border space-y-2">
          <div className="relative">
            <Search size={14} className="absolute left-2 top-2.5 text-muted-foreground" />
            <input className={`${inp} w-full pl-7`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search oil (e.g. lemongrass)" data-testid="docs-search" />
          </div>
          {meta.can_edit && (
            <div className="flex gap-2">
              <button onClick={() => setNewOil(true)} className="flex-1 border border-input px-2 py-1.5 text-[10px] font-bold uppercase tracking-widest hover:bg-muted flex items-center justify-center gap-1"><Plus size={12} /> Oil</button>
              <button onClick={() => setMaker({})} className="flex-1 bg-[#002FA7] text-white px-2 py-1.5 text-[10px] font-bold uppercase tracking-widest flex items-center justify-center gap-1" data-testid="new-coa"><FlaskConical size={12} /> COA maker</button>
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {products.map((p) => (
            <button key={p.id} onClick={() => setSel(p.id)}
              className={`w-full text-left px-3 py-2 border-b border-border/60 hover:bg-muted ${sel === p.id ? "bg-primary/10" : ""}`}>
              <div className="font-bold text-sm">{p.name}</div>
              <div className="flex flex-wrap gap-1 mt-0.5">
                {KIND_ORDER.filter((k) => p.counts?.[k]).map((k) => (
                  <span key={k} className={`text-[9px] px-1.5 py-0.5 font-bold uppercase ${KIND_COLORS[k]}`}>{meta.kinds[k] || k} {p.counts[k] > 1 ? `×${p.counts[k]}` : ""}</span>
                ))}
                {!p.total && <span className="text-[10px] text-muted-foreground">No documents yet</span>}
              </div>
            </button>
          ))}
          {!products.length && <div className="p-6 text-center text-sm text-muted-foreground">{q ? "No oil matches" : "No oils yet"}</div>}
        </div>
      </div>

      {/* Documents of one oil */}
      <div className={`flex-1 min-w-0 overflow-y-auto ${sel ? "block" : "hidden md:block"}`}>
        {!detail ? (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground p-6">Search and pick an oil to see its documents.</div>
        ) : (
          <div className="p-4 md:p-6 max-w-4xl">
            <button onClick={() => setSel(null)} className="md:hidden text-xs text-muted-foreground mb-2">← All oils</button>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <div>
                <h1 className="font-black text-2xl">{detail.product.name}</h1>
                {detail.product.aliases?.length > 0 && <div className="text-xs text-muted-foreground">Also: {detail.product.aliases.join(", ")}</div>}
              </div>
              {meta.can_edit && (
                <div className="flex gap-2">
                  <button onClick={() => setUpload(true)} className="border border-input px-3 py-2 text-[10px] font-bold uppercase tracking-widest hover:bg-muted flex items-center gap-1"><Upload size={12} /> Upload (GCMS, TDS…)</button>
                  <button onClick={() => setMaker({})} className="bg-[#002FA7] text-white px-3 py-2 text-[10px] font-bold uppercase tracking-widest flex items-center gap-1"><FlaskConical size={12} /> New COA</button>
                </div>
              )}
            </div>
            {!grouped.length && <div className="text-sm text-muted-foreground border border-dashed border-input p-6 text-center">No documents for this oil yet.</div>}
            {grouped.map(([k, list]) => (
              <div key={k} className="mb-5">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mb-1">{meta.kinds[k] || k}</div>
                <div className="border border-border divide-y divide-border">
                  {list.map((d) => (
                    <div key={d.id} className="px-3 py-2 flex flex-wrap items-center gap-2">
                      <FileText size={20} className="text-[#E60000] shrink-0" />
                      <div className="flex-1 min-w-[180px]">
                        <div className="font-bold text-sm flex items-center gap-1">
                          {d.title}
                          {d.visibility === "admin" && <span className="text-[9px] bg-gray-900 text-white px-1.5 py-0.5 flex items-center gap-0.5"><Lock size={9} /> ADMIN ONLY</span>}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {d.source === "coa"
                            ? `Made in CRM · ${d.coa?.date_mode === "locked" ? "dates locked" : "dates change monthly"}${d.current_dates?.[0] ? ` · now: ${d.current_dates[0]}${d.current_dates[1] ? ` – ${d.current_dates[1]}` : ""}` : ""}${d.coa?.letterhead === false ? " · no letterhead" : ""}`
                            : `Uploaded file · ${d.filename || ""}`}
                          {d.created_by_name ? ` · by ${d.created_by_name}` : ""}
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <button onClick={() => openDoc(d.id).catch((e) => toast.error(errMsg(e, "Could not open")))} className="p-1.5 text-muted-foreground hover:bg-muted" title="View"><Eye size={16} /></button>
                        <button onClick={() => openDoc(d.id, { download: true, name: `${d.title}.pdf` }).catch((e) => toast.error(errMsg(e, "Could not download")))} className="p-1.5 text-muted-foreground hover:bg-muted" title="Download"><Download size={16} /></button>
                        {meta.can_edit && d.source === "coa" && (
                          <>
                            <button onClick={() => setMaker({ existing: d })} className="p-1.5 text-muted-foreground hover:bg-muted" title="Edit"><Pencil size={16} /></button>
                            <button onClick={() => setMaker({ duplicateOf: d })} className="p-1.5 text-muted-foreground hover:bg-muted" title="Make a copy (e.g. another grade)"><Copy size={16} /></button>
                          </>
                        )}
                        {meta.can_edit && <button onClick={() => del(d)} className="p-1.5 text-muted-foreground hover:text-[#E60000] hover:bg-muted" title="Delete"><Trash2 size={16} /></button>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {maker && (
        <CoaMaker products={allProducts} productId={sel} existing={maker.existing} duplicateOf={maker.duplicateOf}
          isAdmin={meta.is_admin} onClose={() => setMaker(null)} onSaved={(pid) => { setMaker(null); refresh(pid); }} />
      )}
      {upload && detail && (
        <UploadModal product={detail.product} kinds={meta.kinds} isAdmin={meta.is_admin}
          onClose={() => setUpload(false)} onDone={() => { setUpload(false); refresh(sel); }} />
      )}
      {newOil && <NewOilModal onClose={() => setNewOil(false)} onDone={(p) => { setNewOil(false); refresh(p.id); }} />}
    </div>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-background w-full max-w-md shadow-2xl">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="font-black">{title}</div>
          <button onClick={onClose} className="p-1 text-muted-foreground"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">{children}</div>
      </div>
    </div>
  );
}

function NewOilModal({ onClose, onDone }) {
  const [name, setName] = useState("");
  const [aliases, setAliases] = useState("");
  const save = async () => {
    try {
      const { data } = await api.post("/docs/products", { name, aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean) });
      toast.success("Oil added"); onDone(data);
    } catch (e) { toast.error(errMsg(e, "Could not add")); }
  };
  return (
    <Modal title="Add oil" onClose={onClose}>
      <input className={`${inp} w-full`} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Lemongrass Oil" autoFocus />
      <input className={`${inp} w-full`} value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="Other names, comma separated (e.g. lemon grass, Cymbopogon)" />
      <button onClick={save} disabled={!name.trim()} className="w-full bg-[#002FA7] text-white py-2 text-xs font-bold uppercase tracking-widest disabled:opacity-50">Add</button>
    </Modal>
  );
}

function UploadModal({ product, kinds, isAdmin, onClose, onDone }) {
  const [kind, setKind] = useState("gcms");
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState("team");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  const save = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("product_id", product.id); fd.append("kind", kind); fd.append("title", title);
      fd.append("visibility", visibility); fd.append("file", file);
      await api.post("/docs/upload", fd);
      toast.success("Uploaded"); onDone();
    } catch (e) { toast.error(errMsg(e, "Upload failed")); }
    finally { setBusy(false); }
  };
  return (
    <Modal title={`Upload for ${product.name}`} onClose={onClose}>
      <select className={`${inp} w-full`} value={kind} onChange={(e) => setKind(e.target.value)}>
        {Object.entries(kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <input className={`${inp} w-full`} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`Name (default: ${product.name} - ${kinds[kind] || ""})`} />
      <select className={`${inp} w-full`} value={visibility} onChange={(e) => setVisibility(e.target.value)}>
        <option value="team">Everyone (executives can send it)</option>
        <option value="admin">Only system admin{isAdmin ? "" : " (you won't see it after saving)"}</option>
      </select>
      <input ref={ref} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)} className="text-sm" />
      <button onClick={save} disabled={!file || busy} className="w-full bg-[#002FA7] text-white py-2 text-xs font-bold uppercase tracking-widest disabled:opacity-50">{busy ? "Uploading…" : "Upload"}</button>
    </Modal>
  );
}
