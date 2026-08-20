from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable, Mapping


_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_NAME_LINE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_ALIASES_LINE = re.compile(r"^aliases:\s*(.+?)\s*$", re.MULTILINE)
_ENTITY_KEYS = {
    "characters": "character",
    "locations": "location",
    "organizations": "organization",
    "organisations": "organization",
}
_COMMON_SURNAMES = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘斜厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴郁胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公")


@dataclass(frozen=True, slots=True)
class EntityWarning:
    entity_type: str
    canonical: str
    observed: str
    position: int
    excerpt: str
    reason: str = "可能的实体名称漂移"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def canonical_entities_from_baseline(baseline: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    """Extract only explicit entity names; prose is never treated as a name source."""
    entities: dict[str, set[str]] = {}
    for key, entity_type in _ENTITY_KEYS.items():
        for artifact in baseline.get(key, []) or []:
            if not isinstance(artifact, Mapping):
                continue
            content = str(artifact.get("content", ""))
            names = _frontmatter_names(content, include_aliases=False)
            if not names and artifact.get("title"):
                names = [str(artifact["title"])]
            if names:
                entities.setdefault(entity_type, set()).update(names)
    return {kind: tuple(sorted(names, key=lambda value: (-len(value), value))) for kind, names in entities.items()}


def entity_aliases_from_baseline(baseline: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, set[str]] = {}
    for key, entity_type in _ENTITY_KEYS.items():
        for artifact in baseline.get(key, []) or []:
            if not isinstance(artifact, Mapping):
                continue
            for alias in _frontmatter_names(str(artifact.get("content", "")), include_aliases=True)[1:]:
                aliases.setdefault(entity_type, set()).add(alias)
    return {kind: tuple(sorted(names)) for kind, names in aliases.items()}


def find_entity_warnings(
    text: str,
    entities: Mapping[str, Iterable[str]],
    *,
    aliases: Mapping[str, Iterable[str]] | None = None,
    excerpt_radius: int = 18,
) -> list[EntityWarning]:
    warnings: list[EntityWarning] = []
    for entity_type, names in entities.items():
        canonical_names = {name.strip() for name in names if len(name.strip()) >= 3}
        accepted = {name.strip() for name in (aliases or {}).get(entity_type, ()) if name.strip()}
        accepted.update(canonical_names)
        for canonical in canonical_names:
            for observed, position in _nearby_matches(text, canonical, entity_type):
                if observed in accepted:
                    continue
                start = max(0, position - excerpt_radius)
                end = min(len(text), position + len(observed) + excerpt_radius)
                warnings.append(EntityWarning(entity_type, canonical, observed, position, text[start:end]))
    return _dedupe(warnings)


def _frontmatter_names(content: str, *, include_aliases: bool) -> list[str]:
    names: list[str] = []
    name_match = _NAME_LINE.search(content)
    if name_match:
        names.append(_clean_name(name_match.group(1)))
    alias_match = _ALIASES_LINE.search(content)
    if include_aliases and alias_match:
        value = alias_match.group(1).strip().strip("[]")
        names.extend(_clean_name(item) for item in re.split(r"[,，、]", value) if item.strip())
    return [name for name in names if name]


def _clean_name(value: str) -> str:
    return value.strip().strip("'\"")


def _nearby_matches(text: str, canonical: str, entity_type: str) -> Iterable[tuple[str, int]]:
    if entity_type == "character" and (len(canonical) != 3 or canonical[0] not in _COMMON_SURNAMES):
        return
    length = len(canonical)
    for run in _CJK_RUN.finditer(text):
        value = run.group(0)
        if len(value) < length:
            continue
        for offset in range(len(value) - length + 1):
            observed = value[offset : offset + length]
            if observed != canonical and _edit_distance_at_most_one(observed, canonical) and _is_plausible(entity_type, canonical, observed):
                yield observed, run.start() + offset


def _is_plausible(entity_type: str, canonical: str, observed: str) -> bool:
    if entity_type != "character":
        return True
    if observed[0] not in _COMMON_SURNAMES:
        return False
    if canonical[1:] == observed[1:] and observed[0] != canonical[0]:
        return observed[0] in _COMMON_SURNAMES
    return True


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return sum(a != b for a, b in zip(left, right)) <= 1


def _dedupe(warnings: Iterable[EntityWarning]) -> list[EntityWarning]:
    seen: set[tuple[str, str, str, int]] = set()
    result: list[EntityWarning] = []
    for warning in warnings:
        key = (warning.entity_type, warning.canonical, warning.observed, warning.position)
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result
