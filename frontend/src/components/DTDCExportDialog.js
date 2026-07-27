import { useState, useEffect, useRef, useCallback } from "react";
import * as XLSX from "xlsx";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Download, FileSpreadsheet, X, Info, Loader2, Image as ImageIcon } from "lucide-react";

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
// Carrier-risk orders book on the RL1387 account, which handles BOTH service
// types (GROUND EXPRESS / STD EXP-A) with the transit-insurance surcharge on.
// The service type is still auto-picked from the weight/pincode series.
const CARRIER_RISK_ACCOUNT = "RL1387";

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
// NOTE: Order here controls the preview column order.
// Weight is moved right after the box image button (which is a special UI column).
// Order # and Customer Name are sticky-left columns, not in PREVIEW_COLUMNS.
const PREVIEW_COLUMNS = [
  // Manual — weight first (the important one to enter)
  "Weight(KG) (non-document)",
  // From order (auto-filled)
  "Declared Price (non-document)",
  "Destination Pincode",
  "Destination Name",
  "Destination Phone",
  "Destination Address Line 1",
  "Destination Address Line 2",
  "Destination City",
  "Destination State",
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
  if (["Weight(KG) (non-document)"].includes(col)) return 100;
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

// Extract only the primary (first) phone number
function extractPrimaryPhone(phones) {
  if (!phones) return "";
  const arr = Array.isArray(phones) ? phones : [String(phones)];
  // The first non-empty entry is the primary number
  const primary = arr.find(p => String(p).trim() !== "");
  return primary ? String(primary).trim() : "";
}

function buildRowFromOrder(order) {
  const sa = order.shipping_address || {};
  // Only use primary phone number
  const phone = extractPrimaryPhone(order.customer_phone);

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

  // Weight & pieces come from the packing team (read-only here).
  // Pieces = number of boxes; weight column holds the TOTAL weight of all boxes.
  row["Weight(KG) (non-document)"] = order.packaging?.weight_kg || "";
  row["Number of Pieces (non-document)"] = order.packaging?.num_boxes || "1";

  // Carrier-risk orders go to the RL1387 account with the risk surcharge on.
  // Service type stays the D-series default until weight refines it.
  row._carrierRisk = !!order.carrier_risk_applicable;
  if (row._carrierRisk) {
    row["Unique_Id"] = CARRIER_RISK_ACCOUNT;
    row["Client Code"] = CARRIER_RISK_ACCOUNT;
    row["Risk Surcharge (YES/NO) (non-document)"] = "1";
  }

  return row;
}

// ─── Box Image Viewer Modal ───────────────────────────────────────────────────
function BoxImageViewer({ open, onClose, orderId, orderNum, backendUrl, onWeightUpdate }) {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const [weight, setWeight] = useState("");
  const [savingWeight, setSavingWeight] = useState(false);

  useEffect(() => {
    if (!open || !orderId) return;
    setLoading(true);
    setImages([]);
    setActiveIdx(0);
    setWeight("");
    api.get(`/orders/${orderId}`)
      .then(res => {
        const imgs = res.data?.packaging?.packed_box_images || [];
        setImages(imgs);
        setWeight(res.data?.packaging?.weight_kg || "");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, orderId]);

  const handleSaveWeight = async () => {
    if (!orderId) return;
    setSavingWeight(true);
    try {
      await api.put(`/orders/${orderId}/packaging`, { weight_kg: weight });
      toast.success("Order weight saved successfully!");
    } catch (err) {
      console.warn("Could not persist weight to database, using local update", err);
    } finally {
      setSavingWeight(false);
      if (onWeightUpdate) {
        onWeightUpdate(weight);
      }
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 50,
        background: "#ffffff",
        display: "flex",
        flexDirection: "column",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 20px",
          borderBottom: "1px solid #e2e8f0",
          background: "#f8fafc",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={onClose}
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              padding: "6px 12px",
              borderRadius: 6,
              fontSize: "0.8rem",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
            onMouseEnter={e => e.currentTarget.style.background = "#1d4ed8"}
            onMouseLeave={e => e.currentTarget.style.background = "#2563eb"}
          >
            ← Back to Excel Preview
          </button>
          <div>
            <span style={{ fontWeight: 700, fontSize: "0.9rem", color: "#1e293b" }}>Packed Box Images</span>
            <span style={{ fontSize: "0.75rem", color: "#64748b", marginLeft: 8 }}>Order {orderNum}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", cursor: "pointer", padding: 4, color: "#64748b" }}
        >
          <X style={{ width: 20, height: 20 }} />
        </button>
      </div>

      {/* Main Content (Scrollable Split Layout: Left = Images, Right = Weight Entry) */}
      <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%", minHeight: 200 }}>
            <Loader2 style={{ width: 32, height: 32, animation: "spin 1s linear infinite", color: "#3b82f6" }} />
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "row", gap: 24, flexWrap: "wrap" }}>
            
            {/* Left side: Images gallery */}
            <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 12 }}>
              {images.length === 0 ? (
                <div style={{ textAlign: "center", padding: "40px 0", color: "#9ca3af", border: "2px dashed #e2e8f0", borderRadius: 8 }}>
                  <ImageIcon style={{ width: 48, height: 48, margin: "0 auto 12px", opacity: 0.4 }} />
                  <p style={{ fontSize: "0.85rem", color: "#475569" }}>No packed box images uploaded for this order</p>
                </div>
              ) : (
                <>
                  <div style={{ borderRadius: 8, overflow: "hidden", background: "#f1f5f9", textAlign: "center", padding: 10, border: "1px solid #e2e8f0" }}>
                    <img
                      src={`${backendUrl}${images[activeIdx]}`}
                      alt={`Box ${activeIdx + 1}`}
                      style={{ maxHeight: 360, maxWidth: "100%", width: "auto", height: "auto", objectFit: "contain", margin: "0 auto" }}
                    />
                  </div>
                  {images.length > 1 && (
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
                      {images.map((url, i) => (
                        <button
                          key={i}
                          onClick={() => setActiveIdx(i)}
                          style={{
                            width: 56, height: 56, borderRadius: 6, overflow: "hidden",
                            border: i === activeIdx ? "2px solid #3b82f6" : "2px solid #e2e8f0",
                            cursor: "pointer", padding: 0, background: "none",
                          }}
                        >
                          <img
                            src={`${backendUrl}${url}`}
                            alt={`thumb ${i + 1}`}
                            style={{ width: "100%", height: "100%", objectFit: "cover" }}
                          />
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Right side: Weight input & order details */}
            <div style={{ flex: "1 1 200px", minWidth: 200, display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                <h4 style={{ fontWeight: 600, fontSize: "0.85rem", color: "#334155", marginBottom: 12 }}>Weight (entered by packing)</h4>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <label style={{ fontSize: "0.78rem", fontWeight: 600, color: "#64748b" }}>
                    Package Weight (total of all boxes)
                  </label>
                  <input
                    type="text"
                    value={weight ? `${weight} KG` : "Not entered yet"}
                    readOnly
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      fontSize: "0.9rem",
                      fontWeight: 700,
                      border: "1px solid #cbd5e1",
                      borderRadius: 6,
                      outline: "none",
                      background: "#f1f5f9",
                      color: weight ? "#0f172a" : "#b91c1c",
                    }}
                  />
                  <Button
                    onClick={onClose}
                    className="w-full text-xs font-semibold h-9"
                    style={{ background: "#2563eb", color: "#fff", borderRadius: 6, marginTop: 4 }}
                  >
                    Close
                  </Button>
                </div>
              </div>

              {/* Tips / Instructions */}
              <div style={{ padding: 12, border: "1px solid #fef08a", borderRadius: 6, background: "#fef9c3" }}>
                <p style={{ fontSize: "0.72rem", color: "#854d0e", lineHeight: "1.4", margin: 0 }}>
                  💡 The weight is set by the <b>packing team</b> when they seal the box. If it's missing, ask them to weigh and save it — it can't be edited here.
                </p>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}

export default function DTDCExportDialog({ open, onClose, orders }) {
  const [rows, setRows] = useState([]);
  const [orderMeta, setOrderMeta] = useState([]); // {id, orderNum, customerName} per row
  // Per-row series detection state: { [rowIdx]: { loading, series, error } }
  const [rowSeries, setRowSeries] = useState({});
  // Debounce timers per row
  const debounceTimers = useRef({});
  // Ref that mirrors rows so timeouts can read the latest pincode without setState nesting
  const rowsRef = useRef([]);
  useEffect(() => { rowsRef.current = rows; }, [rows]);

  // Box image modal state
  const [boxModal, setBoxModal] = useState({ open: false, orderId: null, orderNum: "" });
  const backendUrl = process.env.REACT_APP_BACKEND_URL || "";

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
      const serviceType = seriesName === "M-Series" ? "STD EXP-A" : "GROUND EXPRESS";
      const isCarrierRisk = rowsRef.current[rowIdx]?._carrierRisk;
      // Carrier-risk rows stay on RL1387 (risk on); only the service type follows
      // the detected series. Everyone else uses the normal per-series account.
      const fields = isCarrierRisk
        ? {
            "Unique_Id": CARRIER_RISK_ACCOUNT,
            "Client Code": CARRIER_RISK_ACCOUNT,
            "Service Type": serviceType,
            "Risk Surcharge (YES/NO) (non-document)": "1",
          }
        : (seriesName === "M-Series" ? M_SERIES : D_SERIES);

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

        // Auto-save to backend in background
        const orderId = row?._orderId;
        if (orderId) {
          api.put(`/orders/${orderId}/packaging`, { weight_kg: value }).catch(() => {});
        }
      }, 600);
    }
  };

  const removeRow = (rowIdx) => {
    setRows(prev => prev.filter((_, i) => i !== rowIdx));
    setOrderMeta(prev => prev.filter((_, i) => i !== rowIdx));
  };

  useEffect(() => {
    if (open && orders.length > 0) {
      const initialRows = orders.map(o => ({
        _orderId:  o.id,
        _orderNum: o.order_number,
        ...buildRowFromOrder(o),
      }));
      setRows(initialRows);
      setOrderMeta(orders.map(o => ({
        id: o.id,
        orderNum: o.order_number,
        customerName: o.customer_name || "",
      })));
      setRowSeries({});
      setBoxModal({ open: false, orderId: null, orderNum: "" });

      // Run detectSeries for any row with prefilled weight!
      initialRows.forEach((row, idx) => {
        const wt = row["Weight(KG) (non-document)"];
        const pin = row["Destination Pincode"];
        if (wt && pin) {
          detectSeries(idx, wt, pin);
        }
      });
    } else if (!open) {
      setBoxModal({ open: false, orderId: null, orderNum: "" });
    }
  }, [open, orders, detectSeries]);

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

    // Warn (but allow) rows the packing team hasn't weighed yet.
    const noWeight = rows.filter(r => !String(r["Weight(KG) (non-document)"] ?? "").trim()).length;
    if (noWeight > 0) {
      toast.warning(`${noWeight} order(s) have no weight yet — they'll export blank. Ask packing to weigh them.`);
    }

    // Warn if some rows have no series detected yet (non-carrier-risk ones default to RL1386)
    const undetected = rows.filter((_, i) => !rowSeries[i]?.series && !rows[i]._carrierRisk).length;
    if (undetected > 0) {
      toast.warning(`${undetected} row(s) have no series detected — they default to the RL1386 file.`);
    }

    // Partition by the account each row is assigned to (one upload file per DTDC account).
    const buckets = { RL1386: [], RL1387: [], RL1423: [] };
    rows.forEach((row) => {
      const acct = row["Client Code"];
      if (acct === CARRIER_RISK_ACCOUNT) buckets.RL1387.push(row);
      else if (acct === "RL1423") buckets.RL1423.push(row);
      else buckets.RL1386.push(row); // RL1386 / undetected default
    });

    const files = [];
    if (buckets.RL1386.length) files.push([buckets.RL1386, "DTDC_RL1386_GROUND-EXPRESS.xlsx", "RL1386"]);
    if (buckets.RL1387.length) files.push([buckets.RL1387, "DTDC_RL1387_CarrierRisk.xlsx", "RL1387"]);
    if (buckets.RL1423.length) files.push([buckets.RL1423, "DTDC_RL1423_STD-EXP-A.xlsx", "RL1423"]);

    // Stagger downloads so the browser doesn't drop concurrent files.
    files.forEach(([rws, fname, sname], i) => {
      setTimeout(() => downloadSheet(rws, fname, sname), i * 700);
    });
    toast.success(`Downloaded ${files.length} file(s): ${files.map(f => `${f[2]} (${f[0].length})`).join(", ")}`);

    onClose();
  };

  if (!open) return null;

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent
          className="p-0 flex flex-col"
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => {
            if (boxModal.open) {
              e.preventDefault();
              setBoxModal({ open: false, orderId: null, orderNum: "" });
            }
          }}
          style={{
            maxWidth: "98vw",
            width: "98vw",
            maxHeight: "95vh",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          {/* Box image modal rendered inside DialogContent to avoid Radix UI blocking pointer events */}
          <BoxImageViewer
            open={boxModal.open}
            onClose={() => setBoxModal({ open: false, orderId: null, orderNum: "" })}
            orderId={boxModal.orderId}
            orderNum={boxModal.orderNum}
            backendUrl={backendUrl}
            onWeightUpdate={(weight) => {
              const rowIdx = rows.findIndex(r => r._orderId === boxModal.orderId);
              if (rowIdx !== -1) {
                updateCell(rowIdx, "Weight(KG) (non-document)", weight);
              }
            }}
          />
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
                { style: COL_STYLES.manual, label: "Weight (from packing) → auto-detects series" },
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
                <span className="inline-block rounded px-2 py-0.5 font-medium" style={{ background: "#b91c1c", color: "#fff" }}>Carrier Risk → RL1387 (both, risk on)</span>
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
                      {/* Sticky Order # column */}
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

                      {/* Sticky Customer Name column */}
                      <th
                        style={{
                          position: "sticky", left: 90, zIndex: 30,
                          background: "#0f2044", color: "#fff",
                          padding: "8px 10px", fontSize: "0.7rem", fontWeight: 600,
                          border: "1px solid #2a4a7f", whiteSpace: "nowrap", minWidth: 130,
                        }}
                      >
                        Customer
                      </th>

                      {/* Box Image button column header */}
                      <th
                        style={{
                          background: "#1e293b", color: "#cbd5e1",
                          padding: "8px 10px", fontSize: "0.7rem", fontWeight: 600,
                          border: "1px solid #334155", whiteSpace: "nowrap", minWidth: 80,
                        }}
                      >
                        Box Img
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
                      const meta = orderMeta[rowIdx] || {};
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
                            whiteSpace: "nowrap", minWidth: 90,
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

                        {/* Customer Name */}
                        <td
                          style={{
                            position: "sticky", left: 90, zIndex: 10,
                            background: rowIdx % 2 === 0 ? "#f0f4ff" : "#e8eeff",
                            padding: "4px 8px", fontSize: "0.7rem",
                            color: "#374151", border: "1px solid #d1d5db",
                            whiteSpace: "nowrap", minWidth: 130,
                            fontWeight: 500,
                          }}
                        >
                          {meta.customerName || "—"}
                        </td>

                        {/* Box Image button */}
                        <td
                          style={{
                            background: rowIdx % 2 === 0 ? "#f8fafc" : "#f1f5f9",
                            border: "1px solid #d1d5db",
                            padding: "4px 8px",
                            textAlign: "center",
                            minWidth: 80,
                          }}
                        >
                          <button
                            onClick={() => setBoxModal({
                              open: true,
                              orderId: meta.id || row._orderId,
                              orderNum: meta.orderNum || row._orderNum,
                            })}
                            title="View packed box images"
                            style={{
                              background: "#1e293b",
                              border: "none",
                              cursor: "pointer",
                              color: "#e2e8f0",
                              padding: "3px 7px",
                              borderRadius: 5,
                              fontSize: "0.62rem",
                              fontWeight: 600,
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 3,
                              letterSpacing: "0.01em",
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = "#334155"}
                            onMouseLeave={e => e.currentTarget.style.background = "#1e293b"}
                          >
                            <ImageIcon style={{ width: 10, height: 10 }} />
                            Box
                          </button>
                        </td>

                        {PREVIEW_COLUMNS.map(col => {
                          const s = getColStyle(col);
                          const isWeight = COL_TYPE.manual.has(col);
                          const missing = isWeight && !String(row[col] ?? "").trim();
                          return (
                            <td
                              key={col}
                              style={{
                                background: missing ? "#fee2e2" : s.cell.background,
                                border: "1px solid #d1d5db",
                                padding: 0,
                                minWidth: getColWidth(col),
                              }}
                            >
                              <input
                                value={row[col] ?? ""}
                                onChange={e => { if (!isWeight) updateCell(rowIdx, col, e.target.value); }}
                                readOnly={isWeight}
                                title={isWeight ? "Weight is entered by the packing team" : ""}
                                placeholder={isWeight ? "⚠ no weight" : ""}
                                style={{
                                  width: "100%",
                                  background: "transparent",
                                  border: "none",
                                  outline: "none",
                                  padding: "5px 8px",
                                  fontSize: "0.7rem",
                                  color: missing ? "#b91c1c" : s.cell.color,
                                  fontFamily: "inherit",
                                  fontWeight: isWeight ? 700 : 400,
                                  cursor: isWeight ? "not-allowed" : "text",
                                }}
                                onFocus={e => { if (!isWeight) { e.target.style.boxShadow = "inset 0 0 0 2px #3b82f6"; e.target.style.borderRadius = "2px"; } }}
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
                  const c = { RL1386: 0, RL1387: 0, RL1423: 0 };
                  rows.forEach((r) => {
                    const a = r["Client Code"];
                    if (a === CARRIER_RISK_ACCOUNT) c.RL1387++;
                    else if (a === "RL1423") c.RL1423++;
                    else c.RL1386++;
                  });
                  const parts = [];
                  if (c.RL1386 > 0) parts.push(`${c.RL1386} RL1386`);
                  if (c.RL1387 > 0) parts.push(`${c.RL1387} RL1387`);
                  if (c.RL1423 > 0) parts.push(`${c.RL1423} RL1423`);
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
                  const accts = new Set(rows.map((r) => (
                    r["Client Code"] === CARRIER_RISK_ACCOUNT ? "RL1387"
                      : r["Client Code"] === "RL1423" ? "RL1423" : "RL1386"
                  )));
                  return `Download ${accts.size} File${accts.size === 1 ? "" : "s"}`;
                })()}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
