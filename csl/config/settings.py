"""CSL 运行默认路径。"""

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
LLM_CONFIG_FILE = CONFIG_DIR / "llm_config.yaml"
DATA_FILE = ROOT_DIR / "data" / "csl_full_paths.yaml"
ENV_FILE = CONFIG_DIR / ".env"
DEV_ENV_FILE = CONFIG_DIR / "dev.env"
PROD_ENV_FILE = CONFIG_DIR / "prod.env"
UAT_ENV_FILE = CONFIG_DIR / "uat.env"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
OUTPUT_DIR = ROOT_DIR / "output"
