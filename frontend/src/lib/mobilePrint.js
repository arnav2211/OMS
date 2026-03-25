// Mobile: Share PDF via native share sheet (Web Share API)
// Desktop: Hidden iframe print

export async function mobilePrintPdf(pdfBlob, filename = "document.pdf") {
  const file = new File([pdfBlob], filename, { type: "application/pdf" });

  // Use Web Share API if available (Android Chrome, Safari 15+)
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: filename });
      return;
    } catch (err) {
      // User cancelled share or share failed — fall through to download
      if (err.name === "AbortError") return;
    }
  }

  // Fallback: download the PDF
  const blobUrl = URL.createObjectURL(pdfBlob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
}
