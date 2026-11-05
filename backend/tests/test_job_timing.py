"""计时以状态切换时间为依据，完成后保持不变。"""
from copy import deepcopy
from backend.app.shared.tasks.timing import record_job_timing


def test_stage_switch_and_job_finish_record_real_elapsed_seconds():
    created='2026-11-04T00:00:00+00:00'
    before={'status':'queued','created_at':created,'stages':[]}
    job=deepcopy(before);job.update(status='running',stages=[{'label':'检索','status':'running'}])
    record_job_timing(job,before,'2026-11-04T00:00:02+00:00')
    before=deepcopy(job)
    job['stages'][0]['status']='completed'
    job['stages'].append({'label':'生成','status':'running'})
    record_job_timing(job,before,'2026-11-04T00:00:07+00:00')
    assert job['stages'][0]['duration_seconds']==5
    before=deepcopy(job);job['status']='completed'
    record_job_timing(job,before,'2026-11-04T00:00:17+00:00')
    assert job['stages'][1]['duration_seconds']==10
    assert job['duration_seconds']==17
    frozen=deepcopy(job)
    record_job_timing(job,frozen,'2026-11-04T01:00:00+00:00')
    assert job==frozen


def test_failure_closes_running_stage_without_changing_completed_stage():
    previous={'status':'running','created_at':'2026-11-04T00:00:00+00:00','stages':[
        {'label':'检索','status':'completed'},
        {'label':'生成','status':'running','started_at':'2026-11-04T00:00:05+00:00'}]}
    job=deepcopy(previous);job['status']='failed'
    record_job_timing(job,previous,'2026-11-04T00:00:08+00:00')
    assert 'duration_seconds' not in job['stages'][0]
    assert job['stages'][1]['status']=='failed'
    assert job['stages'][1]['duration_seconds']==3
