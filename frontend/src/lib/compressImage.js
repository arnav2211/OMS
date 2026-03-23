// Image compression utility - compresses images before upload
// Target: ~100-200KB from ~3-8MB camera images
// Max width: 1280px, quality: 0.7, output: JPEG

export async function compressImage(file) {
  // Skip non-image files (e.g. PDFs)
  if (!file.type.startsWith("image/")) return file;

  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        const MAX_WIDTH = 1280;
        const MAX_HEIGHT = 1280;
        let { width, height } = img;

        // Resize while preserving aspect ratio
        if (width > MAX_WIDTH || height > MAX_HEIGHT) {
          const ratio = Math.min(MAX_WIDTH / width, MAX_HEIGHT / height);
          width = Math.round(width * ratio);
          height = Math.round(height * ratio);
        }

        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          (blob) => {
            if (blob) {
              const compressed = new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), {
                type: "image/jpeg",
                lastModified: Date.now(),
              });
              resolve(compressed);
            } else {
              resolve(file); // fallback to original
            }
          },
          "image/jpeg",
          0.7
        );
      };
      img.onerror = () => resolve(file); // fallback
      img.src = e.target.result;
    };
    reader.onerror = () => resolve(file); // fallback
    reader.readAsDataURL(file);
  });
}
