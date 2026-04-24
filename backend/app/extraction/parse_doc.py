"""Route an uploaded file to text and/or image content parts for the LLM.

Strategy:
- PDF: extract text with pypdf. If text density is low (likely scanned),
  also rasterize first 2 pages and include as image parts.
- DOCX: extract text with python-docx.
- Image: pass through as an image part.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path

from app.extraction.llm_client import image_part_from_path, text_part

log = logging.getLogger(__name__)

IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PDF_MIMES = {"application/pdf"}
DOCX_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

MIN_TEXT_CHARS = 200  # below this we assume scanned PDF


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        return mime
    ext = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")


def parse_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception as e:
            log.warning("pypdf extract_text failed: %s", e)
    return "\n".join(chunks).strip()


def rasterize_pdf(path: Path, max_pages: int = 2) -> list[Path]:
    """Convert first N pages of a PDF to images on disk. Returns image paths."""
    try:
        from pdf2image import convert_from_path
    except Exception as e:
        log.warning("pdf2image unavailable (%s) — skipping rasterization", e)
        return []

    out_paths: list[Path] = []
    try:
        images = convert_from_path(
            str(path), first_page=1, last_page=max_pages, dpi=150)
    except Exception as e:
        log.warning("pdf2image convert_from_path failed: %s", e)
        return []

    for i, img in enumerate(images):
        out = path.with_suffix("").with_name(f"{path.stem}_page{i + 1}.png")
        img.save(out, "PNG")
        out_paths.append(out)
    return out_paths


def parse_docx_text(path: Path) -> str:
    from docx import Document  # python-docx

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def build_user_parts(path: Path, mime: str | None = None) -> list[dict]:
    """Return a list of OpenAI-style content parts for the given file."""
    mime = mime or guess_mime(path)
    parts: list[dict] = []
    if mime in IMAGE_MIMES:
        parts.append(
            text_part("The following image is the candidate's resume:"))
        parts.append(image_part_from_path(path))
        return parts
    if mime in DOCX_MIMES:
        text = parse_docx_text(path)
        parts.append(text_part("Resume (DOCX, plain text):\n\n" + text))
        return parts
    if mime in PDF_MIMES:
        text = parse_pdf_text(path)
        if len(text) >= MIN_TEXT_CHARS:
            parts.append(text_part("Resume (PDF, extracted text):\n\n" + text))
            return parts
        # Scanned-looking PDF — rasterize first pages
        image_paths = rasterize_pdf(path)
        if not image_paths:
            # Last resort: give whatever text we did get
            parts.append(
                text_part(
                    "Resume (PDF, low-text-density, extraction may be incomplete):\n\n" + text
                )
            )
            return parts
        parts.append(
            text_part("Resume (scanned PDF, images of first pages follow):"))
        for p in image_paths:
            parts.append(image_part_from_path(p))
        return parts
    # Unknown — try as text
    try:
        parts.append(text_part(path.read_text(
            encoding="utf-8", errors="ignore")))
    except Exception:
        parts.append(text_part(f"(could not parse file of type {mime})"))
    return parts


async def build_user_parts_async(path: Path, mime: str | None = None) -> list[dict]:
    """Async variant that offloads parsing/rasterization to worker threads.

    This avoids CPU-bound PDF processing from blocking the FastAPI event loop.
    """

    mime = mime or guess_mime(path)
    parts: list[dict] = []

    if mime in IMAGE_MIMES:
        parts.append(
            text_part("The following image is the candidate's resume:"))
        parts.append(await asyncio.to_thread(image_part_from_path, path))
        return parts

    if mime in DOCX_MIMES:
        text = await asyncio.to_thread(parse_docx_text, path)
        parts.append(text_part("Resume (DOCX, plain text):\n\n" + text))
        return parts

    if mime in PDF_MIMES:
        text = await asyncio.to_thread(parse_pdf_text, path)
        if len(text) >= MIN_TEXT_CHARS:
            parts.append(text_part("Resume (PDF, extracted text):\n\n" + text))
            return parts

        image_paths = await asyncio.to_thread(rasterize_pdf, path)
        if not image_paths:
            parts.append(
                text_part(
                    "Resume (PDF, low-text-density, extraction may be incomplete):\n\n" + text
                )
            )
            return parts

        parts.append(
            text_part("Resume (scanned PDF, images of first pages follow):"))
        for image_path in image_paths:
            parts.append(await asyncio.to_thread(image_part_from_path, image_path))
        return parts

    try:
        text = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="ignore")
        parts.append(text_part(text))
    except Exception:
        parts.append(text_part(f"(could not parse file of type {mime})"))
    return parts
