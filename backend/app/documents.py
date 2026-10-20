import json
import sys
import shutil
import tempfile
from pathlib import Path
from .publication import clean_office_in_place

VENDOR = Path(__file__).resolve().parents[2] / "vendor/chemistry"
sys.path.insert(0, str(VENDOR / "scripts"))
from render_outline import prepare_document, render_document
from revise_outline import revise_document
from outline_contract import normalize_outline


class DocumentEngine:
    schema = json.loads((VENDOR / "references/outline.schema.json").read_text())

    def validate(self, payload: dict) -> dict:
        outline, issues = prepare_document(payload)
        return {"outline": outline, "source_issues": issues}

    def render(self, payload, destination, version, allow_draft, previous=None):
        result = render_document(
            payload,
            destination,
            allow_unverified=True,
            version=version,
            previous=previous,
        )
        clean_office_in_place(Path(destination) / "outline.docx")
        return result

    def revise(self, current, patch, destination, version):
        current = Path(current).resolve()
        destination = Path(destination).resolve()
        if destination == current or current in destination.parents:
            raise ValueError("output directory must be outside the current version")
        # Keep the vendor's hash and patch validation, while allowing source gaps
        # for historical versions whose internal compatibility flag was false.
        with tempfile.TemporaryDirectory(prefix="outline-revision-") as temporary:
            snapshot = Path(temporary) / "current"
            snapshot.mkdir()
            for name in ("generation_report.json", "content.json", "source_input.json"):
                shutil.copy2(current / name, snapshot / name)
            report_path = snapshot / "generation_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["draft"] = True
            report_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            result = revise_document(snapshot, patch, destination, version=version)
        result["previous"]["directory"] = str(current)
        (destination / "generation_report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        clean_office_in_place(destination / "outline.docx")
        return result
