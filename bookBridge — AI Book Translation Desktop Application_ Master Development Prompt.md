# bookbridge — AI Book Translation Desktop Application

## 1. Project Overview

Build a production-quality desktop application named **bookbridge** for translating books and novels from English to Arabic using AI translation APIs.

The application must support:

- EPUB books
- PDF books
- English → Arabic translation initially
- Multiple AI providers
- Multiple user-provided API keys per provider
- Automatic provider/key failover
- Provider rate-limit awareness
- User-defined translation glossaries
- Strict terminology rules
- Translation memory and caching
- Pause/resume of large translation jobs
- Preservation of chapter structure
- Preservation of formatting
- Preservation and correct placement of original images
- Arabic RTL output
- EPUB export
- PDF export
- Local-first/private architecture

The application must be designed so additional languages, providers, input formats, and output formats can be added later without rewriting the core system.

---

# 2. Critical Product Principle

Do NOT build this as a simple:

```text
file → LLM → translated file
```

Instead build a structured document translation engine:

```text
INPUT FILE
    ↓
DOCUMENT PARSER
    ↓
UNIVERSAL BOOK MODEL
    ↓
STRUCTURE / BLOCK ANALYSIS
    ↓
GLOSSARY + TERMINOLOGY ENGINE
    ↓
SEGMENTATION / CONTEXT ENGINE
    ↓
TRANSLATION ROUTER
    ↓
AI PROVIDER
    ↓
VALIDATION ENGINE
    ↓
TRANSLATION MEMORY / CACHE
    ↓
UNIVERSAL BOOK MODEL WITH TRANSLATIONS
    ↓
OUTPUT RENDERER
    ↓
EPUB / PDF
```

The AI model must never be responsible for the entire document structure.

The application itself must own:

- document structure
- images
- chapters
- formatting
- glossary rules
- translation state
- retry logic
- caching
- provider routing
- output reconstruction

---

# 3. Platform Decision

Build the first version as a **Windows desktop application**.

Use:

- Python
- PySide6
- SQLite
- asyncio
- httpx

The architecture should remain portable to Linux later.

Do NOT build the first version as:

- mobile-only
- web-only
- cloud-only

The application should process the book locally and only send required text/document data to external AI APIs.

Do not upload whole books to a central BookBridge server.

---

# 4. Privacy and API Key Principle

The user owns the API keys.

The application must allow the user to enter their own:

### Gemini credentials

Example:

```text
Gemini Credential 1
Gemini Credential 2
Gemini Credential 3
Gemini Credential 4
```

### Groq credentials

Example:

```text
Groq Credential 1
Groq Credential 2
Groq Credential 3
```

API keys must NOT be stored as plaintext JSON files.

Use the platform's secure credential storage where possible.

The application should store only metadata in SQLite such as:

```text
provider
credential_name
model
enabled
status
last_error
cooldown_until
usage information
```

Store the actual secret in secure OS credential storage.

---

# 5. IMPORTANT RATE LIMIT RULE

Do NOT design multiple API keys as a mechanism to bypass provider limits.

Multiple credentials are for:

- redundancy
- user-owned multiple projects
- failover
- availability
- handling independent credential limits where legitimately allowed

The system must respect provider rate limits.

The application must detect and handle:

- HTTP 429
- quota exceeded
- rate-limit headers
- temporary network errors
- authentication failures
- invalid key
- model unavailable
- server errors
- timeout
- context-limit errors

Do not blindly retry indefinitely.

---

# 6. Provider Abstraction

Create a provider-independent interface.

For example:

```python
class TranslationProvider(ABC):
    async def translate(
        self,
        text: str,
        context: str | None,
        glossary: list,
        settings: dict,
    ) -> TranslationResult:
        ...
```

Implement:

```text
GeminiProvider
GroqProvider
```

Architecture must allow:

```text
OpenAIProvider
AnthropicProvider
LocalLLMProvider
OllamaProvider
```

to be added later.

The rest of the application must never directly depend on Gemini-specific code.

---

# 7. Translation Router

Create a central:

```text
TranslationRouter
```

The router decides which provider/model/credential should handle each request.

Example:

```text
Translation Request
        ↓
Router
        ↓
Find healthy credential
        ↓
Check cooldown
        ↓
Check rate availability
        ↓
Choose provider
        ↓
Send request
```

If a request fails:

```text
Gemini Credential A
       ↓
429
       ↓
Gemini Credential B
       ↓
temporary error
       ↓
Groq Credential A
       ↓
success
```

The user should normally not need to manually restart the job.

---

# 8. Credential State Machine

Each credential should have a state:

```text
AVAILABLE
ACTIVE
RATE_LIMITED
COOLDOWN
INVALID
AUTH_ERROR
DISABLED
ERROR
```

Track:

```text
last_used_at
last_success_at
last_error_at
failure_count
consecutive_failures
cooldown_until
request_count
token_count if available
```

Use exponential backoff where appropriate.

Do not retry invalid credentials repeatedly.

---

# 9. Universal Book Model

Create an internal document representation independent of EPUB/PDF.

Example:

```python
Book
 ├── metadata
 ├── resources
 └── chapters[]
       ├── id
       ├── title
       ├── order
       └── blocks[]
```

Block types should include at minimum:

```text
HEADING
PARAGRAPH
QUOTE
LIST
IMAGE
TABLE
PAGE_BREAK
SPECIAL
```

Example:

```python
{
    "id": "...",
    "type": "paragraph",
    "source_text": "The water flowed through the valley.",
    "translated_text": None,
    "style": {...},
    "position": {...},
    "source_location": {...}
}
```

Image block:

```python
{
    "type": "image",
    "resource_id": "...",
    "source_path": "...",
    "position": {...}
}
```

The translation engine must operate on this model rather than directly on PDF/HTML structures.

---

# 10. EPUB Support

EPUB is the first priority.

Implement:

```text
EPUB
 ↓
Parse ZIP container
 ↓
Parse OPF
 ↓
Parse XHTML
 ↓
Parse CSS
 ↓
Extract chapters
 ↓
Extract translatable text nodes
 ↓
Extract images/resources
 ↓
Build Universal Book Model
```

When translating EPUB:

- preserve chapter order
- preserve links
- preserve images
- preserve CSS where possible
- preserve formatting tags
- preserve metadata
- preserve cover
- preserve internal resources

Do not send CSS to the translation model.

Do not translate image binaries.

Do not destroy HTML structure.

Only translate appropriate text nodes.

---

# 11. PDF Support

PDF must be implemented after EPUB.

Support two PDF modes.

## Native PDF

If extractable text exists:

```text
PDF
 ↓
PyMuPDF
 ↓
Extract text blocks
 ↓
Extract coordinates
 ↓
Extract images
 ↓
Detect reading order
 ↓
Build Universal Book Model
```

## Scanned PDF

If pages have little/no extractable text:

```text
PDF
 ↓
Render page
 ↓
OCR / Vision
 ↓
Detect text regions
 ↓
Detect image regions
 ↓
Build Universal Book Model
```

Automatically determine whether the PDF is primarily:

```text
TEXT PDF
or
SCANNED PDF
```

---

# 12. Image Preservation

Images must normally remain **exactly original**.

Do not translate the image itself.

Do not replace images with generated images.

Do not send images unnecessarily to the LLM.

For EPUB:

```text
original image resource
```

must remain in the output.

For PDF, preserve:

- image
- dimensions
- aspect ratio
- relative location
- page placement

If the PDF reconstruction system needs to redraw a page, the image must be inserted at its original logical position.

---

# 13. Glossary Engine

This is a core feature.

Users must be able to define terminology rules such as:

```text
water → كين
Qi → تشي
Sword Spirit → روح السيف
Heavenly Sword → السيف السماوي
```

Example rule:

```json
{
  "source": "water",
  "target": "كين",
  "type": "exact",
  "priority": 100,
  "case_sensitive": false,
  "locked": true
}
```

The glossary must be deterministic.

Do not rely only on the LLM prompt.

---

# 14. Protected-Term Translation System

Implement a protected placeholder mechanism.

Example source:

```text
The water flowed through the valley.
```

Glossary:

```text
water → كين
```

Before translation:

```text
The [[TERM_001]] flowed through the valley.
```

The model translates:

```text
تدفقت [[TERM_001]] عبر الوادي.
```

The system restores:

```text
تدفقت كين عبر الوادي.
```

This ensures hard glossary rules are not accidentally changed by the AI.

Use robust tokens that the model is unlikely to modify.

Example:

```text
<NB_TERM_001>
```

or another safe protected-token format.

---

# 15. Glossary Matching

Support:

### Exact terms

```text
water → كين
```

### Phrases

```text
Water Spirit → روح الماء
```

### Case-insensitive matching

```text
Water
water
WATER
```

### Regex/custom matching

For advanced users.

### Priority

Longer/more-specific phrases must be matched before smaller terms.

For example:

```text
Water Spirit → روح الماء
water → كين
```

must produce:

```text
روح الماء
```

not:

```text
كين روح
```

Use longest-match/highest-priority processing.

---

# 16. Glossary Categories

Support:

```text
General terminology
Character names
Places
Organizations
Titles
Techniques
Items
Cultivation terminology
System terminology
Honorifics
Forbidden translations
Formatting rules
```

Allow users to enable/disable categories.

---

# 17. Glossary Profiles

Users should be able to create profiles such as:

```text
Xianxia
Xuanhuan
Chinese Web Novel
Korean LitRPG
Fantasy
Martial Arts
Custom
```

A profile contains:

```text
glossary rules
translation style
name rules
formatting rules
prompt configuration
```

Allow:

```text
Import glossary
Export glossary
```

Support JSON and CSV.

---

# 18. Translation Memory

Implement a persistent translation-memory system.

For every successfully translated segment store:

```text
source_hash
source_text
translated_text
source_language
target_language
glossary_version
prompt_version
provider
model
created_at
```

Before calling the API:

```text
Exact translation-memory match?
    ↓
YES → reuse
NO  → translate
```

This saves API usage.

Optionally support fuzzy matching later.

---

# 19. Translation Cache

Every API translation request should have a deterministic cache key based on relevant configuration.

For example:

```text
hash(
    source_text
    context
    source_language
    target_language
    glossary_version
    style_profile
    prompt_version
    model
)
```

If the same request already succeeded:

```text
DO NOT CALL THE API AGAIN.
```

---

# 20. Segmentation

Never send an entire novel to an API in one request.

Segment by:

```text
book
 ↓
chapter
 ↓
semantic blocks
 ↓
translation chunks
```

Do not blindly split by character count.

Prefer:

- paragraph boundaries
- dialogue boundaries
- heading boundaries
- scene boundaries when detectable

Respect model context limits.

---

# 21. Context-Aware Translation

Novel translation needs context.

For each chunk, optionally provide:

```text
previous paragraph(s)
current chunk
next paragraph(s)
```

Only translate the current chunk.

Context is used to improve:

- pronouns
- character references
- gender
- tone
- terminology
- continuity

Do not duplicate context in the final output.

---

# 22. Translation Prompt Design

The translation engine should generate a structured prompt.

The prompt should specify:

```text
Source language
Target language
Translation style
Genre
Glossary rules
Protected terminology
Context
Formatting requirements
Do not omit content
Do not invent content
Preserve names
Preserve markers
Return only translated text
```

Do not place hundreds of glossary terms directly into every prompt if protected-token preprocessing can handle them.

Prompt construction must be modular.

---

# 23. Translation Styles

Support initial styles:

```text
Natural Arabic
Literary Arabic
Literal Arabic
Web Novel Arabic
Custom
```

The user can select a style before starting the job.

Later allow custom style profiles.

---

# 24. Arabic Output

Arabic output must support:

- RTL
- right alignment
- proper Arabic fonts
- Arabic punctuation
- mixed Arabic/English text
- numbers
- chapter numbering
- dialogue
- names
- technical terms

EPUB CSS should be adapted for Arabic.

Avoid globally destroying existing styling.

Use an Arabic-compatible default font.

---

# 25. Validation Engine

After every translation, run validation.

Check:

### Completeness

Was content omitted?

### Glossary compliance

Did all locked terms remain correct?

### Protected markers

Were all protected tokens preserved?

### Formatting markers

Were important tags/markers lost?

### Names

Did configured names change unexpectedly?

### Numbers

Were important numbers altered?

### Length anomaly

Detect suspiciously short or excessively long translations.

### Empty output

Reject empty responses.

---

# 26. Automatic Retry

If validation fails:

```text
Translation
   ↓
Validation
   ↓
FAIL
   ↓
Retry with improved prompt
```

A limited number of retries only.

If repeated failure:

```text
mark segment as NEEDS_REVIEW
```

Do not endlessly consume API quota.

---

# 27. Translation Job System

A book translation is a job.

Example:

```text
Job
 ├── book_id
 ├── status
 ├── total_chapters
 ├── completed_chapters
 ├── current_chapter
 ├── total_segments
 ├── completed_segments
 ├── failed_segments
 ├── provider_usage
 ├── started_at
 └── updated_at
```

Possible states:

```text
QUEUED
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
NEEDS_REVIEW
```

---

# 28. Resume Support

If the application closes during translation:

```text
Reopen application
       ↓
Detect incomplete job
       ↓
Resume
```

Do not retranslate already completed segments.

This is mandatory.

---

# 29. GUI

Use PySide6.

The UI should have these main areas.

## Dashboard

Show:

```text
Recent books
Active jobs
Completed jobs
Failed jobs
API status
```

## Import Book

Drag-and-drop:

```text
EPUB
PDF
```

## Translation Setup

Choose:

```text
Source language
Target language
Provider strategy
Model
Glossary
Style
Output format
```

## API Keys

Allow:

```text
Gemini credentials
Groq credentials
```

Show health/status, never reveal full secrets.

## Glossary

CRUD interface for:

```text
source
target
category
priority
type
locked
enabled
```

## Translation Progress

Display:

```text
Chapter 145 / 800

██████████████░░░░░░ 71%

Current provider: Gemini
Current model: ...
Current credential: ...
```

Also show:

```text
Translated segments
Cached segments
Retries
Failures
```

## Preview

Allow previewing translated chapters before full-book translation.

---

# 30. Preview Mode

Implement:

```text
Translate Sample
```

User can select:

```text
Chapter 1
first 5 pages
selected paragraphs
```

This allows the user to test:

- model
- glossary
- style
- Arabic formatting

before using significant API quota.

---

# 31. Output System

Initially support:

```text
EPUB
```

Then:

```text
PDF
```

Optionally later:

```text
TXT
HTML
DOCX
```

Output should preserve:

```text
book title
author
cover
chapter order
images
formatting
metadata
```

---

# 32. SQLite Database

Create a clean schema for at minimum:

```text
books
chapters
blocks
translation_jobs
segments
translations
translation_memory
glossaries
glossary_terms
providers
credentials_metadata
usage_records
settings
```

Use migrations.

Do not create one giant database table.

---

# 33. Project Structure

Use a modular architecture similar to:

```text
bookbridge/
│
├── app/
│   ├── main.py
│   ├── config/
│   ├── database/
│   ├── models/
│   ├── services/
│   │   ├── translation/
│   │   ├── glossary/
│   │   ├── validation/
│   │   ├── memory/
│   │   ├── routing/
│   │   ├── jobs/
│   │   └── security/
│   │
│   ├── providers/
│   │   ├── base.py
│   │   ├── gemini.py
│   │   └── groq.py
│   │
│   ├── documents/
│   │   ├── base.py
│   │   ├── epub/
│   │   └── pdf/
│   │
│   ├── renderers/
│   │   ├── epub.py
│   │   └── pdf.py
│   │
│   ├── ui/
│   │   ├── windows/
│   │   ├── widgets/
│   │   └── dialogs/
│   │
│   └── utils/
│
├── tests/
├── migrations/
├── resources/
│   ├── fonts/
│   └── defaults/
│
├── docs/
├── requirements.txt
├── pyproject.toml
└── README.md
```

Adjust the exact structure when necessary, but preserve separation of concerns.

---

# 34. Testing Requirements

Do not build without tests.

Implement tests for:

### Glossary

```text
water → كين
Water → كين
Water Spirit → روح الماء
```

### Placeholder protection

Ensure protected terms are restored exactly.

### EPUB

Verify chapter order and HTML formatting.

### Images

Verify images survive round-trip conversion.

### Translation cache

Verify duplicate requests do not call APIs.

### Resume

Simulate interruption and ensure completed segments are not repeated.

### Provider failover

Simulate:

```text
Gemini 429
Gemini auth failure
Groq success
```

and verify routing.

### Validation

Test missing terms, missing markers and malformed responses.

---

# 35. Error Handling

Every external API request must have controlled handling.

Never allow a single failed request to crash the entire translation job.

Classify errors as:

```text
retryable
non-retryable
credential-specific
provider-specific
content-specific
```

Examples:

Retryable:

```text
429
timeout
temporary 5xx
network failure
```

Non-retryable:

```text
invalid API key
unsupported model
invalid request
```

Content-specific:

```text
context too large
unsafe/blocked request
malformed output
```

---

# 36. Logging

Provide structured logs.

Example:

```text
2026-08-17 10:34:12 INFO  Job started
2026-08-17 10:34:15 INFO  Chapter 12 loaded
2026-08-17 10:34:16 INFO  Segment 4 cache hit
2026-08-17 10:34:18 INFO  Gemini credential A request
2026-08-17 10:34:19 WARN  Gemini credential A returned 429
2026-08-17 10:34:19 INFO  Credential moved to cooldown
2026-08-17 10:34:19 INFO  Using Gemini credential B
```

Do not log API secrets.

---

# 37. Cost / Quota Dashboard

Show users approximate usage:

```text
Today
────────────────────
Requests: 142
Cached: 93
API requests: 49

Gemini
Requests: ...

Groq
Requests: ...
```

If token information is available, display it.

Make it clear that quotas are estimates if the provider does not expose exact remaining quota.

---

# 38. Security

Requirements:

- never log API keys
- never put keys in source code
- never commit keys
- never put keys in Git
- secure local credential storage
- validate imported files
- avoid arbitrary code execution from EPUB/PDF content
- sanitize rendered HTML
- treat book content as untrusted input
- isolate temporary files
- clean sensitive temporary data when possible

---

# 39. Offline Behavior

The application should continue to provide these capabilities offline:

- open local books
- view local translation history
- manage glossary
- manage settings
- view completed translations
- browse translation memory

Translation obviously requires an available provider unless a local model is configured.

---

# 40. Future Local Model Support

Design an interface for:

```text
Ollama
llama.cpp
other local inference
```

without implementing it fully in MVP.

The goal is that users can eventually translate without an external API.

---

# 41. Do NOT implement these in MVP

Avoid unnecessary scope.

Do NOT initially implement:

- user accounts
- cloud synchronization
- social sharing
- online marketplace
- subscription billing
- collaborative editing
- web application
- Android application
- iOS application

Focus on the translation engine.

---

# 42. MVP Definition of Done

MVP is complete when the following workflow works reliably:

```text
1. Open BookBridge
2. Import EPUB
3. Add Gemini API key
4. Create glossary
       water → كين
5. Select Arabic
6. Select translation style
7. Preview chapter 1
8. Start full translation
9. Application translates chapter by chapter
10. Cache completed segments
11. Handle rate limits
12. Resume after restart
13. Preserve images
14. Preserve chapter structure
15. Export valid Arabic EPUB
```

The resulting EPUB must open correctly in common EPUB readers.

---

# 43. Development Strategy

Implement in this order:

## Phase 1

Core project + SQLite + PySide6 shell.

## Phase 2

Universal Book Model.

## Phase 3

EPUB parser/importer.

## Phase 4

Glossary engine.

## Phase 5

Gemini provider.

## Phase 6

Translation engine + segmentation.

## Phase 7

Cache + translation memory.

## Phase 8

Validation.

## Phase 9

Job manager + resume/pause.

## Phase 10

Groq provider.

## Phase 11

Provider/key router.

## Phase 12

EPUB renderer/exporter.

## Phase 13

UI polish.

## Phase 14

PDF native-text pipeline.

## Phase 15

Scanned PDF/OCR pipeline.

---

# 44. Coding Standards

Write production-quality Python.

Requirements:

- type hints
- dataclasses/Pydantic where appropriate
- async API operations
- dependency injection where appropriate
- clear interfaces
- no giant files
- no giant functions
- no hardcoded API keys
- no provider-specific logic outside provider modules
- meaningful exceptions
- structured logging
- unit tests
- integration tests where practical
- `.env.example`
- complete README
- installation instructions

Avoid premature abstraction, but preserve clear module boundaries.

---

# 45. Important UX Principle

The user should not need to understand AI infrastructure.

A normal workflow should look like:

```text
Import Book
      ↓
Choose Arabic
      ↓
Choose Glossary
      ↓
Preview
      ↓
Translate
      ↓
Export
```

Advanced users can access:

```text
Provider settings
Models
Rate limits
Credentials
Prompt settings
Retry settings
```

through an advanced settings section.

---

# 46. Final Product Vision

The final product should feel like:

```text
Calibre
       +
professional CAT translation tool
       +
AI provider router
       +
novel-specific glossary engine
       +
translation memory
       +
PDF/EPUB reconstruction
```

The core differentiator is:

> **High-quality AI book translation with deterministic terminology and preservation of the original book structure.**

Do not optimize only for raw translation quality. Optimize for:

```text
Translation quality
+
Terminology consistency
+
Structural preservation
+
Reliability
+
Resume capability
+
Low API usage
+
Provider failover
```

---

# 47. Agent Execution Instructions

You are the implementation agent.

Before writing large amounts of code:

1. Inspect the repository.
2. Determine whether an existing project structure exists.
3. Reuse good existing components.
4. Do not overwrite working code unnecessarily.
5. Create a clear implementation plan in the repository.
6. Implement incrementally.
7. Run tests after each major subsystem.
8. Fix errors before proceeding.
9. Keep the application runnable throughout development.
10. Update README/documentation as functionality is added.

Do not stop after generating skeleton files.

Actually implement the MVP end-to-end.

The first milestone must produce a working application capable of:

```text
EPUB
→ parse
→ glossary protection
→ Gemini translation
→ validation
→ cache
→ resume
→ Arabic EPUB export
```

After that milestone, implement Groq/failover and then PDF support.

Do not claim a feature is complete until it has been tested.

---

# 48. First Task

Start by inspecting the repository and then implement the **MVP architecture and end-to-end EPUB translation pipeline**.

At the end of the first implementation stage, provide:

```text
1. What was implemented
2. Files created/modified
3. How to install
4. How to run
5. How to add Gemini API keys
6. How to create a glossary
7. How to translate an EPUB
8. Tests executed
9. Known limitations
10. Next recommended implementation step
```

Prioritize a **working, tested end-to-end MVP** over building every future feature immediately.