from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CHROMA_DIR = PROJECT_ROOT / "data" / "chromadb"
COLLECTION_NAME = "knowledge"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MEMORY_SLOTS = 5
DEFAULT_MEMORY_STRATEGY = "chroma_strategy"

CHARACTERS_DIR = PROJECT_ROOT / "resources" / "characters"
DEFAULT_CHARACTER_STRATEGY = "json_strategy"
