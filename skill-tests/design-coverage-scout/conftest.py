import sys
from pathlib import Path

# skill-tests/design-coverage-scout/ -> <repo>/skill-tests/design-coverage-scout
# design-coverage lib lives at <repo>/skills/design-tooling/design-coverage/lib
REPO = Path(__file__).resolve().parents[2]
DC_SKILL = REPO / "skills" / "design-tooling" / "design-coverage"
DC_LIB = DC_SKILL / "lib"
# Expose the lib directory directly so `from validator import ...` works,
# matching the pattern used by skill-tests/design-coverage/conftest.py.
if str(DC_LIB) not in sys.path:
    sys.path.insert(0, str(DC_LIB))
