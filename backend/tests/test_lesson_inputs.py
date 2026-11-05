"""三个 Agent 必须接收实际课题，缺失时不得补入固定化学章节。"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.study_guide.domain.models import SessionInput
from backend.app.courseware.domain.models import CoursewareSettings
from backend.app.timed_practice.domain.models import LessonSettings


@pytest.mark.parametrize('model', [SessionInput, CoursewareSettings, LessonSettings])
def test_lesson_models_require_an_explicit_chapter(model):
    with pytest.raises(ValidationError):
        model()
    with pytest.raises(ValidationError):
        model(chapter='')
    assert model(chapter='知识库实际课题').chapter == '知识库实际课题'


@pytest.mark.parametrize('prefix', ['/api', '/api/courseware', '/api/timed-practice'])
def test_missing_chapter_is_rejected_without_saving_a_default_lesson(tmp_path, prefix):
    config = Settings(data_dir=tmp_path)
    with TestClient(create_app(config)) as client:
        response = client.post(prefix+'/sessions', json={})
        assert response.status_code == 422
        assert any(error['loc'] == ['body', 'chapter'] for error in response.json()['detail'])
        assert client.get(prefix+'/sessions').json() == []
        created = client.post(prefix+'/sessions', json={'chapter':'知识库实际课题'}).json()
        assert created['settings']['chapter'] == '知识库实际课题'
