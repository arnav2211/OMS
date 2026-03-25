// Mobile-safe print: renders PDF pages as images, then triggers native print.
// Android Chrome cannot render PDFs in iframes, so we convert to images first.
// Uses an approach that avoids popup blockers on mobile.

export async function mobilePrintPdf(pdfBlob) {
  const arrayBuffer = await pdfBlob.arrayBuffer();
  const pdfjsLib = await import("pdfjs-dist/build/pdf.mjs");
  pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.mjs",
    import.meta.url
  ).toString();

  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const numPages = pdf.numPages;
  const imageDataUrls = [];

  for (let i = 1; i <= numPages; i++) {
    const page = await pdf.getPage(i);
    const scale = 2;
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    await page.render({ canvasContext: ctx, viewport }).promise;
    imageDataUrls.push(canvas.toDataURL("image/png"));
  }

  const imagesHtml = imageDataUrls
    .map(
      (src, i) =>
        `<img src="${src}" style="width:100%;max-width:100%;display:block;${i < imageDataUrls.length - 1 ? "page-break-after:always;" : ""}" />`
    )
    .join("");

  const htmlContent = `<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Print</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#fff}img{width:100%;height:auto;display:block}@media print{body{margin:0}img{width:100%;page-break-inside:avoid}img:last-child{page-break-after:auto}}</style></head><body>${imagesHtml}</body></html>`;

  // Strategy 1: Try window.open first (works on most desktop + some mobile)
  let printWindow = window.open("", "_blank");
  if (printWindow) {
    printWindow.document.write(htmlContent);
    printWindow.document.close();
    // Wait for images to load before printing
    printWindow.onload = () => {
      setTimeout(() => {
        try {
          printWindow.focus();
          printWindow.print();
        } catch {
          // If print() fails, the user can still manually print from the new tab
        }
      }, 500);
    };
    // Fallback: if onload doesn't fire, try after a delay
    setTimeout(() => {
      try {
        printWindow.focus();
        printWindow.print();
      } catch {
        // Silently fail — window is already open with content
      }
    }, 1500);
    return;
  }

  // Strategy 2: Popup blocked — use an iframe in the current page
  const iframe = document.createElement("iframe");
  iframe.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;z-index:99999;border:none;background:#fff";
  document.body.appendChild(iframe);

  const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
  iframeDoc.open();
  iframeDoc.write(htmlContent);
  iframeDoc.close();

  // Add a close button for mobile
  const closeBtn = iframeDoc.createElement("button");
  closeBtn.textContent = "Close";
  closeBtn.style.cssText = "position:fixed;top:10px;right:10px;z-index:100000;padding:8px 20px;background:#333;color:#fff;border:none;border-radius:6px;font-size:16px;cursor:pointer";
  closeBtn.onclick = () => document.body.removeChild(iframe);
  iframeDoc.body.appendChild(closeBtn);

  // Add a print button for mobile
  const printBtn = iframeDoc.createElement("button");
  printBtn.textContent = "Print / Save PDF";
  printBtn.style.cssText = "position:fixed;top:10px;left:10px;z-index:100000;padding:8px 20px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:16px;cursor:pointer";
  printBtn.onclick = () => {
    try {
      iframe.contentWindow.focus();
      iframe.contentWindow.print();
    } catch {
      window.print();
    }
  };
  iframeDoc.body.appendChild(printBtn);

  // Auto-trigger print after a delay
  setTimeout(() => {
    try {
      iframe.contentWindow.focus();
      iframe.contentWindow.print();
    } catch {
      // Fallback: user can use the print button
    }
  }, 800);
}
