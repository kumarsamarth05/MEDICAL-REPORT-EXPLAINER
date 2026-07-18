"""
nlp/extractor.py

Extracts raw text from an uploaded medical report file.
Supports:
  - PDF   -> PyMuPDF (fitz)
  - Images (jpg/png/scanned) -> EasyOCR, with a Tesseract fallback

Heavy libraries (fitz, easyocr) are imported lazily inside functions so the
rest of the app can still run / be imported even if those aren't installed yet.
"""

import os

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
SUPPORTED_PDF_EXTS = {".pdf"}

_easyocr_reader = None  # lazy singleton so the OCR model loads only once


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF using PyMuPDF. Falls back page-by-page OCR
    is NOT attempted here (assumes text-based PDF, not scanned)."""
    import fitz  # PyMuPDF

    text_chunks = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_chunks.append(page.get_text())
    return "\n".join(text_chunks)


def extract_text_from_image(file_path: str) -> str:
    """Extract text from an image using EasyOCR (falls back to pytesseract)."""
    global _easyocr_reader
    try:
        import easyocr

        if _easyocr_reader is None:
            _easyocr_reader = easyocr.Reader(["en"], gpu=False)
        results = _easyocr_reader.readtext(file_path, detail=0)
        return "\n".join(results)
    except Exception:
        # Fallback to pytesseract if easyocr isn't available/fails
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(file_path))


def extract_text(file_path: str) -> str:
    """Dispatch to the correct extractor based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in SUPPORTED_PDF_EXTS:
        text = extract_text_from_pdf(file_path)
        # If the PDF was actually a scanned image with no embedded text,
        # PyMuPDF will return an (almost) empty string. In that case, we
        # could rasterize + OCR each page — omitted here for simplicity.
        return text

    if ext in SUPPORTED_IMAGE_EXTS:
        return extract_text_from_image(file_path)

    raise ValueError(f"Unsupported file type: {ext}")
