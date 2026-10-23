import importlib.util
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

spec = importlib.util.spec_from_file_location(
    "catalog_clean_under_test", Path(__file__).resolve().parents[1] / "routes" / "olymp_catalog_clean.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CatalogPreservationTests(unittest.TestCase):
    def test_no_content_loss(self):
        examples = [
            "а) " + "Обоснование. " * 20 + "\nб) Доказательство.\nв) Докажем по индукции.",
            "Условие. " * 12 + "\nОтвет: 7.\nРешение. Другой вариант.",
            "Начало. " * 30 + "© МФТИ, 2024\nПродолжение доказательства.",
            r"\begin{task}Лемма\end{task}\begin{solution}Доказательство\end{solution}",
            r"\(x^2\) и \[\frac{a}{b}\] и символы ￿ ⇡ ↵ ",
        ]
        with tempfile.TemporaryDirectory() as directory:
            for text in examples:
                with self.subTest(text=text):
                    task = dict(text=text, solution=text, answer="4", fig_statement=["missing.svg"], fig_solution=[])
                    before = deepcopy(task)
                    qa = module.new_qa()
                    result = module.clean_task(task, qa, directory)
                    for key in before:
                        self.assertEqual(result[key], before[key])
                    self.assertEqual(result["fig_missing"], 1)
                    self.assertFalse(result["garbled"])
                    self.assertEqual(qa["solution_truncated"], 0)
                    self.assertEqual(qa["text_truncated"], 0)


if __name__ == "__main__":
    unittest.main()
