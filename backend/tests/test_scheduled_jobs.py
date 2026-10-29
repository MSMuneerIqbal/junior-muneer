import asyncio

from fastapi.testclient import TestClient

from junior import scheduler
from junior.main import create_app
from junior.settings_store import get_setting, set_setting


def test_catalog_switches_share_existing_settings_and_reject_unknown_jobs():
    with TestClient(create_app()) as client:
        data = client.get('/api/scheduled-jobs').json()
        assert {j['id'] for j in data['jobs']} == set(scheduler.CATALOG)
        assert client.patch('/api/scheduled-jobs/news', json={'enabled': False}).status_code == 200
        assert get_setting('news_digest_enabled') is False
        client.patch('/api/settings', json={'news_digest_enabled': True})
        assert next(j for j in client.get('/api/scheduled-jobs').json()['jobs'] if j['id'] == 'news')['enabled'] is True
        assert client.patch('/api/scheduled-jobs/not-a-job', json={'enabled': True}).status_code == 404
        assert client.patch('/api/scheduled-jobs/news', json={'enabled': 'false'}).status_code == 422
        assert client.patch('/api/scheduled-jobs/news', json={'enabled': True, 'code': 'x'}).status_code == 422


def test_scheduler_skips_disabled_jobs_but_manual_call_still_works(monkeypatch):
    calls = []
    def job():
        calls.append('backup')
    async def feeds():
        calls.append('feeds')
    with TestClient(create_app()):
        monkeypatch.setattr(scheduler, 'JOBS', [('daily backup', job)])
        set_setting('scheduled_backup_enabled', False)
        set_setting('scheduled_feeds_enabled', False)
        asyncio.run(scheduler.run_due_jobs([('your feeds', feeds)]))
        assert calls == []
        job()  # The switch only controls the schedule.
        assert calls == ['backup']
        set_setting('scheduled_backup_enabled', True)
        set_setting('scheduled_feeds_enabled', True)
        asyncio.run(scheduler.run_due_jobs([('your feeds', feeds)]))
        assert calls == ['backup', 'backup', 'feeds']
