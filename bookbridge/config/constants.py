"""Core constants and enums for BookBridge AI Book Translation Engine."""

from enum import Enum


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    LIST = "list"
    IMAGE = "image"
    TABLE = "table"
    PAGE_BREAK = "page_break"
    SPECIAL = "special"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


class SegmentStatus(str, Enum):
    PENDING = "pending"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    CACHED = "cached"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class CredentialState(str, Enum):
    AVAILABLE = "available"
    ACTIVE = "active"
    RATE_LIMITED = "rate_limited"
    COOLDOWN = "cooldown"
    INVALID = "invalid"
    AUTH_ERROR = "auth_error"
    DISABLED = "disabled"
    ERROR = "error"


class ProviderType(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    MOCK = "mock"


class MatchType(str, Enum):
    EXACT = "exact"
    PHRASE = "phrase"
    REGEX = "regex"


class TranslationStyleType(str, Enum):
    NATURAL = "natural"
    LITERARY = "literary"
    LITERAL = "literal"
    WEB_NOVEL = "web_novel"
    CUSTOM = "custom"


class GlossaryCategory(str, Enum):
    GENERAL = "General terminology"
    NAMES = "Character names"
    PLACES = "Places"
    ORGANIZATIONS = "Organizations"
    TITLES = "Titles"
    TECHNIQUES = "Techniques"
    ITEMS = "Items"
    CULTIVATION = "Cultivation terminology"
    SYSTEM = "System terminology"
    HONORIFICS = "Honorifics"
    FORBIDDEN = "Forbidden translations"
    FORMATTING = "Formatting rules"


# Protected Token Prefix & Suffix
TOKEN_PREFIX = "<NB_TERM_"
TOKEN_SUFFIX = ">"
TOKEN_PATTERN = r"<NB_TERM_(\d+)>"

# Default Model Constants
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# Rate limit & Backoff Defaults
DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_MAX_RETRIES = 3
DEFAULT_SEGMENT_MAX_CHARS = 1200
DEFAULT_CONTEXT_WINDOW_BLOCKS = 2
