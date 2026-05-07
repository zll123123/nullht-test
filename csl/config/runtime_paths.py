"""CSL 运行默认路径。"""

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"
LLM_CONFIG_FILE = ROOT_DIR / "llm_config.yaml"
DATA_FILE = ROOT_DIR / "data" / "csl_full_paths.yaml"
ENV_FILE = ROOT_DIR / ".env"
DEV_ENV_FILE = ROOT_DIR / "prod.env"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
OUTPUT_DIR = ROOT_DIR / "output"
