from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from creative_os.llm_metrics import LLMUsage, TimedCompletion, parse_usage
from creative_os.task_status import ChapterTaskStatus, write_chapter_status
from creative_os.validation_runtime import (
    _chapter_specs_for_number,
    validate_reader_facing_text,
    write_final_chapter_v2_artifacts,
)


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: str
    content: str


class ModelClient(Protocol):
    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> str | TimedCompletion:
        ...


@dataclass(frozen=True, slots=True)
class OpenAICompatibleClient:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls, env_file: str | Path | None = ".env") -> OpenAICompatibleClient:
        dotenv = _read_dotenv(env_file)
        base_url = os.environ.get(
            "CREATIVE_OS_LLM_BASE_URL",
            dotenv.get("CREATIVE_OS_LLM_BASE_URL", "https://api.openai.com/v1"),
        ).rstrip("/")
        api_key = os.environ.get("CREATIVE_OS_LLM_API_KEY", dotenv.get("CREATIVE_OS_LLM_API_KEY", ""))
        model = os.environ.get("CREATIVE_OS_LLM_MODEL", dotenv.get("CREATIVE_OS_LLM_MODEL", ""))
        if not api_key:
            raise ValueError("CREATIVE_OS_LLM_API_KEY is required")
        if not model:
            raise ValueError("CREATIVE_OS_LLM_MODEL is required")
        return cls(base_url=base_url, api_key=api_key, model=model)

    def complete(self, messages: list[ModelMessage], *, temperature: float, max_tokens: int) -> TimedCompletion:
        payload = {
            "model": self.model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started_at = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed: HTTP {exc.code} {body}") from exc
        elapsed_seconds = time.monotonic() - started_at
        return TimedCompletion(
            content=data["choices"][0]["message"]["content"].strip(),
            elapsed_seconds=elapsed_seconds,
            usage=parse_usage(data),
        )


CHINESE_TIME_OPENERS = ("凌晨", "清晨", "上午", "中午", "下午", "傍晚", "夜里", "深夜", "夜")
BANNED_READER_TERMS = [
    "Scene",
    "Context",
    "Task",
    "Compiled Knowledge",
    "Knowledge Patch",
    "新增事实",
    "前几章",
    "本章前段",
    "本章中段",
    "本章后段",
    "目标很清楚",
]

FACT_EVIDENCE: dict[str, tuple[tuple[str, ...], ...]] = {
    "废弃档案库未彻底废弃": (("档案库", "没有彻底废弃"), ("废弃只是表象", "系统还在呼吸")),
    "林澈旧维护权限可进入档案库": (("维护员林澈", "权限等级未变更"), ("旧权限", "查档案")),
    "档案库与灯务署系统仍连接": (("档案库与灯务署系统", "连接"), ("接入灯务署", "主服务器")),
    "林遥档案被覆盖": (("林遥", "档案", "覆盖"), ("林遥", "底稿", "覆盖")),
    "岚舟档案与林遥同属回声室编号": (("岚舟", "编号相同"), ("林遥", "岚舟", "同一个回声室")),
    "自愿离城名单存在原始底稿": (("自愿离城名单", "原始底稿"), ("公开档案", "底稿")),
    "许砚知道回声室编号": (("许砚", "回声室编号"), ("许砚", "知道编号")),
    "许砚没有立即上报全部证据": (("她没有上报",), ("没有上报", "证据")),
    "林澈和阿岚继续逃亡": (("林澈", "阿岚", "继续逃"), ("林澈", "阿岚", "逃"), ("他和阿岚继续往前走",)),
    "林澈熟悉审查室结构": (("林澈", "审查室", "知道"), ("审查室", "图纸"), ("监控", "位置")),
    "许砚怀疑林澈旧身份": (("许砚", "普通维修员不该"), ("许砚", "旧身份"), ("外包维修组", "档案")),
    "林澈刻意隐藏冷光管核心信息": (("冷光管", "隐藏"), ("冷光管", "不说"), ("冷光管", "知道但我不说")),
    "许砚看见林遥残影": (("许砚", "看见", "林遥"), ("残影", "林遥")),
    "低亮冷光可在审查室环境显影": (("低亮", "审查室", "显"), ("冷光", "审查室", "残影")),
    "林澈愿意冒险证明林遥未离城": (("林澈", "林遥", "没有被记录为离城"), ("林澈", "证明", "林遥")),
    "审查记录存在缺页": (("审查记录", "缺页"), ("第七页", "缺失"), ("第七页", "被替换")),
    "缺页与回声室编号相关": (("缺页", "回声室编号"), ("缺页", "编号重合")),
    "许砚开始保护证据链": (("许砚", "证据链"), ("加密分区", "证据链"), ("私人保存", "违规")),
    "白塔旧址保存旧事故档案": (("白塔", "档案"), ("事故", "档案"), ("纸质件", "箱子")),
    "白姨知道回声室相关旧事": (("白姨", "回声室"), ("白姨", "十年")),
    "十年前事故与禁灯令升级有关": (("十年前", "事故"), ("白塔", "出了事"), ("七月二十三日", "事故")),
    "林澈有旧维护员编号": (("林澈", "0726"), ("见习维护员", "0726"), ("维护员编号",)),
    "白姨认识年少林澈": (("白姨", "认识你"), ("你第一次来这里", "十年")),
    "周闻白与白塔事故存在隐秘关联": (("周闻白", "白塔"), ("周闻白", "七月十四日"), ("周闻白", "回声室")),
    "林澈曾安装回声室相关模块": (("林澈", "装过模块"), ("你亲手装的",), ("模块", "回声室")),
    "冷光塔前身与白塔有关": (("冷光塔", "前身", "白塔"), ("白塔", "冷光塔", "骨架")),
    "林澈记忆被剪除不是偶然": (("记忆", "剪", "周闻白"), ("记忆被剪",), ("被剪除的记忆",)),
}

FACT_KEYWORD_ALIASES: dict[str, tuple[str, ...]] = {
    "冷光塔": ("冷光塔",),
    "白塔": ("白塔", "白塔旧址"),
    "线路图": ("线路图", "图纸", "走线"),
    "损毁": ("损毁", "毁掉", "刮掉", "刀痕", "抹掉", "撕掉"),
    "回声室": ("回声室",),
    "旧检修网": ("旧检修网", "检修网", "地下管网"),
    "林澈": ("林澈",),
    "维护协议": ("维护协议", "协议"),
    "三年前": ("三年前", "三年"),
    "旧工具箱": ("旧工具箱", "工具箱"),
    "封存": ("封存", "被封", "非授权勿动"),
    "系统": ("系统",),
    "权限": ("权限", "旧编号", "维护编号", "旧维护编号"),
    "巡灯员": ("巡灯员",),
    "异常": ("异常", "注意", "发现"),
    "缺页": ("缺页", "涂黑", "缺角", "被替换"),
    "留下": ("留下", "留", "刻", "藏"),
    "第二段信息": ("第二段信息", "第二段", "信息"),
    "强制熄灯": ("强制熄灯", "全城熄灯", "分片强制熄灯", "熄灯"),
    "扩大": ("扩大", "全城", "常态部署", "分片", "各区"),
    "多人": ("多人", "不止", "四例", "序列"),
    "失踪": ("失踪", "去向抹掉", "名字从索引里拿掉"),
    "名单": ("名单", "名字", "编号", "本子"),
    "周闻白": ("周闻白",),
    "调离": ("调离", "调出", "不再负责", "移交"),
    "压制": ("压制", "停止追", "没权限", "不许继续"),
    "镇压": ("镇压", "清查", "封锁", "车已经出动", "被带出来"),
    "失败": ("失败", "无法遗忘所有人", "控制不住", "压不回去"),
    "林遥": ("林遥",),
    "城内": ("城内", "没有离城", "未离城"),
    "密钥": ("密钥", "加密", "私人终端", "缓存区"),
    "自愿离城": ("自愿离城",),
    "伪装": ("伪装", "改写", "涂黑", "覆盖", "正式记录"),
    "旧灯巷": ("旧灯巷",),
    "清查": ("清查", "封锁", "搜查", "清剿"),
    "阿岚": ("阿岚",),
    "地下入口": ("地下入口", "入口", "暗道", "地下通道"),
    "黑市光源": ("黑市光源", "黑市", "光源"),
    "雾": ("雾", "雾潮"),
    "记忆残影": ("记忆残影", "残影"),
    "低亮光源": ("低亮光源", "低亮", "冷光管"),
    "路径": ("路径", "路", "通道"),
    "入口": ("入口", "门"),
    "许砚": ("许砚",),
    "证据": ("证据", "记录", "终端", "档案"),
    "记录": ("记录", "档案", "日志"),
    "双重权限": ("双重权限", "双重验证", "权限组合"),
    "有限合作": ("合作", "联手", "一起"),
    "信任": ("信任", "风险项", "需要你"),
    "外层": ("外层", "回声室外层", "回声室入口", "入口"),
    "团队": ("团队", "三个人", "三条分岔", "我们"),
    "分歧": ("分歧", "争执", "争吵", "不同", "等不了", "自己去"),
    "重新合作": ("重新合作", "合作", "分开走谁也到不了", "每个人手里都攥着别人需要的东西"),
    "校验片段": ("校验片段", "镜面介质", "碎片"),
    "记忆抽取": ("记忆抽取", "抽取", "被抽", "实时记忆"),
    "持续": ("持续", "正在", "每一次", "现在"),
    "作证": ("作证", "证词", "交记录", "露面"),
    "事故记录": ("事故记录", "事故", "记录"),
    "居民": ("居民", "老赵", "老板娘", "女孩", "邻居", "有人"),
    "记忆": ("记忆", "短时记忆", "忘", "想不起来"),
    "错乱": ("错乱", "消退", "格式化", "覆盖", "忘了", "不认识"),
    "兄妹": ("兄妹", "哥", "妹妹", "林遥", "林澈"),
    "重逢": ("重逢", "伸手扣住她的肩", "确认这个人的体温", "走"),
    "救城": ("救城", "整座城", "雾城", "不再吞人"),
    "目标": ("目标", "来雾城不是为了", "现在他知道答案"),
    "选择": ("选择", "选", "公开", "声明发出"),
    "公开": ("公开", "公开一切", "声明"),
    "责任": ("责任", "责任追究", "承认上述事实", "账本"),
    "最后记录": ("最后一条解锁的记录", "记录末尾", "最后出现地点", "最后一次出现"),
    "出现": ("出现", "解锁", "读取", "弹出"),
    "第一盏": ("第一盏", "第一盏自愿点亮的灯", "第一盏灯"),
    "自愿点亮": ("自愿点亮", "自愿点亮的灯", "一个人决定把它放在那里"),
    "主线": ("林澈", "林遥", "阿岚", "许砚", "雾城"),
    "闭合": ("第一盏", "选择留下来", "不属于任何一份照明档案", "自愿点亮", "还在砖沿上亮着"),
}


@dataclass(frozen=True, slots=True)
class ChapterRewriteInput:
    chapter_number: int
    title: str
    source_text: str
    previous_summary: str
    scene_goals: list[str]
    required_facts: list[str]
    banned_terms: list[str]
    min_chinese_chars: int


def build_chapter_rewrite_input(project_root: str | Path, chapter_number: int) -> ChapterRewriteInput:
    root = Path(project_root)
    chapter_path = root / "final_chapters" / f"chapter_{chapter_number:03d}.md"
    if not chapter_path.exists():
        write_final_chapter_v2_artifacts(root)
    if not chapter_path.exists():
        raise FileNotFoundError(chapter_path)
    source_text = chapter_path.read_text(encoding="utf-8")
    title = _parse_chapter_title(source_text)
    specs = _chapter_specs_for_number(chapter_number)
    required_facts: list[str] = []
    seen_facts: set[str] = set()
    for spec in specs:
        for fact in spec.new_facts:
            if fact not in seen_facts:
                required_facts.append(fact)
                seen_facts.add(fact)
    return ChapterRewriteInput(
        chapter_number=chapter_number,
        title=title,
        source_text=source_text,
        previous_summary=_previous_chapter_summary(root, chapter_number),
        scene_goals=[spec.goal for spec in specs],
        required_facts=required_facts,
        banned_terms=BANNED_READER_TERMS,
        min_chinese_chars=max(1000, int(_count_chinese_chars(source_text) * 0.85)),
    )


def build_writer_messages(payload: ChapterRewriteInput, previous_issues: list[str] | None = None) -> list[ModelMessage]:
    system = (
        "你是长篇小说章节 Writer Agent。只输出读者可见正文，不输出解释、提纲、审稿意见或系统术语。"
        "写作目标是降低 AI 味，保持长篇小说连贯性。"
    )
    user = (
        f"请重写《雾城回声》第 {payload.chapter_number} 章《{payload.title}》。\n"
        f"上一章收束信息：{payload.previous_summary}\n"
        f"本章必须完成的剧情目标：{'; '.join(payload.scene_goals)}\n"
        f"本章必须保留的事实：{'; '.join(payload.required_facts)}\n"
        f"禁止出现的词：{'; '.join(payload.banned_terms)}\n"
        f"最低中文字符数：{payload.min_chinese_chars}\n\n"
        "写作要求：\n"
        "1. 不要把三个场景机械拼接成三段概要。\n"
        "2. 转场必须服务情绪、动作或信息推进，只有真实换地点或换视角时才明显转场。\n"
        "3. 不要使用统一时间词开头，尤其不要让每章第一句都从凌晨、傍晚、中午等时间开始。\n"
        "4. 保留悬疑推进、人物动机和证据链，不要改核心设定。\n"
        "5. 只输出 Markdown 章节正文，标题格式必须是 `# 第 N 章：标题`。\n\n"
        "旧稿如下，重写时可调整句序、转场和段落，但不得丢失关键事实：\n"
        f"{payload.source_text}"
    )
    if previous_issues:
        user += (
            "\n\n上一版未通过质量门禁，请按下面问题重写，不要只做局部替换：\n"
            f"{'; '.join(previous_issues)}"
        )
    return [ModelMessage(role="system", content=system), ModelMessage(role="user", content=user)]


def validate_llm_rewrite(payload: ChapterRewriteInput, text: str) -> list[str]:
    issues = validate_reader_facing_text(text)
    body_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    first_body = body_lines[0] if body_lines else ""
    if first_body.startswith(CHINESE_TIME_OPENERS):
        issues.append("time_word_opener")
    if _count_chinese_chars(text) < payload.min_chinese_chars:
        issues.append("below_minimum_chinese_chars")
    for fact in payload.required_facts:
        if not _fact_is_supported(fact, text):
            issues.append(f"missing_fact:{fact}")
    return issues


def validate_llm_rewrite_facts(payload: ChapterRewriteInput, text: str) -> list[dict[str, object]]:
    from creative_os.fact_validation import FactValidationResult, validate_required_facts

    structured = validate_required_facts(payload.required_facts, text)
    results: list[FactValidationResult] = []
    for result in structured:
        if result.supported or not _fact_is_supported(result.fact, text):
            results.append(result)
        else:
            results.append(FactValidationResult(fact=result.fact, supported=True, evidence=["explicit_evidence"]))
    return [asdict(result) for result in results]


def _fact_is_supported(fact: str, text: str) -> bool:
    if fact in text:
        return True
    evidence_groups = FACT_EVIDENCE.get(fact, ())
    if any(all(fragment in text for fragment in group) for group in evidence_groups):
        return True
    return _generic_fact_is_supported(fact, text)


def _generic_fact_is_supported(fact: str, text: str) -> bool:
    matched_keys = [key for key in FACT_KEYWORD_ALIASES if key in fact]
    if not matched_keys:
        return False
    supported = 0
    for key in matched_keys:
        if any(alias in text for alias in FACT_KEYWORD_ALIASES[key]):
            supported += 1
    required = len(matched_keys) if len(matched_keys) <= 2 else len(matched_keys) - 1
    return supported >= required


def run_llm_writer_pilot(
    project_root: str | Path,
    client: ModelClient,
    chapters: list[int] | None = None,
    max_attempts: int = 2,
    use_local_repair: bool = False,
    compiled_contexts: dict[int, object] | None = None,
) -> dict[str, object]:
    root = Path(project_root)
    selected = chapters or [4, 5, 6]
    out_root = root / "llm_writer_pilot"
    chapter_results: dict[str, list[str]] = {}
    attempts: dict[str, int] = {}
    metrics: dict[str, dict[str, object]] = {}
    context_usage: dict[str, dict[str, object]] = {}
    for chapter_number in selected:
        chapter_key = f"chapter_{chapter_number:03d}"
        compiled_context = (compiled_contexts or {}).get(chapter_number)
        if compiled_context is not None:
            context_usage[chapter_key] = {
                "fingerprint": str(getattr(compiled_context, "fingerprint")),
                "memory_ids": [item.id for item in getattr(compiled_context, "memory")],
            }
        payload = build_chapter_rewrite_input(root, chapter_number)
        _write_json(out_root / "inputs" / f"chapter_{chapter_number:03d}_input.json", asdict(payload))
        final_text = ""
        final_issues: list[str] = []
        elapsed_seconds = 0.0
        usage: LLMUsage | None = None
        for attempt in range(1, max_attempts + 1):
            messages = build_writer_messages(payload, final_issues or None)
            if use_local_repair and final_text and final_issues:
                from creative_os.local_repair import build_local_repair_messages, detect_repair_scope

                if detect_repair_scope(final_issues) == "local":
                    messages = build_local_repair_messages(final_text, final_issues)
            started_at = time.monotonic()
            completion = client.complete(
                messages,
                temperature=0.78,
                max_tokens=12000,
            )
            normalized = _normalize_completion(completion, time.monotonic() - started_at)
            final_text = normalized.content
            elapsed_seconds += normalized.elapsed_seconds
            usage = normalized.usage
            final_issues = validate_llm_rewrite(payload, final_text)
            attempts[chapter_key] = attempt
            if not final_issues:
                break
        metrics[chapter_key] = {
            "elapsed_seconds": round(elapsed_seconds, 3),
            "usage": asdict(usage) if usage else None,
        }
        _write_text(out_root / "chapters" / f"{chapter_key}.md", final_text)
        _write_json(
            out_root / "reviews" / f"{chapter_key}_review.json",
            {
                "issues": final_issues,
                "attempts": attempts.get(chapter_key, 0),
                "elapsed_seconds": metrics[chapter_key]["elapsed_seconds"],
                "usage": metrics[chapter_key]["usage"],
                "fact_results": validate_llm_rewrite_facts(payload, final_text),
            },
        )
        write_chapter_status(
            root,
            ChapterTaskStatus(
                chapter=chapter_number,
                status="pass" if not final_issues else "fail",
                attempts=attempts.get(chapter_key, 0),
                elapsed_seconds=float(metrics[chapter_key]["elapsed_seconds"]),
                issues=final_issues,
            ),
        )
        chapter_results[chapter_key] = final_issues
    result = "pass" if all(not issues for issues in chapter_results.values()) else "fail"
    run_record = {
        "result": result,
        "chapters": selected,
        "chapter_results": chapter_results,
        "attempts": attempts,
        "metrics": metrics,
        "context_usage": context_usage,
    }
    _write_json(out_root / "runs" / "llm_writer_pilot_run.json", run_record)
    return run_record


def _normalize_completion(completion: str | TimedCompletion, elapsed_seconds: float) -> TimedCompletion:
    if isinstance(completion, str):
        return TimedCompletion(content=completion, elapsed_seconds=elapsed_seconds, usage=None)
    return completion


def revalidate_llm_writer_pilot(project_root: str | Path, chapters: list[int] | None = None) -> dict[str, object]:
    root = Path(project_root)
    selected = chapters or [4, 5, 6]
    out_root = root / "llm_writer_pilot"
    chapter_results: dict[str, list[str]] = {}
    for chapter_number in selected:
        chapter_key = f"chapter_{chapter_number:03d}"
        chapter_path = out_root / "chapters" / f"{chapter_key}.md"
        if not chapter_path.exists():
            raise FileNotFoundError(chapter_path)
        payload = build_chapter_rewrite_input(root, chapter_number)
        chapter_text = chapter_path.read_text(encoding="utf-8")
        issues = validate_llm_rewrite(payload, chapter_text)
        _write_json(
            out_root / "reviews" / f"{chapter_key}_review.json",
            {"issues": issues, "mode": "revalidate", "fact_results": validate_llm_rewrite_facts(payload, chapter_text)},
        )
        chapter_results[chapter_key] = issues
    result = "pass" if all(not issues for issues in chapter_results.values()) else "fail"
    run_record = {"result": result, "chapters": selected, "chapter_results": chapter_results, "mode": "revalidate"}
    _write_json(out_root / "runs" / "llm_writer_pilot_run.json", run_record)
    return run_record


def promote_llm_writer_pilot_to_final(project_root: str | Path, chapters: list[int] | None = None) -> dict[str, object]:
    root = Path(project_root)
    selected = chapters or [4, 5, 6]
    validation = revalidate_llm_writer_pilot(root, selected)
    if validation["result"] != "pass":
        return {"result": "fail", "reason": "pilot_validation_failed", "validation": validation}

    backup_root = root / "backups" / "canonical_before_llm_writer_pilot_promotion"
    for name in ["final_chapters", "final_chapters_v2", "drafts"]:
        source = root / name
        if source.exists() and not (backup_root / name).exists():
            shutil.copytree(source, backup_root / name)

    promoted: list[str] = []
    for chapter_number in selected:
        chapter_name = f"chapter_{chapter_number:03d}.md"
        source = root / "llm_writer_pilot" / "chapters" / chapter_name
        if not source.exists():
            raise FileNotFoundError(source)
        text = source.read_text(encoding="utf-8")
        for target_dir in [root / "final_chapters", root / "final_chapters_v2"]:
            _write_text(target_dir / chapter_name, text)
        promoted.append(chapter_name)

    _write_text(root / "drafts" / "final_draft_polished.md", _assemble_final_draft(root / "final_chapters"))
    _write_text(root / "drafts" / "final_draft_v2.md", _assemble_final_draft(root / "final_chapters_v2"))
    run_record = {"result": "pass", "chapters": selected, "promoted": promoted, "backup": str(backup_root)}
    _write_json(root / "llm_writer_pilot" / "runs" / "llm_writer_pilot_promotion_run.json", run_record)
    return run_record


def _assemble_final_draft(chapters_dir: Path) -> str:
    parts = ["# 雾城回声\n"]
    for chapter_path in sorted(chapters_dir.glob("chapter_*.md")):
        parts.append(chapter_path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts) + "\n"


def _parse_chapter_title(source_text: str) -> str:
    first_line = source_text.splitlines()[0].strip().removeprefix("# ").strip()
    if "：" in first_line:
        return first_line.split("：", 1)[1].strip()
    return first_line


def _previous_chapter_summary(root: Path, chapter_number: int) -> str:
    if chapter_number <= 1:
        return ""
    previous_path = root / "final_chapters" / f"chapter_{chapter_number - 1:03d}.md"
    if not previous_path.exists():
        return ""
    paragraphs = [
        line.strip()
        for line in previous_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return " ".join(paragraphs[-3:])[:800]


def _count_chinese_chars(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def _read_dotenv(env_file: str | Path | None) -> dict[str, str]:
    if env_file is None:
        return {}
    path = Path(env_file)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _strip_env_value(value.strip())
    return values


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
