import { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SpellCheck, Undo2, CheckCircle2 } from "lucide-react";

// Item name box: suggests names already used in orders/PIs while typing, and checks
// spelling. Sure mistakes (rosemarry, lavander, oli) are corrected as soon as the
// user leaves the box, with Undo. Unsure ones are asked: Fix / Keep as typed.
const checkCache = new Map();
const keptAsTyped = new Set();          // names the user chose to keep this session

const norm = (s) => (s || "").replace(/\s+/g, " ").trim();

async function spellcheck(name) {
  const n = norm(name);
  if (n.length < 2) return null;
  if (checkCache.has(n)) return checkCache.get(n);
  const r = await api.get("/items/spellcheck", { params: { name: n } });
  checkCache.set(n, r.data);
  return r.data;
}

export default function ItemNameInput({ value, onChange, placeholder = "Product name", testId, className = "" }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [hi, setHi] = useState(-1);
  const [check, setCheck] = useState(null);
  const [autoNote, setAutoNote] = useState(null);   // {from, to, words}
  const focused = useRef(false);
  const typed = useRef(false);        // only suggest after the user types, not on load

  // suggestions while typing
  useEffect(() => {
    const q = (value || "").trim();
    if (!typed.current || q.length < 2) { setItems([]); return; }
    let alive = true;
    const t = setTimeout(() => {
      api.get("/items/suggest", { params: { q } })
        .then(r => {
          if (!alive) return;
          const list = (r.data.suggestions || []).filter(s => s.name.toLowerCase() !== q.toLowerCase());
          setItems(list);
          setHi(-1);
          if (focused.current) setOpen(list.length > 0);
        })
        .catch(() => {});
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [value]);

  // spelling check once typing pauses
  useEffect(() => {
    const name = norm(value);
    if (name.length < 2) { setCheck(null); return; }
    if (checkCache.has(name)) { setCheck(checkCache.get(name)); return; }
    let alive = true;
    const t = setTimeout(() => {
      spellcheck(name).then(d => { if (alive) setCheck(d); }).catch(() => {});
    }, 500);
    return () => { alive = false; clearTimeout(t); };
  }, [value]);

  const pick = (name) => {
    typed.current = false;
    setAutoNote(null);
    onChange(name);
    setOpen(false);
    setItems([]);
  };

  // leaving the box: tidy spaces, then apply the sure corrections
  const onBlur = async () => {
    focused.current = false;
    setTimeout(() => setOpen(false), 150);
    const tidy = norm(value);
    if (tidy !== value) onChange(tidy);
    if (!tidy || keptAsTyped.has(tidy)) return;
    try {
      const d = await spellcheck(tidy);
      if (d && d.auto_corrected && d.auto_corrected !== tidy) {
        typed.current = false;
        onChange(d.auto_corrected);
        setAutoNote({ from: tidy, to: d.auto_corrected, words: d.issues.filter(i => i.sure) });
      }
    } catch { /* the check is a helper; never block typing */ }
  };

  const undo = () => {
    keptAsTyped.add(autoNote.from);
    typed.current = false;
    onChange(autoNote.from);
    setAutoNote(null);
  };

  const keep = () => {
    keptAsTyped.add(norm(value));
    setCheck({ ...check, issues: [] });
  };

  const onKeyDown = (e) => {
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi(h => Math.min(items.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi(h => Math.max(-1, h - 1)); }
    else if (e.key === "Enter" && hi >= 0) { e.preventDefault(); pick(items[hi].name); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  const current = norm(value);
  const issues = (check?.issues || []).filter(() => !keptAsTyped.has(current));
  const showAsk = issues.length > 0 && check.corrected && check.corrected !== current;
  const showAuto = autoNote && autoNote.to === current;

  return (
    <div className="relative">
      <Input value={value} placeholder={placeholder} data-testid={testId} autoComplete="off" spellCheck={false}
        className={`${className} ${showAsk ? "border-amber-400 focus-visible:ring-amber-400" : ""}`}
        onChange={e => { typed.current = true; setAutoNote(null); onChange(e.target.value); }}
        onFocus={() => { focused.current = true; if (items.length) setOpen(true); }}
        onBlur={onBlur}
        onKeyDown={onKeyDown} />
      {open && items.length > 0 && (
        <div className="absolute z-50 mt-1 w-full min-w-[220px] rounded-md border bg-popover shadow-lg max-h-64 overflow-y-auto" data-testid={`${testId}-suggestions`}>
          {items.map((s, i) => (
            <button key={s.name} type="button"
              onMouseDown={e => { e.preventDefault(); pick(s.name); }}
              className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm ${i === hi ? "bg-accent" : "hover:bg-accent"}`}>
              <span className="truncate">{s.name}</span>
              <span className="text-[10px] text-muted-foreground shrink-0">used {s.count}×</span>
            </button>
          ))}
        </div>
      )}
      {showAuto && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-emerald-700 dark:text-emerald-400" data-testid={`${testId}-autocorrected`}>
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          <span>Auto-corrected: {autoNote.words.map(i => <span key={i.word} className="mr-1.5"><s className="opacity-70">{i.word}</s> → <b>{i.suggestion}</b></span>)}</span>
          <button type="button" onClick={undo} className="inline-flex items-center gap-0.5 font-semibold underline-offset-2 hover:underline" data-testid={`${testId}-undo`}>
            <Undo2 className="w-3 h-3" /> Undo
          </button>
        </div>
      )}
      {showAsk && !showAuto && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-amber-700 dark:text-amber-400" data-testid={`${testId}-spelling`}>
          <SpellCheck className="w-3.5 h-3.5 shrink-0" />
          <span>Did you mean {issues.map(i => <span key={i.word} className="mr-1"><s className="opacity-70">{i.word}</s> → <b>{i.suggestion}</b></span>)}?</span>
          <button type="button" onClick={() => pick(check.corrected)} data-testid={`${testId}-fix`}
            className="rounded bg-amber-100 dark:bg-amber-900/50 px-2 py-0.5 font-semibold text-amber-800 dark:text-amber-200 hover:bg-amber-200">
            Fix → {check.corrected}
          </button>
          <button type="button" onClick={keep} className="text-muted-foreground hover:underline" data-testid={`${testId}-keep`}>Keep as typed</button>
        </div>
      )}
    </div>
  );
}

// ── Check before saving ─────────────────────────────────────────────────────
// Applies the sure corrections, and asks once about the unsure ones.
// Resolves to the items to save, or null if the user goes back to edit.
function SpellingDialog({ rows, onDone }) {
  const [open, setOpen] = useState(true);
  const finish = (v) => { setOpen(false); setTimeout(() => onDone(v), 150); };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) finish("back"); }}>
      <DialogContent className="max-w-md" data-testid="spelling-review">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><SpellCheck className="w-5 h-5 text-amber-600" /> Check item spelling</DialogTitle>
          <DialogDescription>These item names may be misspelt. Fix them before saving?</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {rows.map(r => (
            <div key={r.from} className="rounded-md border px-3 py-2 text-sm">
              <div className="text-muted-foreground line-through">{r.from}</div>
              <div className="font-semibold text-emerald-700 dark:text-emerald-400">{r.to}</div>
            </div>
          ))}
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" onClick={() => finish("back")}>Go back</Button>
          <Button variant="outline" onClick={() => finish("keep")} data-testid="spelling-keep">Keep as typed</Button>
          <Button onClick={() => finish("fix")} data-testid="spelling-fix">Fix {rows.length > 1 ? "all" : ""}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function askSpelling(rows) {
  return new Promise(resolve => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    root.render(<SpellingDialog rows={rows} onDone={(v) => { resolve(v); setTimeout(() => { root.unmount(); host.remove(); }, 0); }} />);
  });
}

export async function reviewItemSpelling(items) {
  const out = items.map(i => ({ ...i }));
  const ask = [];
  for (const it of out) {
    const name = norm(it.product_name);
    if (!name || keptAsTyped.has(name)) continue;
    let d = null;
    try { d = await spellcheck(name); } catch { continue; }
    if (!d || !d.issues?.length) continue;
    if (d.auto_corrected && d.auto_corrected !== name) it.product_name = d.auto_corrected;
    const after = norm(it.product_name);
    if (d.corrected && d.corrected !== after && d.issues.some(i => !i.sure)) ask.push({ item: it, from: after, to: d.corrected });
  }
  if (ask.length) {
    const choice = await askSpelling(ask.map(a => ({ from: a.from, to: a.to })));
    if (choice === "back") return null;
    for (const a of ask) {
      if (choice === "fix") a.item.product_name = a.to;
      else keptAsTyped.add(a.from);
    }
  }
  return out;
}
