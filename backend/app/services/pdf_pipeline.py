import pymupdf as fitz

from app.config import settings


def pdf_to_ordered_images(pdf_path: str, output_dir: str, dpi: int | None = None) -> list[str]:
    """Convert PDF pages to ordered PNG images (TechDoc §4)."""
    dpi = dpi or settings.pdf_dpi
    doc = fitz.open(pdf_path)
    image_paths: list[str] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        out_path = f"{output_dir}/page_{i + 1:03d}.png"
        pix.save(out_path)
        image_paths.append(out_path)
    doc.close()
    return image_paths
