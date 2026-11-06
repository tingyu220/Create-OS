import pytest
from creative_os.publication_models import ChapterSnapshot, PublicationStatus
from creative_os.tomato_browser_adapter import FakeTomatoPage, TomatoBrowserAdapter, TargetSpec


def snap(n=1, content='正文'):
    return ChapterSnapshot('book-1', n, 'rev-1', content)


def adapter():
    return TomatoBrowserAdapter(FakeTomatoPage(work_id='work-1', title='书名'))


def test_verify_open_target_and_capabilities():
    a = adapter()
    assert a.connect()['status'] == 'connected'
    result = a.verify_target(TargetSpec('work-1', '书名', 1, '第一章'))
    assert result['ok'] is True


def test_fill_publish_query_evidence_and_idempotency():
    a = adapter(); a.connect(); target = TargetSpec('work-1', '书名', 1, '第一章')
    s = snap(); a.verify_target(target); a.prepare_chapter(s, target)
    filled = a.fill_chapter(s, target, operation_id='op-1')
    assert filled['content_sha256'] == s.content_sha256
    first = a.publish('op-1'); second = a.publish('op-1')
    assert first == second and first['status'] == 'published'
    assert a.query_result('op-1')['content_sha256'] == s.content_sha256
    assert a.capture_evidence('op-1')['platform'] == 'tomato'


def test_fill_rejects_target_or_hash_mismatch():
    a = adapter(); a.connect(); target = TargetSpec('work-1', '书名', 1, '第一章'); a.verify_target(target)
    with pytest.raises(ValueError): a.fill_chapter(snap(), TargetSpec('other', '书名', 1, '第一章'), 'op')
    a.fill_chapter(snap(), target, 'op')
    with pytest.raises(ValueError): a.fill_chapter(ChapterSnapshot('book-1', 1, 'rev-2', '改稿'), target, 'op')


def test_captcha_login_loss_and_dropped_response_are_paused_or_unknown():
    a = adapter(); a.connect(); target = TargetSpec('work-1', '书名', 1, '第一章'); a.verify_target(target); a.fill_chapter(snap(), target, 'op')
    a.page.captcha_required = True
    assert a.publish('op')['pause_reason'] == 'captcha_required'
    a.page.captcha_required = False; a.page.logged_in = False
    assert a.publish('op')['pause_reason'] == 'login_expired'
    a.page.logged_in = True; a.fill_chapter(snap(), target, 'op2'); a.page.drop_next_response = True
    assert a.publish('op2')['status'] == 'unknown'
    assert a.query_result('op2')['status'] == 'unknown'


def test_fake_never_creates_or_logs_in():
    a = TomatoBrowserAdapter(FakeTomatoPage(work_id='', title='书名'))
    with pytest.raises(ConnectionError): a.connect(require_existing=True)

def test_query_detects_page_tampering_and_evidence_unavailable():
    a = adapter(); a.connect(); target = TargetSpec('work-1', '书名', 1, '第一章'); s = snap(); a.fill_chapter(s, target, 'op')
    a.page.chapters[1]['content_sha256'] = 'tampered'
    result = a.query_result('op')
    assert result['status'] == 'unknown'
    assert result['mismatch'] == 'content_sha256'
    assert a.capture_evidence('op')['evidence_available'] is False


def test_verify_requires_query_and_evidence_capabilities_and_snapshot_chapter_match():
    page = FakeTomatoPage(work_id='work-1', title='书名', capabilities={'fill_chapter', 'publish'})
    a = TomatoBrowserAdapter(page); a.connect()
    with pytest.raises(ValueError, match='能力'):
        a.verify_target(TargetSpec('work-1', '书名', 1, '第一章'))
    a = adapter(); a.connect()
    with pytest.raises(ValueError, match='章节'):
        a.prepare_chapter(snap(2), TargetSpec('work-1', '书名', 1, '第一章'))
