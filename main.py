"""
main.py — Entry point for UCC AI Drawing Review Comment Analyzer.

Run:
    python main.py
"""
import sys
import os

# Crucial Windows DLL fix: torch and OpenMP runtime must load before PySide6/Qt6 DLLs
try:
    import torch  # noqa: F401
except Exception:
    pass

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QFontDatabase

from app.theme import ThemeManager
from app.screens.splash_screen import SplashScreen
from app.main_window import MainWindow
from app.screens.login_screen import LoginWindow
from app.controllers.app_controller import AppController
from src.infrastructure.logging.logger import get_logger

logger = get_logger("Main")


def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """Catch-all exception handler to log crashes and prevent silent desktop termination."""
    import traceback
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.critical(f"Unhandled application exception:\n{err_msg}")
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = _global_exception_handler


def main():
    # ── HiDPI & platform setup ────────────────────────────────────
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("UCC Analyzer")
    app.setApplicationDisplayName("UCC AI Drawing Review Comment Analyzer")
    app.setOrganizationName("UCC Engineering")

    # ── Font setup ────────────────────────────────────────────────
    font = QFont("Segoe UI Variable", 14)
    app.setFont(font)

    # ── Theme ─────────────────────────────────────────────────────
    theme = ThemeManager(app)
    theme.apply("dark")          # default dark theme

    # ── Splash ────────────────────────────────────────────────────
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    # ── Backend Controller ─────────────────────────────────────────
    controller = AppController()

    login = LoginWindow(controller=controller)
    main_window_holder = {'window': None}

    def _open_main_window(_session=None):
        login.hide()
        main_window_holder['window'] = MainWindow(theme_manager=theme, controller=controller)
        main_window_holder['window'].logout_requested.connect(_on_logout)
        main_window_holder['window'].show()

    def _on_logout():
        controller.sign_out()
        if main_window_holder['window']:
            main_window_holder['window'].close()
            main_window_holder['window'].deleteLater()
            main_window_holder['window'] = None
        login.reset()
        login.show()

    login.authenticated.connect(_open_main_window)

    def _launch():
        splash.close()
        login.show()

    QTimer.singleShot(2200, _launch)    # 2.2 s splash

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
