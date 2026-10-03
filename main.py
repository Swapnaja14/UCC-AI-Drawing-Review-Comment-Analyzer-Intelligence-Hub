"""
main.py — Entry point for UCC AI Drawing Review Comment Analyzer.

Run:
    python main.py
"""
import sys
import os

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
