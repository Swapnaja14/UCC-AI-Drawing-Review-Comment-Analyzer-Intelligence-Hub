"""
login_screen.py — Department-wise authentication gate (Sign In / Register).

Clean Light Theme & Enterprise Royal Blue Design System, matching the rest of
the application (Inter typography, #0F172A headings, #F8FAFC canvas, #0284C7 /
#2563EB accents, white cards with #E2E8F0 borders).

Every account is scoped to a single engineering department. After a successful
sign-in the whole application (dashboard, upload, viewer, analytics, export)
is filtered to that department.

Signals
-------
authenticated(object)
    Emitted with the active SessionTokenDTO after a successful sign-in or
    registration (registration auto signs the new user in).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFrame, QStackedWidget, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, QRegularExpression
from PySide6.QtGui import QFont, QColor, QLinearGradient, QPainter
from PySide6.QtGui import QRegularExpressionValidator

from src.infrastructure.logging.logger import get_logger

logger = get_logger("LoginScreen")

# ── Royal Blue design tokens (kept in sync with dashboard/upload screens) ──
_BG_CANVAS   = "#F8FAFC"
_CARD_BG     = "#FFFFFF"
_BORDER      = "#E2E8F0"
_TEXT_DARK   = "#0F172A"
_TEXT_MUTED  = "#64748B"
_ACCENT      = "#0284C7"
_ACCENT_HOV  = "#0EA5E9"
_ACCENT_DEEP = "#2563EB"
_SUCCESS     = "#059669"
_DANGER      = "#E11D48"

_EMAIL_RE = QRegularExpression(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _BrandPanel(QFrame):
    """Left-hand royal-blue branding panel with gradient + feature bullets."""

    _FEATURES = [
        ("📂", "Upload department drawings"),
        ("🔍", "AI markup & OCR extraction"),
        ("📊", "Department-scoped analytics"),
        ("📤", "Per-department error trackers"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BrandPanel")
        self.setFixedWidth(360)
        self.setStyleSheet("#BrandPanel { background: transparent; border: none; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 44, 36, 40)
        lay.setSpacing(0)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(12)
        logo = QLabel("📐")
        logo.setFont(QFont("Segoe UI Emoji", 26))
        logo_row.addWidget(logo)
        brand = QLabel("UCC Analyzer")
        brand.setFont(QFont("Inter", 20, QFont.Weight.Bold))
        brand.setStyleSheet("color: #FFFFFF; letter-spacing: -0.3px; background: transparent;")
        logo_row.addWidget(brand)
        logo_row.addStretch()
        lay.addLayout(logo_row)

        lay.addSpacing(28)

        head = QLabel("Drawing Review\nIntelligence Hub")
        head.setFont(QFont("Inter", 24, QFont.Weight.Bold))
        head.setStyleSheet("color: #FFFFFF; background: transparent;")
        head.setWordWrap(True)
        lay.addWidget(head)

        sub = QLabel("Sign in with your engineering department to access your drawings, analytics and reports.")
        sub.setFont(QFont("Inter", 12))
        sub.setStyleSheet("color: #CBD5E1; background: transparent;")
        sub.setWordWrap(True)
        lay.addSpacing(12)
        lay.addWidget(sub)

        lay.addStretch()

        for icon, text in self._FEATURES:
            row = QHBoxLayout()
            row.setSpacing(12)
            ic = QLabel(icon)
            ic.setFont(QFont("Segoe UI Emoji", 14))
            ic.setStyleSheet("background: transparent;")
            row.addWidget(ic)
            tx = QLabel(text)
            tx.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
            tx.setStyleSheet("color: #E2E8F0; background: transparent;")
            row.addWidget(tx)
            row.addStretch()
            wrap = QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setLayout(row)
            lay.addSpacing(10)
            lay.addWidget(wrap)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0.0, QColor("#0B2A4A"))
        grad.setColorAt(0.55, QColor("#123E6B"))
        grad.setColorAt(1.0, QColor("#0284C7"))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 14, 14)
        p.end()


class _FormField(QFrame):
    """Labelled input row with a consistent light-theme style."""

    def __init__(self, label: str, placeholder: str = "", password: bool = False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._label = QLabel(label)
        self._label.setFont(QFont("Inter", 11, QFont.Weight.DemiBold))
        self._label.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent;")
        lay.addWidget(self._label)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFixedHeight(42)
        if password:
            self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: {_CARD_BG}; color: {_TEXT_DARK}; border: 1px solid {_BORDER};"
            f" border-radius: 8px; padding: 0 12px; font-family: 'Inter'; font-size: 13px; }}"
            f"QLineEdit:focus {{ border: 1.5px solid {_ACCENT}; }}"
        )
        lay.addWidget(self.edit)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)

    def clear_field(self) -> None:
        self.edit.clear()


class LoginWindow(QWidget):
    """Standalone authentication window shown before the main application."""

    authenticated = Signal(object)   # SessionTokenDTO

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("UCC Analyzer — Sign In")
        self.setFixedSize(940, 600)
        self.setStyleSheet(f"background-color: {_BG_CANVAS};")

        self._center_on_screen()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("AuthCard")
        card.setStyleSheet(
            f"#AuthCard {{ background: {_CARD_BG}; border: 1px solid {_BORDER}; border-radius: 14px; }}"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(15, 23, 42, 28))
        shadow.setOffset(0, 6)
        card.setGraphicsEffect(shadow)

        card_lay = QHBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        card_lay.addWidget(_BrandPanel())

        form_host = QWidget()
        form_host.setStyleSheet(f"background: {_CARD_BG}; border: none;")
        card_lay.addWidget(form_host, 1)

        outer.addWidget(card, 1)

        form_root = QVBoxLayout(form_host)
        form_root.setContentsMargins(44, 34, 44, 30)
        form_root.setSpacing(0)

        # ── Mode tabs ──────────────────────────────────────────────
        self._tabs = QHBoxLayout()
        self._tabs.setSpacing(8)
        self._signin_tab = self._make_tab("Sign In", True)
        self._register_tab = self._make_tab("Register", False)
        self._signin_tab.clicked.connect(lambda: self._switch_mode(0))
        self._register_tab.clicked.connect(lambda: self._switch_mode(1))
        self._tabs.addWidget(self._signin_tab)
        self._tabs.addWidget(self._register_tab)
        self._tabs.addStretch()
        form_root.addLayout(self._tabs)
        form_root.addSpacing(14)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")
        self._stack.addWidget(self._build_signin_form())
        self._stack.addWidget(self._build_register_form())
        form_root.addWidget(self._stack, 1)

        # ── Shared status message ──────────────────────────────────
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setFont(QFont("Inter", 11))
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(f"color: {_DANGER}; background: transparent;")
        self._status.hide()
        form_root.addWidget(self._status)

        demo = QLabel("Demo:  admin / Password123!  ·  soham / Password123!  ·  reviewer / Password123!")
        demo.setFont(QFont("Inter", 10))
        demo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        demo.setStyleSheet(f"color: #94A3B8; background: transparent;")
        demo.setWordWrap(True)
        form_root.addSpacing(8)
        form_root.addWidget(demo)

        # Surface controller auth errors inside this window.
        if self._controller is not None:
            try:
                self._controller.auth_error_signal.connect(self._show_error)
            except Exception:
                pass

    # ── Construction helpers ───────────────────────────────────────

    def _center_on_screen(self):
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(sg.center() - self.rect().center())

    def _make_tab(self, text: str, active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._tab_style(active))
        return btn

    @staticmethod
    def _tab_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {_ACCENT_DEEP}; color: #FFFFFF; border: none;"
                f" border-radius: 8px; padding: 0 18px; font-family: 'Inter'; font-size: 13px; font-weight: 700; }}"
            )
        return (
            f"QPushButton {{ background: #F1F5F9; color: {_TEXT_MUTED}; border: 1px solid {_BORDER};"
            f" border-radius: 8px; padding: 0 18px; font-family: 'Inter'; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ color: {_TEXT_DARK}; background: #E2E8F0; }}"
        )

    def _primary_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(46)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT}; color: #FFFFFF; border: none; border-radius: 8px; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOV}; }}"
            f"QPushButton:disabled {{ background: #E2E8F0; color: #94A3B8; }}"
        )
        return btn

    def _build_signin_form(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._heading("Welcome back", "Sign in to your department workspace"))
        lay.addSpacing(16)

        self._si_user = _FormField("Username or Email", "you@ucc.com")
        self._si_pass = _FormField("Password", "••••••••", password=True)
        self._si_pass.edit.returnPressed.connect(self._on_signin)
        lay.addWidget(self._si_user)
        lay.addSpacing(12)
        lay.addWidget(self._si_pass)
        lay.addSpacing(20)

        self._si_btn = self._primary_button("Sign In")
        self._si_btn.clicked.connect(self._on_signin)
        lay.addWidget(self._si_btn)
        lay.addStretch()
        return w

    def _build_register_form(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._heading("Create account", "Register with your engineering department"))
        lay.addSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)

        self._rg_name = _FormField("Full Name", "Jane Doe")
        self._rg_user = _FormField("Username", "jdoe")
        self._rg_email = _FormField("Email", "jane@ucc.com")
        self._rg_email.edit.setValidator(QRegularExpressionValidator(_EMAIL_RE, self._rg_email.edit))

        self._rg_dept = QComboBox()
        self._rg_dept.setFixedHeight(42)
        self._rg_dept.setStyleSheet(
            f"QComboBox {{ background: {_CARD_BG}; color: {_TEXT_DARK}; border: 1px solid {_BORDER};"
            f" border-radius: 8px; padding: 0 12px; font-family: 'Inter'; font-size: 13px; }}"
            f"QComboBox:focus {{ border: 1.5px solid {_ACCENT}; }}"
            f"QComboBox QAbstractItemView {{ background: {_CARD_BG}; color: {_TEXT_DARK};"
            f" selection-background-color: #EFF6FF; selection-color: {_ACCENT_DEEP}; border: 1px solid {_BORDER}; }}"
        )
        dept_wrap = QFrame()
        dept_wrap.setStyleSheet("background: transparent; border: none;")
        dept_lay = QVBoxLayout(dept_wrap)
        dept_lay.setContentsMargins(0, 0, 0, 0)
        dept_lay.setSpacing(6)
        dept_lbl = QLabel("Engineering Department")
        dept_lbl.setFont(QFont("Inter", 11, QFont.Weight.DemiBold))
        dept_lbl.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent;")
        dept_lay.addWidget(dept_lbl)
        dept_lay.addWidget(self._rg_dept)

        self._rg_pass = _FormField("Password", "Min. 8 characters", password=True)
        self._rg_conf = _FormField("Confirm Password", "Re-enter password", password=True)

        grid.addWidget(self._rg_name, 0, 0)
        grid.addWidget(self._rg_user, 0, 1)
        grid.addWidget(self._rg_email, 1, 0)
        grid.addWidget(dept_wrap, 1, 1)
        grid.addWidget(self._rg_pass, 2, 0)
        grid.addWidget(self._rg_conf, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addSpacing(20)

        self._rg_btn = self._primary_button("Create Account")
        self._rg_btn.clicked.connect(self._on_register)
        lay.addWidget(self._rg_btn)
        lay.addStretch()

        self._populate_departments()
        return w

    def _heading(self, title: str, subtitle: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setFont(QFont("Inter", 22, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {_TEXT_DARK}; background: transparent;")
        s = QLabel(subtitle)
        s.setFont(QFont("Inter", 12))
        s.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent;")
        lay.addWidget(t)
        lay.addWidget(s)
        return w

    def _populate_departments(self) -> None:
        self._rg_dept.blockSignals(True)
        self._rg_dept.clear()
        self._rg_dept.addItem("Select your department…", None)
        depts = []
        if self._controller is not None:
            try:
                depts = self._controller.get_all_departments()
            except Exception as e:
                logger.warning(f"Could not load departments for registration: {e}")
        for d in depts:
            name = d.get("name") if isinstance(d, dict) else getattr(d, "name", "")
            dept_id = d.get("id") if isinstance(d, dict) else getattr(d, "id", None)
            if name:
                self._rg_dept.addItem(name, dept_id or name)
        self._rg_dept.blockSignals(False)

    # ── Mode switching ─────────────────────────────────────────────

    def _switch_mode(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._signin_tab.setStyleSheet(self._tab_style(index == 0))
        self._register_tab.setStyleSheet(self._tab_style(index == 1))
        self._hide_status()
        if index == 1:
            self._populate_departments()

    # ── Status helpers ─────────────────────────────────────────────

    def _show_error(self, msg: str) -> None:
        self._status.setText(msg or "Something went wrong.")
        self._status.setStyleSheet(f"color: {_DANGER}; background: transparent;")
        self._status.show()

    def _show_success(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(f"color: {_SUCCESS}; background: transparent;")
        self._status.show()

    def _hide_status(self) -> None:
        self._status.clear()
        self._status.hide()

    # ── Actions ────────────────────────────────────────────────────

    def _on_signin(self) -> None:
        self._hide_status()
        username = self._si_user.text()
        password = self._si_pass.edit.text()
        if not username or not password:
            self._show_error("Please enter both username/email and password.")
            return
        if self._controller is None:
            self._show_error("Authentication service unavailable.")
            return

        self._si_btn.setEnabled(False)
        self._si_btn.setText("Signing in…")
        try:
            ok = self._controller.sign_in(username, password)
        finally:
            self._si_btn.setEnabled(True)
            self._si_btn.setText("Sign In")

        if ok:
            self._emit_authenticated()

    def _on_register(self) -> None:
        self._hide_status()
        if self._controller is None:
            self._show_error("Authentication service unavailable.")
            return

        full_name = self._rg_name.text()
        username = self._rg_user.text()
        email = self._rg_email.text()
        dept_idx = self._rg_dept.currentIndex()
        dept_id = self._rg_dept.itemData(dept_idx) if dept_idx >= 0 else None
        password = self._rg_pass.edit.text()
        confirm = self._rg_conf.edit.text()

        if not full_name or not username or not email:
            self._show_error("Full name, username, and email are required.")
            return
        if not _EMAIL_RE.match(email).hasMatch():
            self._show_error("Please enter a valid email address.")
            return
        if dept_idx <= 0 or not dept_id:
            self._show_error("Please select your engineering department.")
            return
        if len(password) < 8:
            self._show_error("Password must be at least 8 characters long.")
            return
        if password != confirm:
            self._show_error("Passwords do not match.")
            return

        self._rg_btn.setEnabled(False)
        self._rg_btn.setText("Creating account…")
        try:
            ok = self._controller.register_user(
                username=username,
                display_name=full_name,
                email=email,
                password=password,
                department_id=dept_id,
            )
        finally:
            self._rg_btn.setEnabled(True)
            self._rg_btn.setText("Create Account")

        if ok:
            self._emit_authenticated()

    def _emit_authenticated(self) -> None:
        session = getattr(self._controller, "_current_session", None)
        user = getattr(session, "user", None) if session else None
        dept = getattr(user, "department_name", "Unassigned") if user else "Unassigned"
        name = (getattr(user, "display_name", None) or getattr(user, "username", "User")) if user else "User"
        self._show_success(f"Welcome, {name} · {dept}")
        logger.info(f"LoginWindow: authenticated '{getattr(user, 'username', '?')}' (dept='{dept}').")
        self.authenticated.emit(session)

    def reset(self) -> None:
        """Clear fields and return to the Sign In tab (used after sign-out)."""
        self._si_pass.clear_field()
        self._rg_pass.clear_field()
        self._rg_conf.clear_field()
        self._switch_mode(0)
