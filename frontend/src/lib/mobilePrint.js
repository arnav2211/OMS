// Mobile-safe print: renders PDF pages as images, then triggers window.print()
// Android Chrome cannot render PDFs in iframes, so we convert to images first.

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
    const scale = 2; // High resolution for print quality
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    await page.render({ canvasContext: ctx, viewport }).promise;
    imageDataUrls.push(canvas.toDataURL("image/png"));
  }

  // Open a new window with the rendered images and trigger print
  const printWindow = window.open("", "_blank");
  if (!printWindow) return; // Popup blocked fallback

  const imagesHtml = imageDataUrls
    .map((src) => `<img src="${src}" style="width:100%;page-break-after:always;display:block;" />`)
    .join("");

  printWindow.document.write(
    `<!DOCTYPE html><html><head><title>Print</title><style>@media print{body{margin:0}img{page-break-after:always;width:100%}}body{margin:0;padding:0;background:#fff}</style></head><body>${imagesHtml}<script>window.onload=function(){setTimeout(function(){window.print()},300)}<\/script></body></html>`
  );
  printWindow.document.close();
}
