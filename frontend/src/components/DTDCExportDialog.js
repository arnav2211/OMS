import { useState, useEffect, useRef } from "react";
import * as XLSX from "xlsx";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Download, FileSpreadsheet, X, Info } from "lucide-react";

// ─── Fixed values (always the same) ────────────────────────────────────────
const FIXED_VALUES = {
  "Unique_Id": "",
  "Client Code": "",
  "Service Type": "",
  "Courier Type": "",
  "Number of Pieces (non-document)": "",
  "Risk Surcharge (YES/NO) (non-document)": "",
  "Length(cm) (non-document)": "",
  "Width(cm) (non-document)": "",
  "Height(cm) (non-document)": "",
  "Origin Pincode": "",
  "Origin Name": "",
  "Origin Address Line 1": "",
  "Origin City": "",
  "Origin State": "",
  "Content Type": "",
};

// ─── All columns in the correct order (matching downloadData.xls) ───────────
const ALL_COLUMNS = [
  "Unique_Id",
  "Client Code",
  "Consignment Number",
  "Customer Reference Number",
  "Service Type",
  "Courier Type",
  "Declared Price (non-document)",
  "Number of Pieces (non-document)",
  "Risk Surcharge (YES/NO) (non-document)",
  "Weight(KG) (non-document)",
  "Length(cm) (non-document)",
  "Width(cm) (non-document)",
  "Height(cm) (non-document)",
  "Origin Pincode",
  "Origin Name",
  "Origin Phone",
  "Origin Address Line 1",
  "Origin Address Line 2",
  "Origin City",
  "Origin State",
  "Destination Pincode",
  "Destination Name",
  "Destination Phone",
  "Destination Address Line 1",
  "Destination Address Line 2",
  "Destination City",
  "Destination State",
  "Product Code",
  "Eway Bill",
  "Content Type",
  "Consignment Type",
  "Cod Amount",
  "In Favor Of",
  "Cod Mode",
  "Description",
  "Return Reason",
  "Origin Country",
  "Destination Country",
  "Destination Latitude",
  "Destination Longitude",
  "Destination Address Email",
  "Return Name",
  "Return Address Line 1",
  "Return Address Line 2",
  "Return Pincode",
  "Return Phone",
  "Return Alternate Phone",
  "Return City",
  "Return State",
  "Return Country",
  "Return Email",
  "Exceptional RTO Name",
  "Exceptional RTO Address Line 1",
  "Exceptional RTO Address Line 2",
  "Exceptional RTO Pincode",
  "Exceptional RTO Phone",
  "Exceptional RTO Alternate Phone",
  "Exceptional RTO City",
  "Exceptional RTO State",
  "Exceptional RTO Country",
  "Type Of Delivery",
  "Consignor Alternate Phone",
  "Inco Terms",
  "Shipment Purpose",
  "Movement Type",
  "Pickup Start Time (HH:MM)",
  "Pickup End Time (HH:MM)",
  "Pickup Service Time (Mins)",
  "Delivery Start Time (HH:MM)",
  "Delivery End Time (HH:MM)",
  "Delivery Service Time (Mins)",
  "Origin Address Email",
];

// Columns visible in the preview (editable columns only — the ones we fill)
const PREVIEW_COLUMNS = [
  "Unique_Id",
  "Client Code",
  "Service Type",
  "Courier Type",
  "Declared Price (non-document)",
  "Number of Pieces (non-document)",
  "Risk Surcharge (YES/NO) (non-document)",
  "Weight(KG) (non-document)",
  "Length(cm) (non-document)",
  "Width(cm) (non-document)",
  "Height(cm) (non-document)",
  "Origin Pincode",
  "Origin Name",
  "Origin Address Line 1",
  "Origin City",
  "Origin State",
  "Destination Pincode",
  "Destination Name",
  "Destination Phone",
  "Destination Address Line 1",
  "Destination Address Line 2",
  "Destination City",
  "Destination State",
  "Content Type",
];

// Which columns the user can edit (manually entered + pre-filled but editable)
const EDITABLE_COLUMNS = new Set(PREVIEW_COLUMNS);

// Which columns come from the order data (pre-filled from order)
const ORDER_COLUMNS = new Set([
  "Declared Price (non-document)",
  "Destination Pincode",
  "Destination Name",
  "Destination Phone",
  "Destination Address Line 1",
  "Destination Address Line 2",
  "Destination City",
  "Destination State",
]);

// Column that requires manual entry
const MANUAL_COLUMNS = new Set(["Weight(KG) (non-document)"]);

// Fixed columns (always the same — pre-filled from FIXED_VALUES, still editable)
const FIXED_COLUMNS = new Set([
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
]);

function buildRowFromOrder(order) {
  const sa = order.shipping_address || {};
  const phone = (order.customer_phone || []).join(", ");

  const row = {};

  // Initialize all preview columns to empty
  for (const col of ALL_COLUMNS) {
    row[col] = "";
  }

  // Fixed columns — empty by default, user can fill
  for (const [col, val] of Object.entries(FIXED_VALUES)) {
    row[col] = val;
  }

  // From order data
  row["Declared Price (non-document)"] = order.grand_total != null ? String(order.grand_total) : "";
  row["Destination Pincode"] = sa.pincode || "";
  row["Destination Name"] = sa.address_name || order.customer_name || "";
  row["Destination Phone"] = phone;
  row["Destination Address Line 1"] = sa.address_line || "";
  row["Destination Address Line 2"] = sa.address_line2 || "";
  row["Destination City"] = sa.city || "";
  row["Destination State"] = sa.state || "";

  // Manual entry — blank
  row["Weight(KG) (non-document)"] = "";

  return row;
}

function getCellColor(col) {
  if (MANUAL_COLUMNS.has(col)) return "#fff3cd"; // yellow — manual entry required
  if (ORDER_COLUMNS.has(col)) return "#d4edda";   // green — from order
  if (FIXED_COLUMNS.has(col)) return "#d1ecf1";   // blue — fixed/same for all
  return "";
}

export default function DTDCExportDialog({ open, onClose, orders }) {
  const [rows, setRows] = useState([]);
  const tableRef = useRef(null);

  useEffect(() => {
    if (open && orders.length > 0) {
      setRows(orders.map(o => ({ _orderId: o.id, _orderNum: o.order_number, ...buildRowFromOrder(o) })));
    }
  }, [open, orders]);

  const updateCell = (rowIdx, col, value) => {
    setRows(prev => {
      const next = [...prev];
      next[rowIdx] = { ...next[rowIdx], [col]: value };
      return next;
    });
  };

  const removeRow = (rowIdx) => {
    setRows(prev => prev.filter((_, i) => i !== rowIdx));
  };

  const handleDownload = () => {
    if (rows.length === 0) {
      toast.error("No rows to export");
      return;
    }

    // Build data with ALL columns (not just preview columns) in correct order
    const exportData = rows.map(row => {
      const exportRow = {};
      for (const col of ALL_COLUMNS) {
        exportRow[col] = row[col] !== undefined ? row[col] : "";
      }
      return exportRow;
    });

    const ws = XLSX.utils.json_to_sheet(exportData, { header: ALL_COLUMNS });
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "DTDC Orders");

    // Style header row
    const headerRange = XLSX.utils.decode_range(ws["!ref"]);
    for (let C = headerRange.s.c; C <= headerRange.e.c; C++) {
      const cellAddr = XLSX.utils.encode_cell({ r: 0, c: C });
      if (ws[cellAddr]) {
        ws[cellAddr].s = {
          font: { bold: true },
          fill: { fgColor: { rgb: "4472C4" }, patternType: "solid" },
        };
      }
    }

    // Set column widths
    ws["!cols"] = ALL_COLUMNS.map(() => ({ wch: 22 }));

    XLSX.writeFile(wb, "DTDC_Orders_Export.xlsx");
    toast.success(`Exported ${rows.length} order(s) to DTDC_Orders_Export.xlsx`);
    onClose();
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent
        className="max-w-[98vw] w-full max-h-[95vh] flex flex-col p-0"
        style={{ borderRadius: "12px", overflow: "hidden" }}
      >
        {/* Header */}
        <DialogHeader className="px-6 pt-5 pb-3 border-b bg-gradient-to-r from-blue-50 to-indigo-50 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <FileSpreadsheet className="w-5 h-5 text-blue-700" />
            </div>
            <div>
              <DialogTitle className="text-lg font-semibold">DTDC Excel Export — Preview & Edit</DialogTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                Review and edit all fields before downloading. All cells are editable.
              </p>
            </div>
          </div>
          {/* Legend */}
          <div className="flex flex-wrap gap-3 mt-3">
            <div className="flex items-center gap-1.5 text-xs">
              <span className="w-3 h-3 rounded-sm inline-block border" style={{ background: "#d4edda" }} />
              <span className="text-muted-foreground">From order data</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <span className="w-3 h-3 rounded-sm inline-block border" style={{ background: "#fff3cd" }} />
              <span className="text-muted-foreground">Manual entry required</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <span className="w-3 h-3 rounded-sm inline-block border" style={{ background: "#d1ecf1" }} />
              <span className="text-muted-foreground">Fixed / same for all</span>
            </div>
          </div>
        </DialogHeader>

        {/* Scrollable Table */}
        <div className="flex-1 overflow-auto" style={{ minHeight: 0 }}>
          {rows.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground">
              No orders to display.
            </div>
          ) : (
            <div className="overflow-x-auto overflow-y-auto max-h-[60vh]">
              <table
                ref={tableRef}
                className="border-collapse text-xs"
                style={{ minWidth: "max-content", tableLayout: "fixed" }}
              >
                <thead className="sticky top-0 z-20 bg-white shadow-sm">
                  <tr>
                    {/* Row label column */}
                    <th
                      className="border border-gray-200 bg-gray-50 px-2 py-2 text-center font-medium text-gray-600 whitespace-nowrap sticky left-0 z-30"
                      style={{ minWidth: 90, background: "#f9fafb" }}
                    >
                      Order #
                    </th>
                    {PREVIEW_COLUMNS.map(col => (
                      <th
                        key={col}
                        className="border border-gray-200 px-2 py-2 text-left font-semibold text-gray-700 whitespace-nowrap"
                        style={{
                          minWidth: col.length > 20 ? 170 : 130,
                          background: getCellColor(col) || "#f0f4ff",
                          fontSize: "0.68rem",
                        }}
                        title={col}
                      >
                        {col}
                        {MANUAL_COLUMNS.has(col) && (
                          <span className="ml-1 text-amber-600 font-bold">*</span>
                        )}
                      </th>
                    ))}
                    <th
                      className="border border-gray-200 bg-gray-50 px-2 py-2 text-center font-medium text-gray-600 sticky right-0 z-30"
                      style={{ minWidth: 50, background: "#f9fafb" }}
                    >
                      ✕
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, rowIdx) => (
                    <tr
                      key={row._orderId || rowIdx}
                      className="hover:bg-blue-50/30 transition-colors"
                    >
                      {/* Order number label */}
                      <td
                        className="border border-gray-200 px-2 py-1 text-center font-mono font-medium text-primary whitespace-nowrap sticky left-0 z-10 bg-white"
                        style={{ background: "white", fontSize: "0.7rem" }}
                      >
                        {row._orderNum || `#${rowIdx + 1}`}
                      </td>

                      {PREVIEW_COLUMNS.map(col => (
                        <td
                          key={col}
                          className="border border-gray-200 p-0"
                          style={{ background: getCellColor(col) || "white" }}
                        >
                          <Input
                            className="border-0 rounded-none h-8 text-xs focus:ring-1 focus:ring-primary focus:z-10 bg-transparent"
                            style={{
                              background: "transparent",
                              fontSize: "0.7rem",
                              minWidth: col.length > 20 ? 160 : 120,
                            }}
                            value={row[col] ?? ""}
                            onChange={e => updateCell(rowIdx, col, e.target.value)}
                            placeholder={MANUAL_COLUMNS.has(col) ? "Enter weight" : ""}
                          />
                        </td>
                      ))}

                      {/* Remove button */}
                      <td
                        className="border border-gray-200 px-2 py-1 text-center sticky right-0 z-10 bg-white"
                      >
                        <button
                          onClick={() => removeRow(rowIdx)}
                          className="text-red-400 hover:text-red-600 transition-colors p-1 rounded hover:bg-red-50"
                          title="Remove this row"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="px-6 py-4 border-t bg-gray-50 flex-shrink-0 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Info className="w-3.5 h-3.5" />
            <span>
              {rows.length} row(s) · The exported file will include all DTDC columns in the correct format
            </span>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleDownload}
              disabled={rows.length === 0}
              className="gap-2 bg-green-600 hover:bg-green-700 text-white"
            >
              <Download className="w-4 h-4" />
              Download Excel
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
