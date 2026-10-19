import json
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[2] / 'vendor/chemistry'
sys.path.insert(0, str(VENDOR / 'scripts'))
from render_outline import prepare_document, render_document
from revise_outline import revise_document
from outline_contract import normalize_outline


class DocumentEngine:
    schema = json.loads((VENDOR/'references/outline.schema.json').read_text())

    def validate(self, payload: dict) -> dict:
        outline, issues = prepare_document(payload)
        return {'outline':outline,'source_issues':issues}

    def render(self, payload, destination, version, allow_draft):
        return render_document(payload,destination,allow_unverified=allow_draft,version=version)

    def revise(self,current,patch,destination,version):
        return revise_document(current,patch,destination,version=version)
