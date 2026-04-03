import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

// Prevent scroll from changing number input values globally
document.addEventListener("wheel", (e) => {
  if (e.target.type === "number") e.target.blur();
}, { passive: true });

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
