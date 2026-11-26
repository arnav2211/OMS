// For the aggregators, the company whose pickup agent comes (booked one, else the one chosen), tagged SR / SM.
// Used by All Orders and Amazon Orders so both show e.g. "Delhivery (SR)" instead of "Shiprocket".
const AGGREGATOR_TAG = { Shiprocket: ["SR", "shiprocket"], Shipmozo: ["SM", "shipmozo"] };

export function courierLabel(o) {
  const agg = AGGREGATOR_TAG[o?.courier_name];
  if (!agg) return o?.courier_name || "Courier";
  const partner = o[`${agg[1]}_shipment`]?.courier_name || o[`${agg[1]}_courier`]?.name || o.dispatch?.courier_partner;
  return partner ? `${partner} (${agg[0]})` : o.courier_name;
}
