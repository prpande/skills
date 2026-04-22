import re
from pathlib import Path

FX = Path(__file__).parents[1] / "fixtures" / "stage-02"

COMPOSE_FN = re.compile(r"@Composable\s+fun\s+(\w+)")
FRAGMENT_CLS = re.compile(r"class\s+(\w+)\s*:\s*(?:AppCompatActivity|FragmentActivity|Fragment|DialogFragment|BottomSheetDialogFragment)")
LAYOUT_INFLATE = re.compile(r"R\.layout\.(\w+)")
COMPOSE_VIEW = re.compile(r"\bComposeView\b")

def _read(*parts):
    return (FX.joinpath(*parts)).read_text()

def test_discovers_composable():
    assert COMPOSE_FN.search(_read("compose-only-screen", "input", "AppointmentDetailsScreen.kt")).group(1) == "AppointmentDetailsScreen"

def test_discovers_fragment_class_and_layout():
    kt = _read("fragment-xml-screen", "input", "ClientListFragment.kt")
    assert FRAGMENT_CLS.search(kt).group(1) == "ClientListFragment"
    assert LAYOUT_INFLATE.search(kt).group(1) == "fragment_client_list"

def test_discovers_compose_view_host():
    kt = _read("hybrid-composeview-host", "input", "HybridFragment.kt")
    assert COMPOSE_VIEW.search(kt) is not None
    assert FRAGMENT_CLS.search(kt).group(1) == "HybridFragment"
