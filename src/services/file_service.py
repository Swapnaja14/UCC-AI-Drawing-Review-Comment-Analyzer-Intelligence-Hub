"""
src/services/file_service.py
Service handling file validation, size limits, SHA-256 hashing, and temp directory management.
"""

import hashlib
import zipfile
from pathlib import Path
from typing import Optional, List
import tempfile
import shutil

from src.core.dtos.workflow_dtos import FileValidationResultDTO
from src.core.exceptions.workflow_exceptions import (
    FileHandlingError,
    InvalidFileExtensionError,
    FileTooLargeError
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger("FileService")

MAX_FILE_SIZE_MB = 500.0  # 500 MB maximum limit for engineering PDFs


class FileService:
    """
    Application Service responsible for file handling, validation, hashing,
    zip extraction, and temporary workspace directory management.
    """

    def __init__(self, max_size_mb: float = MAX_FILE_SIZE_MB) -> None:
        self.max_size_mb = max_size_mb
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)

    def extract_zip_archive(self, zip_path: str | Path) -> List[Path]:
        """
        Safely extracts a .zip archive into the application temp workspace directory
        with explicit Zip Slip (Path Traversal) safety validation, discovering all valid .pdf drawings.

        Args:
            zip_path: Path to the .zip archive on disk.

        Returns:
            List[Path]: Discovered PDF file paths inside extracted workspace.
        """
        path = Path(zip_path).resolve()
        if not path.exists() or not path.is_file():
            logger.error(f"Zip archive not found: {path}")
            return []

        if path.suffix.lower() != ".zip":
            logger.warning(f"File '{path.name}' is not a .zip archive.")
            return []

        temp_workspace = self.get_app_temp_dir() / f"zip_extract_{path.stem}_{int(path.stat().st_mtime)}"
        temp_workspace.mkdir(parents=True, exist_ok=True)
        resolved_temp = temp_workspace.resolve()

        extracted_pdfs: List[Path] = []
        try:
            with zipfile.ZipFile(path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    # ── Zip Slip / Path Traversal Security Check ──────────────────
                    target_path = (resolved_temp / member.filename).resolve()
                    try:
                        target_path.relative_to(resolved_temp)
                    except ValueError:
                        logger.error(f"SECURITY ALERT: Blocked Zip Slip path traversal attempt: '{member.filename}' in {path.name}")
                        continue

                    # Filter out directory entries and hidden/macOS metadata entries
                    if member.is_dir() or member.filename.startswith("._") or "__MACOSX" in member.filename:
                        continue

                    # Only extract PDF files into target folder
                    if member.filename.lower().endswith(".pdf"):
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(member) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        extracted_pdfs.append(target_path)

            logger.info(f"Safely extracted {len(extracted_pdfs)} PDF drawing(s) from zip '{path.name}' into {temp_workspace}")
        except zipfile.BadZipFile as bzf:
            logger.error(f"Corrupted or invalid zip file '{path.name}': {bzf}")
        except Exception as e:
            logger.error(f"Failed to extract zip archive '{path.name}': {e}")

        return extracted_pdfs

    def inspect_zip_archive(self, zip_path: str | Path) -> dict:
        """
        Inspects a .zip archive without extracting to disk, returning detailed
        file breakdown, PDF drawing count, skipped files, and Zip Slip risk status.
        """
        path = Path(zip_path).resolve()
        if not path.exists() or not path.is_file() or path.suffix.lower() != ".zip":
            return {
                "zip_name": path.name if path.exists() else "Invalid ZIP",
                "total_files": 0,
                "pdf_files": [],
                "skipped_files": [],
                "total_size_mb": 0.0,
                "is_corrupted": True,
                "has_path_traversal_risk": False,
            }

        size_mb = round(path.stat().st_size / (1024 * 1024), 2)
        pdf_files: List[str] = []
        skipped_files: List[str] = []
        has_traversal_risk = False
        is_corrupted = False

        try:
            with zipfile.ZipFile(path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    # Check path traversal
                    if ".." in member.filename or member.filename.startswith("/") or member.filename.startswith("\\"):
                        has_traversal_risk = True

                    if member.is_dir() or member.filename.startswith("._") or "__MACOSX" in member.filename:
                        continue

                    if member.filename.lower().endswith(".pdf"):
                        pdf_files.append(Path(member.filename).name)
                    else:
                        skipped_files.append(Path(member.filename).name)
        except zipfile.BadZipFile:
            is_corrupted = True
        except Exception:
            is_corrupted = True

        return {
            "zip_name": path.name,
            "total_files": len(pdf_files) + len(skipped_files),
            "pdf_files": pdf_files,
            "skipped_files": skipped_files,
            "total_size_mb": size_mb,
            "is_corrupted": is_corrupted,
            "has_path_traversal_risk": has_traversal_risk,
        }

    def expand_file_sources(self, file_paths: List[str | Path]) -> List[Path]:
        """
        Takes a list of file paths (which may include single PDFs, multiple PDFs, and .zip archives),
        extracts all zip archives, and returns a deduplicated list of resolved PDF file paths.

        Args:
            file_paths: List of file paths.

        Returns:
            List[Path]: Flattened list of valid PDF file paths.
        """
        resolved_pdfs: List[Path] = []
        seen_hashes = set()

        for f_path in file_paths:
            p = Path(f_path).resolve()
            if not p.exists():
                continue

            if p.suffix.lower() == ".zip":
                extracted = self.extract_zip_archive(p)
                for pdf_p in extracted:
                    if pdf_p.exists() and pdf_p.is_file():
                        file_hash = self.compute_sha256(pdf_p)
                        if file_hash not in seen_hashes:
                            seen_hashes.add(file_hash)
                            resolved_pdfs.append(pdf_p)
            elif p.suffix.lower() == ".pdf":
                file_hash = self.compute_sha256(p)
                if file_hash not in seen_hashes:
                    seen_hashes.add(file_hash)
                    resolved_pdfs.append(p)
            elif p.is_dir():
                for sub_pdf in sorted(p.rglob("*.pdf")):
                    if sub_pdf.is_file() and not sub_pdf.name.startswith("._"):
                        file_hash = self.compute_sha256(sub_pdf)
                        if file_hash not in seen_hashes:
                            seen_hashes.add(file_hash)
                            resolved_pdfs.append(sub_pdf)

        return resolved_pdfs

    def validate_pdf_file(self, file_path: str | Path) -> FileValidationResultDTO:
        """
        Validates an uploaded PDF drawing file path.

        Args:
            file_path: Path to the PDF file on disk.

        Returns:
            FileValidationResultDTO: Validation result container.
        """
        path = Path(file_path).resolve()
        logger.info(f"Validating PDF file: {path}")

        if not path.exists() or not path.is_file():
            logger.error(f"File not found: {path}")
            return FileValidationResultDTO(
                file_path=path,
                is_valid=False,
                file_name=path.name,
                file_size_mb=0.0,
                file_hash_sha256="",
                error_message=f"File does not exist: {path.name}"
            )

        if path.suffix.lower() != ".pdf":
            logger.error(f"Invalid file extension: {path.suffix}")
            return FileValidationResultDTO(
                file_path=path,
                is_valid=False,
                file_name=path.name,
                file_size_mb=round(path.stat().st_size / (1024 * 1024), 2),
                file_hash_sha256="",
                error_message=f"Invalid file format '{path.suffix}'. Only .pdf drawings are supported."
            )

        file_size = path.stat().st_size
        if file_size == 0:
            logger.error(f"Empty PDF file: {path}")
            return FileValidationResultDTO(
                file_path=path,
                is_valid=False,
                file_name=path.name,
                file_size_mb=0.0,
                file_hash_sha256="",
                error_message="Uploaded PDF file is 0 bytes (empty)."
            )

        if file_size > self.max_size_bytes:
            size_mb = round(file_size / (1024 * 1024), 2)
            logger.error(f"File exceeds size limit ({size_mb} MB > {self.max_size_mb} MB)")
            return FileValidationResultDTO(
                file_path=path,
                is_valid=False,
                file_name=path.name,
                file_size_mb=size_mb,
                file_hash_sha256="",
                error_message=f"File size ({size_mb} MB) exceeds maximum allowed limit ({self.max_size_mb} MB)."
            )

        # Compute SHA-256 hash
        file_hash = self.compute_sha256(path)
        size_mb = round(file_size / (1024 * 1024), 2)

        logger.info(f"File '{path.name}' is valid ({size_mb} MB, SHA-256: {file_hash[:8]})")
        return FileValidationResultDTO(
            file_path=path,
            is_valid=True,
            file_name=path.name,
            file_size_mb=size_mb,
            file_hash_sha256=file_hash
        )

    def compute_sha256(self, file_path: Path) -> str:
        """Computes SHA-256 digest of file content in chunks."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_app_temp_dir(self) -> Path:
        """Creates and returns the application temp workspace directory."""
        temp_dir = Path(tempfile.gettempdir()) / "UCCAnalyzer" / "cache"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def get_managed_drawings_dir(self) -> Path:
        """Creates and returns managed persistent application storage directory for drawings."""
        from src.config import PROJECT_ROOT
        storage_dir = (PROJECT_ROOT / "data" / "drawings").resolve()
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    def copy_to_managed_storage(self, file_path: str | Path) -> Path:
        """
        Copies a PDF file into managed persistent application storage,
        returning the persistent Path.
        """
        source = Path(file_path).resolve()
        if not source.exists() or not source.is_file():
            return source

        managed_dir = self.get_managed_drawings_dir()
        file_hash = self.compute_sha256(source)
        safe_name = source.name.replace(" ", "_")
        target_name = f"{file_hash[:12]}_{safe_name}"
        target_path = managed_dir / target_name

        if source.resolve() != target_path.resolve():
            if not target_path.exists():
                shutil.copy2(source, target_path)
            return target_path

        return source


