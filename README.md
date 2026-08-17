# bookbridge — AI Book Translation Desktop Application

bookbridge is a desktop application designed for translating novels and books from English to Arabic with deterministic terminology rules, structural and image preservation, automatic provider failover, rate-limit awareness, translation memory, and pause/resume capabilities.

---

## Key Features

1. **Universal Book Model (UBM)**:
   - High-fidelity parsing of **EPUB** and **PDF** documents into semantic blocks (headings, paragraphs, blockquotes, lists, images, tables).
   - Original embedded illustrations, images, and formatting are preserved without alteration.

2. **Deterministic Glossary & Terminology Protection**:
   - Longest-match and priority-weighted tokenizer.
   - Protected placeholder masking (`<NB_TERM_001>`) ensuring that locked terms (e.g. `Water Spirit -> روح الماء`, `water -> كين`) are never misaligned or modified by AI.
   - Category filtering (Cultivation, Systems, Names, Places, Techniques, Items).
   - Import & Export via JSON and CSV, with built-in presets (Xianxia, LitRPG, Web Novel).

3. **Multi-Key & Multi-Provider Translation Router**:
   - Seamless support for **Google Gemini** (Gemini 2.5 Flash, 1.5 Pro, 1.5 Flash) and **Groq** (Llama 3.3 70B Versatile).
   - Rate-limit aware: automatically detects HTTP 429, activates exponential backoff cooldowns, and fails over to healthy keys and secondary providers without interrupting translation jobs.

4. **Translation Memory & Request Caching**:
   - Segment-level deterministic request cache (SHA-256 hash) to avoid duplicate API requests.
   - Global Translation Memory (TM) for consistent terminology across books.

5. **Atomic Persistence & Resume Engine**:
   - Every translated segment is persisted atomically in SQLite (WAL mode).
   - Close the app anytime: upon reopening, bookbridge detects unfinished jobs and resumes from the exact last pending segment without re-translating completed text.

6. **Arabic RTL Output Engine**:
   - Generates compliant, valid EPUB 3 / EPUB 2 files with proper `dir="rtl"`, CSS typography, table of contents, and embedded assets.
   - Generates high-resolution Arabic RTL PDFs.

7. **Modern PySide6 Desktop GUI**:
   - Fast, non-blocking asynchronous user interface with animated progress, live segment preview stream, sample translation modal, glossary editor, and secure API key manager.

---

## Download & Install

### Windows Installer
Download the latest setup file from the GitHub Releases page and run the installer.

1. Open the latest release on GitHub.
2. Download `BookBridge-Setup.exe`.
3. Run the installer and follow the setup wizard.
4. Once installed, launch BookBridge from the Start menu or desktop shortcut.

### Prerequisites
- Windows 10 / 11
- Microsoft Visual C++ Redistributable (usually installed automatically by Windows)

### Run from Source
If you want to run the app directly from source instead of the installer:

```bash
cd "c:\projects\New folder\gemin"
pip install -r requirements.txt
python -m pytest -v tests/
python -m bookbridge.app
```

---

## Quick Start Guide

### Step 1: Add Your AI API Keys
1. Open BookBridge and navigate to **🔑 API Credentials**.
2. Click **+ Add API Key**.
3. Select **Google Gemini** or **Groq**, name the key (e.g., `Gemini Primary`), and paste your secret key.
4. Click **Test API Key Connection** to verify health, then click **OK**.
5. *(Optional)* Add multiple keys for redundancy and automatic failover.

### Step 2: Import Your Book
1. Go to **📚 Book Library**.
2. Click **+ Import EPUB** (or test with `sample_data/sample_novel.epub`).
3. Inspect chapter blocks and structure in the live hierarchy tree.

### Step 3: Configure Glossary (Optional)
1. Go to **📖 Glossary & Terms**.
2. Select or create a glossary profile (e.g., click **+ Add Xianxia / Web Novel Preset**).
3. Add custom character names, terms, or techniques.

### Step 4: Preview & Translate
1. Click **🌐 Translation Studio**.
2. Select your imported book, translation style (e.g., *Natural Arabic* or *Web Novel Arabic*), and glossary.
3. Click **Translate Sample (Preview)** to inspect the translation and Arabic formatting before full processing.
4. Click **Start Full Translation**.
5. Watch real-time chapter progression and live segment translation. You can pause or resume anytime.

### Step 5: Export Arabic Book
1. When complete, click **Export Output Book**.
2. Choose **EPUB** or **PDF** and save the file. Open it in Apple Books, Thorium, Calibre, or your preferred reader!

---

## Project Architecture

```text
gemin/
├── bookbridge/
│   ├── config/             # App settings, constants, and path managers
│   ├── database/           # SQLite connection with WAL mode, schema DDL, repositories
│   ├── models/             # Universal Book Model, Glossary, Job, Provider, and Style
│   ├── security/           # KeyringManager with encrypted fallback vault
│   ├── providers/          # Gemini, Groq, and Mock translation adapters
│   ├── routing/            # TranslationRouter and CredentialStateMachine
│   ├── glossary/           # Longest-match tokenizer and CSV/JSON importer/exporter
│   ├── memory/             # Request Cache and persistent Translation Memory
│   ├── validation/         # Completeness, token integrity, and anomaly checking
│   ├── segmentation/       # Semantic chunking and context window engine
│   ├── engine/             # TranslationPipeline and asynchronous JobRunner
│   ├── documents/          # EPUB and PDF document parsers
│   ├── renderers/          # Arabic RTL EPUB and PDF exporters
│   ├── ui/                 # PySide6 desktop window, dark theme, and views
│   └── app.py              # Main desktop application entrypoint
├── tests/                  # Pytest automated test suite (13 tests)
├── sample_data/            # Synthetic test novel EPUB
├── requirements.txt
├── pyproject.toml
└── README.md
```
