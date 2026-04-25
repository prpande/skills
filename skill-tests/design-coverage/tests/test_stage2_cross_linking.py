import re
from pathlib import Path
from xml.etree import ElementTree as ET

FX = Path(__file__).parents[1] / "fixtures" / "stage-02" / "nav-graph-with-unwalked"

def parse_nav_destinations(nav_xml: Path):
    ns = {"a": "http://schemas.android.com/apk/res/android"}
    tree = ET.parse(nav_xml)
    out = []
    for frag in tree.iter("fragment"):
        out.append({
            "id": frag.get("{http://schemas.android.com/apk/res/android}id"),
            "class": frag.get("{http://schemas.android.com/apk/res/android}name"),
        })
    return out

def cross_link(nav_dest, known_classes):
    unwalked = []
    linked = []
    for d in nav_dest:
        cls = d["class"].rsplit(".", 1)[-1]
        if cls in known_classes:
            linked.append({"dest": d["id"], "class": cls})
        else:
            unwalked.append({"nav_source": "nav_main.xml", "target": cls, "reason": "unresolved-class"})
    return linked, unwalked

def test_links_known_and_records_unwalked():
    nav_dest = parse_nav_destinations(FX / "input" / "nav_main.xml")
    linked, unwalked = cross_link(nav_dest, {"ClientListFragment"})
    assert any(l["class"] == "ClientListFragment" for l in linked)
    assert any(u["target"] == "HiddenFragment" for u in unwalked)
