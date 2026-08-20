"""API Credentials and Quota Management View."""

import asyncio
from datetime import datetime, timezone
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from bookbridge.config.constants import ProviderType, PROVIDER_DEFAULT_LIMITS
from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.models.provider import ProviderCredentialMetadata
from bookbridge.providers.gemini import GeminiProvider
from bookbridge.providers.groq import GroqProvider
from bookbridge.providers.orcarouter import OrCarRouterProvider
from bookbridge.providers.tokenrouter import TokenRouterProvider
from bookbridge.security.keyring_manager import keyring_manager


PROVIDER_DETAILS = {
    ProviderType.GEMINI: ("Google Gemini", GeminiProvider),
    ProviderType.GROQ: ("Groq", GroqProvider),
    ProviderType.TOKENROUTER: ("TokenRouter", TokenRouterProvider),
    ProviderType.ORCAROUTER: ("OrCarRouter", OrCarRouterProvider),
}


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
        self.provider_combo.addItem("TokenRouter", ProviderType.TOKENROUTER.value)
        self.provider_combo.addItem("OrCarRouter", ProviderType.ORCAROUTER.value)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("AI Provider:", self.provider_combo)

        self.name_edit = QLineEdit("Primary Key")
        form.addRow("Credential Name:", self.name_edit)

        self.model_combo = QComboBox()
        form.addRow("Model:", self.model_combo)

        self.limits_info_lbl = QLabel()
        self.limits_info_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 600;")
        form.addRow("Strict Limits:", self.limits_info_lbl)

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
            self.limits_info_lbl.setText("15 RPM  |  240,000 TPM  |  500 RPD (Strict pacing)")
        elif prov == ProviderType.TOKENROUTER.value:
            models = TokenRouterProvider().get_supported_models()
            self.limits_info_lbl.setText("20 RPM  |  60,000 TPM  |  1,000 RPD")
        elif prov == ProviderType.ORCAROUTER.value:
            models = OrCarRouterProvider().get_supported_models()
            self.limits_info_lbl.setText("20 RPM  |  60,000 TPM  |  1,000 RPD")
        else:
            models = GroqProvider().get_supported_models()
            self.limits_info_lbl.setText("30 RPM  |  8,000 TPM (Strict token pacing)  |  8,000 RPD")
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
        elif prov_val == ProviderType.TOKENROUTER.value:
            provider_inst = TokenRouterProvider()
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
            "🔒 <b>Secure Local Storage & Pacing:</b> API keys are saved exclusively in your OS Keyring / encrypted machine vault. "
            "Strict RPM/TPM/RPD rate-limit pacing prevents quota exhaustion across Gemini, Groq, and TokenRouter."
        )
        sec_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        sec_layout.addWidget(sec_lbl)
        layout.addWidget(sec_card)

        # Provider hierarchy monitor
        table_card = QFrame()
        table_card.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_card)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Provider / API Key", "Status", "Details", "Action"])
        self.tree.setColumnWidth(0, 240)
        self.tree.setColumnWidth(1, 150)
        self.tree.setColumnWidth(2, 560)
        self.tree.setColumnWidth(3, 90)
        self.tree.setAlternatingRowColors(True)
        table_layout.addWidget(self.tree)

        layout.addWidget(table_card)

    def refresh_credentials(self):
        creds = self.cred_repo.list_credentials()
        grouped = {provider: [] for provider in PROVIDER_DETAILS}
        for cred in creds:
            grouped.setdefault(cred.provider, []).append(cred)

        self.tree.clear()
        for provider, (label, provider_class) in PROVIDER_DETAILS.items():
            limits = PROVIDER_DEFAULT_LIMITS[provider]
            root = QTreeWidgetItem([
                label,
                "",
                f"{limits['rpm']} RPM | {limits['tpm']:,} TPM | {limits['rpd']:,} RPD",
                "",
            ])
            self.tree.addTopLevelItem(root)

            key_node = QTreeWidgetItem(["API Key", "", f"{len(grouped[provider])} configured", ""])
            root.addChild(key_node)
            for cred in grouped[provider]:
                status = "AVAILABLE" if cred.is_available else cred.state.value.upper()
                cooldown = ""
                if cred.cooldown_until:
                    remaining = int((cred.cooldown_until - datetime.now(timezone.utc)).total_seconds())
                    if remaining > 0:
                        cooldown = f" | Cooldown: {remaining}s"
                key_item = QTreeWidgetItem([
                    cred.name,
                    status,
                    f"Model: {cred.model} | Tokens: {cred.total_tokens_used:,} | "
                    f"Success/failures: {cred.success_count}/{cred.failure_count}{cooldown}",
                    "",
                ])
                key_node.addChild(key_item)
                delete_button = QPushButton("Delete")
                delete_button.setProperty("class", "DangerBtn")
                delete_button.clicked.connect(lambda _, cred_id=cred.id: self._on_delete_cred(cred_id))
                self.tree.setItemWidget(key_item, 3, delete_button)

            root.addChild(QTreeWidgetItem([
                "Base URL", "", getattr(provider_class, "BASE_URL", "Provider-managed endpoint"), ""
            ]))
            status_text = "No credentials configured" if not grouped[provider] else ", ".join(
                f"{cred.name}: {cred.state.value}" for cred in grouped[provider]
            )
            root.addChild(QTreeWidgetItem(["Status", "", status_text, ""]))

            models_node = QTreeWidgetItem(["Models", "", "Supported models", ""])
            root.addChild(models_node)
            for model in provider_class().get_supported_models():
                models_node.addChild(QTreeWidgetItem([model, "SUPPORTED", "", ""]))

            root.setExpanded(bool(grouped[provider]))

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
