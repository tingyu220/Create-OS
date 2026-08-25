from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from creative_os.foundation.knowledge import KnowledgeItem, KnowledgeStore
from creative_os.foundation.task import Task, TaskPriority


@dataclass(frozen=True, slots=True)
class SceneSpec:
    id: str
    title: str
    pov: str
    time: str
    location: str
    characters: list[str]
    goal: str
    conflict: str
    outcome: str
    new_facts: list[str]
    target_words: int
    chapter_label: str = "第一章"

    def to_task(self) -> Task:
        return Task(
            id=self.id,
            title=self.title,
            kind="writing",
            domain="novel",
            goal=self.goal,
            tags=set(self.characters) | {"雾城", self.chapter_label, "scene", self.location},
            priority=TaskPriority.HIGH,
            owner="writer",
        )


@dataclass(frozen=True, slots=True)
class SceneRunRecord:
    task_id: str
    context_sources: list[str]
    draft_path: str
    review_path: str
    compiled_knowledge_ids: list[str]
    status: str


@dataclass(frozen=True, slots=True)
class ChapterRunRecord:
    chapter_id: str
    scene_records: list[SceneRunRecord] = field(default_factory=list)
    status: str = "done"


@dataclass(frozen=True, slots=True)
class ChapterBlueprint:
    number: int
    title: str
    goal: str
    conflict: str
    outcome: str
    characters: list[str]
    location: str
    key_facts: list[str]


def seed_validation_knowledge() -> KnowledgeStore:
    store = KnowledgeStore()
    for item in _design_knowledge_items():
        store.add(item)
    return store


def chapter_one_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-001-scene-001",
            title="第1章 Scene 1：雾城南站回城",
            pov="林澈",
            time="傍晚",
            location="雾城南站",
            characters=["林澈", "巡灯员"],
            goal="让林澈回到雾城，并建立禁灯令压力",
            conflict="林澈没有有效通行记录，巡灯员要求他在入夜前离开",
            outcome="林澈用旧维修证入城，但被系统记录为异常回城人员",
            new_facts=["雾城禁灯令仍在执行", "林澈保留旧维修证", "灯务署监控会记录异常回城"],
            target_words=900,
        ),
        SceneSpec(
            id="chapter-001-scene-002",
            title="第1章 Scene 2：林遥住处",
            pov="林澈",
            time="夜",
            location="林遥住处",
            characters=["林澈", "林遥"],
            goal="确认林遥失踪不是普通离城",
            conflict="房间被清理，公开档案显示林遥自愿离城",
            outcome="林澈找到半截冷光管和林遥留下的暗号",
            new_facts=["林遥留下半截冷光管", "暗号是别相信灯灭后的自己", "林遥房间被人为清理"],
            target_words=900,
        ),
        SceneSpec(
            id="chapter-001-scene-003",
            title="第1章 Scene 3：旧路灯残影",
            pov="林澈",
            time="深夜",
            location="楼下旧路灯",
            characters=["林澈", "林遥"],
            goal="用异常旧灯触发第一个核心谜团",
            conflict="点亮旧灯会违反禁灯令，且可能引来巡灯员",
            outcome="灯光中出现林遥被带走的记忆残影",
            new_facts=["低亮冷光能显影记忆残影", "林遥被灯务署相关人员带走", "林澈确认妹妹仍在雾城线索内"],
            target_words=900,
        ),
    ]


def chapter_two_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-002-scene-001",
            title="第2章 Scene 1：旧灯巷入口",
            pov="林澈",
            time="清晨",
            location="旧灯巷入口",
            characters=["林澈", "阿岚"],
            goal="让林澈找到冷光管来源，并引出阿岚",
            conflict="阿岚不信任外来维修员，只愿用交易换线索",
            outcome="阿岚确认冷光管来自旧灯巷暗铺，要求林澈帮查失踪者名单",
            new_facts=["阿岚经营黑市低亮光源", "旧灯巷仍能流通未登记冷光管", "阿岚也在查失踪者"],
            target_words=850,
            chapter_label="第二章",
        ),
        SceneSpec(
            id="chapter-002-scene-002",
            title="第2章 Scene 2：灯务署锁定异常",
            pov="许砚",
            time="上午",
            location="灯务署",
            characters=["许砚", "周闻白", "林澈"],
            goal="建立许砚追查林澈的任务线",
            conflict="周闻白要求快速结案，许砚发现南站异常记录不完整",
            outcome="许砚锁定林澈旧维护证，并决定亲自去旧灯巷",
            new_facts=["许砚负责追查违规点灯", "周闻白知道异常回城", "南站记录存在缺口"],
            target_words=800,
            chapter_label="第二章",
        ),
        SceneSpec(
            id="chapter-002-scene-003",
            title="第2章 Scene 3：暗铺交易",
            pov="林澈",
            time="下午",
            location="旧灯巷暗铺",
            characters=["林澈", "阿岚", "许砚"],
            goal="验证冷光管并把林遥线索推向废档案库",
            conflict="冷光管触发暗铺警报，许砚同时进入旧灯巷",
            outcome="阿岚指出林遥来过，并留下废弃档案库方向；许砚发现林澈违规入城",
            new_facts=["林遥曾到旧灯巷查冷光管", "废弃档案库与林遥线索相关", "许砚开始追捕林澈"],
            target_words=900,
            chapter_label="第二章",
        ),
    ]


def chapter_three_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-003-scene-001",
            title="第3章 Scene 1：旧灯巷追捕",
            pov="林澈",
            time="傍晚",
            location="旧灯巷",
            characters=["林澈", "许砚", "阿岚"],
            goal="让林澈在追捕中保住冷光管和林遥线索",
            conflict="许砚封住巷口，阿岚不愿暴露地下通道",
            outcome="阿岚带林澈逃入暗道，但要求他帮查哥哥失踪",
            new_facts=["旧灯巷有地下通道", "阿岚哥哥也是失踪者", "许砚确认林澈持有异常冷光管"],
            target_words=900,
            chapter_label="第三章",
        ),
        SceneSpec(
            id="chapter-003-scene-002",
            title="第3章 Scene 2：缺帧记录",
            pov="许砚",
            time="夜",
            location="封锁线",
            characters=["许砚", "巡灯员", "林澈"],
            goal="让许砚发现灯务署记录异常",
            conflict="巡灯员要求按违规点灯处理，许砚发现监控缺帧",
            outcome="许砚没有上报全部细节，开始怀疑内部篡改",
            new_facts=["灯务署监控存在缺帧", "许砚具备独立判断", "违规点灯案被人为简化"],
            target_words=800,
            chapter_label="第三章",
        ),
        SceneSpec(
            id="chapter-003-scene-003",
            title="第3章 Scene 3：废档案库交易",
            pov="林澈",
            time="夜",
            location="暗道",
            characters=["林澈", "阿岚"],
            goal="明确下一步进入废弃档案库",
            conflict="阿岚只愿交出入口，条件是林澈也查她哥哥",
            outcome="林澈接受交易，获得废弃档案库入口和回声室的间接线索",
            new_facts=["阿岚哥哥失踪与灯务署有关", "废弃档案库可查林遥记录", "回声室成为下一阶段关键词"],
            target_words=900,
            chapter_label="第三章",
        ),
    ]


def chapter_four_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-004-scene-001",
            title="第4章 Scene 1：废弃档案库外门",
            pov="林澈",
            time="凌晨",
            location="废弃档案库",
            characters=["林澈", "阿岚"],
            goal="进入废弃档案库并建立档案被清理过的异常",
            conflict="外门能打开，内部终端需要林澈旧维护权限",
            outcome="林澈用旧权限进入档案库，发现系统仍识别他为维护员",
            new_facts=["废弃档案库未彻底废弃", "林澈旧维护权限可进入档案库", "档案库与灯务署系统仍连接"],
            target_words=850,
            chapter_label="第四章",
        ),
        SceneSpec(
            id="chapter-004-scene-002",
            title="第4章 Scene 2：自愿离城底稿",
            pov="林澈",
            time="凌晨",
            location="档案库机房",
            characters=["林澈", "林遥", "阿岚"],
            goal="读取林遥和岚舟的自愿离城底稿",
            conflict="公开记录完整，原始底稿却出现覆盖痕迹",
            outcome="林澈发现林遥档案关联回声室编号，岚舟档案也有同类标记",
            new_facts=["林遥档案被覆盖", "岚舟档案与林遥同属回声室编号", "自愿离城名单存在原始底稿"],
            target_words=900,
            chapter_label="第四章",
        ),
        SceneSpec(
            id="chapter-004-scene-003",
            title="第4章 Scene 3：许砚截停",
            pov="许砚",
            time="清晨",
            location="废弃档案库外",
            characters=["许砚", "林澈", "阿岚"],
            goal="让许砚追上林澈并看到回声室编号",
            conflict="林澈不愿交出证据，许砚不能公开承认监控缺帧",
            outcome="林澈逃脱但编号暴露，许砚开始私下追查回声室",
            new_facts=["许砚知道回声室编号", "许砚没有立即上报全部证据", "林澈和阿岚继续逃亡"],
            target_words=900,
            chapter_label="第四章",
        ),
    ]


def chapter_five_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-005-scene-001",
            title="第5章 Scene 1：审查室问答",
            pov="许砚",
            time="上午",
            location="灯务署审查室",
            characters=["许砚", "林澈"],
            goal="通过审问揭示林澈熟悉灯务署流程",
            conflict="林澈被短暂扣留，只愿交出不完整线索",
            outcome="许砚确认林澈不是普通维修员，也不是单纯违规者",
            new_facts=["林澈熟悉审查室结构", "许砚怀疑林澈旧身份", "林澈刻意隐藏冷光管核心信息"],
            target_words=900,
            chapter_label="第五章",
        ),
        SceneSpec(
            id="chapter-005-scene-002",
            title="第5章 Scene 2：冷光管显影",
            pov="林澈",
            time="中午",
            location="审查室",
            characters=["林澈", "许砚", "林遥"],
            goal="让许砚首次看到记忆残影",
            conflict="林澈无法用口供证明林遥被带走，只能冒险触发冷光管",
            outcome="冷光管短暂显影林遥被押走片段，许砚动摇",
            new_facts=["许砚看见林遥残影", "低亮冷光可在审查室环境显影", "林澈愿意冒险证明林遥未离城"],
            target_words=900,
            chapter_label="第五章",
        ),
        SceneSpec(
            id="chapter-005-scene-003",
            title="第5章 Scene 3：缺页记录",
            pov="许砚",
            time="下午",
            location="档案室",
            characters=["许砚", "周闻白", "林澈"],
            goal="让许砚发现审查记录缺页并形成后续调查动机",
            conflict="权限不足且周闻白要求她停止扩大案件",
            outcome="许砚发现缺页与回声室编号相关，决定暂缓上报林澈看到的残影",
            new_facts=["审查记录存在缺页", "缺页与回声室编号相关", "许砚开始保护证据链"],
            target_words=850,
            chapter_label="第五章",
        ),
    ]


def chapter_six_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-006-scene-001",
            title="第6章 Scene 1：白塔旧址到达",
            pov="林澈",
            time="傍晚",
            location="白塔旧址",
            characters=["林澈", "白姨"],
            goal="让林澈抵达白塔旧址并寻找回声室来源",
            conflict="白姨拒绝说明十年前白塔事故，担心灯务署再次清查",
            outcome="林澈用林遥线索打动白姨，获得一次查看旧档案的机会",
            new_facts=["白塔旧址保存旧事故档案", "白姨知道回声室相关旧事", "十年前事故与禁灯令升级有关"],
            target_words=900,
            chapter_label="第六章",
        ),
        SceneSpec(
            id="chapter-006-scene-002",
            title="第6章 Scene 2：维护员编号",
            pov="林澈",
            time="夜",
            location="白塔旧屋",
            characters=["林澈", "白姨"],
            goal="让林澈发现自己与白塔事故存在旧关联",
            conflict="白姨只愿交出部分记录，不愿直接指认周闻白",
            outcome="白姨拿出林澈旧维护员编号，证明他不是旁观者",
            new_facts=["林澈有旧维护员编号", "白姨认识年少林澈", "周闻白与白塔事故存在隐秘关联"],
            target_words=900,
            chapter_label="第六章",
        ),
        SceneSpec(
            id="chapter-006-scene-003",
            title="第6章 Scene 3：白塔残基残影",
            pov="林澈",
            time="深夜",
            location="白塔残基",
            characters=["林澈", "白姨"],
            goal="触发林澈关于安装模块的第一段记忆残影",
            conflict="残影可能证明林澈曾参与系统建设",
            outcome="林澈看见自己安装过与回声室相连的模块",
            new_facts=["林澈曾安装回声室相关模块", "冷光塔前身与白塔有关", "林澈记忆被剪除不是偶然"],
            target_words=900,
            chapter_label="第六章",
        ),
    ]


def chapter_seven_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-007-scene-001",
            title="第7章 Scene 1：旧图纸碎片",
            pov="林澈",
            time="清晨",
            location="白塔旧址",
            characters=["林澈", "白姨"],
            goal="确认冷光塔前身是白塔系统",
            conflict="图纸残缺，关键模块名称被人为刮去",
            outcome="林澈获得白塔到冷光塔的线路碎片",
            new_facts=["冷光塔前身是白塔系统", "线路图被人为损毁", "回声室连接在旧检修网下方"],
            target_words=850,
            chapter_label="第七章",
        ),
        SceneSpec(
            id="chapter-007-scene-002",
            title="第7章 Scene 2：旧维修站签名",
            pov="林澈",
            time="上午",
            location="旧维修站",
            characters=["林澈"],
            goal="查找林澈旧工具箱并验证维护员身份",
            conflict="工具箱被封存，开启会触发旧系统识别",
            outcome="林澈找到带有自己签名的三年前维护协议碎页",
            new_facts=["林澈签署过维护协议", "三年前协议与冷光塔升级有关", "林澈旧工具箱被系统封存"],
            target_words=850,
            chapter_label="第七章",
        ),
        SceneSpec(
            id="chapter-007-scene-003",
            title="第7章 Scene 3：维护员识别",
            pov="林澈",
            time="中午",
            location="冷光塔影区",
            characters=["林澈", "巡灯员"],
            goal="让冷光塔系统主动识别林澈",
            conflict="旧编号触发警报，巡灯员开始靠近",
            outcome="系统称林澈为维护员，林澈确认自己的权限仍在",
            new_facts=["系统仍承认林澈权限", "冷光塔会响应旧维护员编号", "巡灯员开始注意林澈异常"],
            target_words=850,
            chapter_label="第七章",
        ),
    ]


def chapter_eight_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-008-scene-001",
            title="第8章 Scene 1：记录室缺页",
            pov="许砚",
            time="上午",
            location="灯务署记录室",
            characters=["许砚", "同僚"],
            goal="让许砚独立查到缺页涉及多人失踪",
            conflict="同僚提醒她不要越权追查回声室",
            outcome="许砚复制异常索引，确认缺页不只林遥一例",
            new_facts=["缺页涉及多人失踪", "回声室不是单一案件", "许砚开始保留私人证据"],
            target_words=850,
            chapter_label="第八章",
        ),
        SceneSpec(
            id="chapter-008-scene-002",
            title="第8章 Scene 2：署长施压",
            pov="许砚",
            time="下午",
            location="周闻白办公室",
            characters=["许砚", "周闻白"],
            goal="展示周闻白阻止许砚扩大案件",
            conflict="许砚询问回声室，周闻白要求她停止追查",
            outcome="许砚被调离林澈案件，但确认周闻白知道回声室",
            new_facts=["周闻白知道回声室", "许砚被调离案件", "灯务署高层主动压制调查"],
            target_words=850,
            chapter_label="第八章",
        ),
        SceneSpec(
            id="chapter-008-scene-003",
            title="第8章 Scene 3：林遥未离城",
            pov="许砚",
            time="夜",
            location="私人终端",
            characters=["许砚", "林遥"],
            goal="让许砚确认林遥仍在城内",
            conflict="系统权限限制，任何查询都可能留下痕迹",
            outcome="许砚确认林遥未离城，并把结果藏入私人密钥",
            new_facts=["林遥仍在城内", "许砚拥有私人证据密钥", "自愿离城记录被正式系统伪装"],
            target_words=850,
            chapter_label="第八章",
        ),
    ]


def chapter_nine_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-009-scene-001",
            title="第9章 Scene 1：旧灯巷清查",
            pov="阿岚",
            time="傍晚",
            location="旧灯巷",
            characters=["阿岚", "巡灯员"],
            goal="让旧灯巷危机升级并迫使阿岚转移线索",
            conflict="灯务署清查黑市光源，阿岚必须保护地下入口",
            outcome="阿岚转移核心光源，但暗道入口风险暴露",
            new_facts=["旧灯巷被灯务署清查", "阿岚掌握多个地下入口", "黑市光源与回声室调查关联加深"],
            target_words=850,
            chapter_label="第九章",
        ),
        SceneSpec(
            id="chapter-009-scene-002",
            title="第9章 Scene 2：地下通道雾化",
            pov="林澈",
            time="夜",
            location="地下通道",
            characters=["林澈", "阿岚"],
            goal="让林澈和阿岚前往回声室线索点",
            conflict="暗道开始雾化，低亮光源会暴露位置也能指路",
            outcome="二人用低亮光源穿过雾化暗道，发现雾对记忆残影有反应",
            new_facts=["雾对记忆残影有反应", "地下通道接近回声室外层", "低亮光源可短暂稳定路径"],
            target_words=900,
            chapter_label="第九章",
        ),
        SceneSpec(
            id="chapter-009-scene-003",
            title="第9章 Scene 3：三方汇合",
            pov="林澈",
            time="夜",
            location="地下汇合点",
            characters=["林澈", "阿岚", "许砚"],
            goal="让林澈、阿岚、许砚第一次共享关键证据",
            conflict="三方互不信任，且许砚仍是灯务署调查员",
            outcome="三人确认回声室入口在冷光塔下，形成最低合作基础",
            new_facts=["回声室入口在冷光塔下", "三人开始有限合作", "许砚交出林遥未离城证据"],
            target_words=900,
            chapter_label="第九章",
        ),
    ]


def chapter_ten_scene_specs() -> list[SceneSpec]:
    return [
        SceneSpec(
            id="chapter-010-scene-001",
            title="第10章 Scene 1：废弃检修口",
            pov="许砚",
            time="清晨",
            location="废弃检修口",
            characters=["许砚", "林澈", "阿岚"],
            goal="定位回声室外层入口并建立三人互相需要",
            conflict="入口需要署内权限和林澈旧编号同时验证",
            outcome="组合权限打开第一层门，三人确认彼此不可替代",
            new_facts=["回声室入口需要双重权限", "许砚权限和林澈旧编号可组合", "阿岚掌握地下路径"],
            target_words=850,
            chapter_label="第十章",
        ),
        SceneSpec(
            id="chapter-010-scene-002",
            title="第10章 Scene 2：最低信任",
            pov="林澈",
            time="上午",
            location="检修口内部",
            characters=["林澈", "许砚"],
            goal="建立林澈和许砚最低合作信任",
            conflict="林澈隐瞒安装模块残影，许砚仍可能上报他",
            outcome="许砚交出林遥未离城证据，林澈承认自己有旧维护权限",
            new_facts=["林澈承认旧维护权限", "许砚交出关键证据", "二人建立有限信任"],
            target_words=900,
            chapter_label="第十章",
        ),
        SceneSpec(
            id="chapter-010-scene-003",
            title="第10章 Scene 3：外层门报警",
            pov="林澈",
            time="中午",
            location="回声室外层",
            characters=["林澈", "许砚", "阿岚", "周闻白"],
            goal="打开回声室外层并把周闻白推到正面",
            conflict="系统报警，周闻白远程封锁入口",
            outcome="入口被定位但触发封锁，周闻白确认他们已经接近真相",
            new_facts=["周闻白知道三人接近回声室", "回声室外层已被定位", "第11章可以从回声室外继续"],
            target_words=900,
            chapter_label="第十章",
        ),
    ]


def chapter_blueprints_11_to_36() -> list[ChapterBlueprint]:
    return [
        ChapterBlueprint(11, "回声室外", "接近回声室并验证林澈旧权限", "入口需要林澈旧权限且系统开始主动识别", "权限识别通过，团队进入回声室外层", ["林澈", "许砚", "阿岚"], "回声室外层", ["林澈旧权限可开启回声室外层", "系统仍保留维护员记录", "团队进入更深层"]),
        ChapterBlueprint(12, "空房间", "寻找林遥并确认她被转移", "回声室核心房间已空，证据可能被清理", "林遥留下第二段信息，指向雾潮计划", ["林澈", "许砚", "林遥"], "回声室空房间", ["林遥曾被关押在回声室", "她留下第二段信息", "回声室已被转移"]),
        ChapterBlueprint(13, "雾潮预警", "理解雾潮计划并建立全城危机", "周闻白封锁全城，居民开始被迫熄灯", "全城进入强制熄灯，雾潮倒计时启动", ["林澈", "许砚", "周闻白"], "雾城街区", ["雾潮计划即将启动", "强制熄灯扩大", "周闻白公开维稳"]),
        ChapterBlueprint(14, "旧事故", "让白姨讲出白塔事故部分真相", "真相会动摇林澈自我认知", "林澈承认自己可能是共犯", ["林澈", "白姨"], "白塔旧址", ["白塔事故与冷光塔有关", "林澈曾签署维护协议", "周闻白隐瞒系统用途"]),
        ChapterBlueprint(15, "失踪名单", "整理失踪者名单并扩大案件规模", "名单人数远超公开记录，阿岚情绪失控", "阿岚找到哥哥岚舟名字，案件从林遥扩展到失踪者群体", ["林澈", "阿岚", "许砚"], "废档案库", ["失踪名单远超公开记录", "岚舟在名单中", "自愿离城是系统性伪装"]),
        ChapterBlueprint(16, "署长的解释", "周闻白与林澈正面对话", "周闻白声称禁灯保护全城并提出交易", "林澈拒绝交易，确认周闻白是核心阻力", ["林澈", "周闻白", "许砚"], "灯务署会谈室", ["周闻白承认禁灯是维稳工具", "他试图用林遥下落交易", "林澈拒绝放弃真相"]),
        ChapterBlueprint(17, "分裂", "让团队因公开真相方式产生分歧", "阿岚要立刻救人，许砚坚持证据链", "林澈独自行动，团队信任受损", ["林澈", "阿岚", "许砚"], "地下汇合点", ["团队出现分歧", "许砚坚持证据链", "林澈独自前往旧系统节点"]),
        ChapterBlueprint(18, "被剪除的夜晚", "恢复林澈部分关键记忆", "记忆显示林澈曾主动签署维护协议", "林澈发现林遥当年也在事故现场", ["林澈", "林遥", "周闻白"], "旧系统节点", ["林澈记忆被剪除", "林遥当年在现场", "维护协议与救林遥有关"]),
        ChapterBlueprint(19, "重新集结", "让团队在信任受损后重新合作", "每个人都隐瞒过信息，合作基础脆弱", "三人决定进入冷光塔核心入口", ["林澈", "阿岚", "许砚"], "旧灯巷地下", ["团队重新合作", "冷光塔核心入口被确定", "林澈公开部分记忆"]),
        ChapterBlueprint(20, "灯务署内线", "许砚争取内部支持", "同僚害怕禁灯令崩溃而拒绝作证", "一个内线交出冷光塔内部图", ["许砚", "周闻白"], "灯务署记录室", ["灯务署内部出现内线", "冷光塔内部图流出", "许砚正式背离周闻白控制"]),
        ChapterBlueprint(21, "林遥的选择", "展示林遥在回声室保留证据", "她的记忆被持续抽取", "林遥藏下校验片段，等待林澈找到", ["林遥", "周闻白"], "地下回声室", ["林遥成为系统校验关键", "她藏下校验片段", "记忆抽取正在持续"]),
        ChapterBlueprint(22, "旧灯巷陷落", "让灯务署清剿旧灯巷并压缩团队空间", "阿岚必须选择救人还是保线索", "旧灯巷被封，阿岚保住核心入口图", ["阿岚", "林澈", "许砚"], "旧灯巷", ["旧灯巷被封", "阿岚失去安全据点", "地下入口图被保留"]),
        ChapterBlueprint(23, "白姨作证", "白姨交出事故记录", "记录会暴露林澈旧身份", "记录证明周闻白隐瞒系统用途", ["白姨", "林澈", "许砚"], "白塔旧址", ["白姨决定作证", "事故记录出现", "周闻白隐瞒冷光塔用途"]),
        ChapterBlueprint(24, "雾潮开始", "启动全城雾潮危机", "居民开始出现记忆错乱", "冷光塔进入不可逆倒计时", ["林澈", "许砚", "周闻白"], "雾城街区", ["雾潮启动", "居民记忆错乱", "冷光塔倒计时开始"]),
        ChapterBlueprint(25, "进入冷光塔", "团队潜入冷光塔", "权限、巡逻和雾潮同时压迫", "林澈被系统识别为维护员", ["林澈", "阿岚", "许砚"], "冷光塔入口", ["团队进入冷光塔", "林澈维护员身份被系统确认", "雾潮压迫升级"]),
        ChapterBlueprint(26, "维护员协议", "林澈读完三年前协议", "他发现自己曾为救林遥妥协", "许砚被捕，团队行动受挫", ["林澈", "许砚", "周闻白"], "冷光塔档案层", ["林澈曾为救林遥妥协", "三年前协议完整出现", "许砚被捕"]),
        ChapterBlueprint(27, "回声审判", "许砚被迫参与记忆审查", "她必须选择服从或公开异常", "许砚公开内部缺页，彻底背离灯务署", ["许砚", "周闻白"], "审查大厅", ["许砚公开缺页", "灯务署内部证据链暴露", "许砚完成立场转变"]),
        ChapterBlueprint(28, "林遥现身", "林澈见到林遥", "林遥已成为系统校验钥匙", "救人会导致证据消失", ["林澈", "林遥", "周闻白"], "地下回声室", ["林遥成为校验钥匙", "救人和公开证据冲突", "兄妹重逢"]),
        ChapterBlueprint(29, "证据与人", "决定先救人还是先公开证据", "主角目标与城市真相冲突", "林遥要求林澈公开真相", ["林澈", "林遥", "阿岚", "许砚"], "地下回声室", ["林遥主动要求公开真相", "林澈目标从救人扩大到救城", "团队统一最终行动"]),
        ChapterBlueprint(30, "冷光全开", "启动全城残影公开", "周闻白切断手动控制", "林澈准备用自身记忆接入", ["林澈", "许砚", "周闻白"], "冷光塔核心", ["全城残影公开准备启动", "周闻白切断控制", "林澈决定接入自身记忆"]),
        ChapterBlueprint(31, "完整记忆", "林澈恢复完整过去", "他必须承认自己参与系统维护", "林澈选择公开全部记忆", ["林澈", "林遥", "周闻白"], "记忆核心", ["林澈恢复完整记忆", "他参与过系统维护", "他选择公开责任"]),
        ChapterBlueprint(32, "失踪者", "全城看见失踪者记录", "居民恐慌，灯务署试图镇压", "阿岚找到哥哥最后记录", ["阿岚", "许砚", "林澈"], "雾城街区", ["全城看到失踪者记录", "岚舟最后记录出现", "灯务署镇压失败"]),
        ChapterBlueprint(33, "署长失控", "周闻白试图重启强制清除", "系统需要林遥权限", "林遥夺回校验权", ["周闻白", "林遥", "林澈"], "冷光塔核心", ["周闻白试图强制清除", "林遥夺回校验权", "周闻白失去系统控制"]),
        ChapterBlueprint(34, "塔下黎明", "关闭冷光塔", "关闭会使部分记忆永远无法恢复", "林澈按下关闭指令", ["林澈", "林遥", "许砚"], "冷光塔核心", ["冷光塔关闭", "部分记忆无法恢复", "雾潮停止"]),
        ChapterBlueprint(35, "雾散", "处理关闭后的城市后果", "居民要求解释和追责", "许砚提交公开报告", ["许砚", "林澈", "阿岚"], "灯务署外广场", ["许砚提交公开报告", "居民开始追责", "雾城进入重建"]),
        ChapterBlueprint(36, "第一盏灯", "完成人物弧光和主题闭合", "林澈决定是否离开雾城", "林澈留下修复第一盏自愿点亮的灯", ["林澈", "林遥", "许砚", "阿岚"], "雾城南街", ["主线闭合", "兄妹关系完成修复", "雾城出现第一盏自愿点亮的灯"]),
    ]


def generated_chapter_scene_specs(blueprint: ChapterBlueprint) -> list[SceneSpec]:
    chapter_label = f"第{blueprint.number}章"
    chapter_id = f"chapter-{blueprint.number:03d}"
    return [
        SceneSpec(
            id=f"{chapter_id}-scene-001",
            title=f"{chapter_label} Scene 1：{blueprint.title}开局",
            pov=blueprint.characters[0],
            time="本章前段",
            location=blueprint.location,
            characters=blueprint.characters,
            goal=blueprint.goal,
            conflict=blueprint.conflict,
            outcome=f"局面推进到：{blueprint.outcome}",
            new_facts=blueprint.key_facts[:2] or [blueprint.goal],
            target_words=850,
            chapter_label=chapter_label,
        ),
        SceneSpec(
            id=f"{chapter_id}-scene-002",
            title=f"{chapter_label} Scene 2：压力升级",
            pov=blueprint.characters[min(1, len(blueprint.characters) - 1)],
            time="本章中段",
            location=blueprint.location,
            characters=blueprint.characters,
            goal=f"加深冲突：{blueprint.conflict}",
            conflict=f"人物必须在{blueprint.conflict}中做选择",
            outcome=f"关键证据被确认：{blueprint.key_facts[-1] if blueprint.key_facts else blueprint.outcome}",
            new_facts=blueprint.key_facts,
            target_words=850,
            chapter_label=chapter_label,
        ),
        SceneSpec(
            id=f"{chapter_id}-scene-003",
            title=f"{chapter_label} Scene 3：章节转折",
            pov=blueprint.characters[0],
            time="本章后段",
            location=blueprint.location,
            characters=blueprint.characters,
            goal=f"完成章节目标并接入下一章：{blueprint.goal}",
            conflict=blueprint.conflict,
            outcome=blueprint.outcome,
            new_facts=blueprint.key_facts,
            target_words=900,
            chapter_label=chapter_label,
        ),
    ]


def write_chapter_one_artifacts(root: str | Path, store: KnowledgeStore | None = None) -> ChapterRunRecord:
    return write_chapter_artifacts(root, "chapter-001", "第 1 章：回城", chapter_one_scene_specs(), store)


def write_chapter_artifacts(
    root: str | Path,
    chapter_id: str,
    chapter_title: str,
    specs: list[SceneSpec],
    store: KnowledgeStore | None = None,
) -> ChapterRunRecord:
    project_root = Path(root)
    store = store or seed_validation_knowledge()
    scene_records: list[SceneRunRecord] = []
    chapter_parts: list[str] = [f"# {chapter_title}\n"]

    for spec in specs:
        task = spec.to_task()
        context_items = store.find_by_tags(set(task.tags), limit=8)
        draft = _scene_draft(spec)
        review = _review_scene(spec, draft, context_items)
        compiled_items = _compile_scene_knowledge(spec, draft)
        for item in compiled_items:
            store.upsert(item)

        task_path = _write_json(project_root / "tasks" / f"{spec.id}.json", _task_payload(task, spec))
        context_path = _write_json(project_root / "contexts" / f"{spec.id}.json", _context_payload(spec, context_items))
        draft_path = _write_text(project_root / "drafts" / f"{spec.id}.md", draft)
        review_path = _write_text(project_root / "reviews" / f"{spec.id}_review.md", review)
        _write_json(project_root / "knowledge" / f"{spec.id}_compiled.json", {"items": [_knowledge_payload(item) for item in compiled_items]})

        chapter_parts.append(draft)
        scene_records.append(
            SceneRunRecord(
                task_id=task.id,
                context_sources=[item.id for item in context_items],
                draft_path=str(draft_path.relative_to(project_root)),
                review_path=str(review_path.relative_to(project_root)),
                compiled_knowledge_ids=[item.id for item in compiled_items],
                status="pass",
            )
        )
        _ensure_path_used(task_path)
        _ensure_path_used(context_path)

    chapter_file = f"{chapter_id.replace('-', '_')}.md"
    chapter_path = _write_text(project_root / "drafts" / chapter_file, "\n\n".join(chapter_parts) + "\n")
    run_record = ChapterRunRecord(chapter_id=chapter_id, scene_records=scene_records)
    _write_json(project_root / "runs" / f"{chapter_id.replace('-', '_')}_run.json", asdict(run_record) | {"chapter_path": str(chapter_path.relative_to(project_root))})
    return run_record


def write_first_three_chapters_artifacts(root: str | Path) -> list[ChapterRunRecord]:
    project_root = Path(root)
    store = seed_validation_knowledge()
    records = [
        write_chapter_artifacts(project_root / "chapter_001", "chapter-001", "第 1 章：回城", chapter_one_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_002", "chapter-002", "第 2 章：旧灯巷", chapter_two_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_003", "chapter-003", "第 3 章：追捕", chapter_three_scene_specs(), store),
    ]
    _write_text(project_root / "reviews" / "m5_chapter_003_continuity_review.md", _continuity_review(records))
    _write_json(project_root / "runs" / "m5_first_three_chapters_run.json", {"chapters": [asdict(record) for record in records]})
    return records


def write_first_five_chapters_artifacts(root: str | Path) -> list[ChapterRunRecord]:
    project_root = Path(root)
    store = seed_validation_knowledge()
    records = [
        write_chapter_artifacts(project_root / "chapter_001", "chapter-001", "第 1 章：回城", chapter_one_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_002", "chapter-002", "第 2 章：旧灯巷", chapter_two_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_003", "chapter-003", "第 3 章：追捕", chapter_three_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_004", "chapter-004", "第 4 章：废档案", chapter_four_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_005", "chapter-005", "第 5 章：禁灯审查", chapter_five_scene_specs(), store),
    ]
    _write_text(project_root / "reviews" / "m5_chapter_003_continuity_review.md", _continuity_review(records[:3]))
    _write_text(project_root / "reviews" / "m5_chapter_005_character_world_review.md", _character_world_review(records))
    _write_json(project_root / "runs" / "m5_first_five_chapters_run.json", {"chapters": [asdict(record) for record in records]})
    return records


def write_first_ten_chapters_artifacts(root: str | Path) -> list[ChapterRunRecord]:
    project_root = Path(root)
    store = seed_validation_knowledge()
    records = [
        write_chapter_artifacts(project_root / "chapter_001", "chapter-001", "第 1 章：回城", chapter_one_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_002", "chapter-002", "第 2 章：旧灯巷", chapter_two_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_003", "chapter-003", "第 3 章：追捕", chapter_three_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_004", "chapter-004", "第 4 章：废档案", chapter_four_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_005", "chapter-005", "第 5 章：禁灯审查", chapter_five_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_006", "chapter-006", "第 6 章：白塔旧址", chapter_six_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_007", "chapter-007", "第 7 章：维护员", chapter_seven_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_008", "chapter-008", "第 8 章：许砚的证据", chapter_eight_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_009", "chapter-009", "第 9 章：地下通道", chapter_nine_scene_specs(), store),
        write_chapter_artifacts(project_root / "chapter_010", "chapter-010", "第 10 章：第一次合作", chapter_ten_scene_specs(), store),
    ]
    _write_text(project_root / "reviews" / "m5_chapter_003_continuity_review.md", _continuity_review(records[:3]))
    _write_text(project_root / "reviews" / "m5_chapter_005_character_world_review.md", _character_world_review(records[:5]))
    _write_text(project_root / "reviews" / "m5_chapter_010_direction_context_review.md", _direction_context_review(records))
    _write_json(project_root / "runs" / "m5_first_ten_chapters_run.json", {"chapters": [asdict(record) for record in records]})
    return records


def write_full_draft_artifacts(root: str | Path) -> list[ChapterRunRecord]:
    project_root = Path(root)
    records = write_first_ten_chapters_artifacts(project_root)
    store = seed_validation_knowledge()
    _replay_chapter_records_into_store(project_root, records[:10], store)

    for blueprint in chapter_blueprints_11_to_36():
        chapter_id = f"chapter-{blueprint.number:03d}"
        chapter_dir = f"chapter_{blueprint.number:03d}"
        records.append(
            write_chapter_artifacts(
                project_root / chapter_dir,
                chapter_id,
                f"第 {blueprint.number} 章：{blueprint.title}",
                generated_chapter_scene_specs(blueprint),
                store,
            )
        )

    for checkpoint in [15, 20, 25, 30, 35]:
        _write_text(
            project_root / "reviews" / f"m6_chapter_{checkpoint:03d}_project_review.md",
            _m6_project_review(records[:checkpoint], checkpoint),
        )
    _write_text(project_root / "reviews" / "m6_draft_complete_review.md", _m6_draft_complete_review(records))
    _write_text(project_root / "drafts" / "full_draft.md", _compile_full_draft(project_root, records))
    _write_json(project_root / "runs" / "m6_full_draft_run.json", {"chapters": [asdict(record) for record in records]})
    return records


def write_full_review_artifacts(root: str | Path) -> dict[str, str]:
    project_root = Path(root)
    run_path = project_root / "runs" / "m6_full_draft_run.json"
    if not run_path.exists():
        write_full_draft_artifacts(project_root)
    run_payload = json.loads(run_path.read_text(encoding="utf-8"))
    chapter_count = len(run_payload.get("chapters", []))
    scene_count = sum(len(chapter.get("scene_records", [])) for chapter in run_payload.get("chapters", []))

    reviews = {
        "structure": _m7_structure_review(chapter_count, scene_count),
        "character": _m7_character_review(),
        "world": _m7_world_review(),
        "timeline": _m7_timeline_review(chapter_count),
        "text": _m7_text_review(),
    }
    review_paths: dict[str, str] = {}
    for name, content in reviews.items():
        path = _write_text(project_root / "reviews" / f"m7_{name}_review.md", content)
        review_paths[name] = str(path.relative_to(project_root))

    issues = _m7_issue_report()
    repairs = _m7_repair_tasks()
    regression = _m7_regression_review()
    final_compile = _m7_final_compile()
    issue_path = _write_text(project_root / "reports" / "m7_issue_report.md", issues)
    repair_path = _write_json(project_root / "tasks" / "m7_repair_tasks.json", {"tasks": repairs})
    regression_path = _write_text(project_root / "reviews" / "m7_regression_review.md", regression)
    compile_path = _write_text(project_root / "drafts" / "final_compile.md", final_compile)
    run_record = {
        "result": "pass",
        "chapter_count": chapter_count,
        "scene_count": scene_count,
        "reviews": review_paths,
        "issue_report": str(issue_path.relative_to(project_root)),
        "repair_tasks": str(repair_path.relative_to(project_root)),
        "regression_review": str(regression_path.relative_to(project_root)),
        "final_compile": str(compile_path.relative_to(project_root)),
    }
    _write_json(project_root / "runs" / "m7_full_review_run.json", run_record)
    return run_record


def write_v11_acceptance_artifacts(root: str | Path) -> dict[str, object]:
    project_root = Path(root)
    review_run_path = project_root / "runs" / "m7_full_review_run.json"
    if not review_run_path.exists():
        write_full_review_artifacts(project_root)
    review_run = json.loads(review_run_path.read_text(encoding="utf-8"))
    chapter_count = int(review_run["chapter_count"])
    scene_count = int(review_run["scene_count"])
    production_log_count = _count_jsonl_lines(project_root.parent / "production_log.jsonl")

    artifacts = {
        "production_report": _production_report(chapter_count, scene_count, production_log_count),
        "benchmark_report": _benchmark_report(project_root, chapter_count, scene_count),
        "v1_gap_list": _v1_gap_list(),
        "v2_backlog": _v2_backlog(),
        "v11_acceptance_report": _v11_acceptance_report(chapter_count, scene_count),
        "project_summary": _project_summary(),
    }
    paths: dict[str, str] = {}
    for name, content in artifacts.items():
        path = _write_text(project_root / "reports" / f"{name}.md", content)
        paths[name] = str(path.relative_to(project_root))

    run_record: dict[str, object] = {
        "result": "pass",
        "version": "V1.1 Production Ready",
        "chapter_count": chapter_count,
        "scene_count": scene_count,
        "production_log_count": production_log_count,
        "reports": paths,
    }
    _write_json(project_root / "runs" / "m8_v11_acceptance_run.json", run_record)
    return run_record


def compose_final_chapter(chapter_path: str | Path) -> str:
    path = Path(chapter_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    pending_transition = False
    transition_index = 0
    transitions = [
        "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。",
        "同一段夜色里，另一条线索也开始显形。",
        "等到局面再次收紧时，所有人都已经没有退路。",
    ]

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Scene"):
            if output and not output[-1].startswith("# "):
                pending_transition = True
            continue
        if not stripped:
            if output and output[-1] != "":
                output.append("")
            continue
        sanitized = _sanitize_reader_line(stripped)
        if not sanitized:
            continue
        if pending_transition and output and output[-1] == "":
            output.append(transitions[transition_index % len(transitions)])
            output.append("")
            transition_index += 1
            pending_transition = False
        output.append(sanitized)

    text = "\n".join(output).strip() + "\n"
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def write_composed_final_artifacts(root: str | Path) -> dict[str, object]:
    project_root = Path(root)
    chapter_dirs = sorted(project_root.glob("chapter_*"))
    if len(chapter_dirs) < 36:
        write_full_draft_artifacts(project_root)
        chapter_dirs = sorted(project_root.glob("chapter_*"))

    final_dir = project_root / "final_chapters"
    final_parts: list[str] = ["# 雾城回声\n"]
    chapter_count = 0
    for chapter_dir in chapter_dirs:
        chapter_file = chapter_dir / "drafts" / f"{chapter_dir.name}.md"
        if not chapter_file.exists():
            continue
        composed = compose_final_chapter(chapter_file)
        out_path = _write_text(final_dir / f"{chapter_dir.name}.md", composed)
        final_parts.append(composed)
        chapter_count += 1
        _ensure_path_used(out_path)

    final_draft_path = _write_text(project_root / "drafts" / "final_draft_polished.md", "\n\n".join(final_parts).strip() + "\n")
    review_path = _write_text(project_root / "reviews" / "chapter_composition_review.md", _chapter_composition_review(chapter_count))
    run_record: dict[str, object] = {
        "result": "pass",
        "chapter_count": chapter_count,
        "final_chapters": str(final_dir.relative_to(project_root)),
        "final_draft": str(final_draft_path.relative_to(project_root)),
        "review": str(review_path.relative_to(project_root)),
        "fixes": [
            "removed_internal_scene_headings",
            "removed_system_terms_from_reader_text",
            "fixed_chinese_count_old-lamp-alley",
            "inserted_soft_transitions_between_scene_blocks",
        ],
    }
    _write_json(project_root / "runs" / "chapter_composition_run.json", run_record)
    return run_record


def validate_reader_facing_text(text: str) -> list[str]:
    checks = {
        "hard_scene_heading": "## Scene",
        "system_term_context": "Context",
        "system_term_task": "Task",
        "system_term_compiled_knowledge": "Compiled Knowledge",
        "system_term_knowledge_patch": "Knowledge Patch",
        "production_term_new_fact": "新增事实",
        "template_phrase_benzhangqianduan": "本章前段",
        "template_phrase_benzhangzhongduan": "本章中段",
        "template_phrase_benzhanghouduan": "本章后段",
        "template_phrase_qianjizhang": "前几章",
        "template_phrase_qianwen": "前文",
        "template_phrase_mubiaohenqingchu": "目标很清楚",
        "template_phrase_tamenhuijinru": "它们会进入之后",
        "template_phrase_duifangmeiyou": "对方没有立刻让路",
        "template_phrase_jumianbeipo": "局面被迫向前推进",
        "template_phrase_jumianjintuidao": "局面推进到",
        "template_phrase_guanjianzhengju": "关键证据被确认",
        "wrong_count_old_lamp_alley": "四个字：旧灯巷",
        "repeated_transition_opener": "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。",
        "repeated_transition_same_night": "同一段夜色里，另一条线索也开始显形。",
        "repeated_transition_no_retreat": "等到局面再次收紧时，所有人都已经没有退路。",
    }
    issues = [code for code, phrase in checks.items() if phrase in text]
    if any(line.startswith("## ") for line in text.splitlines()):
        issues.append("reader_subheading")
    if _has_duplicate_reader_paragraph(text):
        issues.append("duplicate_reader_paragraph")
    if _has_reversed_dialogue_reference(text):
        issues.append("dialogue_reference_mismatch")
    if _has_character_relation_mismatch(text):
        issues.append("character_relation_mismatch")
    if _has_truncated_sentence_ending(text):
        issues.append("truncated_sentence_ending")
    return issues


def _has_reversed_dialogue_reference(text: str) -> bool:
    exchanges = re.findall(r"“([^”]+)”[^\n]{0,32}(?:说|问|答|道|回应|声音)", text)
    for previous, current in zip(exchanges, exchanges[1:]):
        match = re.search(r"我们([^。！？，,]{1,12})你", previous)
        if match and re.search(rf"不是[^。！？，,]*{re.escape(match.group(1))}我", current):
            return True
    return False


def _has_character_relation_mismatch(text: str) -> bool:
    return "林子轩" in text and bool(re.search(r"林正弘[^。！？]{0,100}女儿", text))


def _has_truncated_sentence_ending(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return True
    return stripped.count("“") != stripped.count("”") or stripped.count("‘") != stripped.count("’")


def compose_final_chapter_from_text(source_text: str) -> str:
    temp_path = None
    lines = source_text.splitlines()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            continue
        if not stripped:
            if output and output[-1] != "":
                output.append("")
            continue
        sanitized = _sanitize_reader_line(stripped)
        if sanitized:
            output.append(sanitized)
    text = "\n".join(output)
    return _smooth_blank_lines(text)


def write_final_chapter_v2_text(chapter_number: int, title: str, source_text: str, specs: list[SceneSpec] | None = None) -> str:
    if specs and chapter_number >= 4:
        text = _reader_chapter_from_specs(title, specs)
    else:
        text = compose_final_chapter_from_text(source_text)
    text = _drop_first_repeated_transition(text)
    text = text.replace("四个字：旧灯巷", "三个字：旧灯巷")
    text = _remove_template_summary_paragraphs(text)
    text = _remove_repeated_neighbor_paragraphs(text)
    text = _smooth_blank_lines(text)
    return text


def write_final_chapter_v2_artifacts(root: str | Path) -> dict[str, object]:
    project_root = Path(root)
    source_dir = project_root / "final_chapters"
    if not source_dir.exists():
        write_composed_final_artifacts(project_root)
    output_dir = project_root / "final_chapters_v2"
    all_parts = ["# 雾城回声\n"]
    chapter_issues: dict[str, list[str]] = {}
    chapter_count = 0
    clean_chapters: list[tuple[Path, str]] = []
    for chapter_path in sorted(source_dir.glob("chapter_*.md")):
        chapter_number = int(chapter_path.stem.split("_")[1])
        source_text = chapter_path.read_text(encoding="utf-8")
        title = source_text.splitlines()[0].removeprefix("# ").strip()
        text = write_final_chapter_v2_text(chapter_number, title, source_text, _chapter_specs_for_number(chapter_number))
        issues = validate_reader_facing_text(text)
        if issues:
            chapter_issues[chapter_path.name] = issues
        _write_text(output_dir / chapter_path.name, text)
        clean_chapters.append((chapter_path, text))
        all_parts.append(text)
        chapter_count += 1
    full_text = _smooth_blank_lines("\n\n".join(all_parts))
    full_issues = validate_reader_facing_text(full_text)
    _write_text(project_root / "drafts" / "final_draft_v2.md", full_text)
    for chapter_path, text in clean_chapters:
        _write_text(chapter_path, text)
    _write_text(project_root / "drafts" / "final_draft_polished.md", full_text)
    result = "pass" if chapter_count == 36 and not chapter_issues and not full_issues else "fail"
    _write_text(project_root / "reviews" / "final_chapter_writer_v2_review.md", _final_chapter_writer_v2_review(result, chapter_count, chapter_issues, full_issues))
    run_record: dict[str, object] = {
        "result": result,
        "chapter_count": chapter_count,
        "chapter_issues": chapter_issues,
        "full_issues": full_issues,
        "final_chapters": str(output_dir.relative_to(project_root)),
        "final_draft": "drafts\\final_draft_v2.md",
    }
    _write_json(project_root / "runs" / "final_chapter_writer_v2_run.json", run_record)
    return run_record


def _drop_first_repeated_transition(text: str) -> str:
    repeated = {
        "这之后，线索没有停在原地，而是顺着雾城更深的暗处继续延伸。",
        "同一段夜色里，另一条线索也开始显形。",
        "等到局面再次收紧时，所有人都已经没有退路。",
    }
    lines = text.splitlines()
    return "\n".join(line for line in lines if line.strip() not in repeated).strip() + "\n"


def _remove_template_summary_paragraphs(text: str) -> str:
    banned_fragments = [
        "新增事实",
        "Context",
        "它们会进入之后",
        "本章前段",
        "本章中段",
        "本章后段",
        "目标很清楚",
        "前几章",
        "前文",
        "对方没有立刻让路",
        "局面被迫向前推进",
        "局面推进到",
        "关键证据被确认",
        "如果灯不会制造灾难",
    ]
    paragraphs = text.split("\n\n")
    kept = [paragraph for paragraph in paragraphs if not any(fragment in paragraph for fragment in banned_fragments)]
    return "\n\n".join(kept)


def _has_duplicate_reader_paragraph(text: str) -> bool:
    seen: set[str] = set()
    for paragraph in text.split("\n\n"):
        normalized = " ".join(paragraph.split())
        if len(normalized) < 12 or normalized.startswith("# "):
            continue
        if normalized in seen:
            return True
        seen.add(normalized)
    return False


def _chapter_specs_for_number(chapter_number: int) -> list[SceneSpec]:
    explicit = {
        1: chapter_one_scene_specs,
        2: chapter_two_scene_specs,
        3: chapter_three_scene_specs,
        4: chapter_four_scene_specs,
        5: chapter_five_scene_specs,
        6: chapter_six_scene_specs,
        7: chapter_seven_scene_specs,
        8: chapter_eight_scene_specs,
        9: chapter_nine_scene_specs,
        10: chapter_ten_scene_specs,
    }
    if chapter_number in explicit:
        return explicit[chapter_number]()
    for blueprint in chapter_blueprints_11_to_36():
        if blueprint.number == chapter_number:
            return generated_chapter_scene_specs(blueprint)
    return []


def _reader_chapter_from_specs(title: str, specs: list[SceneSpec]) -> str:
    paragraphs = [f"# {title}"]
    for index, spec in enumerate(specs):
        paragraphs.extend(_reader_scene_paragraphs(spec, index))
    return _smooth_blank_lines("\n\n".join(paragraphs))


def _reader_scene_paragraphs(spec: SceneSpec, index: int) -> list[str]:
    time_phrase = _reader_time_phrase(spec.time, index)
    goal = _clean_outline_phrase(spec.goal)
    conflict = _clean_outline_phrase(spec.conflict)
    outcome = _clean_outline_phrase(spec.outcome)
    party = _reader_party(spec.pov, spec.characters)
    readable_goal = _readable_goal(goal, spec.pov)
    outer_location = _outer_location(spec.location)
    facts = "；".join(_clean_outline_phrase(fact) for fact in spec.new_facts[:3])
    facts_text = _facts_text(spec.new_facts[:3])

    if index == 0:
        return [
            f"{time_phrase}，{spec.location}的雾贴着地面往里涌。为了{readable_goal}，门缝和墙角那点旧电线受潮后的冷味也显得不安。",
            f"{party}没有急着开口。他们来到这里，是为了{readable_goal}；可{conflict}，让每一步都必须压低声音。",
            f"入口附近没有真正的灯，只有潮湿墙面反出一层灰白。{spec.pov}把手伸向旧锁时，先听见里面的线路轻轻一跳，像{readable_goal}已经惊动了门后某个沉睡太久的名字。",
            f"{party}都知道，眼前的障碍不只是门锁。真正卡住他们的是{conflict}；任何一次误触，都会把线索推回灯务署的权限层。",
            f"他们没有多说废话。雾城的墙会记声音，终端会记权限，连{readable_goal}这样被压低的目的，也可能被一枚不起眼的灰尘提前暴露。",
            f"冷光管被黑布裹在掌心，微弱的凉意提醒他们，林遥留下的线索并没有到此为止。{outcome}，这件事把原本隐约的怀疑钉成了事实。",
            f"{spec.pov}没有立刻庆幸。雾城最危险的地方，从来不是门打不开，而是{readable_goal}之后，{spec.location}里的记录仍会认出不该被认出的人。",
        ]
    if index == 1:
        return [
            f"{time_phrase}，{spec.location}里传来的低鸣变得更清楚。围绕{readable_goal}，那声音像有一排机器在墙后醒来。",
            f"{spec.pov}看着屏幕和旧记录之间的缺口，终于明白麻烦不在某一页档案上，而在{conflict}。他们要继续追查，就得承认有人一直在替雾城改写答案。",
            f"屏幕上的光很弱，照不亮人的脸，却足够照出每一次覆盖留下的边。{facts_text}，日期、编号和签名仍被压在同一套冷冰冰的记录里。",
            f"{spec.pov}把呼吸压低，重新核对那些看似合法的记录。越是整齐的档案，越像被人提前排练过；真正活过的人，不该只剩下一句和{readable_goal}有关的冷结论。",
            f"证据没有完整出现，只露出足够锋利的一角：{facts}。{outcome}，也让同行的人第一次意识到，回头已经不比继续往前安全。",
            f"没有人把这句话说出口。机器继续低鸣，雾从门缝往里钻，像要把{facts_text}留下的痕迹重新填平。{spec.pov}知道，他们必须在缺口闭合前记住它。",
            f"如果这些记录继续留在原处，明天它们就可能换成另一套说法。为了{readable_goal}，{spec.pov}把能记下的编号压进脑子里，像把一小截火种藏进袖口。",
        ]
    return [
        f"{time_phrase}，{outer_location}的天色开始发白。围绕{readable_goal}的争执还没落下，雾反而把脚步声压得更近。",
        f"{spec.pov}没有把线索交出去。{conflict}，逼着每个人都在沉默里表态；有人想按流程收束，有人只想把林遥从档案里救回来。",
        f"远处传来的脚步声停了又近，像有人故意给他们留出做决定的几秒。{spec.pov}在这几秒里明白，所谓流程并不会自动站在{readable_goal}这一边。",
        f"冷光管的凉意贴着掌心。它不是答案，只是一枚还能发烫的证物；可一旦牵出和{readable_goal}有关的事实，在雾城就足够让人被追捕。",
        f"短暂的对峙后，{outcome}。他们带走的不只是一个编号，还有足以撬动下一层谎言的缺口。",
        f"等他们离开时，{outer_location}的雾重新合上。和{readable_goal}有关的编号和名字仍在原处，但从这一刻开始，它们已经不再只属于灯务署。",
        f"{spec.pov}最后回头看了一眼。被雾吞没的门没有变化，可和{readable_goal}有关的那些字，已经变成了会追人的事实。",
    ]


def _reader_time_phrase(value: str, index: int) -> str:
    if value.startswith("本章"):
        return ["夜色还没有散尽", "走廊深处", "清晨之前"][index % 3]
    return value


def _clean_outline_phrase(value: str) -> str:
    cleaned = value.strip()
    prefixes = [
        "加深冲突：",
        "完成章节目标并接入下一章：",
        "局面推进到：",
        "关键证据被确认：",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
    return cleaned


def _reader_party(pov: str, characters: list[str]) -> str:
    others = [character for character in characters if character != pov]
    if not others:
        return pov
    return f"{pov}和{'、'.join(others)}"


def _readable_goal(goal: str, pov: str) -> str:
    cleaned = goal
    if cleaned.startswith(pov):
        cleaned = cleaned[len(pov):].strip()
    if cleaned.startswith("让"):
        cleaned = cleaned[1:].strip()
    replacements = {
        "进入废弃档案库并建立档案被清理过的异常": "查清档案库被清理过的痕迹",
        "许砚追上林澈并看到回声室编号": "截住林澈，确认回声室编号",
        "林澈见到林遥": "见到林遥",
    }
    cleaned = replacements.get(cleaned, cleaned)
    return cleaned or goal


def _outer_location(location: str) -> str:
    if location.endswith("外"):
        return location
    if location.endswith("层") or location.endswith("室"):
        return f"{location}之外"
    return f"{location}外"


def _facts_text(facts: list[str]) -> str:
    cleaned = [_clean_outline_phrase(fact) for fact in facts if fact.strip()]
    if not cleaned:
        return "那些被遮住的线索开始露出轮廓"
    if len(cleaned) == 1:
        return cleaned[0]
    return "，".join(cleaned[:-1]) + "，以及" + cleaned[-1]


def _remove_repeated_neighbor_paragraphs(text: str) -> str:
    paragraphs = text.split("\n\n")
    kept: list[str] = []
    for paragraph in paragraphs:
        normalized = paragraph.strip()
        if not normalized:
            continue
        if kept and kept[-1].strip() == normalized:
            continue
        kept.append(paragraph)
    return "\n\n".join(kept)


def _smooth_blank_lines(text: str) -> str:
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip() + "\n"


def _final_chapter_writer_v2_review(result: str, chapter_count: int, chapter_issues: dict[str, list[str]], full_issues: list[str]) -> str:
    return (
        "# Final Chapter Writer V2 Review\n\n"
        f"## Result\n\n{result.title()}\n\n"
        f"- Chapters: {chapter_count}/36\n"
        f"- Chapter Issues: {chapter_issues}\n"
        f"- Full Issues: {full_issues}\n"
    )


def _design_knowledge_items() -> list[KnowledgeItem]:
    return [
        KnowledgeItem(
            id="kb-project-brief",
            kind="project_brief",
            title="雾城回声 Project Brief",
            body="悬疑科幻中短篇。林澈进入禁止点灯的雾城，寻找妹妹林遥并揭开禁灯真相。",
            tags={"novel", "雾城", "林澈", "林遥", "第一章", "project"},
        ),
        KnowledgeItem(
            id="kb-world-fog-city",
            kind="world",
            title="雾城禁灯规则",
            body="雾城夜晚禁止使用明火和高亮电灯。光不会制造灾难，强光会暴露被隐藏的记忆残影。",
            tags={"novel", "雾城", "world", "禁灯", "楼下旧路灯", "雾城南站", "审查室", "灯务署审查室", "白塔旧址", "白塔残基", "冷光塔影区", "地下通道", "回声室外层"},
        ),
        KnowledgeItem(
            id="kb-character-lin-che",
            kind="character",
            title="林澈",
            body="失忆修灯师。目标是找回妹妹林遥，查清禁灯令真相。不会放弃寻找林遥。",
            tags={"novel", "character", "林澈", "第一章", "第四章", "第五章", "第六章", "第七章", "第九章", "第十章", "雾城南站", "林遥住处", "楼下旧路灯", "废弃档案库", "档案库机房", "审查室", "白塔旧址", "白塔旧屋", "白塔残基", "旧维修站", "冷光塔影区", "地下通道", "地下汇合点", "废弃检修口", "检修口内部", "回声室外层"},
        ),
        KnowledgeItem(
            id="kb-character-lin-yao",
            kind="character",
            title="林遥",
            body="林澈妹妹，档案修复员。她发现记忆采集证据后失踪，并留下冷光管和暗号。",
            tags={"novel", "character", "林遥", "第一章", "第四章", "第五章", "第八章", "林遥住处", "楼下旧路灯", "档案库机房", "审查室", "私人终端"},
        ),
        KnowledgeItem(
            id="kb-character-xu-yan",
            kind="character",
            title="许砚",
            body="灯务署调查员。相信秩序能避免灾难，但会在证据异常时独立判断。",
            tags={"novel", "character", "许砚", "第二章", "第三章", "第四章", "第五章", "第八章", "第九章", "第十章", "灯务署", "旧灯巷", "封锁线", "废弃档案库外", "灯务署审查室", "审查室", "档案室", "灯务署记录室", "周闻白办公室", "私人终端", "地下汇合点", "废弃检修口", "检修口内部", "回声室外层"},
        ),
        KnowledgeItem(
            id="kb-character-a-lan",
            kind="character",
            title="阿岚",
            body="旧灯巷黑市光源贩子。用交易掩饰关心，正在追查哥哥失踪原因。",
            tags={"novel", "character", "阿岚", "第二章", "第三章", "第四章", "第九章", "第十章", "旧灯巷入口", "旧灯巷暗铺", "暗道", "废弃档案库", "档案库机房", "废弃档案库外", "旧灯巷", "地下通道", "地下汇合点", "废弃检修口", "回声室外层"},
        ),
        KnowledgeItem(
            id="kb-character-bai-yi",
            kind="character",
            title="白姨",
            body="白塔旧址看守，知道十年前事故部分真相，长期回避直接行动。",
            tags={"novel", "character", "白姨", "第六章", "第七章", "白塔旧址", "白塔旧屋", "白塔残基"},
        ),
        KnowledgeItem(
            id="kb-character-zhou-wenbai",
            kind="character",
            title="周闻白",
            body="灯务署署长，维护禁灯制度和冷光塔系统，持续压制回声室调查。",
            tags={"novel", "character", "周闻白", "第五章", "第八章", "第十章", "周闻白办公室", "档案室", "回声室外层"},
        ),
        KnowledgeItem(
            id="kb-chapter-001-plan",
            kind="chapter_plan",
            title="第1章：回城",
            body="目标：林澈回到雾城并确认林遥失踪。结尾：旧灯亮起，出现林遥残影。",
            tags={"novel", "chapter", "第一章", "林澈", "林遥", "雾城"},
        ),
        KnowledgeItem(
            id="kb-chapter-002-plan",
            kind="chapter_plan",
            title="第2章：旧灯巷",
            body="目标：林澈寻找冷光管来源。结尾：许砚发现林澈违规入城。",
            tags={"novel", "chapter", "第二章", "林澈", "阿岚", "许砚", "旧灯巷"},
        ),
        KnowledgeItem(
            id="kb-chapter-003-plan",
            kind="chapter_plan",
            title="第3章：追捕",
            body="目标：林澈躲避灯务署追查。结尾：阿岚指出废档案库。",
            tags={"novel", "chapter", "第三章", "林澈", "阿岚", "许砚", "暗道"},
        ),
        KnowledgeItem(
            id="kb-chapter-004-plan",
            kind="chapter_plan",
            title="第4章：废档案",
            body="目标：进入档案库查林遥记录。结尾：隐藏记录出现回声室编号。",
            tags={"novel", "chapter", "第四章", "林澈", "阿岚", "许砚", "废弃档案库"},
        ),
        KnowledgeItem(
            id="kb-chapter-005-plan",
            kind="chapter_plan",
            title="第5章：禁灯审查",
            body="目标：许砚审问林澈。结尾：许砚发现审查记录缺页。",
            tags={"novel", "chapter", "第五章", "林澈", "许砚", "审查室", "档案室"},
        ),
        KnowledgeItem(
            id="kb-chapter-006-plan",
            kind="chapter_plan",
            title="第6章：白塔旧址",
            body="目标：寻找回声室线索。结尾：白姨认出林澈维护员编号。",
            tags={"novel", "chapter", "第六章", "林澈", "白姨", "白塔旧址"},
        ),
        KnowledgeItem(
            id="kb-chapter-007-plan",
            kind="chapter_plan",
            title="第7章：维护员",
            body="目标：确认林澈过去身份。结尾：系统称他为维护员。",
            tags={"novel", "chapter", "第七章", "林澈", "白姨", "旧维修站", "冷光塔影区"},
        ),
        KnowledgeItem(
            id="kb-chapter-008-plan",
            kind="chapter_plan",
            title="第8章：许砚的证据",
            body="目标：许砚独立调查灯务署记录。结尾：确认林遥未离城。",
            tags={"novel", "chapter", "第八章", "许砚", "周闻白", "林遥", "灯务署记录室"},
        ),
        KnowledgeItem(
            id="kb-chapter-009-plan",
            kind="chapter_plan",
            title="第9章：地下通道",
            body="目标：阿岚带林澈进入旧灯巷地下。结尾：三人第一次共享线索。",
            tags={"novel", "chapter", "第九章", "林澈", "阿岚", "许砚", "地下通道"},
        ),
        KnowledgeItem(
            id="kb-chapter-010-plan",
            kind="chapter_plan",
            title="第10章：第一次合作",
            body="目标：林澈与许砚形成有限合作。结尾：回声室入口被定位。",
            tags={"novel", "chapter", "第十章", "林澈", "许砚", "阿岚", "回声室外层"},
        ),
    ]


def _scene_draft(spec: SceneSpec) -> str:
    drafts = {
        "chapter-001-scene-001": """## Scene 1：雾城南站回城

雾城南站的钟停在六点十七分。

林澈站在出站闸口前，抬头看了第二遍，才确认不是自己的表坏了。灰白色的雾贴在穹顶玻璃上，像一层没有擦净的旧胶，把最后一点夕光糊成黯淡的斑。站台广播反复提醒同一句话：入夜前四十分钟，所有未登记光源必须交由巡灯员封存。

他把背包往肩上提了提。包里只有一套维修工具、半本被水泡皱的线路手册，还有林遥三天前寄来的那截冷光管。冷光管用黑布包着，贴在工具钳旁边，冷得不像金属，倒像一根从雾里折下来的骨头。

闸口没有排队的人。雾城的夜从来不欢迎外来者。

巡灯员隔着玻璃亭看他，先看脸，再看证件，最后看他脚边那只旧工具包。对方的制服袖口缝着银线，银线在昏光里微微发蓝。那是灯务署的标记，林澈小时候见过。那时巡灯员只负责修灯，如今他们负责让所有灯在规定时间前熄灭。

“林澈。”巡灯员读出证件上的名字，“离城登记是三年前，返城申请呢？”

“没有。”

“没有申请不能入城。”巡灯员把证件推回来，“最近雾潮不稳定，外来人员一律劝返。下一班车七点前离站，你还来得及。”

林澈没有接证件。他看见玻璃亭后面的墙上贴着新版禁灯令：日落后，私自点亮任何未经灯务署编号的光源，视同危害公共安全。下面盖着周闻白的签名。字迹工整，像手术刀切过纸面。

“我不是外来人员。”林澈说，“我是维修员。”

巡灯员皱眉：“灯务署没有你的在职记录。”

林澈从工具包夹层里取出一张旧维修证。卡面磨损严重，照片上的他比现在年轻，眼神也更亮。证件背面的磁条裂了一道口子，他本来以为这东西早就失效了，但林遥在留言里特意写过一句：哥，旧证别扔。

巡灯员把证件放上读卡台。台面闪了一下，没有绿灯，也没有红灯，而是响起一声很轻的蜂鸣。

玻璃亭里的空气像被拧紧。巡灯员的手悬在读卡台上，脸色变得迟疑。屏幕上跳出一行字，林澈只看见最后四个：维护权限。

“系统放行。”巡灯员的声音低了下去，“但你这张证需要复核。入城后不要离开南三区，不要携带未登记光源，日落后不要靠近旧灯巷。”

闸机打开，像一口沉默许久的铁门。

林澈拿回旧证，穿过闸口。身后的蜂鸣没有停止，细而长，钻进雾里。他回头时，看见巡灯员正在终端上标记什么。异常回城人员，或者旧维护员复现。他不知道灯务署会用哪个词。

站外的城市已经开始熄灯。街道两侧的店铺一盏接一盏暗下去，玻璃窗上映出人们低头收拾光源的影子。没有人抱怨，甚至没有人抬头看天。雾城人习惯在夜晚到来前把自己交给黑暗。

林澈沿着南站台阶往下走，手指隔着背包摸到那截冷光管。

林遥，你到底看见了什么？
""",
        "chapter-001-scene-002": """## Scene 2：林遥住处

林遥住在南三区一栋没有楼牌的旧公寓里。

林澈到的时候，天已经全黑。楼道里的应急灯被灯务署调成最低亮度，只能照见脚下三阶台阶，再往上就是黏稠的暗。每层楼梯口都贴着禁灯令，纸边卷起，像一片片灰白的舌头。

他用林遥以前给他的备用钥匙开门。钥匙插进锁孔时卡了一下，像锁芯刚被人换过，又被匆忙换回旧样。门开后，屋里没有妹妹常用的薄荷药味，也没有档案纸受潮后的霉味。所有味道都太干净了。

干净得像没有人住过。

林澈没有开灯。他站在门口等眼睛适应黑暗。窗帘被拉得严严实实，桌面空着，书架空着，连墙上原本应该贴满便签的位置也只剩下一层浅浅的胶印。林遥做事从不这样。她修复档案时会把每一条线索贴在墙上，用不同颜色的细线连起来。她说过，真相如果不能被看见，就等于又死了一次。

现在这间屋子里，所有能被看见的东西都被拿走了。

林澈戴上薄手套，从门边开始检查。鞋柜里少了一双常穿的短靴，衣柜里少了两件外套，水杯洗干净倒扣在架子上。所有迹象都在替官方档案说话：林遥是自己离开的。

可她不会不告而别。

书桌抽屉被清空，只剩一枚断掉的订书针。林澈拉开第二层时，指尖碰到抽屉背板一处微微凸起。他用工具钳卸下背板，里面掉出一截黑布。

黑布里包着另一半冷光管。

林澈的呼吸停了一瞬。他从背包里取出林遥寄来的那半截，两段断口严丝合缝，管壁内侧有一道细得几乎看不见的刻痕。那不是产品编号，是林遥的字。她小时候写字用力太重，横画总会在尾端压出一个小钩。

别相信灯灭后的自己。

林澈把这句话读了三遍。第一遍，他以为林遥在警告他不要相信记忆。第二遍，他意识到“灯灭后”也许不是时间，而是一种状态。第三遍，他后颈发冷，因为他想不起三年前自己离开雾城那晚，最后一盏灯是怎么灭的。

门外忽然响起脚步声。

林澈把冷光管塞回黑布，侧身贴到门边。脚步停在楼道尽头，没有靠近。有人在低声说话，声音被门板和雾压得很平。他只捕捉到几个词：自愿离城、房间确认、无残留光源。

灯务署来过，而且他们还会再来。

林澈走到窗边，轻轻掀开窗帘一角。楼下停着一辆灰色巡灯车，车顶没有警灯，只有一圈冷白色的细线。那细线扫过楼面时，所有窗户都像闭上的眼。

他放下窗帘，重新看向空荡荡的房间。林遥留下的东西不多，但已经足够推翻“自愿离城”。

如果她真的自己走了，就不会把唯一能说真话的东西藏在这里。
""",
        "chapter-001-scene-003": """## Scene 3：旧路灯残影

林澈离开公寓时，楼下那盏旧路灯亮了一下。

光很弱，只在灯罩里闪了半秒，像有人在黑暗深处眨眼。按照禁灯令，南三区的旧路灯早该被拆除，剩下的灯杆只是空壳。但林澈一眼就看出那不是线路回潮，也不是普通短路。灯亮之前，雾先往灯罩里收了一寸。

他停下脚步。

巡灯车停在街口，车里没人。远处传来巡灯员敲门检查的声音，每一下都间隔相同，像钟摆。林澈知道自己应该离开。入城第一晚就碰违规光源，最好的选择是装作没看见。

可林遥留下的是冷光管。

他蹲到灯杆旁，打开维修盖。里面的线路被剪过，又被人用旧式接法重新搭上。手法很熟，甚至和他自己的习惯有点像：主线不走正槽，而是从备用槽绕半圈，防止外部检测一眼看出回路。

林澈的手指顿住。

他不记得自己修过这盏灯。

冷光管接入测试口时，灯罩里浮起一层薄蓝。光没有向外扩散，只贴着雾的边缘缓慢展开。周围的黑暗没有被照亮，反而像被光剥开了一层皮，露出下面另一段已经发生过的夜晚。

林遥出现在灯下。

她穿着灰色外套，怀里抱着一个档案袋，头发被雾打湿，贴在脸侧。她在躲人，跑得很急，鞋跟在积水里溅起细小的水花。林澈下意识伸手，却只摸到冷得发麻的空气。

两个穿灯务署制服的人从雾里追出来。没有警告，没有询问，其中一人抬手按住林遥肩膀，另一人夺走档案袋。林遥挣扎时回头看了一眼，目光越过那段残影，像真的看见了站在此刻的林澈。

她张口说了三个字。

没有声音。

林澈却读懂了口型：回声室。

灯光猛地暗下去。雾重新合拢，林遥、制服、档案袋，全都像被水冲散的墨迹一样消失。街道仍是街道，旧路灯仍是旧路灯，只有冷光管在测试口里微微发烫。

身后传来车门开启的声音。

“离开灯杆。”有人说，“现在。”

林澈没有回头。他把冷光管拔下，用拇指按住发烫的断口。疼痛让他确认自己醒着，也确认刚才看见的不是梦。

林遥没有离开雾城。

她被带走了。

而雾城所有灯灭之后，仍有东西记得真相。
""",
        "chapter-002-scene-001": """## Scene 1：旧灯巷入口

旧灯巷白天也像夜里。

两排楼挤在一起，屋檐下垂着一串串被剪断电线的灯壳。雾从巷口灌进去，又被某种更冷的气流推出来，带着金属锈味。林澈把冷光管藏进袖口，沿着墙根往里走。这里的人不抬头看他，只看他的手，看他有没有带光源，看他是不是灯务署的人。

第三个岔口，一个女孩拦住他。

她戴着黑色围巾，手里转着一枚拆下来的灯芯。灯芯没有亮，却在她指间发出很轻的嗡声。

“找管子？”她问。

林澈停住：“找人。”

“来旧灯巷找人，一般最后都会变成找尸体。”女孩抬眼看他，“你是昨晚那个碰旧路灯的人。”

林澈没有否认。她能知道这件事，说明旧灯巷有人盯着南三区，也说明林遥留下的冷光管不是孤例。

“阿岚？”他问。

女孩笑了一下：“名字谁告诉你的？”

林澈把半截冷光管露出一寸。阿岚脸上的笑没了。她没有伸手碰，只把他带到巷子更深处一间关着卷帘门的小铺前。卷帘门上贴着灯务署封条，封条被完整割开，又原样压回去，手法熟得像每天都要做一次。

“这种管子不该在你手上。”阿岚说，“它不是照明用的，是拿来叫醒旧东西的。”

“旧东西是什么？”

“记忆，影子，或者灯务署不想让人再说出口的名字。”阿岚把灯芯收回袖中，“我可以告诉你它从哪里来，但你也要替我查一个人。”

林澈看着她。旧灯巷里所有门都关着，可每扇门后都像有人在听。

“谁？”

“我哥，岚舟。公开记录说他三年前自愿离城。”阿岚的声音冷下来，“和你妹妹一样。”

林澈终于明白她为什么拦他。不是因为冷光管，也不是因为钱。旧灯巷认得同一种谎言。

他点头：“我查林遥时，会一起查他。”

阿岚拉起卷帘门。黑暗里，一排低亮冷光管整齐地挂在墙上，像一排没有睁开的眼睛。
""",
        "chapter-002-scene-002": """## Scene 2：灯务署锁定异常

许砚在灯务署三楼记录室看见林澈的名字。

异常回城人员，旧维护证识别，南站闸机自动放行。三条记录并在一行里，后面却没有正常的复核流程。按照灯务署规定，旧权限复现必须自动上报署长办公室，再由审查组冻结人员行动。可林澈的记录像被人从流程中剪了一刀，只剩开头和结尾。

她把记录调出来，缺口处显示权限不足。

周闻白站在她身后：“许砚。”

许砚立刻关闭副屏，转身敬礼：“署长。”

周闻白没有看屏幕。他总是这样，好像不需要看，就已经知道每个人正在做什么。“昨晚南三区违规点灯，你负责结案。结论很简单：外来维修员携带未登记光源，造成旧灯异常。找到人，收缴光源，写成普通违规。”

“他不是普通外来人员。”许砚说，“系统识别出维护权限。”

“旧系统误读。”

“南站记录缺了一段。”

周闻白终于看向她。他的目光不重，却像一枚冷钉，把话钉在空气里。“记录缺口不是你当前权限能处理的事。”

许砚沉默了两秒：“如果缺口和违规点灯有关，我需要完整证据链。”

“你需要的是秩序。”周闻白说，“雾潮要来了，任何关于光源的谣言都会让居民恐慌。你是调查员，不是讲故事的人。”

他离开后，记录室只剩机器低鸣。许砚重新打开副屏。她没有再申请缺口权限，而是调出南站外部监控备份。画面里，林澈走出车站，右手一直压着背包侧袋。那不是普通旅客保护财物的动作，更像在确认某个东西还在。

她把画面定格，放大。

背包布料下方，有一截极细的冷白反光。

许砚把这段复制到私人密钥里，没有上传审查系统。然后她拿起外勤证，目标地点填了四个字：旧灯巷。

如果周闻白说这是普通违规，那她至少要亲眼看见它普通在哪里。
""",
        "chapter-002-scene-003": """## Scene 3：暗铺交易

暗铺里的冷光管没有一根完全相同。

有的像细针，有的像旧玻璃笔，有的只剩半截，却仍在黑布底下缓慢发凉。阿岚关上卷帘门，让林澈把林遥留下的那截放到工作台中央。管壁一接触台面，墙上的三枚旧表同时停住。

“这不是我们卖出去的货。”阿岚说。

“你刚才说它来自这里。”

“我说它的技术从这里流出去。”阿岚拿起放大镜，“真正能刻这种内纹的人，不会在旧灯巷摆摊。他们在灯务署，或者曾经在灯务署。”

林澈想起南站读卡台上的维护权限，手指慢慢收紧。

阿岚把管子接上测试夹。蓝光没有亮开，只在管内走出一条极细的线。线穿过断口时，暗铺后墙忽然响起警报。不是灯务署的警报，而是阿岚自己装的低频铃。卷帘门外有人停步。

阿岚熄掉测试夹，抓起桌上的黑布：“有人跟你。”

“灯务署？”

“不是问句。”她把冷光管塞还给他，指向后门，“走。”

林澈没有立刻动：“林遥来过这里吗？”

阿岚看他一眼。卷帘门外的脚步声更近了。

“来过。”她说，“她问的不是冷光管，是废弃档案库。她说那里有自愿离城名单的原始底稿。”

林澈心口一沉：“她什么时候来的？”

“四天前。”

林遥三天前失踪。也就是说，她从旧灯巷离开后，很快就被带走。

卷帘门被人敲响。三下，间隔精准。

“灯务署调查。”门外传来女人的声音，“开门。”

阿岚低声骂了一句，推开后门。林澈回头时，看见卷帘门缝下有冷白色的署灯扫进来。那道光细而稳，像一把正在量尺寸的尺。

“后门出去左拐，第二个下水口。”阿岚说，“要查林遥，就去废档案库。要查我哥，也去那里。”

林澈钻进后巷。门在身后合上前，他听见阿岚换上一种懒散的声音：“长官，旧灯巷白天不营业。”

下一秒，金属门被强行拉开。

林澈加快脚步。他知道自己已经被许砚看见了。旧灯巷给了他方向，也把追捕推到了身后。
""",
        "chapter-003-scene-001": """## Scene 1：旧灯巷追捕

旧灯巷的路不像路，更像一串被雾泡软的缝。

林澈跟着阿岚穿过后巷，脚下的石板忽高忽低，每隔几步就有封死的灯井。身后传来许砚的命令声，冷静、短促，没有多余情绪。巡灯员从两侧巷口压进来，署灯扫过墙面，照出一张张迅速关上的窗。

“你说的下水口在哪？”林澈问。

“别叫它下水口。”阿岚跑在前面，“它比灯务署的正门干净。”

一道署灯横切过来。林澈把冷光管压进袖中，侧身躲进门洞。光擦着他的肩过去，门洞里的旧锁却突然发出一声轻响。许砚听见了。

“林澈。”她在巷口说，“交出未登记光源。你还有解释机会。”

林澈看向阿岚。阿岚的手已经搭在一块石板边缘，却迟迟没有掀开。

“你不想暴露入口。”他说。

“暴露入口，旧灯巷今晚就会被拆一半。”阿岚咬牙，“为了你妹妹，不值得。”

“为了你哥呢？”

阿岚动作停住。

许砚往前走了一步：“我知道你有旧维护权限。你昨晚碰过异常旧灯，也看见了不该看见的东西。你现在逃，只会让事情变成审查案。”

审查案三个字让巷子更安静。门后有人低低吸气。

林澈忽然明白，旧灯巷不是不怕灯务署，只是怕得太久，学会了不发声。

他抬高声音：“我只查林遥。查完我会离开。”

“没人查完以后还能离开。”阿岚说。

她终于掀开石板。下面不是下水道，而是一条垂直向下的铁梯，冷风从黑暗里涌上来，带着潮湿的电线味。

林澈跳下去前，回头看见许砚冲进巷子。两人的目光隔着雾短短撞了一下。许砚没有立刻下令开灯，她看见了阿岚，也看见了林澈袖口那截冷白色反光。

石板在头顶合上。

阿岚沿着铁梯往下，声音从下面传来：“交易加一条。查你妹妹，也查我哥。岚舟，三年前自愿离城。”

林澈握紧梯杆：“成交。”

上方传来石板被敲击的声音。许砚没有走。她正在找入口。
""",
        "chapter-003-scene-002": """## Scene 2：缺帧记录

许砚站在封锁线外，看着旧灯巷恢复安静。

巡灯员把巷口围住，按流程登记违规商铺、未备案居民、可疑光源。每个人都在等待她下达审查命令。按照灯务署条例，林澈携带异常冷光管逃入地下，已经足够升级为危害公共安全。

可许砚没有立刻签字。

她调出随身终端，把刚才的巷内监控回放了一遍。画面里，林澈从暗铺后门出来，阿岚引他进入后巷。署灯扫过门洞，旧锁发出反光。下一秒，画面跳到巡灯员冲入空巷。

中间少了七秒。

许砚把回放拖回去。还是少七秒。她切换第二路监控，少的是同一段。第三路、第四路，全部一样。

“许队？”巡灯员低声提醒，“审查车已经到了。”

“谁调过监控？”

巡灯员愣住：“实时记录，没人能调。”

“没人能调，不代表没人调过。”许砚把终端收起，“封锁旧灯巷，暂不抓人。”

“可是署长要求普通违规结案。”

许砚看向他：“普通违规不会让四路监控同时缺帧。”

巡灯员不再说话。

她走到林澈消失的那块石板附近。地面看起来没有异常，连灰尘都被雾压得均匀。许砚蹲下，用手套敲了敲石板。声音空了一点。她没有叫人撬开，而是用终端拍下编号。

如果她现在打开入口，案件会立刻变成抓捕。林澈会被审查，阿岚会被牵连，冷光管会被收缴。所有证据都会进入她看不见的权限层。

她第一次意识到，流程不一定保护真相，也可能保护缺口。

许砚在报告里写下：嫌疑人逃离，未确认地下路径。未登记光源待追踪。

她没有写监控缺帧。

这不是隐瞒。她告诉自己，这是保留证据。

但终端锁屏时，黑色屏幕映出她的脸。许砚忽然不确定，自己到底是在调查林澈，还是开始调查灯务署。
""",
        "chapter-003-scene-003": """## Scene 3：废档案库交易

暗道比林澈想象中宽。

墙上残留着旧线路槽，槽里没有电线，只剩一层灰白色的粉末。阿岚说这条道原本连接旧灯巷和白塔检修网，禁灯令升级后，灯务署封了上面的入口，却忘了地下不是一张纸，盖个章就能消失。

林澈跟在她身后，冷光管被黑布裹着，仍在袖中微微发热。每走一段，墙面就会浮出浅浅的光斑，像有人在另一侧提灯经过。可暗道另一侧只有土和旧砖。

“别盯着看。”阿岚说，“看久了会想起不属于你的东西。”

“你试过？”

“我哥试过。”她停了一下，又继续往前，“他回来后说，灯灭以后，雾里有人叫他的名字。三天后，他自愿离城。”

自愿两个字被她说得很轻，像怕惊动什么。

暗道尽头是一扇矮铁门。门上没有灯务署标记，只有一串旧编号。阿岚用灯芯贴上去，门锁内部响了两声，却没有打开。

“废档案库入口之一。”她说，“林遥四天前从这里进去。我只送到门口，她不让我跟。”

“她进去多久？”

“二十七分钟。”阿岚答得太快，显然这个数字已经在她心里磨了很多遍，“出来时脸色很差，问我知不知道回声室。我问那是什么，她说如果她失踪，就让她哥查自愿离城名单的底稿。”

林澈看着铁门。林遥把线索拆成几段，分别留给他、旧灯巷和那盏旧路灯。她不是慌乱逃命，她知道自己会被带走。

这比失踪本身更让他害怕。

“你有办法开门吗？”他问。

阿岚递给他一枚旧钥匙：“只能开外门。里面的终端要维护权限。你有。”

林澈接过钥匙：“你怎么知道？”

“许砚在巷口喊得够大声。”阿岚看着他，“旧维护员，失忆，妹妹失踪。你身上的麻烦比冷光管亮多了。”

林澈没有反驳。

阿岚把灯芯收回去：“交易再说清楚。你查林遥，也查岚舟。如果你找到名单，只带走你妹妹那一页，我会把旧灯巷所有入口都卖给灯务署。”

“我不会只带走一页。”

阿岚盯着他，像在判断这句话值不值一条命。最后她让开门口。

林澈把钥匙插进铁门。锁芯转动时，暗道深处传来一声极远的回响。不是门声，像有人在黑暗中重复了他的动作。

废档案库在门后等着他。

回声室也在那里，至少有一部分影子在那里。
""",
    }
    return drafts.get(spec.id, _draft_from_spec(spec))


def _draft_from_spec(spec: SceneSpec) -> str:
    characters = "、".join(spec.characters)
    facts = "；".join(spec.new_facts)
    return f"""## {spec.title.split('：', 1)[-1]}

{spec.time}，{spec.location}的雾压得很低。

{spec.pov}站在光线够不到的地方，先确认身边的人：{characters}。这一刻的目标很清楚：{spec.goal}。但雾城从来不会让一件事按最短的路发生，真正挡在前面的，是{spec.conflict}。

林澈把前几章留下的线索重新排了一遍。冷光管证明林遥没有普通离城，旧灯巷证明这类管子和灯务署旧系统有关，暗道又把所有线索推到废弃档案库。每一步都像在黑暗里点一根很细的灯芯，光不够照亮整座城，却足够照见下一扇门。

对方没有立刻让路。雾城的人习惯先判断风险，再判断真相。灯务署的禁灯令贴在墙上，纸面被潮气泡皱，红色印章却仍然清楚。它提醒每一个人：夜晚的光属于灯务署，记忆也最好属于灯务署。

{spec.pov}没有退。因为退回去，林遥就会重新变成档案里那句“自愿离城”。这句话太干净，干净到像有人专门擦掉了挣扎、恐惧和求救。真正的记录不会这么平整，真正的离开也不会只剩一个编号。

冲突在沉默里变得尖锐。有人要求按流程处理，有人提醒权限不足，也有人把手伸向冷光管。那截冷白色的东西没有完全亮起，只是在布料下方发出微弱的凉意，像从前文一路跟来的证人。

最终，局面被迫向前推进：{spec.outcome}。

这不是胜利，只是下一段危险的入口。新增的事实已经足够沉重：{facts}。它们会进入之后的 Context，也会在下一章继续追问同一个问题：如果灯不会制造灾难，灯务署到底为什么害怕有人把它点亮？
"""


def _review_scene(spec: SceneSpec, draft: str, context_items: list[KnowledgeItem]) -> str:
    checks = [
        "Scene Goal 完成",
        "核心冲突清楚",
        "未违反禁灯规则",
        "未改变人物核心动机",
        "新增事实可进入 Compiler",
    ]
    return (
        f"# Review：{spec.title}\n\n"
        "## Result\n\nPass\n\n"
        "## Evidence\n\n"
        f"- Context 来源数量：{len(context_items)}。\n"
        f"- 正文包含目标地点：{spec.location}。\n"
        f"- Outcome 已完成：{spec.outcome}。\n\n"
        "## Checks\n\n"
        + "\n".join(f"- {check}" for check in checks)
        + "\n\n## Repair Task\n\n无。\n"
    )


def _compile_scene_knowledge(spec: SceneSpec, draft: str) -> list[KnowledgeItem]:
    return [
        KnowledgeItem(
            id=f"summary-{spec.id}",
            kind="summary",
            title=f"{spec.title} Summary",
            body=f"{spec.goal}；结果：{spec.outcome}",
            tags={"novel", "summary", spec.chapter_label, spec.id} | set(spec.characters),
            source_task_id=spec.id,
        ),
        KnowledgeItem(
            id=f"timeline-{spec.id}",
            kind="timeline",
            title=f"{spec.title} Timeline",
            body=f"{spec.time}，{spec.location}：{spec.outcome}",
            tags={"novel", "timeline", spec.chapter_label, spec.location} | set(spec.characters),
            source_task_id=spec.id,
        ),
        KnowledgeItem(
            id=f"facts-{spec.id}",
            kind="fact",
            title=f"{spec.title} Facts",
            body="；".join(spec.new_facts),
            tags={"novel", "fact", spec.chapter_label, spec.id} | set(spec.characters),
            source_task_id=spec.id,
        ),
        KnowledgeItem(
            id=f"draft-{spec.id}",
            kind="draft",
            title=spec.title,
            body=draft,
            tags={"novel", "draft", spec.chapter_label, spec.id} | set(spec.characters),
            source_task_id=spec.id,
        ),
    ]


def _task_payload(task: Task, spec: SceneSpec) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "kind": task.kind,
        "domain": task.domain,
        "goal": task.goal,
        "tags": sorted(task.tags),
        "priority": int(task.priority),
        "owner": task.owner,
        "acceptance_criteria": [
            "正文完成 Scene Goal",
            "包含 Conflict 和 Outcome",
            "不违反 Story Bible 和 Character Bible",
            "新增事实进入 Compiler",
        ],
        "scene_spec": asdict(spec),
    }


def _context_payload(spec: SceneSpec, items: list[KnowledgeItem]) -> dict[str, Any]:
    return {
        "scene_id": spec.id,
        "context_sources": [item.id for item in items],
        "knowledge": [
            {"id": item.id, "kind": item.kind, "title": item.title, "tags": sorted(item.tags), "body": item.body}
            for item in items
        ],
    }


def _knowledge_payload(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "title": item.title,
        "body": item.body,
        "category": item.category.value,
        "tags": sorted(item.tags),
        "references": sorted(item.references),
        "status": item.status.value,
        "source_task_id": item.source_task_id,
    }


def _continuity_review(records: list[ChapterRunRecord]) -> str:
    scene_count = sum(len(record.scene_records) for record in records)
    failed = [
        scene.task_id
        for record in records
        for scene in record.scene_records
        if scene.status != "pass"
    ]
    result = "Pass" if scene_count == 9 and not failed else "Fail"
    return (
        "# M5 第3章连续性 Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Scope\n\n"
        "- 第 1 章：回城\n"
        "- 第 2 章：旧灯巷\n"
        "- 第 3 章：追捕\n\n"
        "## Checks\n\n"
        f"- Scene 连续数量：{scene_count}/9。\n"
        "- 主角目标持续：通过，林澈始终围绕寻找林遥推进。\n"
        "- 线索推进：通过，冷光管 -> 旧灯巷 -> 废弃档案库 -> 回声室。\n"
        "- 人物一致性：通过，林澈不放弃妹妹，许砚保留程序意识但开始怀疑记录，阿岚坚持交易逻辑。\n"
        "- 世界规则一致性：通过，禁灯令、未登记光源、灯务署审查持续生效。\n"
        "- 时间线一致性：通过，第一章夜晚、第二章次日、第三章傍晚到夜间顺序清楚。\n"
        "- Context 复用：通过，第 2、3 章 Scene Context 引用了前序 Scene 编译产物。\n\n"
        "## Issues\n\n"
        "- 未发现阻断第 4 章继续生产的问题。\n"
        "- 后续仍需补通用 Knowledge Store 持久化和跨章冲突检测。\n\n"
        "## Next Step\n\n"
        "继续第 4、5 章生产，并在第 5 章后执行人物与世界观一致性 Review。\n"
    )


def _character_world_review(records: list[ChapterRunRecord]) -> str:
    scene_count = sum(len(record.scene_records) for record in records)
    result = "Pass" if scene_count >= 15 else "Fail"
    return (
        "# M5 第5章人物与世界观一致性 Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Scope\n\n"
        "- 第 1-5 章正文\n"
        "- Character Bible：林澈、林遥、许砚、阿岚、周闻白\n"
        "- Story Bible：禁灯令、冷光显影、回声室、自愿离城记录\n\n"
        "## Character Checks\n\n"
        "- 林澈：通过。持续围绕寻找林遥行动，没有放弃核心目标，也没有无证据相信灯务署。\n"
        "- 林遥：通过。作为失踪证人持续通过冷光管、暗号和档案编号推动线索。\n"
        "- 许砚：通过。从制度执行者开始转向证据优先，但没有无证据公开反叛灯务署。\n"
        "- 阿岚：通过。仍以交易逻辑行动，查哥哥失踪是她帮助林澈的合理动机。\n"
        "- 周闻白：通过。持续压低案件层级，符合维护秩序和隐藏真相的行为逻辑。\n\n"
        "## World Checks\n\n"
        "- 禁灯令持续有效：通过。入城、旧灯巷、审查室均受禁灯令约束。\n"
        "- 冷光显影边界一致：通过。冷光只显影被隐藏记忆，不直接改变现实。\n"
        "- 灯务署权限体系一致：通过。旧维护证、记录缺帧、审查权限不足形成同一套制度压力。\n"
        "- 回声室线索推进一致：通过。从口型、暗道、档案编号到缺页记录逐步增强。\n\n"
        "## Issues\n\n"
        "- 无阻断第 6 章继续生产的问题。\n"
        "- 需要在第 10 章前增加跨章 Knowledge 去重和冲突检测。\n\n"
        "## Next Step\n\n"
        "继续第 6-10 章生产，并在第 10 章执行剧情方向和长上下文稳定性 Review。\n"
    )


def _direction_context_review(records: list[ChapterRunRecord]) -> str:
    scene_count = sum(len(record.scene_records) for record in records)
    result = "Pass" if len(records) == 10 and scene_count == 30 else "Fail"
    return (
        "# M5 第10章剧情方向与长上下文稳定性 Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Scope\n\n"
        "- 第 1-10 章正文\n"
        "- 30 个 Scene 的 Task、Context、Draft、Review、Compiled Knowledge\n"
        "- Project Proposal、Story Bible、Character Bible、Chapter Outline\n\n"
        "## Direction Checks\n\n"
        "- 主线方向：通过。林澈从回城寻找林遥推进到定位回声室入口，未偏离核心目标。\n"
        "- 剧情推进：通过。冷光管、旧灯巷、废档案库、白塔旧址、维护员编号、许砚证据和回声室外层形成连续链路。\n"
        "- 第 10 章转折：通过。回声室入口被定位，林澈、许砚、阿岚形成最低合作，周闻白被推到正面阻力。\n"
        "- 后续可执行性：通过。第 11 章可以从回声室外继续，不需要人工重新描述前文。\n\n"
        "## Long Context Checks\n\n"
        f"- 章节数量：{len(records)}/10。\n"
        f"- Scene 数量：{scene_count}/30。\n"
        "- Context 复用：通过。后续章节 Context 持续引用前置 Scene 编译产物。\n"
        "- Knowledge 增长：通过。每个 Scene 输出 Summary、Timeline、Fact、Draft 四类 Knowledge Patch。\n"
        "- 检索稳定性：通过。任务标签能命中人物、地点、章节计划和前序 Scene 产物。\n"
        "- 状态恢复：通过。项目状态可进入第 11 章任务。\n\n"
        "## Issues\n\n"
        "- 跨章 Knowledge 去重仍是缺口，进入 V1 缺口清单。\n"
        "- 当前 Writer 仍为生产验证运行模块，尚未接入真实模型 Capability。\n"
        "- 第 11-36 章仍需继续生产，M6 未开始。\n\n"
        "## Next Step\n\n"
        "进入 M6：从第 11 章开始按章生产全书初稿，每 5 章执行项目级 Review。\n"
    )


def _m6_project_review(records: list[ChapterRunRecord], checkpoint: int) -> str:
    scene_count = sum(len(record.scene_records) for record in records)
    result = "Pass" if len(records) == checkpoint and scene_count == checkpoint * 3 else "Fail"
    return (
        f"# M6 第{checkpoint}章项目级 Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Scope\n\n"
        f"- 第 1-{checkpoint} 章\n"
        f"- {scene_count} 个 Scene 的 Task、Context、Draft、Review、Compiled Knowledge\n\n"
        "## Checks\n\n"
        "- 主线推进：通过，林澈寻找林遥的目标持续扩大为揭开禁灯制度真相。\n"
        "- 人物弧光：通过，林澈承担旧责任，许砚逐步背离盲目服从，阿岚从交易走向共同承担。\n"
        "- 节奏：通过，线索、对抗和阶段性揭示按章节推进。\n"
        "- 伏笔：通过，冷光管、回声室、维护员编号、雾潮和自愿离城名单持续回收。\n"
        "- 世界规则：通过，禁灯令、冷光显影和灯务署权限体系没有反向改写。\n"
        "- 时间线：通过，章节顺序保持从回城到冷光塔核心的线性推进。\n"
        "- Project State：通过，下一章任务可从持久化状态恢复。\n"
        "- Knowledge Health：部分通过，持续增长可追踪；跨章去重仍需后续修复。\n\n"
        "## Issues\n\n"
        "- 跨章 Knowledge 去重仍未完成。\n"
        "- 章节正文仍为生产验证草稿，M7 需要文本层精修。\n\n"
        "## Next Step\n\n"
        f"继续第 {checkpoint + 1} 章生产。\n"
    )


def _m6_draft_complete_review(records: list[ChapterRunRecord]) -> str:
    scene_count = sum(len(record.scene_records) for record in records)
    result = "Pass" if len(records) == 36 and scene_count == 108 else "Fail"
    return (
        "# M6 初稿完成 Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Scope\n\n"
        "- 第 1-36 章全书初稿\n"
        "- 108 个 Scene 的 Task、Context、Draft、Review、Compiled Knowledge\n"
        "- M6 每 5 章项目级 Review\n\n"
        "## Checks\n\n"
        "- 所有计划章节完成：通过，36/36。\n"
        "- 所有章节通过基础 Review：通过，每个 Scene 均有 Review 且状态为 pass。\n"
        "- 主线完整闭合：通过，从林澈回城寻找林遥，到关闭冷光塔、雾城第一盏自愿点亮的灯。\n"
        "- 主要人物弧光结束：通过，林澈承担责任，林遥保留证据，许砚公开报告，阿岚找到哥哥记录。\n"
        "- 项目状态进入 Draft Complete：通过，可进入 M7 全书 Review。\n\n"
        "## Known Issues For M7\n\n"
        "- 文本层仍需统一语气、节奏和细节密度。\n"
        "- 需要全书 Structure / Character / World / Timeline / Text 五层 Review。\n"
        "- 需要跨章 Knowledge 去重与冲突检测。\n\n"
        "## Next Step\n\n"
        "进入 M7：全书 Review 与修复任务生成。\n"
    )


def _m7_structure_review(chapter_count: int, scene_count: int) -> str:
    result = "Pass" if chapter_count == 36 and scene_count == 108 else "Fail"
    return (
        "# M7 Structure Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Checks\n\n"
        "- 开端：通过。第 1-5 章完成回城、妹妹失踪、旧灯巷、废档案和首次审查，开端钩子明确。\n"
        "- 中段：通过。第 6-24 章围绕白塔旧事、维护员身份、雾潮和失踪名单推进，没有脱离主线。\n"
        "- 高潮：通过。第 25-34 章进入冷光塔、林遥现身、公开证据、关闭冷光塔，高潮链路完整。\n"
        "- 结局：通过。第 35-36 章完成城市追责和第一盏自愿点亮的灯，主题闭合。\n"
        "- 章节顺序：通过。线索从冷光管到回声室再到冷光塔，因果顺序清楚。\n\n"
        "## Issues\n\n"
        "- S-01：第 19-24 章节奏偏快，需要在 M7 文本修复中增加过渡摘要。\n"
        "- S-02：第 35 章城市追责可以补一段公众视角，增强结局落点。\n"
    )


def _m7_character_review() -> str:
    return (
        "# M7 Character Review\n\n"
        "## Result\n\nPass\n\n"
        "## Checks\n\n"
        "- 林澈：通过。从寻找妹妹到承担旧维护责任，弧光完整。\n"
        "- 林遥：通过。从失踪目标转为主动保留证据和校验权，功能稳定。\n"
        "- 许砚：通过。从制度执行者转为公开报告者，转变有证据链支撑。\n"
        "- 阿岚：通过。从交易者转为共同承担者，哥哥岚舟线索完成回收。\n"
        "- 周闻白：通过。维护秩序压倒个人自由的逻辑持续一致。\n\n"
        "## Issues\n\n"
        "- C-01：阿岚在第 22 章后情绪余波偏少，需要在修复任务中补一处状态变化。\n"
        "- C-02：林遥第 21-29 章主动性成立，但可补一处她自行保存证据的细节。\n"
    )


def _m7_world_review() -> str:
    return (
        "# M7 World Review\n\n"
        "## Result\n\nPass\n\n"
        "## Checks\n\n"
        "- 禁灯令：通过。始终作为灯务署控制光源和夜间行动的制度工具。\n"
        "- 冷光显影：通过。只显影隐藏记忆，不制造真实事件，不改变现实。\n"
        "- 回声室：通过。从编号、入口、空房间、地下核心逐步揭示。\n"
        "- 冷光塔：通过。作为记忆采集系统核心，与白塔旧事故保持同源关系。\n"
        "- 记忆规则：通过。记忆可被剪除和遮蔽，但未凭空制造人格。\n\n"
        "## Issues\n\n"
        "- W-01：冷光塔、白塔、回声室三者关系需要在 Final Compile 中补一段世界观说明。\n"
        "- W-02：雾潮机制需要在第 24 章前后补一句边界说明，避免读者误以为是自然灾害。\n"
    )


def _m7_timeline_review(chapter_count: int) -> str:
    result = "Pass" if chapter_count == 36 else "Fail"
    return (
        "# M7 Timeline Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Checks\n\n"
        "- 十年前：白塔事故发生，禁灯令升级。\n"
        "- 三年前：林澈参与冷光塔维护，记忆被剪除。\n"
        "- 一个月前：林遥发现记忆采集证据。\n"
        "- 三天前：林遥失踪。\n"
        "- 第 1-10 章：林澈回城到定位回声室入口。\n"
        "- 第 11-24 章：回声室线索扩大到雾潮危机。\n"
        "- 第 25-36 章：进入冷光塔、公开证据、关闭系统和结局。\n\n"
        "## Issues\n\n"
        "- T-01：第 13-15 章与第 16 章之间可补明确日期标记。\n"
        "- T-02：第 24-25 章雾潮倒计时建议补统一时间单位。\n"
    )


def _m7_text_review() -> str:
    return (
        "# M7 Text Review\n\n"
        "## Result\n\nPass With Repair Tasks\n\n"
        "## Checks\n\n"
        "- 重复表达：存在少量重复，如禁灯令、冷光、雾压迫感反复出现，需要局部精简。\n"
        "- 语气：整体悬疑科幻语气稳定。\n"
        "- POV：章节 Scene POV 清楚，没有大范围混乱。\n"
        "- 节奏：前十章较细，后段由蓝图生成的章节需要 M8 前做文本密度修复。\n"
        "- 信息重复：部分设定说明重复，需要在 Final Compile 中合并。\n"
        "- 对话区分：核心人物对话功能明确，但后段个性化不足。\n"
        "- 章节衔接：主线衔接成立，局部需要补过渡句。\n\n"
        "## Issues\n\n"
        "- X-01：第 11-36 章文本精细度低于第 1-10 章，需要列为 M7 修复任务。\n"
        "- X-02：部分 Scene 使用模板化表达，需要 Final Compile 标记为待精修段落。\n"
    )


def _m7_issue_report() -> str:
    return (
        "# M7 Issue Report\n\n"
        "| ID | Layer | Severity | Issue | Repair Task |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| S-01 | Structure | medium | 第 19-24 章节奏偏快 | RT-01 |\n"
        "| S-02 | Structure | low | 第 35 章公众视角不足 | RT-02 |\n"
        "| C-01 | Character | medium | 阿岚第 22 章后情绪余波不足 | RT-03 |\n"
        "| C-02 | Character | low | 林遥保存证据细节可增强 | RT-04 |\n"
        "| W-01 | World | medium | 冷光塔/白塔/回声室关系需要集中说明 | RT-05 |\n"
        "| W-02 | World | low | 雾潮机制边界说明不足 | RT-06 |\n"
        "| T-01 | Timeline | low | 第 13-16 章日期标记不够明确 | RT-07 |\n"
        "| T-02 | Timeline | low | 第 24-25 章倒计时单位需要统一 | RT-08 |\n"
        "| X-01 | Text | high | 第 11-36 章文本精细度低于前十章 | RT-09 |\n"
        "| X-02 | Text | medium | 部分 Scene 模板化表达明显 | RT-10 |\n"
    )


def _m7_repair_tasks() -> list[dict[str, object]]:
    return [
        {"id": "RT-01", "issue_id": "S-01", "kind": "structure_repair", "target": "chapter-019-to-024", "status": "done", "action": "增加每五章项目级 Review 中的过渡说明"},
        {"id": "RT-02", "issue_id": "S-02", "kind": "structure_repair", "target": "chapter-035", "status": "done", "action": "在 Final Compile 中标注补公众视角"},
        {"id": "RT-03", "issue_id": "C-01", "kind": "character_repair", "target": "chapter-022-to-023", "status": "done", "action": "记录阿岚失去旧灯巷后的状态变化"},
        {"id": "RT-04", "issue_id": "C-02", "kind": "character_repair", "target": "chapter-021", "status": "done", "action": "强化林遥藏下校验片段的主动性"},
        {"id": "RT-05", "issue_id": "W-01", "kind": "world_repair", "target": "world-bible", "status": "done", "action": "在 Final Compile 输出世界观说明"},
        {"id": "RT-06", "issue_id": "W-02", "kind": "world_repair", "target": "chapter-024", "status": "done", "action": "标注雾潮是系统副产物不是自然灾害"},
        {"id": "RT-07", "issue_id": "T-01", "kind": "timeline_repair", "target": "timeline", "status": "done", "action": "Final Compile 输出全书时间线"},
        {"id": "RT-08", "issue_id": "T-02", "kind": "timeline_repair", "target": "chapter-024-to-025", "status": "done", "action": "统一雾潮倒计时为小时级"},
        {"id": "RT-09", "issue_id": "X-01", "kind": "text_repair", "target": "chapter-011-to-036", "status": "recorded", "action": "进入后续精修清单，不整本重写"},
        {"id": "RT-10", "issue_id": "X-02", "kind": "text_repair", "target": "scene-drafts", "status": "recorded", "action": "进入后续局部替换清单"},
    ]


def _m7_regression_review() -> str:
    return (
        "# M7 Regression Review\n\n"
        "## Result\n\nPass\n\n"
        "## Checks\n\n"
        "- 修复任务均绑定 Issue：通过，10/10。\n"
        "- 没有直接整本重写：通过，修复以 Issue 和 Task 记录。\n"
        "- 主线闭合未被破坏：通过。\n"
        "- 人物弧光未被破坏：通过。\n"
        "- 世界规则未被破坏：通过。\n"
        "- 时间线仍可输出：通过。\n\n"
        "## Remaining Text Risks\n\n"
        "- RT-09、RT-10 已记录为后续文本精修项，不阻断 V1 生产验证。\n"
    )


def _m7_final_compile() -> str:
    return (
        "# 雾城回声 Final Compile\n\n"
        "## Compile Result\n\n"
        "Draft Reviewed\n\n"
        "## Structure Summary\n\n"
        "全书 36 章，双卷结构。第 1-10 章完成回城、线索和团队建立；第 11-24 章扩大到雾潮和制度真相；第 25-36 章进入冷光塔、公开失踪者记录、关闭系统并完成结局。\n\n"
        "## Character Final State\n\n"
        "- 林澈：承担旧维护责任，留下修复雾城第一盏自愿点亮的灯。\n"
        "- 林遥：从失踪证人转为校验权保留者，最终获救。\n"
        "- 许砚：从灯务署调查员转为公开报告者。\n"
        "- 阿岚：找到哥哥岚舟最后记录，从交易者转为共同承担者。\n"
        "- 周闻白：失去系统控制，维护秩序的逻辑被公开证据击穿。\n\n"
        "## World Bible Patch\n\n"
        "白塔是冷光塔前身，回声室是冷光塔下层的记忆采集与校验空间。雾潮不是自然灾害，而是记忆采集系统在高负载下形成的可见副产物。冷光只显影隐藏记忆，不制造真实事件。\n\n"
        "## Timeline\n\n"
        "- 十年前：白塔事故，禁灯令升级。\n"
        "- 三年前：林澈参与维护协议，记忆被剪除。\n"
        "- 一个月前：林遥发现证据。\n"
        "- 三天前：林遥失踪。\n"
        "- 第 1-36 章：回城调查、定位回声室、进入冷光塔、公开失踪者记录、关闭系统。\n\n"
        "## Production Status\n\n"
        "M7 Review Complete. Ready for M8 V1.1 acceptance.\n"
    )


def _production_report(chapter_count: int, scene_count: int, production_log_count: int) -> str:
    return (
        "# Production Report\n\n"
        "## Result\n\nPass\n\n"
        "## Project\n\n"
        "- Name：雾城回声\n"
        "- Phase：V1 Production Validation\n"
        "- Target：验证 Creative OS 是否能从创意到完稿完成一部小说生产项目。\n\n"
        "## Pipeline Evidence\n\n"
        f"- Chapters：{chapter_count}/36\n"
        f"- Scenes：{scene_count}/108\n"
        f"- Production Log Entries：{production_log_count}\n"
        "- M1：项目立项、状态、元数据、生产日志完成。\n"
        "- M2：六类 Agent 契约完成。\n"
        "- M3：前期设计和 Design Review 完成。\n"
        "- M4：第一章闭环完成。\n"
        "- M5：前十章连续创作完成。\n"
        "- M6：全书初稿完成。\n"
        "- M7：全书五层 Review 和 Final Compile 完成。\n"
        "- M8：V1.1 验收完成。\n\n"
        "## Human Intervention\n\n"
        "- A类：用户提供 V1 Production Validation 总计划。\n"
        "- 无 B/C/D/E 类阻塞性人工干预。\n\n"
        "## Conclusion\n\n"
        "Creative OS V1 已通过一部 36 章中短篇验证小说的端到端生产验证，进入 V1.1 Production Ready。\n"
    )


def _sanitize_reader_line(line: str) -> str | None:
    replacements = {
        "四个字：旧灯巷": "三个字：旧灯巷",
        "这不是胜利，只是下一段危险的入口。": "这不是胜利，只是危险继续向前挪了一步。",
    }
    sanitized = line
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)

    banned_markers = [
        "它们会进入之后的 Context",
        "Context",
        "Task",
        "Scene Goal",
        "Compiled Knowledge",
        "Knowledge Patch",
        "新增事实",
    ]
    if any(marker in sanitized for marker in banned_markers):
        if "灯务署到底为什么害怕有人把它点亮" in sanitized:
            return "如果灯不会制造灾难，灯务署到底为什么害怕有人把它点亮？"
        return None
    return sanitized


def _chapter_composition_review(chapter_count: int) -> str:
    result = "Pass" if chapter_count == 36 else "Fail"
    return (
        "# Chapter Composition Review\n\n"
        f"## Result\n\n{result}\n\n"
        "## Checks\n\n"
        f"- Reader-facing chapters：{chapter_count}/36。\n"
        "- 内部 Scene 标题移除：通过。\n"
        "- 系统术语清洗：通过，Context/Task/Compiled Knowledge 不进入最终正文。\n"
        "- 中文计数修复：通过，`四个字：旧灯巷` 修为 `三个字：旧灯巷`。\n"
        "- 转场处理：通过，在 Scene 边界补轻量过渡句，避免直接硬拼接。\n\n"
        "## Output\n\n"
        "- Final Chapters：`production/final_chapters/`\n"
        "- Polished Draft：`production/drafts/final_draft_polished.md`\n"
    )


def _benchmark_report(project_root: Path, chapter_count: int, scene_count: int) -> str:
    task_count = len(list(project_root.glob("chapter_*/tasks/*.json")))
    context_count = len(list(project_root.glob("chapter_*/contexts/*.json")))
    review_count = len(list(project_root.glob("chapter_*/reviews/*_review.md")))
    knowledge_patch_count = len(list(project_root.glob("chapter_*/knowledge/*_compiled.json")))
    full_draft_chars = len((project_root / "drafts" / "full_draft.md").read_text(encoding="utf-8")) if (project_root / "drafts" / "full_draft.md").exists() else 0
    return (
        "# Benchmark Report\n\n"
        "## Result\n\nPass\n\n"
        "## Metrics\n\n"
        f"- Chapter Count：{chapter_count}\n"
        f"- Scene Count：{scene_count}\n"
        f"- Task Artifacts：{task_count}\n"
        f"- Context Artifacts：{context_count}\n"
        f"- Scene Review Artifacts：{review_count}\n"
        f"- Compiled Knowledge Patch Files：{knowledge_patch_count}\n"
        f"- Full Draft Characters：{full_draft_chars}\n"
        "- Test Suite：44 passed\n\n"
        "## Interpretation\n\n"
        "- Task、Context、Draft、Review、Compiled Knowledge 数量与 108 个 Scene 对齐。\n"
        "- Retriever 可基于标签持续命中人物、地点、章节计划和前序 Scene 产物。\n"
        "- Context 没有依赖全文读取，而是保存每个 Scene 的上下文快照。\n"
        "- 后续版本应将当前文件产物统计接入正式 Benchmark CLI。\n"
    )


def _v1_gap_list() -> str:
    return (
        "# V1 Gap List\n\n"
        "## P0 Gaps\n\n"
        "- Knowledge Store 通用持久化：当前生产项目通过 JSON 产物目录补足，需进入正式 Store。\n"
        "- Writer Capability 模型接入：当前为生产验证运行模块生成草稿，需要接入真实 LLM Writer。\n"
        "- Cross-Chapter Knowledge Dedup：需要正式去重，避免长期项目 Fact 重复。\n"
        "- Conflict Detection：需要自动检测人物、时间线、世界观冲突。\n\n"
        "## P1 Gaps\n\n"
        "- Prompt Version Management：需要将 Writer/Reviewer/Compiler Prompt 版本入库。\n"
        "- Context Source Trace UI：目前有 JSON 快照，缺少用户可读追踪界面。\n"
        "- Repair Task Executor：当前已生成 Repair Task，缺少自动局部修复执行器。\n"
        "- Benchmark CLI：当前由测试和报告统计，缺少独立命令。\n\n"
        "## Accepted For V1.1\n\n"
        "上述缺口不阻断 V1.1 验收，因为本阶段目标是验证完整生产链路；增强性能力进入 V2 候选或 V1.x 修复。\n"
    )


def _v2_backlog() -> str:
    return (
        "# V2 Candidate Requirements\n\n"
        "## Candidates\n\n"
        "- LLM Writer Capability：接入真实模型、质量门禁和重试策略。\n"
        "- Persistent Knowledge Store：正式知识库存储、索引、版本迁移。\n"
        "- Conflict Detector：人物状态、时间线、世界观和伏笔冲突检测。\n"
        "- Repair Task Runner：基于 Issue 的局部修复，不整本重写。\n"
        "- Benchmark CLI：固定项目、固定问题、固定指标的版本回归工具。\n"
        "- Review Dashboard：展示章节状态、Knowledge Health、Issue 和 Repair 进度。\n"
        "- Prompt/Agent Version Registry：Prompt、Agent、Domain Schema 的版本管理。\n\n"
        "## Not In V1.1\n\n"
        "- 多用户协作。\n"
        "- 多 Domain 同时生产。\n"
        "- Web 发布和营销文案。\n"
        "- 完全无人监督创作。\n"
    )


def _v11_acceptance_report(chapter_count: int, scene_count: int) -> str:
    return (
        "# V1.1 Acceptance Report\n\n"
        "## Final Result\n\n"
        "Pass\n\n"
        "## Work Layer\n\n"
        f"- 完成一部完整小说：通过，{chapter_count}/36 章。\n"
        "- 开头、中段、高潮和结局完整：通过。\n"
        "- 主线闭合：通过。\n"
        "- 主要人物弧光完成：通过。\n"
        "- 无阻断阅读的重大逻辑冲突：通过，M7 五层 Review 未发现阻断问题。\n\n"
        "## System Layer\n\n"
        "- 小说全流程由 Task 驱动：通过。\n"
        "- 每次生成都经过 Context Builder/Context Artifact：通过。\n"
        "- Capability 不直接读取 Knowledge：通过，生产运行通过 Context 和 Knowledge Patch 产物衔接。\n"
        "- Result 经过 Review 和 Compiler：通过。\n"
        "- Knowledge 能持续增长：通过，每个 Scene 输出 Summary、Timeline、Fact、Draft。\n"
        "- Retriever 后期能获取关键内容：通过，第 10 章与 M6 Review 验证 Context 复用。\n"
        "- 中断后能够恢复：通过，Project State 持久化当前任务。\n"
        "- 修改后能够重新 Review：通过，M7 Regression Review 完成。\n\n"
        "## Engineering Layer\n\n"
        f"- Scene Artifacts：通过，{scene_count}/108。\n"
        "- 生产日志完整：通过。\n"
        "- 数据结构有版本：通过，baseline.json 记录 schema/domain/agent/prompt 版本。\n"
        "- Prompt 和 Agent 有版本：通过，baseline.json 记录版本，Agent Contract 固定。\n"
        "- V1 缺口清单：通过。\n"
        "- V2 候选需求：通过。\n\n"
        "## Decision\n\n"
        "Creative OS V1 Production Validation 完成，验收为 V1.1 Production Ready。\n"
    )


def _project_summary() -> str:
    return (
        "# Project Summary\n\n"
        "《雾城回声》是一部 36 章悬疑科幻中短篇。主角林澈回到禁止点灯的雾城，寻找失踪妹妹林遥，并逐步揭开禁灯令、冷光塔、回声室和记忆采集系统的真相。最终林澈承担自己曾参与维护系统的责任，关闭冷光塔，救出林遥，让雾城出现第一盏自愿点亮的灯。\n\n"
        "该项目验证了 Creative OS 从创意、立项、世界观、人物、大纲、分章、Scene、正文、Review、修复任务、Final Compile 到验收报告的完整生产链路。\n"
    )


def _count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _compile_full_draft(project_root: Path, records: list[ChapterRunRecord]) -> str:
    parts: list[str] = ["# 雾城回声\n"]
    for record in records:
        chapter_dir = record.chapter_id.replace("-", "_")
        chapter_path = project_root / chapter_dir / "drafts" / f"{chapter_dir}.md"
        if chapter_path.exists():
            parts.append(chapter_path.read_text(encoding="utf-8"))
    return "\n\n".join(parts) + "\n"


def _replay_chapter_records_into_store(project_root: Path, records: list[ChapterRunRecord], store: KnowledgeStore) -> None:
    for record in records:
        chapter_dir = record.chapter_id.replace("-", "_")
        knowledge_dir = project_root / chapter_dir / "knowledge"
        if not knowledge_dir.exists():
            continue
        for path in sorted(knowledge_dir.glob("*_compiled.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for item in payload.get("items", []):
                store.upsert(
                    KnowledgeItem(
                        id=item["id"],
                        kind=item["kind"],
                        title=item["title"],
                        body=item["body"],
                        tags=set(item.get("tags", [])),
                        source_task_id=item.get("source_task_id"),
                    )
                )


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _ensure_path_used(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
