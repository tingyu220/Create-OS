from creative_os.publication_web import PublicationOrchestrator
from creative_os.publication_models import ChapterSnapshot, PublicationStatus
from creative_os.tomato_browser_adapter import FakeTomatoPage, TomatoBrowserAdapter, TargetSpec
from creative_os.publication_web import create_publication_server
from urllib.request import Request, urlopen
import json
import threading

def make():
 s=ChapterSnapshot('b',1,'r1','标题\n正文内容')
 p=FakeTomatoPage('w','书', chapters={})
 a=TomatoBrowserAdapter(p); a.connect()
 o=PublicationOrchestrator(a)
 return o,s,p
def passing(o): return {name: True for name in o.CHECKS}

def test_gate_failure_zero_publish():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'), checks={'structure_ok':False})
 assert t.status is PublicationStatus.FAILED and not p.chapters

def test_publish_and_idempotent():
 o,s,p=make(); target=TargetSpec('w','书',1,'第1章')
 a=o.submit(s,target,checks=passing(o)); b=o.submit(s,target,checks=passing(o)); assert a.operation_id==b.operation_id
 out=o.run(a.operation_id); assert out['status']=='published'

def test_unknown_reconcile_required():
 o,s,p=make(); target=TargetSpec('w','书',1,'第1章'); t=o.submit(s,target,checks=passing(o)); p.drop_next_response=True
 assert o.run(t.operation_id)['status']=='unknown'
 try: o.resume(t.operation_id); assert False
 except Exception: pass
 reconciled = o.reconcile(t.operation_id)
 assert reconciled['status'] == 'published'
 evidence = reconciled['evidence']
 assert evidence['evidence_available'] is True
 assert evidence['chapter']['status'] == 'published'
 assert evidence['chapter']['reconciled'] is True
 assert o.resume(t.operation_id)['status']=='published'

def test_unknown_without_published_evidence_stays_unknown():
 o,s,p=make(); target=TargetSpec('w','书',1,'第1章'); t=o.submit(s,target,checks=passing(o)); p.drop_next_response=True
 assert o.run(t.operation_id)['status'] == 'unknown'
 original = o.adapter.query_result
 o.adapter.query_result = lambda operation_id: {'status': 'unknown', 'operation_id': operation_id}
 assert o.reconcile(t.operation_id)['status'] == 'unknown'
 o.adapter.query_result = original

def test_all_gate_failures_never_call_fill_or_publish():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'), checks={name:False for name in o.CHECKS})
 assert t.status is PublicationStatus.FAILED and p.chapters == {}

def test_pause_continue_and_http_get_is_read_only():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'),checks=passing(o))
 o.pause(book_id='b', global_pause=True); assert o.state(t.operation_id)['status']=='paused'
 before=dict(p.chapters)
 server=create_publication_server(o); threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  body=urlopen(f'http://{server.server_address[0]}:{server.server_address[1]}/?operation_id={t.operation_id}').read()
  assert json.loads(body)['status']=='paused' and p.chapters==before
 finally: server.shutdown(); server.server_close()

def test_http_post_operation_id_is_idempotent():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'),checks=passing(o))
 server=create_publication_server(o); threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  payload=json.dumps({'action':'run','operation_id':t.operation_id}).encode()
  req=Request(f'http://{server.server_address[0]}:{server.server_address[1]}/',data=payload,method='POST',headers={'Content-Type':'application/json'})
  assert json.loads(urlopen(req).read())['status']=='published'
  req=Request(f'http://{server.server_address[0]}:{server.server_address[1]}/',data=payload,method='POST',headers={'Content-Type':'application/json'})
  assert json.loads(urlopen(req).read())['status']=='published'
 finally: server.shutdown(); server.server_close()

def test_missing_check_evidence_fails_closed_and_repeated_terminal_submit_is_read_only():
 o,s,p=make(); target=TargetSpec('w','书',1,'第1章')
 t=o.submit(s,target)
 assert t.status is PublicationStatus.FAILED
 o=PublicationOrchestrator(TomatoBrowserAdapter(p)); o.adapter.connect(); t=o.submit(s,target,checks=passing(o)); o.run(t.operation_id)
 t2=o.submit(s,target,checks={"structure_ok":False})
 assert t2.status is PublicationStatus.PUBLISHED

def test_get_unknown_operation_is_structured_404():
 o,s,p=make(); server=create_publication_server(o); threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  try: urlopen(f'http://{server.server_address[0]}:{server.server_address[1]}/?operation_id=missing')
  except Exception as exc: assert getattr(exc, 'code', None)==404
 finally: server.shutdown(); server.server_close()

def test_clear_global_pause_is_independent_of_chapter_resume():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'),checks=passing(o)); o.pause(global_pause=True)
 assert o.global_paused
 o.clear_pause(scope='global')
 assert not o.global_paused

def test_clear_pause_releases_only_matching_scope_tasks():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'),checks=passing(o)); o.pause(global_pause=True)
 assert t.status is PublicationStatus.PAUSED
 o.clear_pause(scope='global'); assert t.status is PublicationStatus.READY_TO_PUBLISH
 o2,s2,p2=make(); t2=o2.submit(s2,TargetSpec('w','书',1,'第1章'),checks=passing(o2)); o2.pause(book_id='b'); o2.clear_pause(scope='book', book_id='b')
 assert t2.status is PublicationStatus.READY_TO_PUBLISH

def test_run_records_step_checkpoints_and_failed_exception_checkpoint():
 o,s,p=make(); t=o.submit(s,TargetSpec('w','书',1,'第1章'),checks=passing(o)); o.run(t.operation_id)
 assert o.state(t.operation_id)['current_step']=='published'
 class Bad:
  platform_name='bad'
  def verify_target(self,*a): pass
  def prepare_chapter(self,*a): raise RuntimeError('prepare boom')
 b=PublicationOrchestrator(Bad()); tb=b.submit(s, {'work_id':'w','platform':'bad','chapter_title':'第1章'}, checks=passing(b))
 out=b.run(tb.operation_id)
 assert out['status']=='failed' and out['current_step']=='prepare_chapter' and tb.checkpoint is not None
