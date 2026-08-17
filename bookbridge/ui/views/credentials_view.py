"""API Credentials and Quota Management View."""

import asyncio
from datetime import datetime
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from bookbridge.config.constants import CredentialState, ProviderType
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.providers.gemini import GeminiProvider
from bookbridge.providers.groq import GroqProvider
from bookbridge.providers.orcarouter import OrCarRouterProvider
from bookbridge.security.keyring_manager import keyring_manager


class CredentialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add API Credential")
        self.resize(450, 300)
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Google Gemini", ProviderType.GEMINI.value)
        self.provider_combo.addItem("Groq", ProviderType.GROQ.value)
        self.provider_combo.addItem("OrCarRouter", ProviderType.ORCAROUTER.value)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("AI Provider:", self.provider_combo)

        self.name_edit = QLineEdit("Primary Key")
        form.addRow("Credential Name:", self.name_edit)

        self.model_combo = QComboBox()
        form.addRow("Model:", self.model_combo)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your API key here...")
        form.addRow("API Secret Key:", self.key_edit)

        self._on_provider_changed()
        layout.addLayout(form)

        # Test key button
        test_btn = QPushButton("Test API Key Connection")
        test_btn.setProperty("class", "SecondaryBtn")
        test_btn.clicked.connect(self._on_test_key)
        layout.addWidget(test_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_provider_changed(self):
        self.model_combo.clear()
        prov = self.provider_combo.currentData()
        if prov == ProviderType.GEMINI.value:
            models = GeminiProvider().get_supported_models()
        elif prov == ProviderType.ORCAROUTER.value:
            models = OrCarRouterProvider().get_supported_models()
        else:
            models = GroqProvider().get_supported_models()
        for m in models:
            self.model_combo.addItem(m, m)

    def _on_test_key(self):
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Missing Key", "Please enter an API key first.")
            return

        prov_val = self.provider_combo.currentData()
        model_val = self.model_combo.currentData()
        cred = ProviderCredentialMetadata(
            provider=ProviderType(prov_val),
            name=self.name_edit.text().strip(),
            model=model_val,
        )

        if prov_val == ProviderType.GEMINI.value:
            provider_inst = GeminiProvider()
        elif prov_val == ProviderType.ORCAROUTER.value:
            provider_inst = OrCarRouterProvider()
        else:
            provider_inst = GroqProvider()

        loop = asyncio.new_event_loop()
        try:
            is_valid = loop.run_until_complete(provider_inst.validate_key(cred, key))
            if is_valid:
                QMessageBox.information(self, "Success", "API Key is VALID and connected!")
            else:
                QMessageBox.warning(self, "Invalid Key", "Failed to connect. Please verify your API key.")
        finally:
            loop.close()

    def get_data(self) -> dict:
        return {
            "provider": ProviderType(self.provider_combo.currentData()),
            "name": self.name_edit.text().strip(),
            "model": self.model_combo.currentData(),
            "secret_key": self.key_edit.text().strip(),
        }


class CredentialsView(QWidget):
    def __init__(self, cred_repo: CredentialRepository):
        super().__init__()
        self.cred_repo = cred_repo
        self._setup_ui()
        self.refresh_credentials()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("API Credentials & Health Monitor")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        header.addWidget(title)
        header.addStretch()

        add_btn = QPushButton("+ Add API Key")
        add_btn.setProperty("class", "PrimaryBtn")
        add_btn.clicked.connect(self._on_add_key)
        header.addWidget(add_btn)

        layout.addLayout(header)

        # Security alert frame
        sec_card = QFrame()
        sec_card.setProperty("class", "Card")
        sec_layout = QHBoxLayout(sec_card)
        sec_lbl = QLabel(
            "🔒 <b>Secure Local Storage:</b> API keys are saved exclusively in your OS Keyring / encrypted machine vault. "
            "Secrets are never logged, never committed, and never sent to central servers."
        )
        sec_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        sec_layout.addWidget(sec_lbl)
        layout.addWidget(sec_card)

        # Credentials Table Card
        table_card = QFrame()
        table_card.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_card)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Provider", "Name", "Model", "State / Health", "Tokens Used", "Success / Failures", "Cooldown", "Action"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.table)

        layout.addWidget(table_card)

    def refresh_credentials(self):
        creds = self.cred_repo.list_credentials()
        self.table.setRowCount(len(creds))

        for r_idx, c in enumerate(creds):
            self.table.setItem(r_idx, 0, QTableWidgetItem(c.provider.value.upper()))
            self.table.setItem(r_idx, 1, QTableWidgetItem(c.name))
            self.table.setItem(r_idx, 2, QTableWidgetItem(c.model))

            # State badge item
            state_item = QTableWidgetItem(c.state.value.upper())
            self.table.setItem(r_idx, 3, state_item)

            self.table.setItem(r_idx, 4, QTableWidgetItem(f"{c.total_tokens_used:,}"))
            self.table.setItem(r_idx, 5, QTableWidgetItem(f"{c.success_count} / {c.failure_count}"))

            # Cooldown
            cd_str = "None"
            if c.cooldown_until and datetime.utcnow() < c.cooldown_until:
                remain = int((c.cooldown_until - datetime.utcnow()).total_seconds())
                cd_str = f"{remain}s remaining"
            self.table.setItem(r_idx, 6, QTableWidgetItem(cd_str))

            del_btn = QPushButton("Remove")
            del_btn.setProperty("class", "DangerBtn")
            del_btn.clicked.connect(lambda _, cred_id=c.id: self._on_delete_cred(cred_id))
            self.table.setCellWidget(r_idx, 7, del_btn)

    def _on_add_key(self):
        dlg = CredentialDialog(self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            secret = data.pop("secret_key")
            if not secret:
                QMessageBox.warning(self, "Error", "API Key cannot be empty.")
                return

            cred = ProviderCredentialMetadata(**data)
            self.cred_repo.save_credential_metadata(cred)
            
            # Save secret and verify it was saved
            save_success = keyring_manager.save_secret(cred.id, secret)
            if not save_success:
                QMessageBox.warning(self, "Warning", "Failed to save API key securely. Please try again.")
                return
            
            # Verify the secret was actually saved
            retrieved_secret = keyring_manager.get_secret(cred.id)
            if not retrieved_secret:
                QMessageBox.critical(
                    self,
                    "Error",
                    "API key was not saved properly. Please check your system's secure storage and try again.\n\nEnsure keyring service is available or that the .bookbridge directory is writable."
                )
                self.cred_repo.delete_credential(cred.id)
                return
            
            self.refresh_credentials()
            QMessageBox.information(self, "Saved", f"Credential '{cred.name}' saved securely and verified.")

    def _on_delete_cred(self, cred_id: str):
        confirm = QMessageBox.question(
            self, "Delete Key", "Remove this API key from BookBridge?", QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.cred_repo.delete_credential(cred_id)
            keyring_manager.delete_secret(cred_id)
            self.refresh_credentials()
