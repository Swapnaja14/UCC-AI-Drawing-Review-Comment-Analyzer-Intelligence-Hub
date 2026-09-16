"""
src/infrastructure/pdf/pymupdf_adapter.py
PyMuPDF (fitz) implementation of IPDFLoader interface.
"""

import hashlib
from pathlib import Path
from typing import List, Dict, Any
import pymupdf as fitz

from src.core.interfaces.pdf_loader import IPDFLoader
from src.core.dtos.pdf_dtos import PDFDocumentDTO, PageMetadataDTO, RenderedPageDTO
from src.core.exceptions.pdf_exceptions import (
    PDFNotFoundError,
    CorruptedPDFError,
    EncryptedPDFError,
    InvalidPageError,
    PDFProcessingError
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger("PyMuPDFAdapter")


class PyMuPDFAdapter(IPDFLoader):
    """
    Concrete adapter wrapping PyMuPDF engine for drawing operations.
    """

    def load_document(self, file_path: Path) -> PDFDocumentDTO:
        """Loads and extracts document & page metadata using PyMuPDF."""
        file_path = Path(file_path).resolve()
        if not file_path.exists() or not file_path.is_file():
            logger.error(f"File not found: {file_path}")
            raise PDFNotFoundError(f"PDF file does not exist: {file_path}")

        try:
            doc = fitz.open(file_path)
        except fitz.FileDataError as e:
            logger.error(f"Corrupted PDF file {file_path}: {e}")
            raise CorruptedPDFError(f"Failed to open corrupted PDF file: {file_path}") from e
        except Exception as e:
            logger.error(f"Unexpected error opening PDF {file_path}: {e}")
            raise PDFProcessingError(f"Unexpected error loading PDF: {e}") from e

        try:
            if doc.is_encrypted:
                logger.warning(f"Encrypted PDF detected: {file_path}")
                raise EncryptedPDFError(f"PDF is encrypted or password-protected: {file_path}")

            file_size = file_path.stat().st_size
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            sha256_hash = hasher.hexdigest()

            pages_metadata: List[PageMetadataDTO] = []
            scanned_page_count = 0

            for i, page in enumerate(doc):
                page_num = i + 1
                rect = page.rect
                width_pt = rect.width
                height_pt = rect.height
                aspect_ratio = width_pt / height_pt if height_pt > 0 else 1.0

                text_content = page.get_text("text").strip()
                char_count = len(text_content)
                has_native_text = char_count > 20  # Threshold for native text

                if not has_native_text:
                    scanned_page_count += 1

                pages_metadata.append(
                    PageMetadataDTO(
                        page_number=page_num,
                        width_pt=width_pt,
                        height_pt=height_pt,
                        aspect_ratio=aspect_ratio,
                        has_native_text=has_native_text,
                        text_character_count=char_count,
                        orientation_deg=page.rotation
                    )
                )

            total_pages = len(doc)
            is_scanned = (scanned_page_count / total_pages > 0.5) if total_pages > 0 else True
            metadata = doc.metadata or {}

            logger.info(f"Loaded PDF '{file_path.name}' ({total_pages} pages, Scanned={is_scanned})")

            return PDFDocumentDTO(
                file_path=file_path,
                file_name=file_path.name,
                file_size_bytes=file_size,
                file_hash_sha256=sha256_hash,
                total_pages=total_pages,
                is_encrypted=False,
                is_scanned=is_scanned,
                title=metadata.get("title"),
                author=metadata.get("author"),
                pages=pages_metadata
            )
        finally:
            doc.close()

    def render_page_image(self, file_path: Path, page_number: int, dpi: int = 300) -> RenderedPageDTO:
        """Renders page at target DPI using PyMuPDF pixmap rendering."""
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise PDFNotFoundError(f"File not found: {file_path}")

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise CorruptedPDFError(f"Failed to open PDF for rendering: {e}") from e

        try:
            if page_number < 1 or page_number > len(doc):
                raise InvalidPageError(f"Page number {page_number} out of bounds (1-{len(doc)})")

            page = doc.load_page(page_number - 1)
            # Zoom matrix derived from target DPI (72 DPI default)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            image_bytes = pix.tobytes("png")

            logger.info(f"Rendered page {page_number} of '{file_path.name}' at {dpi} DPI ({pix.width}x{pix.height} px)")

            return RenderedPageDTO(
                page_number=page_number,
                width_px=pix.width,
                height_px=pix.height,
                dpi=dpi,
                image_bytes=image_bytes,
                format="PNG"
            )
        finally:
            doc.close()

    def extract_page_text_blocks(self, file_path: Path, page_number: int) -> List[Dict[str, Any]]:
        """Extracts native text blocks with coordinates (x0, y0, x1, y1)."""
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise PDFNotFoundError(f"File not found: {file_path}")

        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise CorruptedPDFError(f"Failed to open PDF: {e}") from e

        try:
            if page_number < 1 or page_number > len(doc):
                raise InvalidPageError(f"Page number {page_number} out of range (1-{len(doc)})")

            page = doc.load_page(page_number - 1)
            blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)

            extracted_blocks = []
            for b in blocks:
                if len(b) >= 5 and b[4].strip():
                    extracted_blocks.append({
                        "bbox": (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                        "text": b[4].strip(),
                        "block_no": b[5] if len(b) > 5 else 0
                    })

            return extracted_blocks
        finally:
            doc.close()
