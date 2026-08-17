"""Modern Sleek Dark Theme Stylesheet for BookBridge."""

DARK_THEME_QSS = """
/* Global Window Styling */
QMainWindow, QWidget#CentralWidget {
    background-color: #0f1117;
    color: #f1f5f9;
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 13px;
}

/* Sidebar Navigation */
QFrame#Sidebar {
    background-color: #161922;
    border-right: 1px solid #232736;
    min-width: 220px;
    max-width: 220px;
}

QLabel#AppTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
    padding: 16px 12px 6px 12px;
}

QLabel#AppSubtitle {
    color: #818cf8;
    font-size: 11px;
    font-weight: 600;
    padding: 0 12px 16px 12px;
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #94a3b8;
    font-size: 13px;
    font-weight: 600;
    text-align: left;
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px 8px;
    border: none;
}

QPushButton.NavBtn:hover {
    background-color: #1e2230;
    color: #f1f5f9;
}

QPushButton.NavBtn:checked, QPushButton.NavBtn[active="true"] {
    background-color: #4f46e5;
    color: #ffffff;
}

/* Cards & Containers */
QFrame.Card {
    background-color: #161922;
    border: 1px solid #232736;
    border-radius: 12px;
    padding: 16px;
}

QFrame.StatCard {
    background-color: #1a1e2b;
    border: 1px solid #282e42;
    border-radius: 10px;
    padding: 12px;
}

QLabel.CardTitle {
    color: #f8fafc;
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 8px;
}

QLabel.StatValue {
    color: #6366f1;
    font-size: 24px;
    font-weight: 800;
}

QLabel.StatLabel {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 500;
}

/* Buttons */
QPushButton.PrimaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 18px;
    border-radius: 8px;
    border: none;
}

QPushButton.PrimaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4338ca, stop:1 #4f46e5);
}

QPushButton.SecondaryBtn {
    background-color: #1e2230;
    color: #cbd5e1;
    font-size: 13px;
    font-weight: 500;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid #2d3448;
}

QPushButton.SecondaryBtn:hover {
    background-color: #282e42;
    color: #ffffff;
}

QPushButton.DangerBtn {
    background-color: #ef4444;
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 8px;
    border: none;
}

QPushButton.DangerBtn:hover {
    background-color: #dc2626;
}

QPushButton.SuccessBtn {
    background-color: #10b981;
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: 8px;
    border: none;
}

QPushButton.SuccessBtn:hover {
    background-color: #059669;
}

/* Form Controls */
QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #1a1e2b;
    color: #f1f5f9;
    border: 1px solid #282e42;
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: #6366f1;
}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #6366f1;
    background-color: #1e2333;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

/* Tables & Lists */
QTableWidget, QTreeWidget, QListWidget {
    background-color: #13161f;
    color: #f1f5f9;
    border: 1px solid #232736;
    border-radius: 8px;
    gridline-color: #1e2230;
    selection-background-color: #2e354f;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #1a1e2b;
    color: #cbd5e1;
    font-weight: 600;
    font-size: 12px;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #282e42;
}

QTableWidget::item {
    padding: 6px 10px;
}

/* Progress Bar */
QProgressBar {
    background-color: #1e2230;
    border: none;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    height: 18px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #06b6d4);
    border-radius: 6px;
}

/* ScrollBars */
QScrollBar:vertical {
    background: #13161f;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #282e42;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #3e4765;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Status Badges */
QLabel.BadgeSuccess {
    background-color: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel.BadgeWarning {
    background-color: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel.BadgeDanger {
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}
"""
