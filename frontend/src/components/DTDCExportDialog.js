import { useState, useEffect, useRef, useCallback } from "react";
import * as XLSX from "xlsx";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Download, FileSpreadsheet, X, Info, Loader2 } from "lucide-react";

// ─── Series configs ──────────────────────────────────────────────────────────
const D_SERIES = {
  "Unique_Id":   "RL1386",
  "Client Code": "RL1386",
  "Service Type": "GROUND EXPRESS",
};
const M_SERIES = {
  "Unique_Id":   "RL1423",
  "Client Code": "RL1423",
  "Service Type": "STD EXP-A",
};

// ─── Default values for fixed columns (from downloadData.xls) ──────────────
const FIXED_DEFAULTS = {
  ...D_SERIES, // Default to D-series; overridden once series is detected
  "Courier Type":                         "NON-DOCUMENT",
  "Number of Pieces (non-document)":      "1",
  "Risk Surcharge (YES/NO) (non-document)":"0",
  "Length(cm) (non-document)":            "5",
  "Width(cm) (non-document)":             "5",
  "Height(cm) (non-document)":            "5",
  "Origin Pincode":                       "440025",
  "Origin Name":                          "Nagpur",
  "Origin Phone":                         "",
  "Origin Address Line 1":               "Plot No. B 101, Poonam Heights, Kapil Nagar, Pande Layout, Khamla, Nagpur, Maharashtra 440025",
  "Origin Address Line 2":               "",
  "Origin City":                          "NAGPUR",
  "Origin State":                         "MAHARASHTRA",
  "Content Type":                         "Perfumes",
};

// ─── All DTDC columns in exact order (from the XLS header row) ─────────────
const ALL_COLUMNS = [
  "Unique_Id","Client Code","Consignment Number","Customer Reference Number",
  "Service Type","Courier Type","Declared Price (non-document)",
  "Number of Pieces (non-document)","Risk Surcharge (YES/NO) (non-document)",
  "Weight(KG) (non-document)","Length(cm) (non-document)","Width(cm) (non-document)",
  "Height(cm) (non-document)","Origin Pincode","Origin Name","Origin Phone",
  "Origin Address Line 1","Origin Address Line 2","Origin City","Origin State",
  "Destination Pincode","Destination Name","Destination Phone",
  "Destination Address Line 1","Destination Address Line 2","Destination City",
  "Destination State","Product Code","Eway Bill","Content Type",
  "Consignment Type","Cod Amount","In Favor Of","Cod Mode","Description",
  "Return Reason","Origin Country","Destination Country","Destination Latitude",
  "Destination Longitude","Destination Address Email","Return Name",
  "Return Address Line 1","Return Address Line 2","Return Pincode","Return Phone",
  "Return Alternate Phone","Return City","Return State","Return Country",
  "Return Email","Exceptional RTO Name","Exceptional RTO Address Line 1",
  "Exceptional RTO Address Line 2","Exceptional RTO Pincode","Exceptional RTO Phone",
  "Exceptional RTO Alternate Phone","Exceptional RTO City","Exceptional RTO State",
  "Exceptional RTO Country","Type Of Delivery","Consignor Alternate Phone",
  "Inco Terms","Shipment Purpose","Movement Type","Pickup Start Time (HH:MM)",
  "Pickup End Time (HH:MM)","Pickup Service Time (Mins)","Delivery Start Time (HH:MM)",
  "Delivery End Time (HH:MM)","Delivery Service Time (Mins)","Origin Address Email",
];

// ─── Columns shown in the editable preview (only the ones we fill) ──────────
const PREVIEW_COLUMNS = [
  // Fixed
  "Unique_Id",
  "Client Code",
  "Service Type",
  "Courier Type",
  "Number of Pieces (non-document)",
  "Risk Surcharge (YES/NO) (non-document)",
  "Length(cm) (non-document)",
  "Width(cm) (non-document)",
  "Height(cm) (non-document)",
  "Origin Pincode",
  "Origin Name",
  "Origin Address Line 1",
  "Origin City",
  "Origin State",
  "Content Type",
  // From order (auto-filled)
  "Declared Price (non-document)",
  "Destination Pincode",
  "Destination Name",
  "Destination Phone",
  "Destination Address Line 1",
  "Destination Address Line 2",
  "Destination City",
  "Destination State",
  // Manual
  "Weight(KG) (non-document)",
];

// Column type classification
const COL_TYPE = {
  fixed: new Set([
    "Unique_Id","Client Code","Service Type","Courier Type",
    "Number of Pieces (non-document)","Risk Surcharge (YES/NO) (non-document)",
    "Length(cm) (non-document)","Width(cm) (non-document)","Height(cm) (non-document)",
    "Origin Pincode","Origin Name","Origin Address Line 1","Origin City","Origin State","Content Type",
  ]),
  order: new Set([
    "Declared Price (non-document)","Destination Pincode","Destination Name",
    "Destination Phone","Destination Address Line 1","Destination Address Line 2",
    "Destination City","Destination State",
  ]),
  manual: new Set(["Weight(KG) (non-document)"]),
};

// Readable short labels for header display
const SHORT_LABEL = {
  "Number of Pieces (non-document)":       "Pieces",
  "Risk Surcharge (YES/NO) (non-document)":"Risk",
  "Length(cm) (non-document)":             "L(cm)",
  "Width(cm) (non-document)":              "W(cm)",
  "Height(cm) (non-document)":             "H(cm)",
  "Weight(KG) (non-document)":             "Wt(KG) ★",
  "Declared Price (non-document)":         "Decl. Price",
  "Destination Pincode":                   "Dest. PIN",
  "Destination Name":                      "Dest. Name",
  "Destination Phone":                     "Dest. Phone",
  "Destination Address Line 1":            "Dest. Addr 1",
  "Destination Address Line 2":            "Dest. Addr 2",
  "Destination City":                      "Dest. City",
  "Destination State":                     "Dest. State",
  "Origin Pincode":                        "Orig. PIN",
  "Origin Name":                           "Orig. Name",
  "Origin Address Line 1":                 "Orig. Addr",
  "Origin City":                           "Orig. City",
  "Origin State":                          "Orig. State",
  "Content Type":                          "Content",
  "Unique_Id":                             "Unique ID",
  "Client Code":                           "Client Code",
  "Service Type":                          "Service",
  "Courier Type":                          "Type",
};

function getShortLabel(col) {
  return SHORT_LABEL[col] || col;
}

// Column min-widths for display
function getColWidth(col) {
  if (["Origin Address Line 1","Destination Address Line 1","Destination Address Line 2"].includes(col)) return 220;
  if (["Destination Name","Destination Phone"].includes(col)) return 140;
  return 110;
}

// Cell background & text styles per type
const COL_STYLES = {
  fixed: {
    header: { background: "#1e3a5f", color: "#ffffff" },
    cell:   { background: "#e8f0fe", color: "#1a1a2e" },
  },
  order: {
    header: { background: "#145a32", color: "#ffffff" },
    cell:   { background: "#d5f5e3", color: "#0d3b24" },
  },
  manual: {
    header: { background: "#7d5a00", color: "#ffffff" },
    cell:   { background: "#fff8e1", color: "#3d2c00" },
  },
  default: {
    header: { background: "#374151", color: "#ffffff" },
    cell:   { background: "#ffffff", color: "#111827" },
  },
};

function getColStyle(col) {
  if (COL_TYPE.fixed.has(col))  return COL_STYLES.fixed;
  if (COL_TYPE.order.has(col))  return COL_STYLES.order;
  if (COL_TYPE.manual.has(col)) return COL_STYLES.manual;
  return COL_STYLES.default;
}

function buildRowFromOrder(order) {
  const sa = order.shipping_address || {};
  const phones = order.customer_phone || [];
  const phone = Array.isArray(phones) ? phones.join(", ") : String(phones || "");

  // Start with all columns empty
  const row = {};
  for (const col of ALL_COLUMNS) row[col] = "";

  // Apply fixed defaults
  Object.assign(row, FIXED_DEFAULTS);

  // Fill from order data
  row["Declared Price (non-document)"] = order.grand_total != null ? String(Math.round(order.grand_total)) : "";
  row["Destination Pincode"]            = sa.pincode       || "";
  row["Destination Name"]               = sa.address_name  || order.customer_name || "";
  row["Destination Phone"]              = phone;
  row["Destination Address Line 1"]     = sa.address_line  || "";
  row["Destination Address Line 2"]     = sa.address_line2 || "";
  row["Destination City"]               = sa.city          || "";
  row["Destination State"]              = sa.state         || "";

  // Manual entry — empty
  row["Weight(KG) (non-document)"] = "";

  return row;
}

export default function DTDCExportDialog({ open, onClose, orders }) {
  const [rows, setRows] = useState([]);
  // Per-row series detection state: { [rowIdx]: { loading, series, error } }
  const [rowSeries, setRowSeries] = useState({});
  // Debounce timers per row
  const debounceTimers = useRef({});
  // Ref that mirrors rows so timeouts can read the latest pincode without setState nesting
  const rowsRef = useRef([]);
  useEffect(() => { rowsRef.current = rows; }, [rows]);

  useEffect(() => {
    if (open && orders.length > 0) {
      setRows(orders.map(o => ({
        _orderId:  o.id,
        _orderNum: o.order_number,
        ...buildRowFromOrder(o),
      })));
      setRowSeries({});
    }
  }, [open, orders]);

  // Detect series for a row using weight + destination pincode
  const detectSeries = useCallback(async (rowIdx, weightStr, pincode) => {
    const weight = parseFloat(weightStr);
    const pin = String(pincode || "").trim();

    // Skip if weight or pincode is missing / invalid
    if (!pin || pin.length < 6 || isNaN(weight) || weight <= 0) {
      setRowSeries(prev => ({ ...prev, [rowIdx]: { loading: false, series: null, error: null } }));
      return;
    }

    setRowSeries(prev => ({ ...prev, [rowIdx]: { loading: true, series: null, error: null } }));

    try {
      const res = await api.post("/dtdc/calculate", {
        pincode: pin,
        kg: Math.floor(weight),
        grams: Math.round((weight - Math.floor(weight)) * 1000),
      });
      const data = res.data;

      if (!data.serviceable) {
        setRowSeries(prev => ({ ...prev, [rowIdx]: { loading: false, series: null, error: "Pincode not serviceable" } }));
        return;
      }

      const seriesName = data.series; // "D-Series" or "M-Series"
      const fields = seriesName === "M-Series" ? M_SERIES : D_SERIES;

      // Autofill the series-dependent fields
      setRows(prev => {
        const next = [...prev];
        next[rowIdx] = { ...next[rowIdx], ...fields };
        return next;
      });
      setRowSeries(prev => ({ ...prev, [rowIdx]: { loading: false, series: seriesName, error: null } }));
    } catch {
      setRowSeries(prev => ({ ...prev, [rowIdx]: { loading: false, series: null, error: "Lookup failed" } }));
    }
  }, []);

  const updateCell = (rowIdx, col, value) => {
    setRows(prev => {
      const next = [...prev];
      next[rowIdx] = { ...next[rowIdx], [col]: value };
      return next;
    });

    // Trigger series detection when weight column is edited
    if (col === "Weight(KG) (non-document)") {
      if (debounceTimers.current[rowIdx]) clearTimeout(debounceTimers.current[rowIdx]);
      debounceTimers.current[rowIdx] = setTimeout(() => {
        // Read pincode from the ref (safe — no setState nesting)
        const row = rowsRef.current[rowIdx];
        const pincode = row?.["Destination Pincode"] ?? "";
        detectSeries(rowIdx, value, pincode);
      }, 600);
    }
  };

  const removeRow = (rowIdx) => {
    setRows(prev => prev.filter((_, i) => i !== rowIdx));
  };

  // Helper: build and trigger download of one xlsx file
  const downloadSheet = (exportRows, filename, sheetName) => {
    const data = exportRows.map(row => {
      const out = {};
      for (const col of ALL_COLUMNS) out[col] = row[col] ?? "";
      return out;
    });
    const ws = XLSX.utils.json_to_sheet(data, { header: ALL_COLUMNS });
    ws["!cols"] = ALL_COLUMNS.map(() => ({ wch: 28 }));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, sheetName);
    XLSX.writeFile(wb, filename);
  };

  const handleDownload = () => {
    if (rows.length === 0) { toast.error("No rows to export"); return; }

    // Partition rows by detected series
    const dRows = rows.filter((_, i) => rowSeries[i]?.series === "D-Series" || !rowSeries[i]?.series);
    const mRows = rows.filter((_, i) => rowSeries[i]?.series === "M-Series");

    // Warn if some rows have no series detected yet
    const undetected = rows.filter((_, i) => !rowSeries[i]?.series).length;
    if (undetected > 0) {
      toast.warning(`${undetected} row(s) have no series detected — they will be included in the D-Series file by default.`);
    }

    const hasBoth = dRows.length > 0 && mRows.length > 0;

    if (hasBoth) {
      // Download D-Series first, then M-Series after a short delay
      downloadSheet(dRows, "DTDC_D-Series_RL1386.xlsx", "D-Series");
      setTimeout(() => {
        downloadSheet(mRows, "DTDC_M-Series_RL1423.xlsx", "M-Series");
      }, 600);
      toast.success(`Downloaded 2 files: ${dRows.length} D-Series + ${mRows.length} M-Series order(s)`);
    } else if (mRows.length > 0) {
      downloadSheet(mRows, "DTDC_M-Series_RL1423.xlsx", "M-Series");
      toast.success(`Exported ${mRows.length} M-Series order(s) to DTDC_M-Series_RL1423.xlsx`);
    } else {
      downloadSheet(dRows, "DTDC_D-Series_RL1386.xlsx", "D-Series");
      toast.success(`Exported ${dRows.length} D-Series order(s) to DTDC_D-Series_RL1386.xlsx`);
    }

    onClose();
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent
        className="p-0 flex flex-col"
        style={{
          maxWidth: "98vw",
          width: "98vw",
          maxHeight: "95vh",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        {/* ── Header ── */}
        <DialogHeader
          className="flex-shrink-0 px-5 pt-4 pb-3 border-b"
          style={{ background: "linear-gradient(135deg,#0f2044 0%,#1a3a6b 100%)" }}
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg" style={{ background: "rgba(255,255,255,0.15)" }}>
              <FileSpreadsheet className="w-5 h-5 text-white" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-white">
                DTDC Excel Export — Preview &amp; Edit
              </DialogTitle>
              <p className="text-xs mt-0.5" style={{ color: "rgba(255,255,255,0.7)" }}>
                All cells are editable. Review before downloading.
              </p>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-4 mt-3">
            {[
              { style: COL_STYLES.fixed,  label: "Fixed defaults" },
              { style: COL_STYLES.order,  label: "From order data" },
              { style: COL_STYLES.manual, label: "Weight ★ → auto-detects series" },
            ].map(({ style, label }) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span
                  className="inline-block rounded px-2 py-0.5 font-medium"
                  style={{ background: style.cell.background, color: style.cell.color, border: `1px solid ${style.header.background}` }}
                >
                  {label}
                </span>
              </div>
            ))}
            <div className="flex items-center gap-2 text-xs">
              <span className="inline-block rounded px-2 py-0.5 font-medium" style={{ background: "#7c3aed", color: "#fff" }}>M-Series → RL1423 / STD EXP-A</span>
              <span className="inline-block rounded px-2 py-0.5 font-medium" style={{ background: "#0369a1", color: "#fff" }}>D-Series → RL1386 / GROUND EXPRESS</span>
            </div>
          </div>
        </DialogHeader>

        {/* ── Table ── */}
        <div className="flex-1 overflow-auto" style={{ minHeight: 0 }}>
          {rows.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground">
              No orders to display.
            </div>
          ) : (
            <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: "calc(95vh - 200px)" }}>
              <table style={{ borderCollapse: "collapse", minWidth: "max-content", tableLayout: "fixed" }}>
                <thead style={{ position: "sticky", top: 0, zIndex: 20 }}>
                  <tr>
                    {/* Sticky order# column */}
                    <th
                      style={{
                        position: "sticky", left: 0, zIndex: 30,
                        background: "#0f2044", color: "#fff",
                        padding: "8px 10px", fontSize: "0.7rem", fontWeight: 600,
                        border: "1px solid #2a4a7f", whiteSpace: "nowrap", minWidth: 90,
                      }}
                    >
                      Order #
                    </th>

                    {PREVIEW_COLUMNS.map(col => {
                      const s = getColStyle(col);
                      return (
                        <th
                          key={col}
                          title={col}
                          style={{
                            ...s.header,
                            padding: "7px 8px",
                            fontSize: "0.68rem",
                            fontWeight: 600,
                            border: "1px solid rgba(0,0,0,0.15)",
                            whiteSpace: "nowrap",
                            minWidth: getColWidth(col),
                            letterSpacing: "0.01em",
                          }}
                        >
                          {getShortLabel(col)}
                        </th>
                      );
                    })}

                    {/* Remove column */}
                    <th
                      style={{
                        position: "sticky", right: 0, zIndex: 30,
                        background: "#0f2044", color: "#fff",
                        padding: "8px 6px", fontSize: "0.7rem", fontWeight: 600,
                        border: "1px solid #2a4a7f", minWidth: 44,
                      }}
                    >
                      ✕
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {rows.map((row, rowIdx) => {
                    const rs = rowSeries[rowIdx];
                    const seriesBadgeStyle = rs?.series === "M-Series"
                      ? { background: "#7c3aed", color: "#fff" }
                      : rs?.series === "D-Series"
                        ? { background: "#0369a1", color: "#fff" }
                        : rs?.error
                          ? { background: "#dc2626", color: "#fff" }
                          : { background: "#e5e7eb", color: "#374151" };
                    const seriesLabel = rs?.loading
                      ? "…"
                      : rs?.series || (rs?.error ? "!": "—");
                    return (
                    <tr
                      key={row._orderId || rowIdx}
                      style={{ background: rowIdx % 2 === 0 ? "#fff" : "#f8fafc" }}
                    >
                      {/* Order number + series badge */}
                      <td
                        style={{
                          position: "sticky", left: 0, zIndex: 10,
                          background: rowIdx % 2 === 0 ? "#f0f4ff" : "#e8eeff",
                          padding: "4px 8px", fontSize: "0.7rem", fontWeight: 600,
                          color: "#1e3a8a", border: "1px solid #d1d5db",
                          whiteSpace: "nowrap", minWidth: 120,
                        }}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span>{row._orderNum || `#${rowIdx + 1}`}</span>
                          <span
                            title={rs?.error || (rs?.series ? `Auto-detected: ${rs.series}` : "Enter weight to auto-detect series")}
                            style={{
                              ...seriesBadgeStyle,
                              fontSize: "0.6rem",
                              fontWeight: 700,
                              padding: "1px 5px",
                              borderRadius: 4,
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 3,
                              letterSpacing: "0.02em",
                            }}
                          >
                            {rs?.loading && <Loader2 style={{ width: 8, height: 8, animation: "spin 1s linear infinite" }} />}
                            {seriesLabel}
                          </span>
                        </div>
                      </td>

                      {PREVIEW_COLUMNS.map(col => {
                        const s = getColStyle(col);
                        return (
                          <td
                            key={col}
                            style={{
                              background: s.cell.background,
                              border: "1px solid #d1d5db",
                              padding: 0,
                              minWidth: getColWidth(col),
                            }}
                          >
                            <input
                              value={row[col] ?? ""}
                              onChange={e => updateCell(rowIdx, col, e.target.value)}
                              placeholder={COL_TYPE.manual.has(col) ? "★ Enter weight" : ""}
                              style={{
                                width: "100%",
                                background: "transparent",
                                border: "none",
                                outline: "none",
                                padding: "5px 8px",
                                fontSize: "0.7rem",
                                color: s.cell.color,
                                fontFamily: "inherit",
                                fontWeight: COL_TYPE.manual.has(col) ? 600 : 400,
                              }}
                              onFocus={e => { e.target.style.boxShadow = "inset 0 0 0 2px #3b82f6"; e.target.style.borderRadius = "2px"; }}
                              onBlur={e => { e.target.style.boxShadow = "none"; }}
                            />
                          </td>
                        );
                      })}

                      {/* Remove */}
                      <td
                        style={{
                          position: "sticky", right: 0, zIndex: 10,
                          background: rowIdx % 2 === 0 ? "#fff" : "#f8fafc",
                          border: "1px solid #d1d5db",
                          padding: "4px 6px", textAlign: "center",
                        }}
                      >
                        <button
                          onClick={() => removeRow(rowIdx)}
                          title="Remove row"
                          style={{
                            background: "none", border: "none", cursor: "pointer",
                            color: "#ef4444", padding: "2px 4px", borderRadius: 4,
                            fontSize: "0.75rem", lineHeight: 1,
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = "#fee2e2"}
                          onMouseLeave={e => e.currentTarget.style.background = "none"}
                        >
                          <X style={{ width: 13, height: 13 }} />
                        </button>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <DialogFooter
          className="flex-shrink-0 px-5 py-3 border-t flex items-center justify-between gap-3"
          style={{ background: "#f8fafc" }}
        >
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Info className="w-3.5 h-3.5" />
            <span>
              {rows.length} row(s) ·{" "}
              {(() => {
                const d = rows.filter((_, i) => rowSeries[i]?.series === "D-Series").length;
                const m = rows.filter((_, i) => rowSeries[i]?.series === "M-Series").length;
                const u = rows.filter((_, i) => !rowSeries[i]?.series).length;
                const parts = [];
                if (d > 0) parts.push(`${d} D-Series`);
                if (m > 0) parts.push(`${m} M-Series`);
                if (u > 0) parts.push(`${u} pending`);
                return parts.length > 0 ? parts.join(" · ") : "Enter weights to detect series";
              })()}
            </span>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} className="h-8 text-sm">
              Cancel
            </Button>
            <Button
              onClick={handleDownload}
              disabled={rows.length === 0}
              className="h-8 text-sm gap-2"
              style={{ background: "#16a34a", color: "#fff" }}
            >
              <Download className="w-4 h-4" />
              {(() => {
                const d = rows.filter((_, i) => rowSeries[i]?.series === "D-Series" || !rowSeries[i]?.series).length;
                const m = rows.filter((_, i) => rowSeries[i]?.series === "M-Series").length;
                if (d > 0 && m > 0) return `Download 2 Files (${d}D + ${m}M)`;
                if (m > 0) return `Download M-Series (${m})`;
                return `Download D-Series (${d})`;
              })()}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
