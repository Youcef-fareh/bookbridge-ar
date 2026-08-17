"""Glossary & Terminology Manager View."""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from bookbridge.config.constants import GlossaryCategory, MatchType
from bookbridge.database.repositories.glossary_repo import GlossaryRepository
from bookbridge.glossary.importer_exporter import (
    export_glossary_to_csv,
    export_glossary_to_json,
    get_default_xianxia_profile,
    import_glossary_from_csv,
    import_glossary_from_json,
)
from bookbridge.models.glossary import GlossaryProfile, GlossaryTerm


class TermDialog(QDialog):
    def __init__(self, term: Optional[GlossaryTerm] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Term" if term else "Add New Glossary Term")
        self.resize(450, 350)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.src_edit = QLineEdit(term.source if term else "")
        form.addRow("Source English Term:", self.src_edit)

        self.tgt_edit = QLineEdit(term.target if term else "")
        self.tgt_edit.setLayoutDirection(Qt.RightToLeft)
        form.addRow("Target Arabic Term:", self.tgt_edit)

        self.cat_combo = QComboBox()
        for cat in GlossaryCategory:
            self.cat_combo.addItem(cat.value, cat.value)
        if term:
            self.cat_combo.setCurrentText(term.category.value)
        form.addRow("Category:", self.cat_combo)

        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 1000)
        self.priority_spin.setValue(term.priority if term else 100)
        form.addRow("Priority (Higher = Matches First):", self.priority_spin)

        self.match_combo = QComboBox()
        for mt in MatchType:
            self.match_combo.addItem(mt.value.upper(), mt.value)
        if term:
            self.match_combo.setCurrentText(term.match_type.value.upper())
        form.addRow("Match Type:", self.match_combo)

        self.case_check = QCheckBox("Case Sensitive Matching")
        self.case_check.setChecked(term.case_sensitive if term else False)
        form.addRow("", self.case_check)

        self.locked_check = QCheckBox("Locked (Strict placeholder protection)")
        self.locked_check.setChecked(term.locked if term else True)
        form.addRow("", self.locked_check)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_term_data(self) -> dict:
        return {
            "source": self.src_edit.text().strip(),
            "target": self.tgt_edit.text().strip(),
            "category": GlossaryCategory(self.cat_combo.currentData()),
            "priority": self.priority_spin.value(),
            "match_type": MatchType(self.match_combo.currentData()),
            "case_sensitive": self.case_check.isChecked(),
            "locked": self.locked_check.isChecked(),
        }


class GlossaryView(QWidget):
    def __init__(self, glossary_repo: GlossaryRepository):
        super().__init__()
        self.glossary_repo = glossary_repo
        self.current_profile: Optional[GlossaryProfile] = None

        self._setup_ui()
        self.refresh_profiles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("Glossary & Terminology Rules")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        header.addWidget(title)
        header.addStretch()

        preset_btn = QPushButton("+ Add Xianxia / Web Novel Preset")
        preset_btn.setProperty("class", "SecondaryBtn")
        preset_btn.clicked.connect(self._on_add_preset)
        header.addWidget(preset_btn)

        import_btn = QPushButton("Import (CSV/JSON)")
        import_btn.setProperty("class", "SecondaryBtn")
        import_btn.clicked.connect(self._on_import)
        header.addWidget(import_btn)

        export_btn = QPushButton("Export Profile")
        export_btn.setProperty("class", "SecondaryBtn")
        export_btn.clicked.connect(self._on_export)
        header.addWidget(export_btn)

        layout.addLayout(header)

        # Profile selection card
        profile_card = QFrame()
        profile_card.setProperty("class", "Card")
        profile_layout = QHBoxLayout(profile_card)

        profile_label = QLabel("Active Profile:")
        profile_label.setStyleSheet("color: #f1f5f9;")
        profile_layout.addWidget(profile_label)
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_layout.addWidget(self.profile_combo, 1)

        new_profile_btn = QPushButton("+ New Profile")
        new_profile_btn.setProperty("class", "SecondaryBtn")
        new_profile_btn.clicked.connect(self._on_new_profile)
        profile_layout.addWidget(new_profile_btn)

        add_term_btn = QPushButton("+ Add Term")
        add_term_btn.setProperty("class", "PrimaryBtn")
        add_term_btn.clicked.connect(self._on_add_term)
        profile_layout.addWidget(add_term_btn)

        layout.addWidget(profile_card)

        # Terms Table Card
        table_card = QFrame()
        table_card.setProperty("class", "Card")
        table_layout = QVBoxLayout(table_card)

        # Search filter bar
        filter_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search source or target terms...")
        self.search_edit.textChanged.connect(self._filter_terms)
        filter_layout.addWidget(self.search_edit)

        table_layout.addLayout(filter_layout)

        self.terms_table = QTableWidget()
        self.terms_table.setColumnCount(7)
        self.terms_table.setHorizontalHeaderLabels([
            "Source (English)", "Target (Arabic)", "Category", "Priority", "Type", "Locked", "Action"
        ])
        self.terms_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.terms_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.terms_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.terms_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.terms_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.terms_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.terms_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.terms_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.terms_table)

        layout.addWidget(table_card)

    def refresh_profiles(self):
        profiles = self.glossary_repo.list_profiles()
        if not profiles:
            # Seed with default xianxia profile
            default_prof = get_default_xianxia_profile()
            self.glossary_repo.save_profile(default_prof)
            profiles = [default_prof]

        self.profile_combo.clear()
        for p in profiles:
            self.profile_combo.addItem(f"{p.name} ({len(p.terms)} terms)", p.id)

    def _on_profile_changed(self):
        prof_id = self.profile_combo.currentData()
        if prof_id:
            self.current_profile = self.glossary_repo.get_profile(prof_id)
            self._render_terms()

    def _render_terms(self, query: str = ""):
        if not self.current_profile:
            self.terms_table.setRowCount(0)
            return

        terms = self.current_profile.terms
        if query:
            q_lower = query.lower()
            terms = [t for t in terms if q_lower in t.source.lower() or q_lower in t.target.lower()]

        self.terms_table.setRowCount(len(terms))
        for r_idx, t in enumerate(terms):
            self.terms_table.setItem(r_idx, 0, QTableWidgetItem(t.source))
            
            tgt_item = QTableWidgetItem(t.target)
            tgt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.terms_table.setItem(r_idx, 1, tgt_item)

            self.terms_table.setItem(r_idx, 2, QTableWidgetItem(t.category.value))
            self.terms_table.setItem(r_idx, 3, QTableWidgetItem(str(t.priority)))
            self.terms_table.setItem(r_idx, 4, QTableWidgetItem(t.match_type.value.upper()))
            self.terms_table.setItem(r_idx, 5, QTableWidgetItem("Yes" if t.locked else "No"))

            del_btn = QPushButton("Delete")
            del_btn.setProperty("class", "DangerBtn")
            del_btn.clicked.connect(lambda _, term_id=t.id: self._on_delete_term(term_id))
            self.terms_table.setCellWidget(r_idx, 6, del_btn)

    def _filter_terms(self, text: str):
        self._render_terms(text.strip())

    def _on_add_term(self):
        if not self.current_profile:
            return
        dlg = TermDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_term_data()
            if not data["source"] or not data["target"]:
                QMessageBox.warning(self, "Validation Error", "Both source and target terms are required.")
                return
            new_term = GlossaryTerm(
                glossary_id=self.current_profile.id,
                **data,
            )
            self.current_profile.terms.append(new_term)
            self.glossary_repo.save_profile(self.current_profile)
            self._render_terms()

    def _on_delete_term(self, term_id: str):
        if not self.current_profile:
            return
        self.glossary_repo.delete_term(term_id)
        self.current_profile.terms = [t for t in self.current_profile.terms if t.id != term_id]
        self._render_terms()

    def _on_new_profile(self):
        name, ok = QLineEdit.getText(self, "New Profile", "Enter Glossary Profile Name:")
        if ok and name.strip():
            prof = GlossaryProfile(name=name.strip())
            self.glossary_repo.save_profile(prof)
            self.refresh_profiles()

    def _on_add_preset(self):
        preset = get_default_xianxia_profile()
        self.glossary_repo.save_profile(preset)
        self.refresh_profiles()
        QMessageBox.information(self, "Preset Added", "Added Xianxia / Cultivation Glossary Preset.")

    def _on_export(self):
        if not self.current_profile:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Glossary", f"{self.current_profile.name}.json", "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        if path.endswith(".csv"):
            content = export_glossary_to_csv(self.current_profile)
        else:
            content = export_glossary_to_json(self.current_profile)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        QMessageBox.information(self, "Exported", f"Glossary exported to:\n{path}")

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Glossary", "", "Glossary Files (*.json *.csv)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if path.endswith(".csv"):
                profile = import_glossary_from_csv(content, profile_name=Path(path).stem)
            else:
                profile = import_glossary_from_json(content)
            self.glossary_repo.save_profile(profile)
            self.refresh_profiles()
            QMessageBox.information(self, "Import Success", f"Imported glossary profile '{profile.name}' with {len(profile.terms)} terms.")
        except Exception as ex:
            QMessageBox.critical(self, "Import Error", f"Failed to import glossary:\n{str(ex)}")
