// How an order goes out, as the media (sticker) team sees it.
export const SHIP_FILTERS = [
  ["all", "All shipping"],
  ["office_collection", "Office collection"],
  ["courier", "Courier"],
  ["transport", "Transport"],
  ["porter", "Porter"],
  ["self_arranged", "Self-arranged"],
];

const METHOD_LABEL = {
  office_collection: "Office collection",
  courier: "Courier",
  transport: "Transport",
  porter: "Porter",
  self_arranged: "Self-arranged",
};

export function shipLabel(o) {
  const base = METHOD_LABEL[o?.method] || (o?.method ? o.method : "Shipping not set");
  if (o?.method === "courier" && o.courier) return `Courier · ${o.courier}`;
  if (o?.method === "transport" && o.transporter) return `Transport · ${o.transporter}`;
  return base;
}

export const SHIP_BADGE = {
  office_collection: "bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-200",
  courier: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300",
  transport: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300",
  porter: "bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300",
  self_arranged: "bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
};
