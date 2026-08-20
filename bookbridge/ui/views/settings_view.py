"""Application Settings View."""

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from bookbridge.config.settings import settings


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Application Settings & Paths")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        layout.addWidget(title)

        card = QFrame()
        card.setProperty("class", "Card")
        form = QFormLayout(card)
        form.setSpacing(14)

        # Export Directory
        export_layout = QHBoxLayout()
        export_label = QLabel("Default Export Directory:")
        export_label.setStyleSheet("color: #f1f5f9;")
        self.export_dir_edit = QLineEdit(str(settings.exports_dir))
        export_layout.addWidget(self.export_dir_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.setProperty("class", "SecondaryBtn")
        browse_btn.clicked.connect(self._on_browse_export)
        export_layout.addWidget(browse_btn)
        form.addRow(export_label, export_layout)

        # Max segment characters
        max_chars_label = QLabel("Max Segment Characters (Chunk size):")
        max_chars_label.setStyleSheet("color: #f1f5f9;")
        self.max_chars_spin = QSpinBox()
        self.max_chars_spin.setRange(200, 5000)
        self.max_chars_spin.setValue(settings.max_segment_chars)
        form.addRow(max_chars_label, self.max_chars_spin)

        # Context window blocks
        ctx_label = QLabel("Context Window (Surrounding Blocks):")
        ctx_label.setStyleSheet("color: #f1f5f9;")
        self.ctx_blocks_spin = QSpinBox()
        self.ctx_blocks_spin.setRange(0, 10)
        self.ctx_blocks_spin.setValue(settings.context_window_blocks)
        form.addRow(ctx_label, self.ctx_blocks_spin)

        # Max retries
        retries_label = QLabel("Max Validation Retries:")
        retries_label.setStyleSheet("color: #f1f5f9;")
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 5)
        self.retries_spin.setValue(settings.max_validation_retries)
        form.addRow(retries_label, self.retries_spin)

        cooldown_label = QLabel("Additional Normal Request Cooldown (seconds):")
        cooldown_label.setStyleSheet("color: #f1f5f9;")
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 60.0)
        self.cooldown_spin.setSingleStep(0.05)
        self.cooldown_spin.setDecimals(2)
        self.cooldown_spin.setValue(settings.normal_request_cooldown_seconds)
        form.addRow(cooldown_label, self.cooldown_spin)

        layout.addWidget(card)

        # Save button
        save_btn = QPushButton("Save Settings")
        save_btn.setProperty("class", "PrimaryBtn")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        layout.addStretch()

    def _on_browse_export(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if dir_path:
            self.export_dir_edit.setText(dir_path)

    def _on_save(self):
        export_dir = self.export_dir_edit.text().strip()
        if not export_dir:
            QMessageBox.warning(self, "Invalid Directory", "Please select an export directory.")
            return

        settings.export_directory = export_dir
        settings.max_segment_chars = self.max_chars_spin.value()
        settings.context_window_blocks = self.ctx_blocks_spin.value()
        settings.max_validation_retries = self.retries_spin.value()
        settings.normal_request_cooldown_seconds = self.cooldown_spin.value()
        try:
            settings.save()
            settings.ensure_directories()
        except OSError as exc:
            QMessageBox.critical(self, "Settings Error", f"Could not save settings:\n{exc}")
            return
        QMessageBox.information(self, "Saved", "Settings updated successfully.")
