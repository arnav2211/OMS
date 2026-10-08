import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { SpellCheck } from "lucide-react";

// Item name box with suggestions from names already used in orders/PIs, and a
// spelling hint ("Lavander → Lavender  [Fix]"). It only suggests; the name is
// changed only when the user picks a suggestion or clicks Fix.
const checkCache = new Map();

export default function ItemNameInput({ value, onChange, placeholder = "Product name", testId, className = "" }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [hi, setHi] = useState(-1);
  const [check, setCheck] = useState(null);
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
    const name = (value || "").trim();
    if (name.length < 3) { setCheck(null); return; }
    if (checkCache.has(name)) { setCheck(checkCache.get(name)); return; }
    let alive = true;
    const t = setTimeout(() => {
      api.get("/items/spellcheck", { params: { name } })
        .then(r => { checkCache.set(name, r.data); if (alive) setCheck(r.data); })
        .catch(() => {});
    }, 600);
    return () => { alive = false; clearTimeout(t); };
  }, [value]);

  const pick = (name) => {
    typed.current = false;
    onChange(name);
    setOpen(false);
    setItems([]);
  };

  const onKeyDown = (e) => {
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi(h => Math.min(items.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi(h => Math.max(-1, h - 1)); }
    else if (e.key === "Enter" && hi >= 0) { e.preventDefault(); pick(items[hi].name); }
    else if (e.key === "Escape") { setOpen(false); }
  };

  const issues = check?.issues || [];
  const showFix = issues.length > 0 && check.corrected && check.corrected !== (value || "").trim();

  return (
    <div className="relative">
      <Input value={value} placeholder={placeholder} data-testid={testId} autoComplete="off"
        className={`${className} ${showFix ? "border-amber-400 focus-visible:ring-amber-400" : ""}`}
        onChange={e => { typed.current = true; onChange(e.target.value); }}
        onFocus={() => { focused.current = true; if (items.length) setOpen(true); }}
        onBlur={() => {
          focused.current = false;
          setTimeout(() => setOpen(false), 150);
          // tidy stray spaces ("Guava  Fragrance ") - never changes the words
          const tidy = (value || "").replace(/\s+/g, " ").trim();
          if (tidy !== value) onChange(tidy);
        }}
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
      {showFix && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-amber-700 dark:text-amber-400" data-testid={`${testId}-spelling`}>
          <SpellCheck className="w-3.5 h-3.5 shrink-0" />
          <span>Spelling: {issues.map(i => <span key={i.word} className="mr-1.5"><s className="opacity-70">{i.word}</s> → <b>{i.suggestion}</b></span>)}</span>
          <button type="button" onClick={() => pick(check.corrected)} data-testid={`${testId}-fix`}
            className="rounded bg-amber-100 dark:bg-amber-900/50 px-2 py-0.5 font-semibold text-amber-800 dark:text-amber-200 hover:bg-amber-200">
            Fix → {check.corrected}
          </button>
        </div>
      )}
    </div>
  );
}
