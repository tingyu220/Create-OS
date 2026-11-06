"""前期领域的确认边界与安全建书；全部使用临时根。"""

from concurrent.futures import ThreadPoolExecutor
import pytest

from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.novel_project import create_novel_project
from creative_os.novel_project_command import NovelProjectCreator


BLOCKS = [{"key": "core", "title": "核心", "text": "记忆可交易"},
          {"key": "world", "title": "世界", "text": "海上城市"},
          {"key": "cast", "title": "人物", "text": "修钟人"},
          {"key": "conflict", "title": "冲突", "text": "救人与守约"},
          {"key": "direction", "title": "方向", "text": "寻找失落航线"}]


def test_candidate_confirm_cas_and_formal_stays_immutable(tmp_path):
    store = StoryArchitectureStore(tmp_path, "p")
    session = store.view()["session_id"]
    assert not list(tmp_path.iterdir())
    first = store.propose(session, BLOCKS, ["结局待讨论"], expected_revision=0, actor="agent", operation_id="one")
    confirmed = store.confirm(session, first["revision"], first["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm")
    assert confirmed["version"] == 1
    second = store.propose(session, [{**BLOCKS[0], "text": "未确认哨兵"}], [], expected_revision=1, actor="作者", operation_id="two")
    assert store.view()["confirmed"] == confirmed
    assert store.confirm(session, first["revision"], first["hash"], expected_confirmed_version=0, actor="作者", operation_id="confirm") == confirmed
    with pytest.raises(ValueError, match="candidate_conflict"):
        store.confirm(session, 1, first["hash"], expected_confirmed_version=1, actor="作者", operation_id="old")
    with pytest.raises(ValueError, match="confirmed_conflict"):
        store.confirm(session, 2, second["hash"], expected_confirmed_version=0, actor="作者", operation_id="stale")
    with pytest.raises(ValueError, match="session_scope_mismatch"):
        store.propose("other", BLOCKS, [], expected_revision=2, actor="作者", operation_id="cross")


@pytest.mark.parametrize("title", [".", "..", "CON", "nul.txt", "LPT1", "COM¹", "CON .txt", "尾点.", "尾空格 ", "a/b", "", "a\x01b"])
def test_new_book_rejects_unsafe_names(tmp_path, title):
    with pytest.raises(ValueError):
        create_novel_project(tmp_path, title)


def test_creation_never_overwrites_and_parent_idempotency(tmp_path):
    creator = NovelProjectCreator(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: creator.create("海城", "想法", operation_id="same"), range(4)))
    assert len(set(results)) == 1
    path = results[0]
    (path / "brief.json").write_text("作者原稿", encoding="utf-8")
    assert creator.create("海城", "想法", operation_id="same") == path
    assert (path / "brief.json").read_text(encoding="utf-8") == "作者原稿"
    with pytest.raises(ValueError, match="idempotency_conflict"):
        creator.create("海城", "另一个想法", operation_id="same")
    with pytest.raises((ValueError, FileExistsError)):
        create_novel_project(tmp_path, "海城")
    create_novel_project(tmp_path, "Book")
    with pytest.raises((ValueError, FileExistsError)):
        create_novel_project(tmp_path, "book")


def test_cleaned_collision_and_recover_interrupted_creation(tmp_path, monkeypatch):
    import creative_os.novel_project as project_module
    original = project_module.initialize_novel_project
    create_novel_project(tmp_path, "A:B")
    with pytest.raises(FileExistsError):
        create_novel_project(tmp_path, "AB")
    def interrupt(path, *args, **kwargs):
        original(path, *args, **kwargs)
        (path / "brief.json").write_text("中断后作者编辑", encoding="utf-8")
        raise RuntimeError("模拟断电")
    monkeypatch.setattr(project_module, "initialize_novel_project", interrupt)
    creator = NovelProjectCreator(tmp_path)
    with pytest.raises(RuntimeError):
        creator.create("中断书", "Idea", operation_id="recover")
    monkeypatch.setattr(project_module, "initialize_novel_project", original)
    restored = NovelProjectCreator(tmp_path).create("中断书", "Idea", operation_id="recover")
    assert (restored / "brief.json").read_text(encoding="utf-8") == "中断后作者编辑"


def test_concurrent_confirmation_cas_and_atomic_command_recovery(tmp_path, monkeypatch):
    from creative_os.story_architecture_command import story_commands
    from creative_os.workspace_command import CommandRequest
    store = StoryArchitectureStore(tmp_path, "p")
    candidate = store.propose(store.session_id, BLOCKS, [], expected_revision=0, actor="agent", operation_id="candidate")
    target = {"project_id": "p", "scope": "story", "session_id": store.session_id}
    request = CommandRequest("confirm_story_candidate", "confirm", "作者", target,
                             {"revision": 1, "hash": candidate["hash"], "expected_confirmed_version": 0}, idempotency_key="confirm")
    boundary = story_commands(store)
    original = boundary._store.complete
    monkeypatch.setattr(boundary._store, "complete", lambda *args: (_ for _ in ()).throw(RuntimeError("回执中断")))
    assert boundary.execute(request).error.code == "command_outcome_unknown"
    assert store.view()["confirmed"]["version"] == 1
    monkeypatch.setattr(boundary._store, "complete", original)
    assert story_commands(StoryArchitectureStore(tmp_path, "p")).execute(request).status.value == "accepted"
    assert store.view()["confirmed"]["version"] == 1
    changed = CommandRequest("confirm_story_candidate", "other", "作者", target,
                             {"revision": 1, "hash": "different", "expected_confirmed_version": 0}, idempotency_key="confirm")
    assert boundary.execute(changed).error.code == "idempotency_conflict"
    candidate = store.propose(store.session_id, BLOCKS, [], expected_revision=1, actor="作者", operation_id="candidate2")
    def confirm(index):
        try:
            return store.confirm(store.session_id, 2, candidate["hash"], expected_confirmed_version=1, actor="作者", operation_id=f"concurrent-{index}")["version"]
        except ValueError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, range(2)))
    assert outcomes.count(2) == 1 and outcomes.count("confirmed_conflict") == 1
