"""Build contact sheets of the current source-reviewed PNG attachments."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/figures_qa"


def run():
    files = []
    for journal in sorted((ROOT / "reports").glob("figures_verified_*.json")):
        for uid, record in json.loads(journal.read_text()).items():
            if record.get("verification_scope") == "earlier_pass_source_comparison":
                continue
            for attachment in record.get("attachments", []):
                if attachment["path"].endswith(".png"):
                    files.append((uid[:12] + " " + attachment["role"],
                                  ROOT / "static/olymp_figures" / attachment["path"]))
    OUT.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(files), 16):
        sheet = Image.new("RGB", (1600, 1640), "#ddd")
        for j, (label, path) in enumerate(files[start:start + 16]):
            with Image.open(path) as image:
                pic = image.convert("RGB")
            pic.thumbnail((380, 360))
            x, y = j % 4 * 400, j // 4 * 410
            sheet.paste(pic, (x + 10, y + 35))
            ImageDraw.Draw(sheet).text((x + 10, y + 5), label, fill="black")
        sheet.save(OUT / f"review_{start // 16:02}.jpg", quality=88)
    print(f"{len(files)} images in {(len(files) + 15) // 16} contact sheets")


if __name__ == "__main__":
    run()
