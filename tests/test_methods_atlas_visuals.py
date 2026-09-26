"""Dependency-free regression checks for the embedded methods atlas."""

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from clean_methods_atlas import FILES, clean, embedded  # noqa: E402


class MethodsAtlasVisualsTest(unittest.TestCase):
    def test_only_geometry_drawings_remain_in_both_documents(self):
        for file in FILES:
            with self.subTest(file=file.name):
                html = file.read_text(encoding="utf-8")
                _, methods = embedded(html, "methods-data")
                _, visuals = embedded(html, "visuals-data")
                _, stats = embedded(html, "build-stats")
                examples = [e for m in methods for e in m["examples"]]
                geometry = [e for m in methods if m["section"] == "F" for e in m["examples"]]
                other = [e for m in methods if m["section"] != "F" for e in m["examples"]]
                self.assertEqual((len(methods), len(examples), len(geometry)), (102, 306, 63))
                self.assertTrue(all("visual_id" not in e for e in other))
                self.assertEqual(len(visuals), 189)
                self.assertEqual(stats["rendered"], 63)
                self.assertEqual(stats["stages"], 189)
                for example in geometry:
                    for stage in ("condition", "construction", "result"):
                        key = f'{example["visual_id"]}:{stage}'
                        self.assertIn(key, visuals)
                        self.assertEqual(ET.fromstring(visuals[key]).tag,
                                         "{http://www.w3.org/2000/svg}svg")
                clean(file, check=True)

    def test_fixed_diagrams_show_problem_constraints(self):
        _, visuals = embedded(FILES[0].read_text(encoding="utf-8"), "visuals-data")
        ns = "{http://www.w3.org/2000/svg}"

        def shape(id, kind):
            root = ET.fromstring(visuals[id + ":result"])
            return root.findall(f".//{ns}{kind}")

        # A and B are the endpoints of the diameter; C lies on the circle.
        c = next(c for c in shape("f2-2", "circle") if float(c.attrib["r"]) > 50)
        center = (float(c.attrib["cx"]), float(c.attrib["cy"]))
        radius = float(c.attrib["r"])
        pts = [(float(p.attrib["cx"]), float(p.attrib["cy"]))
               for p in shape("f2-2", "circle") if float(p.attrib["r"]) < 10]
        self.assertGreaterEqual(sum(abs((x-center[0])**2+(y-center[1])**2-radius**2) < 5
                                    for x, y in pts), 3)
        self.assertGreaterEqual(len(shape("f3-2", "circle")), 6)  # circle plus A,B,C,D,E
        self.assertGreaterEqual(len(shape("f3-2", "line")), 4)  # two crossing chords + joins
        self.assertGreaterEqual(len(shape("f16-2", "line")), 6)  # sides and three cevians
        self.assertGreaterEqual(len(shape("f17-2", "line")), 6)
        self.assertGreaterEqual(len(shape("f14-1", "line")), 4)  # two lines and two bisectors


if __name__ == "__main__":
    unittest.main()
