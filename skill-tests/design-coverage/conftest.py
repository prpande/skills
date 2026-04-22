import sys
from pathlib import Path

# skill-tests/design-coverage/conftest.py -> <repo>/skill-tests/design-coverage
# skill lib lives at <repo>/skills/design-tooling/design-coverage/lib
REPO = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO / "skills" / "design-tooling" / "design-coverage"
LIB = SKILL_ROOT / "lib"
# Tests import module names directly (e.g. `from validator import ...`),
# so expose the lib directory on sys.path.
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
# Also expose the skill root so fixtures can resolve schemas/ and platforms/.
import os
os.environ.setdefault("DESIGN_COVERAGE_SKILL_ROOT", str(SKILL_ROOT))
