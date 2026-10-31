import { mobilePrintPdf } from "@/lib/mobilePrint";

// One reusable print frame. The old code added a new hidden PDF viewer for every print and
// never removed it, so a packing tab slowed down with each sheet; and a 0x0 frame parked
// off-screen is treated by Chrome/Edge as invisible and rendered at low priority. This frame
// sits inside the viewport (transparent, behind everything) and is replaced on the next print.
let frame = null;
let frameUrl = null;

export function printPdfBlob(blob, filename = "document.pdf") {
  const pdf = blob.type === "application/pdf" ? blob : new Blob([blob], { type: "application/pdf" });
  if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {
    mobilePrintPdf(pdf, filename);
    return;
  }
  if (frame) frame.remove();
  if (frameUrl) URL.revokeObjectURL(frameUrl);
  frameUrl = URL.createObjectURL(pdf);
  frame = document.createElement("iframe");
  Object.assign(frame.style, {
    position: "fixed", right: "0", bottom: "0", width: "200px", height: "200px",
    opacity: "0", pointerEvents: "none", zIndex: "-1", border: "0",
  });
  const f = frame;
  f.onload = () => setTimeout(() => {     // a moment for the PDF viewer inside the frame to start
    try {
      f.contentWindow.focus();
      f.contentWindow.print();
    } catch {
      window.open(frameUrl, "_blank");
    }
  }, 150);
  frame.src = frameUrl;
  document.body.appendChild(frame);
}
