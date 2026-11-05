"""【计时规则】在状态写入事务内记录阶段和任务结束时间，历史缺失值不补造。"""
from datetime import datetime


def seconds_between(start, end):
    try:
        return round(max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()), 3)
    except (TypeError, ValueError):
        return None


def record_job_timing(job, previous, timestamp):
    previous = previous or {}
    terminal = job.get('status') in ('completed', 'failed')
    if job.get('status') == 'running' and previous.get('status') == 'queued':
        job.setdefault('started_at', timestamp)
    old_steps = previous.get('stages', [])
    for index, stage in enumerate(job.get('stages', [])):
        old = old_steps[index] if index < len(old_steps) else None
        if stage.get('status') == 'running':
            if old is None:
                stage.setdefault('started_at', timestamp)
            if terminal:
                stage['status'] = 'failed' if job['status'] == 'failed' else 'completed'
        if old and old.get('status') == 'running' and stage.get('status') in ('completed', 'failed'):
            stage.setdefault('ended_at', timestamp)
        elapsed = seconds_between(stage.get('started_at'), stage.get('ended_at'))
        if elapsed is not None:
            stage['duration_seconds'] = elapsed
    if terminal and previous.get('status') not in ('completed', 'failed'):
        job.setdefault('ended_at', timestamp)
    elapsed = seconds_between(job.get('created_at'), job.get('ended_at'))
    if elapsed is not None:
        job['duration_seconds'] = elapsed
