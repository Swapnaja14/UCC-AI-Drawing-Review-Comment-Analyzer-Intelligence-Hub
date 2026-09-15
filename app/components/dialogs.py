"""
dialogs.py — Common reusable modal dialog helpers.

Provides:
    show_confirm(parent, title, message) -> bool
    show_error(parent, title, message)
    show_info(parent, title, message)
    open_pdf_file(parent) -> str
    open_folder(parent) -> str

All functions are pure convenience wrappers around Qt's standard dialog
classes so that individual screens do not import QMessageBox / QFileDialog
directly — keeping screen files thin and the dialog logic centralised.
"""
from __future__ import annotations
from PySide6.QtWidgets import QMessageBox, QFileDialog, QWidget


def show_confirm(
    parent: QWidget | None,
    title: str,
    message: str,
) -> bool:
    """
    Show a Yes / No confirmation dialog.

    Returns
    -------
    bool
        ``True`` if the user clicked **Yes**.
    """
    reply = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


def show_error(
    parent: QWidget | None,
    title: str,
    message: str,
) -> None:
    """Display a critical error dialog."""
    QMessageBox.critical(parent, title, message)


def show_info(
    parent: QWidget | None,
    title: str,
    message: str,
) -> None:
    """Display an informational message dialog."""
    QMessageBox.information(parent, title, message)


def open_pdf_file(parent: QWidget | None = None) -> str:
    """
    Open a file-chooser filtered to PDF files.

    Returns
    -------
    str
        Selected local file path, or an empty string if cancelled.
    """
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Select PDF Drawing",
        "",
        "PDF Files (*.pdf)",
    )
    return path


def open_folder(parent: QWidget | None = None) -> str:
    """
    Open a directory-chooser dialog.

    Returns
    -------
    str
        Selected directory path, or an empty string if cancelled.
    """
    return QFileDialog.getExistingDirectory(parent, "Select Folder")


def open_multiple_pdf_or_zip_files(parent: QWidget | None = None) -> list[str]:
    """
    Open a file-chooser allowing multi-selection of PDF files and/or Zip archives.

    Returns
    -------
    list[str]
        List of selected file paths, or empty list if cancelled.
    """
    paths, _ = QFileDialog.getOpenFileNames(
        parent,
        "Select PDF Drawings or Zipped Folders",
        "",
        "PDF Files & Zip Archives (*.pdf *.zip);;PDF Files (*.pdf);;Zip Archives (*.zip);;All Files (*)",
    )
    return paths

