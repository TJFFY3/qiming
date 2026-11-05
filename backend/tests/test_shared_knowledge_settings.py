"""三个 Agent 的知识库范围只能来自公共配置。"""
import sys
from types import SimpleNamespace

from backend.app.config import Settings
from backend.app.courseware.configuration.settings import resolve_settings
from backend.app.timed_practice.configuration.settings import practice_settings


def test_courseware_uses_shared_datasets_even_with_legacy_override(monkeypatch):
    base = Settings(datasets=[{'id': 'shared-folder', 'type': 'folder'}])
    monkeypatch.setitem(sys.modules, 'backend.app.courseware_config', SimpleNamespace(
        overrides={'datasets': [{'id': 'old-courseware'}]},
    ))
    actual = resolve_settings(base)
    assert actual.datasets == base.datasets
    actual.datasets[0]['id'] = 'changed'
    assert base.datasets[0]['id'] == 'shared-folder'


def test_practice_uses_shared_datasets_even_with_legacy_override():
    base = Settings(datasets=[{'id': 'shared-folder', 'type': 'folder'}])
    base.timed_practice = {'datasets': [{'id': 'old-practice'}]}
    actual = practice_settings(base)
    assert actual.datasets == base.datasets
    actual.datasets[0]['id'] = 'changed'
    assert base.datasets[0]['id'] == 'shared-folder'
