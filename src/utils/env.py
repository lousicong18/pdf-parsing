import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# VLM
VLM_BASE_URL = os.getenv("VLM_BASE_URL", "")
VLM_API_KEY = os.getenv("VLM_API_KEY", "")
VLM_MODEL = os.getenv("VLM_MODEL", "")
VLM_MODELS_FILE = os.getenv("VLM_MODELS_FILE", "models.json")
VLM_DEFAULT_MODEL = os.getenv("VLM_DEFAULT_MODEL", "MiniMax-M3")

# Upload
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "50"))

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8083"))

# Classification thresholds
CLS_LINE_COUNT_TABLE = int(os.getenv("CLS_LINE_COUNT_TABLE", "20"))
CLS_TEXT_BLOCKS_MIN = int(os.getenv("CLS_TEXT_BLOCKS_MIN", "4"))
CLS_LINE_COUNT_TEXT = int(os.getenv("CLS_LINE_COUNT_TEXT", "20"))
CLS_AREA_RATIO_MIN = float(os.getenv("CLS_AREA_RATIO_MIN", "0.15"))
CLS_DRAWINGS_PATH_MIXED = int(os.getenv("CLS_DRAWINGS_PATH_MIXED", "200"))
CLS_VLM_FALLBACK = os.getenv("CLS_VLM_FALLBACK", "off")

# OSS (optional)
OSS_ENABLED = os.getenv("OSS_ENABLED", "off")
OSS_PROVIDER = os.getenv("OSS_PROVIDER", "aliyun")
OSS_BUCKET = os.getenv("OSS_BUCKET", "")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY", "")
OSS_SECRET_KEY = os.getenv("OSS_SECRET_KEY", "")
OSS_PREFIX = os.getenv("OSS_PREFIX", "tasks/")

# Research / evaluation layer
TABLE_EXTRACTOR = os.getenv("TABLE_EXTRACTOR", "hybrid")
FORMULA_MODE = os.getenv("FORMULA_MODE", "annotate")
FORMULA_VLM_RESTORE = os.getenv("FORMULA_VLM_RESTORE", "off")
VLM_OCR_DPI = int(os.getenv("VLM_OCR_DPI", "200"))
VLM_DESC_DPI = int(os.getenv("VLM_DESC_DPI", "200"))
VLM_RESPONSE_CACHE = os.getenv("VLM_RESPONSE_CACHE", "off")
EVAL_SAMPLES_DIR = os.getenv("EVAL_SAMPLES_DIR", "samples")


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
