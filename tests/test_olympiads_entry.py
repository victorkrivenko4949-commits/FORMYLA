"""Verify the legacy /olympiads URL renders the two-option menu.

Extract just the route under test so this check does not initialize the
production database, seeders, or unrelated Flask extensions.
"""

import ast
import re
import unittest
from pathlib import Path

from flask import Flask, render_template

ROOT = Path(__file__).resolve().parents[1]


class OlympiadsEntryTest(unittest.TestCase):
    def test_entry_renders_calendar_and_methods_only(self):
        app = Flask(__name__, template_folder=str(ROOT / "templates"),
                    static_folder=str(ROOT / "static"))
        for template in ("base.html", "olympiads_menu.html"):
            text = (ROOT / "templates" / template).read_text(encoding="utf-8")
            for endpoint in re.findall(r"url_for\('([^']+)'", text):
                if endpoint not in ("static", "olympiads") and endpoint not in app.view_functions:
                    app.add_url_rule("/_stub/" + endpoint, endpoint=endpoint, view_func=lambda: "")

        class Anonymous:
            is_authenticated = False
            role = None

        @app.context_processor
        def context():
            return {"asset_version": "test", "current_user": Anonymous()}

        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "olympiads")
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"),
             {"app": app, "render_template": render_template})
        response = app.test_client().get("/olympiads")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'class="olm-card"'), 2)
        self.assertIn(b'href="/_stub/olympiad_prep.calendar" class="olm-card"', response.data)
        self.assertIn(b'href="/_stub/olympiad.methods" class="olm-card"', response.data)


if __name__ == "__main__":
    unittest.main()
