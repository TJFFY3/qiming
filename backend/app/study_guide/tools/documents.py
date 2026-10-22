"""【文档工具·导学案】封装 vendor 的大纲校验、局部修订和 Word 渲染，不调用大模型。"""

import json
import sys
import shutil
import tempfile
from pathlib import Path
from backend.app.shared.tools.publication import clean_office_in_place
from backend.app.study_guide.tools.images import image_catalog, prepare_image_assets

from backend.app.paths import VENDOR
sys.path.insert(0, str(VENDOR / "scripts"))
from render_outline import prepare_document, render_document
from revise_outline import revise_document
from outline_contract import normalize_outline, outline_digest


class DocumentEngine:
    schema = json.loads((VENDOR / "references/outline.schema.json").read_text())

    def __init__(self, settings=None, image_transport=None):
        self.image_transport = image_transport
        self.image_origin = getattr(settings, "fastgpt_url", "") or "https://cloud.fastgpt.cn"

    @staticmethod
    def _blocks(outline):
        return [block for section in outline.get("sections", []) for block in section.get("blocks", [])]

    @staticmethod
    def _check_images(blocks, sources):
        available = {image["image_id"] for image in image_catalog(sources)}
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError("each replacement must be a block object")
            if block.get("type") == "image" and block.get("image_id") not in available:
                raise ValueError("图片 image_id 不在本课引用原图中，请只使用 image_catalog 中的图片")

    def validate(self, payload: dict) -> dict:
        outline, issues = prepare_document(payload)
        self._check_images(self._blocks(outline), payload.get("sources", []))
        return {"outline": outline, "source_issues": issues}

    def render(self, payload, destination, version, allow_draft, previous=None):
        validated = self.validate(payload)
        with tempfile.TemporaryDirectory(prefix="outline-images-") as temporary:
            assets = prepare_image_assets(
                self._blocks(validated["outline"]), payload.get("sources", []), Path(temporary),
                transport=self.image_transport, allowed_origin=self.image_origin,
            )
            result = render_document(
                payload, destination, allow_unverified=True, version=version,
                previous=previous, image_assets=assets,
            )
        clean_office_in_place(Path(destination) / "outline.docx")
        return result

    def revise(
        self, current, patch, destination, version, sources=None,
        source_gaps=None, source_conflicts=None,
    ):
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
            if any(value is not None for value in (sources, source_gaps, source_conflicts)):
                source_path = snapshot / "source_input.json"
                source_input = json.loads(source_path.read_text(encoding="utf-8"))
                if sources is not None:
                    source_input["sources"] = sources
                for key, values in (("source_gaps", source_gaps), ("source_conflicts", source_conflicts)):
                    if values is not None:
                        source_input[key] = list(dict.fromkeys(
                            source_input.get(key, []) + values
                        ))
                source_path.write_text(
                    json.dumps(source_input, ensure_ascii=False, allow_nan=False),
                    encoding="utf-8",
                )
            report_path = snapshot / "generation_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["draft"] = True
            report_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            old_sources = json.loads((snapshot / "source_input.json").read_text()).get("sources", [])
            content = json.loads((snapshot / "content.json").read_text())
            legacy_report = json.loads(report_path.read_text())
            if not isinstance(patch, dict) or set(patch) != {"base_sha256", "changes"}:
                raise ValueError("patch requires exactly base_sha256 and changes")
            canonical = normalize_outline(content)
            digest = outline_digest(canonical)
            if canonical != content or legacy_report.get("content_sha256") != digest:
                raise ValueError("current content does not match the generation report hash")
            if patch["base_sha256"] != digest:
                raise ValueError("stale patch: base_sha256 does not match the current content")
            if not isinstance(patch["changes"], list) or not patch["changes"]:
                raise ValueError("changes must be a nonempty list")
            replacements = {change["block_id"]: change["replacement"] for change in patch.get("changes", [])}
            blocks = [new for block in self._blocks(content)
                      for new in replacements.get(block["id"], [block])]
            self._check_images(blocks, old_sources)
            cached = snapshot / "images"
            if (current / "images").is_dir():
                shutil.copytree(current / "images", cached)
            assets = prepare_image_assets(
                blocks, old_sources, cached, transport=self.image_transport,
                allowed_origin=self.image_origin,
            )
            result = revise_document(snapshot, patch, destination, version=version, image_assets=assets)
        result["previous"]["directory"] = str(current)
        (destination / "generation_report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        clean_office_in_place(destination / "outline.docx")
        return result
