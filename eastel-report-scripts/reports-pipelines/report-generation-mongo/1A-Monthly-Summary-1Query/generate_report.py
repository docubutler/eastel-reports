from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
SOURCE_SCRIPT = CURRENT_DIR.parent / "1A-Monthly-Summary" / "generate_report.py"

spec = spec_from_file_location("base_mongo_report_generator", SOURCE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load base report generator from: {SOURCE_SCRIPT}")

module = module_from_spec(spec)
spec.loader.exec_module(module)
module.DEFAULT_CONFIG_PATH = CURRENT_DIR / "config.yml"


if __name__ == "__main__":
    module.main()
