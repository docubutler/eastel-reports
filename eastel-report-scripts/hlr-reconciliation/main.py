from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))

from hlr_reconciliation.core.cli import main  # noqa: E402


if __name__ == "__main__":
    main(default_config_path=Path(__file__).with_name("config.yml"))
