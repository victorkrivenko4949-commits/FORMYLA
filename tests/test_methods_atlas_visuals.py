"""Dependency-free regression checks for the embedded methods atlas."""

import sys
import unittest
import xml.etree.ElementTree as ET
from math import hypot
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
                geometry = [e for m in methods if m["section"] == "F"
                            for e in m["examples"] if e.get("visual_id")]
                other = [e for e in examples if not e.get("visual_id")]
                self.assertEqual((len(methods), len(examples), len(geometry)), (102, 306, 62))
                self.assertTrue(all("visual_id" not in e for e in other))
                self.assertEqual(len(visuals), 186)
                self.assertEqual(stats["rendered"], 62)
                self.assertEqual(stats["stages"], 186)
                f8 = next(m for m in methods if m["method_code"] == "F8")
                self.assertNotIn("visual_id", f8["examples"][0])
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

    def test_new_drawings_respect_geometry_and_coordinates(self):
        _, visuals = embedded(FILES[0].read_text(encoding="utf-8"), "visuals-data")
        ns = "{http://www.w3.org/2000/svg}"

        def components(id):
            root = ET.fromstring(visuals[id + ":result"])
            children = list(root)
            points = {}
            for current, following in zip(children, children[1:]):
                if (current.tag == ns + "circle" and
                        current.attrib.get("r") == "4.5" and
                        following.tag == ns + "text"):
                    points[following.text] = (float(current.attrib["cx"]),
                                              float(current.attrib["cy"]))
            circles = [(float(c.attrib["cx"]), float(c.attrib["cy"]),
                        float(c.attrib["r"]))
                       for c in children if c.tag == ns + "circle"
                       and float(c.attrib["r"]) > 10]
            lines = [(float(l.attrib["x1"]), float(l.attrib["y1"]),
                      float(l.attrib["x2"]), float(l.attrib["y2"]))
                     for l in children if l.tag == ns + "line"]
            return points, circles, lines

        def distance(a, b):
            return hypot(a[0]-b[0], a[1]-b[1])

        points, circles, _ = components("f4b-3")
        a, b, c, d, p = (points[k] for k in "ABCDP")
        self.assertEqual(a[1], c[1])
        self.assertEqual(a[1], d[1])
        self.assertAlmostEqual((c[0]-240)*(p[0]-c[0]) +
                               (c[1]-155)*(p[1]-c[1]), 0)
        self.assertAlmostEqual((d[0]-360)*(p[0]-d[0]) +
                               (d[1]-155)*(p[1]-d[1]), 0)
        cyclic = next((x, y, r) for x, y, r in circles if r == 125)
        for vertex in (b, c, d, p):
            self.assertAlmostEqual(distance(vertex, cyclic[:2]), cyclic[2], places=2)

        points, circles, _ = components("f7-2")
        o, g, h = (points[k] for k in "OGH")
        self.assertAlmostEqual((g[0]-o[0])*(h[1]-o[1]) -
                               (g[1]-o[1])*(h[0]-o[0]), 0, delta=2)
        self.assertAlmostEqual(distance(h, g)/distance(g, o), 2, delta=.02)
        ox, oy, r = circles[0]
        for vertex in "ABC":
            self.assertAlmostEqual(distance(points[vertex], (ox, oy)), r, delta=.02)
        for id in ("f9-3", "f17-3"):
            self.assertEqual(components(id)[0], points)

        points, _, _ = components("f7-1")
        sides = [distance(points[a], points[b]) for a, b in
                 (("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"))]
        self.assertLess(max(sides)-min(sides), .01)
        self.assertEqual(points["A"][1], points["C"][1])
        self.assertEqual(points["B"][0], points["D"][0])

        points, circles, _ = components("f9a-1")
        self.assertEqual(points["O"], (240, 230))
        for vertex in "ABC":
            self.assertAlmostEqual(distance(points[vertex], points["O"]), 200)
        self.assertEqual((points["B"][0]-points["A"][0],
                          points["A"][1]-points["C"][1]), (240, 320))

        points, circles, _ = components("f9a-2")
        self.assertEqual((points["A"], points["B"], points["O"]),
                         ((120, 300), (300, 300), (360, 300)))
        self.assertAlmostEqual(distance(points["M"], points["A"]) /
                               distance(points["M"], points["B"]), 2)
        self.assertIn((360, 300, 120), circles)

        points, _, _ = components("f9a-3")
        self.assertEqual((points["A"], points["B"], points["C"], points["H"]),
                         ((130, 390), (470, 390), (215, 135), (215, 305)))
        self.assertAlmostEqual((points["H"][0]-points["B"][0]) *
                               (points["C"][0]-points["A"][0]) +
                               (points["H"][1]-points["B"][1]) *
                               (points["C"][1]-points["A"][1]), 0)

        points, circles, lines = components("f15-2")
        o, h, hp, p, pp = (points[k] for k in ("O", "H", "H′", "P", "P′"))
        self.assertTrue(any(x1 == x2 == h[0] for x1, _, x2, _ in lines))
        self.assertAlmostEqual(distance(o, h)*distance(o, hp), 22500)
        self.assertAlmostEqual(distance(o, p)*distance(o, pp), 22500, delta=2)
        self.assertTrue(any(abs(distance(pp, (x, y))-r) < .02
                            and distance(o, (x, y)) == r for x, y, r in circles))


if __name__ == "__main__":
    unittest.main()
