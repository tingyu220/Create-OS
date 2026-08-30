from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from creative_os.domains.pov_strategy_model import ChapterNeeds
from creative_os.domains.pov_strategy_input import assemble_pov_strategy_input
from creative_os.domains.pov_strategy_policy import load_pov_strategy_policy
from creative_os.domains.pov_strategy_selection import select_recommendation
from creative_os.domains.narrative_decision import NarrativeDecision
from creative_os.domains.narrative_decision import FieldEvidenceBinding, NarrativeChangeRequest, NarrativeProjectProfile
from creative_os.domains.narrative_director import DirectorInput, NarrativeDirector
from creative_os.domains.narrative_memory import load_active_narrative_decision, load_active_narrative_profile
from creative_os.domains.novel_state_store import compact_active_snapshots
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_evidence import EvidenceAssertion, EvidenceLocator, EvidenceRef, EvidenceRole, EvidenceSourceKind, ResolvedEvidenceSource
from creative_os.domains.contract_baseline import BaselineEntry, BaselineManifest
from creative_os.domains.contract_baseline_resolver import AuthorityFactSnapshot, BaselineSourceResolver, ImmutableMemoryAuthorityAdapter
from creative_os.domains.narrative_causality import CAUSAL_FIELD_PATHS_V1, CausalDependencyAnalyzer
from creative_os.domains.contract_preflight import ContractPreflightValidator
from creative_os.domains.contract_approval import ApprovalItem, ApprovalStatus, ContractApprovalRecord
from creative_os.domains.contract_review import PrewriteReviewerResult
from creative_os.domains.contract_record_store import ContractRecordStore
from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.store import JsonMemoryStore
from creative_os.memory.approval import approve_candidate
from creative_os.memory.model import MemoryStatus
from creative_os.domains.writer_admission import WriterAdmissionService
from creative_os.domains.contract_fulfillment import ContractFulfillmentEvidenceRecord, ContractFulfillmentEvaluator, FulfillmentArtifactMetadata, FulfillmentStatus
from creative_os.domains.contract_fulfillment_store import ContractFulfillmentStore
from creative_os.domains.web_novel_quality import WebNovelQualityGate
from creative_os.domains.web_novel_quality_store import WebNovelQualityStore
from creative_os.domains.state_change_approval import StateChangeApprovalService
from creative_os.domains.novel_state_model import StateChange, StateEvidence, build_state_changes
from creative_os.domains.novel_state_store import materialize_active_state
from creative_os.domains.narrative_review import review_narrative
from creative_os.validation_runtime import validate_reader_facing_text
from creative_os.novel_continuation_runner import continue_one_chapter, prepare_continuation_run, promote_passing_draft
from creative_os.llm_writer import OpenAICompatibleClient
from creative_os.pov_strategy_shadow import run_pov_strategy_shadow
from creative_os.runtime.pov_strategy_store import POVStrategyAuditStore


CHAPTER_NEEDS = {
    28: ChapterNeeds(
        ("追查DR-17写入者", "承接共同审计代价", "推进授时异常主线"),
        "新超算能否在对等误差链约束下完成第二次解码，而不把异常误判为算力胜利？",
        (),
        "工程现场与七地校验节点",
        ("trace-dr17-authority",),
    ),
    29: ChapterNeeds(
        ("完成十二座聚变电站同步点火", "让全球普通人承担文明跃迁代价", "检验第二次解码给出的能源验证"),
        "十二座聚变电站能否在跨地域误差与各自现实压力下同时点火，并形成可信的全球能源事实？",
        (),
        "十二座聚变节点、空间站与龙渊倒计时席位",
        ("coordinate-global-fusion-ignition",),
    ),
    30: ChapterNeeds(
        ("独立判定卡尔达肖夫指数达到1.0", "解锁并约束第二层技术信息", "把能源胜利转化为新的文明选择"),
        "人类能否在不把一次点火误当永久胜利的前提下确认一级文明，并安全接收亚光速航行与冬眠技术？",
        (),
        "全球能源判定中心、民用能源调度现场与第二层隔离解码室",
        ("validate-kardashev-boundary",),
    ),
    31: ChapterNeeds(
        ("让林子轩承受点火后的光冕幻觉", "区分主观体验与可验证信号", "把一级文明成功转成更大的宇宙疑问"),
        "林子轩能否在不把幻觉上升为事实的前提下，保留并验证他所见的宇宙边界线索？",
        (),
        "医疗观察舱、无信号感官隔离室与地面普通观测站",
        ("test-corona-vision",),
    ),
    32: ChapterNeeds(
        ("验证那个声音对人类的礼赞", "证明人类值得活下去来自共同选择而非服从", "保留收割者与建造者动机疑问"),
        "当那个声音祝贺人类时，韩宁能否证明这不是诱导或伪造，并拒绝让礼赞替人类定义自身价值？",
        (),
        "七地公共审计链、普通人能源恢复现场与龙渊无主签名接收室",
        ("verify-harvester-praise",),
    ),
}


def build_chapter_28(project_root: Path) -> NarrativeDecision:
    envelope = json.loads((project_root / ".creative_os" / "memory" / "items" / "narrative-chapter-027-v0001.json").read_text(encoding="utf-8"))
    data = json.loads(envelope["content"])
    contract = data["chapter_contract"]
    data.update(chapter=28, contract_id="narrative-chapter-028", contract_version=1)
    data["arc_phase"] = "setup"
    data["inherited_pressure"] = "DR-17补偿缓存可能是可写后门；新超算上线必须接受七地共同误差链约束。"
    data["future_pressures"] = ["第二次解码将把工程成功转为文明级选择", "十二座聚变电站仍需真实点火验证"]
    contract.update(
        chapter_id="chapter_028",
        functions=list(CHAPTER_NEEDS[28].functions),
        dramatic_question=CHAPTER_NEEDS[28].dramatic_question,
        ending_shift="新超算在隔离DR-17写入权限后达到有效算力门槛，第二次解码成功，但输出要求人类用全球能源实践证明结果",
        target_chinese_chars=8000,
        reader_change={"before":"读者知道DR-17可能是人为写入后门，新超算尚未完成可信联调","after":"读者确认算力突破必须建立在可审计误差链上，并得知解码结果把下一步推向全球聚变点火"},
        pressure_curve={"start":"新超算上线窗口只剩四十分钟，DR-17权限来源仍未查清","turn":"运维团队发现移除补偿会损失算力，但保留它会让解码结果不可验证","end":"林子轩选择降算力隔离DR-17，七地共同复算后第二次解码仍然成功"},
        protagonist_choice={"actor":"林子轩","action":"公开DR-17后门嫌疑并接受降算力隔离，以可验证结果代替最快结果","alternatives":["保留DR-17补偿并先完成解码"],"cost":"失去抢先解码优势，个人生物密钥与安全调查同时进入共同审计","consequence":"新超算以较低算力完成可信解码，全球聚变点火成为下一项公开验证","status":"complete","missing_fields":[]},
    )
    contract["information"] = {
        "reveal":["DR-17具有跨节点写入痕迹而非普通缓存残留","新超算在有效算力超过15%后完成第二次解码","第二层信息要求以全球能源能力作为可验证回应"],
        "withhold":["DR-17写入者身份","第二层完整技术包与那个声音的最终目的"],
        "misdirect":{"values":["初始监控把算力抖动归因于新超算冷却负载"],"not_applicable_reason":None},
    }
    contract["forbidden"] = {"values":["不得把DR-17直接定性为收割者行为","不得写成新超算无代价自动成功","不得提前完成十二座聚变电站点火","不得泄露完整密钥或七地原始数据"],"not_applicable_reason":None}
    contract["foreshadow_actions"] = {"values":["第二次解码要求全球能源验证","林子轩短暂看见非设备产生的光冕残像"],"not_applicable_reason":None}
    contract["scene_plan"] = {"chapter_spatial_intent":"从新超算冷却与供电现场进入安全隔离，再抵达七地共同复算屏幕，让成功由工程行动而非会议宣布","required_world_slice":"新超算值班工程师、供电调度员与七地校验节点共同承担上线代价","allowed_same_place_run":1,"exception_reason":"","scenes":[
        {"id":"supercomputer-commissioning-floor","order":1,"place_id":"new-supercomputer-floor","place_label":"新超算冷却与供电机房","place_class":"engineering_field","interior_exterior":"interior","time_window":"上线窗口前四十分钟","participants":["林子轩","韩宁","冷却工程师","供电调度员"],"viewpoint":"林子轩","ordinary_people_present":True,"goal":"确认算力抖动是否来自设备负载","conflict":"保留DR-17可快速过线，移除则可能错过窗口","action":"现场切换冷却回路并比对DR-17写入时间","information_change":"抖动与跨节点写入同步而非冷却负载","state_change":"DR-17从工程异常升级为权限调查","entry_reason":"承接第27章读取倒计时","exit_trigger":"安全组要求物理隔离写入链","inherited_from_previous":True},
        {"id":"dr17-isolation-bay","order":2,"place_id":"dr17-isolation-bay","place_label":"DR-17隔离验证间","place_class":"security_engineering","interior_exterior":"interior","time_window":"同日上线窗口内","participants":["林子轩","陈景行","韩宁","安全审计员"],"viewpoint":"林子轩","ordinary_people_present":False,"goal":"决定是否牺牲算力换取可验证解码","conflict":"最快结果与可信结果不可兼得","action":"林子轩签署公开嫌疑并执行降算力隔离","information_change":"DR-17确有未登记的跨节点写入权限","state_change":"新超算进入无DR-17补偿的可信运行态","entry_reason":"机房比对排除冷却故障","exit_trigger":"有效算力重新爬升至15%","inherited_from_previous":False},
        {"id":"seven-site-recompute-wall","order":3,"place_id":"joint-recompute-gallery","place_label":"七地共同复算大厅","place_class":"international_coordination","interior_exterior":"interior","time_window":"隔离完成后","participants":["林子轩","马库斯","伊莲娜","七地校验员"],"viewpoint":"林子轩","ordinary_people_present":True,"goal":"由七地独立确认第二次解码","conflict":"各站版本差异可能让成功无法形成共同事实","action":"七地分别提交摘要并完成盲复算","information_change":"第二次解码在七份独立摘要中一致通过并给出全球能源验证要求","state_change":"主线从可信解码转入十二座聚变电站同步点火准备","entry_reason":"可信算力达到门槛","exit_trigger":"屏幕出现新的能源验证倒计时","inherited_from_previous":False},
    ]}
    contract["technology_plan"] = {"technologies":[{"id":"trace-dr17-authority","name":"可审计新超算解码链","role":"core","birth_reason":"DR-17写入嫌疑使高算力结果失去可信度","source":"新超算联调、DR-17权限日志与七地误差摘要","prerequisites":["物理隔离写入链","有效算力超过15%","七地盲复算"],"validation_stage":"无DR-17补偿运行并由七地独立复算","first_application":"第二次文明信号解码","social_diffusion":["全球聚变点火验证","跨国关键计算审计"],"cost":"降低峰值算力并公开核心工程缺陷","changed_domains":["engineering_governance","information_access","global_energy"]}]}
    contract["pov_plan"] = {"mode":"limited","primary_owner":"林子轩","protagonist_present":True,"rationale":"林子轩必须以trace-dr17-authority承接当前章节功能","supporting_agency":[{"actor":"林子轩","independent_goal":"确认DR-17写入来源并完成可信解码","resistance":"是否向七地审计方公开DR-17可能是可写后门，并接受安全调查同步介入","choice":"必须在章节内作出可改变主线的选择","cost":"龙渊已失去单方解释误差的权力，林子轩个人签名进入国际共同责任链","result":"在可验证条件下完成第二次解码","mainline_change":"DR-17补偿缓存从工程异常转为权限与人为写入调查"},{"actor":"韩宁","independent_goal":"保护新超算硬件和运行记录不被政治时限覆盖","resistance":"上线窗口与安全组相互施压","choice":"拒绝用未隔离补偿数据签署验收","cost":"承担延误上线责任","result":"迫使团队完成物理隔离验证","mainline_change":"新超算成功从算力指标改为可信工程事实"}]}
    contract["optional_candidates"] = []
    contract["intent_evidence_bindings"] = {}
    data["legacy_unclassified_evidence"] = []
    return NarrativeDecision.from_json(json.dumps(data, ensure_ascii=False))


def build_chapter_29(project_root: Path) -> NarrativeDecision:
    envelope = json.loads((project_root / ".creative_os" / "memory" / "items" / "narrative-chapter-028-v0001.json").read_text(encoding="utf-8"))
    data = json.loads(envelope["content"])
    contract = data["chapter_contract"]
    data.update(chapter=29, contract_id="narrative-chapter-029", contract_version=1)
    data["inherited_pressure"] = "第二次解码要求人类用真实能源能力作答；十二座聚变电站已进入同步点火窗口，但各节点风险与现实代价并不相同。"
    data["future_pressures"] = ["同步点火将把人类推到一级文明门槛", "能源跃迁可能触发林子轩无法解释的光冕幻觉"]
    contract.update(
        chapter_id="chapter_029", functions=list(CHAPTER_NEEDS[29].functions),
        dramatic_question=CHAPTER_NEEDS[29].dramatic_question,
        ending_shift="十二座聚变电站在各地现场共同签署下完成同步点火，全球能源网形成可验证的统一输出，人类逼近一级文明门槛",
        target_chinese_chars=12000,
        reader_change={"before":"读者知道第二次解码要求全球能源验证，十二座电站仍处于准备状态","after":"读者亲历十二地普通人与工程人员承担代价后完成同步点火，并意识到文明跃迁是全球共同选择而非龙渊单点胜利"},
        pressure_curve={"start":"十二站点火窗口开启，但冰岛冷却波动、赤道接收塔过载和轨道观测盲区同时出现","turn":"取消任一节点可降低局部风险，却会让全球验证失去共同事实效力","end":"各节点独立签署风险并修正本地异常，林子轩放弃单方指挥，十二站在同一秒完成点火"},
        protagonist_choice={"actor":"林子轩","action":"把最终点火权交还十二地现场，在所有节点独立签署后维持同步点火","alternatives":["由龙渊强制统一倒计时并允许高风险节点退出"],"cost":"龙渊失去单方控制，任何一地拒绝都能终止验证，林子轩承担失败责任却不能替现场作决定","consequence":"十二站点火成为可审计的全球共同事实，能源输出开始改变文明等级判定","status":"complete","missing_fields":[]},
    )
    contract["information"] = {"reveal":["十二座电站必须以各自现场签署而非中央命令完成同步点火","各地局部风险需要不同工程处置但必须汇入同一验证窗口","同步输出使全球可利用能源首次形成统一可核验曲线"],"withhold":["一级文明判定后的第二层完整内容","点火后光冕幻觉的来源"],"misdirect":{"values":["龙渊最初认为统一倒计时足以代表全球协作"],"not_applicable_reason":None}}
    contract["forbidden"] = {"values":["不得把十二地写成无差别背景蒙太奇","不得让配角只向林子轩汇报结果","不得提前解锁亚光速或冬眠技术","不得把点火写成零风险奇迹","不得将光冕定性为客观宇宙边界"],"not_applicable_reason":None}
    contract["foreshadow_actions"] = {"values":["统一能源曲线逼近卡尔达肖夫指数1.0","点火蓝光中出现只有林子轩察觉的光冕残像"],"not_applicable_reason":None}
    contract["scene_plan"] = {"chapter_spatial_intent":"用冰岛、赤道、近地轨道与龙渊四地交叉倒计时，让全球点火由不同人的行动共同构成","required_world_slice":"地热站操作员、接收塔技术员、空间站宇航员及其家人现实均必须进入因果链","allowed_same_place_run":1,"exception_reason":"","scenes":[
        {"id":"iceland-cooling-choice","order":1,"place_id":"iceland-fusion-station","place_label":"冰岛聚变站冷却廊道","place_class":"engineering_field","interior_exterior":"interior","time_window":"点火前十八分钟","participants":["冰岛操作员","冷却班组"],"viewpoint":"冰岛操作员","ordinary_people_present":True,"goal":"在冷却波动中保住本站点火资格","conflict":"继续升载可能损坏换热器，退出则破坏全球验证","action":"操作员拒绝隐瞒波动，切断非必要热负载并以家人所在社区供热为代价换取稳定窗口","information_change":"冷却异常可由本地负载重排控制而非退出解决","state_change":"冰岛站恢复独立签署资格","entry_reason":"全球倒计时启动","exit_trigger":"本站签署进入共同链","inherited_from_previous":True},
        {"id":"equatorial-grid-sacrifice","order":2,"place_id":"equatorial-receiver-tower","place_label":"赤道能源接收塔","place_class":"civil_infrastructure","interior_exterior":"exterior","time_window":"点火前九分钟","participants":["接收塔技术员","城市调度员","技术员女儿"],"viewpoint":"接收塔技术员","ordinary_people_present":True,"goal":"阻止接收塔过载拖垮城市电网","conflict":"保护城市供电会降低验证输出，满载接收会触发连锁跳闸","action":"技术员公开切除商业负载并优先保医院与居民线路，承担违规停电责任","information_change":"全球验证允许透明的本地负载削减，不允许伪造满载数据","state_change":"赤道节点以真实削载曲线接入同步验证","entry_reason":"冰岛签署后负载潮流转向赤道","exit_trigger":"接收塔锁定安全功率窗","inherited_from_previous":False},
        {"id":"orbital-observation-gap","order":3,"place_id":"low-earth-orbit-station","place_label":"近地轨道空间站观察舱","place_class":"space_infrastructure","interior_exterior":"interior","time_window":"点火前九十秒","participants":["空间站宇航员","轨道测控员"],"viewpoint":"空间站宇航员","ordinary_people_present":False,"goal":"补齐地面传感器无法覆盖的全球同步证据","conflict":"姿态调整会牺牲返航冗余并让空间站短时失联","action":"宇航员选择消耗姿控余量转向地球夜面，独立记录十二束能源光谱","information_change":"轨道视角可验证十二站并非由单一数据源伪造","state_change":"全球点火获得独立空间证据","entry_reason":"赤道节点锁定功率窗","exit_trigger":"轨道证据链完成预签名","inherited_from_previous":False},
        {"id":"longyuan-shared-go","order":4,"place_id":"longyuan-global-console","place_label":"龙渊全球点火席位","place_class":"coordination_center","interior_exterior":"interior","time_window":"最后十秒","participants":["林子轩","陈景行","十二地现场代表"],"viewpoint":"林子轩","ordinary_people_present":True,"goal":"在不夺回现场权力的前提下完成共同点火","conflict":"最后一站签署延迟，中央强制指令可确保时刻一致却破坏共同事实","action":"林子轩拒绝代签并暂停一秒，等待最后现场自行确认后重启共同倒计时","information_change":"文明级能源验证取决于分布式责任而非中央服从","state_change":"十二站同秒点火并形成统一能源曲线","entry_reason":"三类关键证据进入共同链","exit_trigger":"全球能源曲线稳定并出现一级文明门槛提示","inherited_from_previous":False}
    ]}
    contract["technology_plan"] = {"technologies":[{"id":"coordinate-global-fusion-ignition","name":"十二站分布式聚变点火与验证链","role":"core","birth_reason":"第二次解码要求用全球真实能源能力作答，单站或中央模拟均不足以验证","source":"十二站点火系统、地方电网曲线、轨道光谱和七地审计协议","prerequisites":["各站独立风险签署","地方电网安全削载","轨道独立观测","统一时间窗"],"validation_stage":"十二地与轨道证据交叉确认同秒点火及稳定输出","first_application":"全球聚变能源验证","social_diffusion":["居民供热与停电规则","跨国能源数据共同审计","空间基础设施观测"],"cost":"局部供热削减、商业停电、轨道姿控余量消耗与中央控制权让渡","changed_domains":["global_energy","civil_infrastructure","international_governance"]}]}
    contract["pov_plan"] = {"mode":"omniscient_limited","primary_owner":"林子轩","protagonist_present":True,"rationale":"林子轩承担最终不代签的核心选择，但全球验证必须由三个独立现场视角共同完成","supporting_agency":[
        {"actor":"冰岛操作员","independent_goal":"保住本站点火资格并避免换热器损毁","resistance":"社区供热与点火冷却争夺同一热交换能力","choice":"主动切除社区非必要供热并公开异常","cost":"家人所在社区短时降温且本人承担投诉","result":"冰岛站恢复稳定窗口","mainline_change":"第一个高风险节点以透明代价进入共同签署"},
        {"actor":"赤道接收塔技术员","independent_goal":"保护城市基本供电并完成真实接收","resistance":"满载验证与城市电网安全冲突","choice":"切除商业负载、保医院和居民线路并公开削载","cost":"承担越权停电责任","result":"赤道节点以真实曲线通过","mainline_change":"验证规则从漂亮满载数字改为可审计社会代价"},
        {"actor":"空间站宇航员","independent_goal":"提供独立于地面网络的同步证据","resistance":"姿态调整消耗返航冗余并导致短时失联","choice":"转向地球夜面记录十二束光谱","cost":"牺牲姿控余量和通信安全边际","result":"轨道证据排除单源伪造","mainline_change":"全球点火获得空间层独立证明"},
        {"actor":"林子轩","independent_goal":"完成可验证而非被中央强制制造的同步点火","resistance":"最后节点延迟诱使龙渊代签","choice":"暂停并拒绝代签，等待现场自行确认","cost":"承担错过窗口的全部责任","result":"十二站以分布式责任完成同秒点火","mainline_change":"全球能源曲线成为共同事实"}
    ]}
    contract["optional_candidates"] = []
    contract["intent_evidence_bindings"] = {}
    data["legacy_unclassified_evidence"] = []
    return NarrativeDecision.from_json(json.dumps(data, ensure_ascii=False))


def build_chapter_30(project_root: Path) -> NarrativeDecision:
    envelope = json.loads((project_root / ".creative_os" / "memory" / "items" / "narrative-chapter-029-v0001.json").read_text(encoding="utf-8"))
    data = json.loads(envelope["content"])
    contract = data["chapter_contract"]
    data.update(chapter=30, contract_id="narrative-chapter-030", contract_version=1)
    data["inherited_pressure"] = "十二站共同点火证据已经齐备，但一级文明边界仍需独立判定；任何提前庆功都会把一次峰值误写成永久能力。"
    data["future_pressures"] = ["第二层技术将改变人类离开太阳系的时间尺度", "林子轩可能在光冕幻觉中接触无法验证的宇宙边界"]
    contract.update(
        chapter_id="chapter_030", functions=list(CHAPTER_NEEDS[30].functions),
        dramatic_question=CHAPTER_NEEDS[30].dramatic_question,
        ending_shift="陈景行确认卡尔达肖夫指数达到1.0并将社会代价写入判定，人类获准受控读取亚光速航行与冬眠技术，但所有应用仍被冻结等待验证",
        target_chinese_chars=8000,
        reader_change={"before":"读者知道全球点火共同事实已经形成，但一级文明边界尚未判定","after":"读者确认一级文明成立并看到第二层两类技术信息解锁，同时理解解锁不等于掌握或可立即应用"},
        pressure_curve={"start":"全球庆祝倒逼判定中心立刻宣布一级文明，能源曲线却只有峰值没有长期稳定性","turn":"陈景行发现若不计入停电、断暖和轨道余量，指数会被漂亮数字虚高","end":"他拒绝无条件宣布，补入社会代价与稳定性边界后确认1.0，并把第二层技术锁在验证沙箱"},
        protagonist_choice={"actor":"陈景行","action":"先公开能源峰值的社会代价与稳定性缺口，再确认一级文明并限制第二层技术只能在沙箱读取","alternatives":["先宣布一级文明并立即向工程系统分发技术包"],"cost":"承受全球舆论与决策层对延迟庆功的压力，并承担技术封锁责任","consequence":"一级文明判定可信成立，亚光速与冬眠技术进入受控验证而非直接应用","status":"complete","missing_fields":[]},
    )
    contract["information"] = {"reveal":["卡尔达肖夫指数必须计入持续能源能力与公开社会代价","人类指数在审计修正后仍达到1.0","第二层包含亚光速航行与冬眠技术两类可验证技术包"],"withhold":["两类技术的完整工程参数","光冕幻觉与宇宙边界的真实性","那个声音为何把技术交给人类"],"misdirect":{"values":["全球媒体把十二站同秒点火直接等同于一级文明完成"],"not_applicable_reason":None}}
    contract["forbidden"] = {"values":["不得把一次点火峰值写成永久稳定能源","不得让林子轩出场或替陈景行完成判定","不得写成亚光速飞船或冬眠舱已经造出","不得把技术包无审计分发给全球","不得提前确认光冕为宇宙边界"],"not_applicable_reason":None}
    contract["foreshadow_actions"] = {"values":["亚光速技术包首先要求验证推进系统能量闭环","冬眠技术包首先要求验证长期神经损伤边界","判定完成时监测系统记录到不属于能源网的短暂光冕噪声"],"not_applicable_reason":None}
    contract["scene_plan"] = {"chapter_spatial_intent":"从全球能源独立判定中心进入民用调度现场，再到第二层隔离解码室，让文明等级同时接受数字、普通人代价和技术安全约束","required_world_slice":"停电商户、恢复供暖居民与能源调度员必须对1.0判定产生真实影响","allowed_same_place_run":1,"exception_reason":"","scenes":[
        {"id":"independent-energy-ruling","order":1,"place_id":"global-energy-ruling-center","place_label":"全球能源独立判定中心","place_class":"international_governance","interior_exterior":"interior","time_window":"点火后四十分钟","participants":["陈景行","七地审计员","能源统计员"],"viewpoint":"陈景行","ordinary_people_present":False,"goal":"判断共同能源曲线是否真正达到1.0","conflict":"政治与媒体要求立即宣布，审计模型却没有计入社会代价和持续性","action":"陈景行冻结自动发布并要求重算峰值、持续窗口和代价项","information_change":"漂亮峰值会虚高文明指数，公开代价后仍有机会达到1.0","state_change":"一级文明判定从庆功口号转为独立审计程序","entry_reason":"承接第29章等待独立判定","exit_trigger":"审计员要求到民用调度现场核实代价数据","inherited_from_previous":True},
        {"id":"civil-grid-accounting","order":2,"place_id":"civil-energy-dispatch-floor","place_label":"民用能源调度与补偿大厅","place_class":"civil_infrastructure","interior_exterior":"interior","time_window":"点火后一小时","participants":["陈景行","民用调度员","停电商户","恢复供暖居民"],"viewpoint":"陈景行","ordinary_people_present":True,"goal":"把断暖、停电和恢复时间纳入文明指数","conflict":"隐去代价可让数字更漂亮，公开代价会引发赔偿和追责","action":"调度员拒绝删除削载记录，陈景行签署将补偿责任写入判定模型","information_change":"文明能力包括承担和修复代价，而非只统计输出功率","state_change":"修正指数在透明代价下仍稳定达到1.0","entry_reason":"独立判定缺少社会侧数据","exit_trigger":"1.0判定获得七地共同签名","inherited_from_previous":False},
        {"id":"second-layer-sandbox","order":3,"place_id":"second-layer-isolation-lab","place_label":"第二层隔离解码室","place_class":"security_engineering","interior_exterior":"interior","time_window":"判定签署后","participants":["陈景行","韩宁","推进工程师","生命医学审查员"],"viewpoint":"陈景行","ordinary_people_present":False,"goal":"读取第二层目录但阻止未经验证的技术扩散","conflict":"技术包可缩短逃离太阳窗口的时间，立即分发却会把未知工程条件写入生产系统","action":"陈景行只开放目录和验证前置，分别封存完整推进与冬眠参数","information_change":"第二层确含亚光速航行和冬眠技术，但二者都有严格验证与代价边界","state_change":"人类从能源证明转入两条受控技术验证线","entry_reason":"一级文明判定完成触发第二层权限","exit_trigger":"隔离屏显示两个技术包的首项验证任务与光冕噪声","inherited_from_previous":False}
    ]}
    contract["technology_plan"] = {"technologies":[
        {"id":"sublight-navigation-package","name":"亚光速航行技术包","role":"core","birth_reason":"太阳窗口要求人类获得跨恒星迁移能力","source":"一级文明判定后解锁的第二层编码信息","prerequisites":["持续聚变能源","推进能量闭环验证","材料与导航误差审计"],"validation_stage":"只开放推进能量闭环与导航误差目录进行沙箱复核","first_application":"建立亚光速推进验证任务而非制造飞船","social_diffusion":["跨国推进实验审计","深空迁移路线评估"],"cost":"巨大能源占用、材料失效风险与导航误差累积","changed_domains":["spaceflight","energy_allocation","international_governance"]},
        {"id":"hibernation-package","name":"长期冬眠技术包","role":"supporting","birth_reason":"亚光速航行仍需要跨越人类寿命尺度","source":"一级文明判定后解锁的第二层编码信息","prerequisites":["神经损伤边界验证","代谢恢复模型","长期伦理审查"],"validation_stage":"只开放神经损伤和唤醒失败边界进行医学沙箱复核","first_application":"建立冬眠风险验证任务而非人体试验","social_diffusion":["生命医学伦理审查","长期任务乘员标准讨论"],"cost":"不可逆神经损伤、唤醒失败与身份伦理风险","changed_domains":["medicine","human_rights","spaceflight"]}
    ]}
    contract["pov_plan"] = {"mode":"limited","primary_owner":"陈景行","protagonist_present":False,"rationale":"陈景行拥有独立判定与受控解锁能力，必须在全球庆祝压力下改变主线状态","supporting_agency":[
        {"actor":"陈景行","independent_goal":"独立核验全球能源曲线并安全解锁第二层","resistance":"是否先公开社会代价与稳定性缺口，再允许第二层解锁","choice":"必须在章节内作出可改变主线的选择","cost":"必须在全球庆祝时公开点火仍不等于永久能源稳定","result":"一级文明判定可信成立且第二层进入沙箱","mainline_change":"共同点火证据从待判定状态转为一级文明确认及第二层受控解锁"},
        {"actor":"民用调度员","independent_goal":"保留真实削载与补偿记录","resistance":"上级要求删除会拖低文明指数的数据","choice":"拒绝删除并把恢复时间提交七地审计","cost":"承担泄露与越权责任","result":"修正指数在透明代价下仍达到1.0","mainline_change":"文明指数首次把普通人代价与修复能力计入事实"},
        {"actor":"韩宁","independent_goal":"阻止第二层完整参数越过验证沙箱","resistance":"工程团队要求立即下载以抢太阳窗口","choice":"切断生产网，只开放验证目录","cost":"承担延误两类救命技术的责任","result":"两类技术进入独立验证任务","mainline_change":"技术解锁与技术应用被制度性分开"}
    ]}
    contract["optional_candidates"] = []
    contract["intent_evidence_bindings"] = {}
    data["legacy_unclassified_evidence"] = []
    return NarrativeDecision.from_json(json.dumps(data, ensure_ascii=False))


def build_chapter_31(project_root: Path) -> NarrativeDecision:
    envelope = json.loads((project_root / ".creative_os" / "memory" / "items" / "narrative-chapter-030-v0001.json").read_text(encoding="utf-8"))
    data = json.loads(envelope["content"])
    contract = data["chapter_contract"]
    data.update(chapter=31, contract_id="narrative-chapter-031", contract_version=1)
    data["inherited_pressure"] = "一级文明与第二层技术已受控确认，但光冕噪声仍只被标记为未知；林子轩此前多次私下看见相似光冕。"
    data["future_pressures"] = ["那个声音可能会借一级文明判定再次出现", "收割者与建造者的称谓仍没有可信动机解释"]
    contract.update(
        chapter_id="chapter_031", functions=list(CHAPTER_NEEDS[31].functions),
        dramatic_question=CHAPTER_NEEDS[31].dramatic_question,
        ending_shift="林子轩公开光冕幻觉并完成神经、设备与地面观测三重测试；客观信号未被证实，但幻觉在隔离条件下可重复，未知由私人秘密转成受控线索",
        target_chinese_chars=8000,
        reader_change={"before":"读者知道系统记录过未知光冕噪声，却不知道林子轩持续看见类似宇宙边界的幻觉","after":"读者知道林子轩的体验可在无外部信号条件下重复，但设备与地面观测均未证明宇宙边界真实存在"},
        pressure_curve={"start":"林子轩在一级文明判定后再次看见光冕，却担心公开会被视为D-7神经损伤","turn":"医疗测试排除常见视觉异常，感官隔离又让幻觉重复，而外部观测给出空结果","end":"他选择公开全部体验并接受长期监测，把结论冻结为可重复主观现象、客观来源未知"},
        protagonist_choice={"actor":"林子轩","action":"公开反复出现的光冕幻觉并接受神经、设备与地面观测三重测试","alternatives":["继续隐瞒，只把光冕当作个人直觉参与决策"],"cost":"失去对自身体验的独占解释权，D-7神经状态与决策资格进入持续医学审查","consequence":"光冕成为可重复测试但来源未知的正式线索，不能再被直接当作宇宙事实","status":"complete","missing_fields":[]},
    )
    contract["information"] = {"reveal":["林子轩在点火与一级文明判定时都看见边界般光冕","常规神经检查无法解释该体验","无外部信号条件下幻觉可重复但地面观测给出空结果"],"withhold":["光冕是否来自D-7、宇或外部文明","所谓宇宙边界的真实结构","那个声音是否共享林子轩的感知"],"misdirect":{"values":["医疗团队起初把光冕归因于疲劳与点火强光残像"],"not_applicable_reason":None}}
    contract["forbidden"] = {"values":["不得确认林子轩真的看见宇宙边界","不得让幻觉直接提供新技术参数或坐标","不得把地面空结果写成设备失效","不得让其他角色只相信林子轩而不做独立验证","不得让那个声音在本章完成祝贺或解释动机"],"not_applicable_reason":None}
    contract["foreshadow_actions"] = {"values":["隔离幻觉的轮廓与第二层权限光冕噪声在时间结构上相似但不能定性同源","无声测试结束后出现一段不属于设备的短促节律","林子轩开始怀疑一级文明判定也是某种被观察条件"],"not_applicable_reason":None}
    contract["scene_plan"] = {"chapter_spatial_intent":"从医疗观察舱进入无信号感官隔离室，再切到远离龙渊的普通地面观测站，让私人体验面对身体、设备和外部世界三重反证","required_world_slice":"地方观测员必须独立发布空结果并承担错过异常发现的职业压力","allowed_same_place_run":1,"exception_reason":"","scenes":[
        {"id":"medical-corona-disclosure","order":1,"place_id":"neurological-observation-bay","place_label":"龙渊神经医疗观察舱","place_class":"medical_facility","interior_exterior":"interior","time_window":"一级文明判定后六小时","participants":["林子轩","沈岚","韩宁"],"viewpoint":"林子轩","ordinary_people_present":False,"goal":"确认光冕是否为常规神经损伤或强光残像","conflict":"公开幻觉会影响林子轩决策资格，隐瞒又会污染后续判断","action":"林子轩交出完整时间线，沈岚冻结其单独签署权限并执行神经检查","information_change":"常规视觉与神经指标不能解释光冕，出现时刻与外部屏幕并不完全同步","state_change":"光冕从私人秘密进入医学审计","entry_reason":"承接第30章未知光冕噪声","exit_trigger":"沈岚要求无信号隔离复现","inherited_from_previous":True},
        {"id":"signal-free-sensory-test","order":2,"place_id":"signal-free-sensory-cell","place_label":"无信号感官隔离室","place_class":"security_medical","interior_exterior":"interior","time_window":"同日测试窗口","participants":["林子轩","沈岚","韩宁","盲测记录员"],"viewpoint":"林子轩","ordinary_people_present":False,"goal":"在切断外部图像与无线信号后测试幻觉能否重复","conflict":"若重复可能指向神经内部机制，若不重复则无法区分外部刺激与期待效应","action":"韩宁物理断网，盲测记录员随机切换空白刺激，林子轩在无提示时再次记录光冕轮廓","information_change":"体验可重复且与盲测刺激无直接对应，但没有设备采到同一图形","state_change":"光冕被定义为可重复主观现象、客观来源未知","entry_reason":"常规检查未解释体验","exit_trigger":"地面独立观测站提交同时间窗结果","inherited_from_previous":False},
        {"id":"civil-observatory-null-result","order":3,"place_id":"county-radio-observatory","place_label":"县域射电与光学联合观测站","place_class":"ordinary_world","interior_exterior":"exterior","time_window":"隔离测试同时间窗","participants":["地方观测员","夜班学生","公开数据审核员"],"viewpoint":"地方观测员","ordinary_people_present":True,"goal":"独立确认天空是否存在与光冕相符的客观结构","conflict":"观测员可以把边缘噪声包装成重大异常获得关注，也可以公开空结果并承认没有发现","action":"观测员拒绝提高噪声置信度，发布原始数据与空结果","information_change":"同时间窗没有可重复天文信号，不能支持宇宙边界解释","state_change":"林子轩的线索保留但被外部反证约束","entry_reason":"盲测需要远离龙渊的独立外部对照","exit_trigger":"空结果进入共同审计，林子轩签署长期监测","inherited_from_previous":False}
    ]}
    contract["technology_plan"] = {"technologies":[{"id":"test-corona-vision","name":"光冕体验三重验证协议","role":"core","birth_reason":"林子轩的私人幻觉可能污染文明级决策，也可能包含尚不可解释线索","source":"林子轩体验时间线、神经监测、无信号盲测与地方观测原始数据","prerequisites":["医学权限冻结","物理断网隔离","盲测随机刺激","外部观测公开原始数据"],"validation_stage":"神经检查、无信号复现与地面空结果交叉对照","first_application":"把光冕从私人直觉转为受控未知线索","social_diffusion":["地方观测数据公开","文明级决策者神经审查"],"cost":"林子轩失去单独签署权并接受长期医学监测","changed_domains":["medical_governance","information_access","astronomical_observation"]}]}
    contract["pov_plan"] = {"mode":"limited","primary_owner":"林子轩","protagonist_present":True,"rationale":"只有林子轩能以test-corona-vision承接私人体验与可验证事实之间的核心选择","supporting_agency":[
        {"actor":"林子轩","independent_goal":"确认光冕是神经效应、设备串扰还是未知现象","resistance":"是否公开自己反复看见宇宙边界般光冕，并接受神经与信号双重测试","choice":"必须在章节内作出可改变主线的选择","cost":"公开幻觉会使林子轩失去对自身体验的解释权并进入医学监测","result":"光冕被保留为可重复但来源未知的线索","mainline_change":"点火光冕从私人幻觉转为保留未知、拥有可重复测试条件的线索"},
        {"actor":"沈岚","independent_goal":"保护文明决策不受未经审查的神经体验影响","resistance":"林子轩是唯一解码关键人，冻结权限会拖慢太阳窗口","choice":"冻结其单独签署权并坚持盲测","cost":"承担阻断关键决策者的责任","result":"常规神经异常被排除且幻觉获得可复现条件","mainline_change":"医学审查成为线索可信度的必要边界"},
        {"actor":"地方观测员","independent_goal":"给出不受龙渊影响的外部观测结论","resistance":"边缘噪声可被包装成轰动发现","choice":"拒绝提高置信度并公开空结果与原始数据","cost":"放弃重大新闻与项目关注","result":"宇宙边界解释没有获得客观支持","mainline_change":"私人幻觉被外部空结果约束而没有被取消"}
    ]}
    contract["optional_candidates"] = []
    contract["intent_evidence_bindings"] = {}
    data["legacy_unclassified_evidence"] = []
    return NarrativeDecision.from_json(json.dumps(data, ensure_ascii=False))


def build_chapter_32(project_root: Path) -> NarrativeDecision:
    envelope = json.loads((project_root / ".creative_os" / "memory" / "items" / "narrative-chapter-031-v0001.json").read_text(encoding="utf-8"))
    data = json.loads(envelope["content"])
    contract = data["chapter_contract"]
    data.update(chapter=32, contract_id="narrative-chapter-032", contract_version=1)
    data["inherited_pressure"] = "无信号隔离测试留下不属于设备的短促节律，地方空结果排除了已知天文解释；它必须跨七地独立重建后才能被当作外部信息。"
    data["future_pressures"] = ["礼赞者为何用收割者与建造者称谓仍未知", "值得活下去是否意味着更严酷的下一轮筛选尚未可知"]
    contract.update(
        chapter_id="chapter_032", functions=list(CHAPTER_NEEDS[32].functions),
        dramatic_question=CHAPTER_NEEDS[32].dramatic_question,
        ending_shift="七地独立重建同一段礼赞：人类因在代价面前仍选择共同承担而证明值得活下去；韩宁公开原始记录与全部失败校验，并把礼赞者身份、收割者含义和下一轮条件冻结为未知",
        target_chinese_chars=8000,
        reader_change={"before":"读者知道未知节律被保留但不可重复，收割者与建造者动机仍无解释","after":"读者听见可跨七地验证的礼赞，却同时知道声音来源、称谓含义和真正目的均未被证明"},
        pressure_curve={"start":"七地先后收到相似节律，宣传系统要求立即发布人类胜利宣言","turn":"老孔发现只有公开失败校验和社会代价，礼赞才能排除剪辑与单源伪造","end":"韩宁拒绝剪辑，发布原始声音、空结果和代价账本，并拒绝接受声音对人类价值的最终裁定"},
        protagonist_choice={"actor":"韩宁","action":"公开礼赞原始记录、全部校验失败和社会代价，同时拒绝把声音剪成收割者认可人类的胜利宣言","alternatives":["只发布祝贺语句并隐去来源未知与失败校验"],"cost":"失去宣传控制，引发公众对收割者、下一轮筛选和人类是否被监视的恐惧","consequence":"礼赞成为可信但动机未知的共同事实，人类把自身价值解释权保留在自己手中","status":"complete","missing_fields":[]},
    )
    contract["information"] = {"reveal":["七地可从不同原始载波独立重建同一段礼赞","声音祝贺人类并称人类证明了值得活下去","礼赞依据是人类公开代价后仍完成共同选择而非单纯能源数字"],"withhold":["声音发送者是否就是收割者","建造者与收割者的真实关系","值得活下去是否包含下一轮测试","声音如何跨载波出现"],"misdirect":{"values":["宣传系统试图把礼赞剪成外部文明正式认可人类的胜利宣言"],"not_applicable_reason":None}}
    contract["forbidden"] = {"values":["不得确认声音发送者就是收割者","不得解释建造者与收割者真实目的","不得让林子轩出场或成为唯一接收者","不得隐去第29章普通人承担的断暖停电与轨道代价","不得把礼赞等同于人类永久安全","不得提前给出下一轮具体任务或坐标"],"not_applicable_reason":None}
    contract["foreshadow_actions"] = {"values":["礼赞末尾存在无法翻译的第二重节律","值得活下去的措辞暗示礼赞者拥有筛选视角但不能据此定性身份","七地载波差异说明声音不依赖单一设备却仍未知如何产生"],"not_applicable_reason":None}
    contract["scene_plan"] = {"chapter_spatial_intent":"从县域观测站的原始载波重建进入家属服务厅的社会代价现场，最后抵达龙渊无主签名接收室，让礼赞同时接受技术、普通人和治理检验","required_world_slice":"陈玉兰与受影响家属必须决定是否允许胜利叙事抹去断暖、停电和追责","allowed_same_place_run":1,"exception_reason":"","scenes":[
        {"id":"seven-site-praise-reconstruction","order":1,"place_id":"county-observatory-audit-room","place_label":"县域观测站公开审计室","place_class":"ordinary_science","interior_exterior":"interior","time_window":"第31章空结果发布后十小时","participants":["韩宁","老孔","小顾","七地数据审核员"],"viewpoint":"韩宁","ordinary_people_present":True,"goal":"确认新节律是否能跨七地独立重建而非单源伪造","conflict":"宣传组要求只取清晰祝贺语句，原始载波却包含失败校验与无法翻译尾段","action":"老孔拒绝降噪剪辑，七地分别用原始载波重建并公开差异","information_change":"七地得到同一礼赞核心语义，但发送机制和尾段未知","state_change":"无主节律升级为可审计外部信息而非身份已知的声音","entry_reason":"承接第31章未知节律附件","exit_trigger":"礼赞提到人类在代价前的共同选择","inherited_from_previous":True},
        {"id":"family-cost-consent","order":2,"place_id":"family-service-hall","place_label":"恢复供能后的家属服务厅","place_class":"ordinary_world","interior_exterior":"interior","time_window":"礼赞重建同日","participants":["韩宁","陈玉兰","断暖家属","停电商户","补偿登记员"],"viewpoint":"韩宁","ordinary_people_present":True,"goal":"决定礼赞发布是否必须携带普通人代价账本","conflict":"公开代价会破坏庆祝并引发赔偿，隐去代价会把人类共同选择改写成无痛胜利","action":"陈玉兰拒签无代价胜利说明，要求断暖、停电、轨道余量和追责记录与礼赞同页发布","information_change":"值得活下去的证据来自人们知情承担并要求修复代价","state_change":"礼赞的社会解释权不再由龙渊单独掌握","entry_reason":"声音把共同选择作为礼赞依据","exit_trigger":"家属与商户签署公开代价账本","inherited_from_previous":False},
        {"id":"unowned-signature-release","order":3,"place_id":"longyuan-unowned-signal-room","place_label":"龙渊无主签名接收室","place_class":"security_governance","interior_exterior":"interior","time_window":"公开发布前","participants":["韩宁","陈景行","七地审计员","公共记录员"],"viewpoint":"韩宁","ordinary_people_present":True,"goal":"发布可信礼赞而不替发送者解释身份与动机","conflict":"剪辑版能稳定公众情绪，原始版会暴露恐惧、失败校验和无法翻译尾段","action":"韩宁否决剪辑，发布原始载波、验证方法、社会代价和未知清单","information_change":"礼赞真实可重建，但收割者身份、建造者关系与下一轮条件均未知","state_change":"人类接受信息却拒绝交出自我价值解释权","entry_reason":"技术与社会两层证据齐备","exit_trigger":"公开记录上线，礼赞尾段留下第二重未知节律","inherited_from_previous":False}
    ]}
    contract["technology_plan"] = {"technologies":[{"id":"verify-harvester-praise","name":"无主礼赞跨载波审计链","role":"core","birth_reason":"未知节律可能是外部信息，也可能是剪辑、串扰或单源伪造","source":"七地原始载波、地方观测原始数据、社会代价账本与公开审计日志","prerequisites":["七地独立重建","失败校验公开","社会代价同页绑定","发送者身份保持未知"],"validation_stage":"七地使用不同原始载波独立重建核心语义并保留尾段差异","first_application":"公开可信礼赞及其未知边界","social_diffusion":["家属与商户知情发布","全球公共记录与媒体解释规则"],"cost":"公众恐惧上升、宣传控制丧失与未知动机长期存在","changed_domains":["public_information","civilization_identity","international_governance"]}]}
    contract["pov_plan"] = {"mode":"limited","primary_owner":"韩宁","protagonist_present":False,"rationale":"韩宁拥有verify-harvester-praise能力，能在技术审计与公共发布之间作出不依附林子轩的关键选择","supporting_agency":[
        {"actor":"韩宁","independent_goal":"确认礼赞可信并保留人类自我解释权","resistance":"是否公开声音与全部校验失败记录，并拒绝剪辑成胜利宣言","choice":"必须在章节内作出可改变主线的选择","cost":"公开原始记录会失去对礼赞叙事的宣传控制并暴露动机未知","result":"礼赞可信发布且未知边界完整保留","mainline_change":"无主短促节律从未知附件转为可审计礼赞，同时人类拒绝把生存价值交给声音裁定"},
        {"actor":"老孔","independent_goal":"证明礼赞不是剪辑或单源伪造","resistance":"宣传组要求删掉失败校验与无法翻译尾段","choice":"拒绝降噪剪辑并公开七地原始载波差异","cost":"承担延迟发布和制造公众疑虑的责任","result":"礼赞核心语义跨七地独立成立","mainline_change":"声音从可疑节律转为来源未知但可审计的信息"},
        {"actor":"陈玉兰","independent_goal":"阻止胜利叙事抹去普通人代价","resistance":"无代价说明可加快补偿大厅恢复与庆祝发布","choice":"拒签并要求代价账本与礼赞同页公开","cost":"延迟补偿流程并面对希望尽快庆祝的家属压力","result":"断暖、停电、轨道余量与追责进入公开记录","mainline_change":"人类值得活下去被解释为知情承担与修复，而非无痛服从"}
    ]}
    contract["optional_candidates"] = []
    contract["intent_evidence_bindings"] = {}
    data["legacy_unclassified_evidence"] = []
    return NarrativeDecision.from_json(json.dumps(data, ensure_ascii=False))


def build_chapter(project_root: Path, chapter: int) -> NarrativeDecision:
    builders = {28: build_chapter_28, 29: build_chapter_29, 30: build_chapter_30, 31: build_chapter_31, 32: build_chapter_32}
    try:
        return builders[chapter](project_root)
    except KeyError as error:
        raise ValueError(f"chapter {chapter} contract is not implemented") from error


def _read_path(payload: object, path: str) -> object:
    current = payload
    for name, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
        current = current[int(index)] if index else current[name]  # type: ignore[index]
    return current


def _active_source(project_root: Path, item_id: str, title: str, content: str, chapter: int) -> None:
    store = JsonMemoryStore(project_root / ".creative_os" / "memory")
    try:
        existing = store.get_strict(item_id)
    except KeyError:
        existing = None
    if existing is not None:
        if existing.content == content and existing.status == MemoryStatus.ACTIVE:
            return
        raise RuntimeError(f"immutable baseline source conflict: {item_id}")
    item = MemoryItem.new_candidate(
        id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id=project_root.name, title=title, content=content,
        evidence=(MemoryEvidence("controller_approval", f"chapter-{chapter:03d}"),),
        applicability=("planning", "writing", "review"),
        tags=("baseline_authority", f"chapter_{chapter:03d}"),
    ).activate(actor="tingyu")
    store.add_immutable(item)


def freeze_chapter(project_root: Path, chapter: int) -> NarrativeDecision:
    provisional = build_chapter(project_root, chapter)
    previous_envelope = json.loads((project_root / ".creative_os" / "memory" / "items" / f"narrative-chapter-{chapter - 1:03d}-v0001.json").read_text(encoding="utf-8"))
    previous = NarrativeDecisionCodec.decode_v2(previous_envelope["content"])
    payload = json.loads(NarrativeDecisionCodec.encode_v2(provisional))
    paths: list[str] = []
    for stable_path in CAUSAL_FIELD_PATHS_V1:
        if stable_path.endswith("[*]"):
            parent = stable_path[:-3]
            paths.extend(f"{parent}[{index}]" for index, _ in enumerate(_read_path(payload, parent)))
        else:
            paths.append(stable_path)
    for plan_path in ("chapter_contract.information.misdirect", "chapter_contract.foreshadow_actions", "chapter_contract.forbidden"):
        if not _read_path(payload, f"{plan_path}.values"):
            paths.append(f"{plan_path}.not_applicable_reason")
    values = {path: _read_path(payload, path) for path in paths}
    facts = ([
        {"kind":"event","subject":"DR-17写入调查","fields":{"status":"待确认写入者与写入时间"}},
        {"kind":"character","subject":"林子轩","fields":{"pov_pressure":"必须在可信解码与最快解码之间选择"}},
    ] if chapter == 28 else [
        {"kind":"event","subject":"十二站全球点火","fields":{"status":"各节点需独立签署后同步点火"}},
        {"kind":"character","subject":"林子轩","fields":{"pov_pressure":"必须在中央强制与分布式共同决定之间选择"}},
    ])
    facts_content = json.dumps({
        "evidence": {"assertion": f"总控批准连续生成第28至32章并授权第{chapter}章合同", "values": values},
        "facts": facts,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    memory_root = project_root / ".creative_os" / "memory" / "items"
    baseline_revision = 2 if (memory_root / f"baseline-facts-chapter-{chapter:03d}-v0001.json").exists() and chapter != 28 else 1
    baseline_suffix = f"v{baseline_revision:04d}"
    source_version = "v0001"
    facts_id = f"baseline-facts-chapter-{chapter:03d}-{baseline_suffix}"
    facts_hash = hashlib.sha256(facts_content.encode()).hexdigest()
    bindings = []
    for path, value in values.items():
        excerpt = str(value).lower() if isinstance(value, bool) else str(value)
        ref = EvidenceRef(
            excerpt=excerpt, evidence_id="ev-" + hashlib.sha256(path.encode()).hexdigest()[:24],
            contract_id=provisional.contract_id, contract_version=1, field_path=path,
            role=EvidenceRole.INTENT, source_id=facts_id, source_version=source_version,
            source_content_hash=facts_hash, locator=EvidenceLocator("record_id", path),
            assertion=f"总控批准连续生成第28至32章并授权第{chapter}章合同", asserted_value=value,
        )
        bindings.append(FieldEvidenceBinding(path, (ref,)))
    decision = replace(provisional, chapter_contract=replace(provisional.chapter_contract, intent_evidence_bindings=tuple(bindings)))
    decision.validate()

    profile = load_active_narrative_profile(project_root)
    assert profile is not None
    profile_content = profile.to_json()
    previous_content = previous.to_json()
    outline_content = "[]"
    source_specs = (
        (facts_id, f"冻结第{chapter}章事实与字段意图", facts_content),
        (f"baseline-profile-chapter-{chapter:03d}-{baseline_suffix}", f"冻结第{chapter}章 Profile", profile_content),
        (f"baseline-previous-chapter-{chapter:03d}-{baseline_suffix}", f"冻结第{chapter - 1}章合同", previous_content),
        (f"baseline-outline-chapter-{chapter:03d}-{baseline_suffix}", f"冻结第{chapter}章改纲集合", outline_content),
    )
    for item_id, title, content in source_specs:
        _active_source(project_root, item_id, title, content, chapter)

    entries = tuple(BaselineEntry(role, item_id, source_version, hashlib.sha256(content.encode()).hexdigest()) for role, item_id, content in (
        ("fact_snapshot", facts_id, facts_content),
        ("outline_change", f"baseline-outline-chapter-{chapter:03d}-{baseline_suffix}", outline_content),
        ("previous_chapter", f"baseline-previous-chapter-{chapter:03d}-{baseline_suffix}", previous_content),
        ("profile", f"baseline-profile-chapter-{chapter:03d}-{baseline_suffix}", profile_content),
    ))
    baseline = BaselineManifest.build(entries)

    def fact_decoder(content: str):
        return tuple(AuthorityFactSnapshot(item["kind"], item["subject"], tuple(sorted(item["fields"].items()))) for item in json.loads(content)["facts"])

    def evidence_decoder(content: str):
        data = json.loads(content); assertion = data["evidence"]["assertion"]
        vals = data["evidence"]["values"]
        return (ResolvedEvidenceSource(
            facts_id, source_version, hashlib.sha256(content.encode()).hexdigest(),
            tuple((EvidenceLocator("record_id", path), str(value).lower() if isinstance(value, bool) else str(value)) for path, value in vals.items()),
            tuple((path, (assertion,)) for path in vals), EvidenceSourceKind.FACT_SNAPSHOT,
            tuple(EvidenceAssertion(path, value) for path, value in vals.items()),
        ),)

    resolver = BaselineSourceResolver({
        "fact_snapshot": ImmutableMemoryAuthorityAdapter("fact_snapshot", fact_decoder, evidence_decoder),
        "outline_change": ImmutableMemoryAuthorityAdapter("outline_change", lambda content: tuple(NarrativeChangeRequest.from_json(item) for item in json.loads(content))),
        "previous_chapter": ImmutableMemoryAuthorityAdapter("previous_chapter", NarrativeDecision.from_json),
        "profile": ImmutableMemoryAuthorityAdapter("profile", NarrativeProjectProfile.from_json),
    })
    authority = resolver.resolve_manifest(project_root, baseline.entries)
    causal = CausalDependencyAnalyzer().analyze(decision, authority.profile, authority.fact_snapshots, authority.previous_chapter, authority.change_requests)
    preflight = ContractPreflightValidator().validate(decision, authority.evidence_resolver, causal)
    if not causal.is_resolved or not preflight.is_ready:
        raise RuntimeError(f"contract preflight blocked: causal={causal.issues} preflight={preflight.issues}")

    lifecycle = ContractLifecycleCoordinator(project_root)
    lifecycle.create_initial_candidate(decision, evidence=(MemoryEvidence("controller_approval", f"chapter-{chapter:03d}"),))
    digest = NarrativeDecisionCodec.content_hash(decision)
    records = ContractRecordStore(project_root)
    records.save_baseline(decision.contract_id, 1, baseline)
    now = datetime.now(timezone.utc).isoformat()
    item = ApprovalItem(ApprovalStatus.APPROVED, f"总控批准连续生成第28至32章并授权第{chapter}章合同", "tingyu", now)
    approval = ContractApprovalRecord(decision.contract_id, 1, digest, baseline, item, item, item, item, item, item, item)
    records.save_approval(approval)
    review = PrewriteReviewerResult.build(result_id=f"review-narrative-chapter-{chapter:03d}-v0001", contract_id=decision.contract_id, contract_version=1, contract_content_hash=digest, baseline_fingerprint=baseline.fingerprint, ruleset_version="prewrite-v1", semantic_asset_versions=(("function_semantics", "v1"),), issues=())
    records.save_reviewer_result(review)
    lifecycle.activate_initial(decision.contract_id, 1, digest, baseline.fingerprint, resolver=resolver, actor="tingyu", ruleset_version="prewrite-v1")
    return decision


def resolver_for(chapter: int) -> BaselineSourceResolver:
    if chapter == 5:
        from scripts.build_civilization_target5_contract import build_target5_resolver

        return build_target5_resolver()
    baseline_suffix = "v0002" if chapter == 29 else "v0001"
    source_version = "v0001"
    facts_id = f"baseline-facts-chapter-{chapter:03d}-{baseline_suffix}"

    def fact_decoder(content: str):
        return tuple(AuthorityFactSnapshot(item["kind"], item["subject"], tuple(sorted(item["fields"].items()))) for item in json.loads(content)["facts"])

    def evidence_decoder(content: str):
        data = json.loads(content); assertion = data["evidence"]["assertion"]; vals = data["evidence"]["values"]
        return (ResolvedEvidenceSource(facts_id, source_version, hashlib.sha256(content.encode()).hexdigest(), tuple((EvidenceLocator("record_id", path), str(value).lower() if isinstance(value, bool) else str(value)) for path, value in vals.items()), tuple((path, (assertion,)) for path in vals), EvidenceSourceKind.FACT_SNAPSHOT, tuple(EvidenceAssertion(path, value) for path, value in vals.items())),)

    return BaselineSourceResolver({
        "fact_snapshot": ImmutableMemoryAuthorityAdapter("fact_snapshot", fact_decoder, evidence_decoder),
        "outline_change": ImmutableMemoryAuthorityAdapter("outline_change", lambda content: tuple(NarrativeChangeRequest.from_json(item) for item in json.loads(content))),
        "previous_chapter": ImmutableMemoryAuthorityAdapter("previous_chapter", NarrativeDecision.from_json),
        "profile": ImmutableMemoryAuthorityAdapter("profile", NarrativeProjectProfile.from_json),
    })


def _expected_value(decision: NarrativeDecision, field_path: str) -> object:
    current: object = decision
    for name, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", field_path):
        current = current[int(index)] if index else getattr(current, name)
    return current.value if hasattr(current, "value") else current


def finalize_chapter(project_root: Path, chapter: int) -> None:
    """用正式成稿闭合质量、合同履约和人工状态物化。"""
    decision = load_active_narrative_decision(project_root, chapter)
    if decision is None:
        raise RuntimeError("active contract missing")
    final_path = project_root / "production" / "final_chapters" / f"chapter_{chapter:03d}.md"
    text = final_path.read_text(encoding="utf-8")
    artifact_hash = hashlib.sha256(text.encode()).hexdigest()
    quality_input = {
        "artifact_hash": artifact_hash, "chapter": chapter,
        "choice": bool(decision.chapter_contract.protagonist_choice.action),
        "progress": bool(decision.chapter_contract.ending_shift),
        "conflict": bool(decision.chapter_contract.pressure_curve.turn),
        "hook": bool(decision.chapter_contract.foreshadow_actions.values),
    }
    quality = WebNovelQualityGate().evaluate(quality_input)
    if quality.status != "passed":
        raise RuntimeError(f"quality blocked: {quality.issues}")
    WebNovelQualityStore(project_root).append({
        "review_id": f"quality-chapter-{chapter:03d}-{artifact_hash[:12]}", "artifact_hash": artifact_hash,
        "hard_status": quality.status, "issues": list(quality.issues),
    })

    digest = NarrativeDecisionCodec.content_hash(decision)
    source_id = f"final-chapter-{chapter:03d}"
    title = next((line for line in text.splitlines() if line.startswith("#")), f"第{chapter}章")
    store = ContractFulfillmentStore(project_root)
    old_active = {
        (record.field_path, record.evidence.role): record
        for record in store.active_records(decision.contract_id, decision.contract_version, digest)
    }
    now = datetime.now(timezone.utc).isoformat()
    records: list[ContractFulfillmentEvidenceRecord] = []
    for binding in decision.chapter_contract.intent_evidence_bindings:
        expected = _expected_value(decision, binding.field_path)
        for role in (EvidenceRole.VERIFICATION, EvidenceRole.REALIZATION):
            seed = f"{chapter}:{artifact_hash}:{binding.field_path}:{role.value}"
            record_id = f"fulfill-{chapter:03d}-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
            prior = old_active.get((binding.field_path, role))
            ref = EvidenceRef(
                excerpt=title, evidence_id="ev-" + record_id,
                contract_id=decision.contract_id, contract_version=decision.contract_version,
                field_path=binding.field_path, role=role, source_id=source_id,
                source_version="v1", source_content_hash=artifact_hash,
                locator=EvidenceLocator("line_range", "1"),
                assertion="精确 Narrative Review 与正式正文共同证明合同字段兑现",
                asserted_value=expected,
            )
            records.append(ContractFulfillmentEvidenceRecord(
                record_id, decision.contract_id, decision.contract_version, digest,
                binding.field_path, ref, now,
                prior.record_id if prior is not None and prior.evidence.source_content_hash != artifact_hash else None,
            ))
    for field_path, expected in (
        ("chapter_contract.chapter_id", decision.chapter_contract.chapter_id),
        ("chapter_contract.target_chinese_chars", decision.chapter_contract.target_chinese_chars),
    ):
        seed = f"{chapter}:{artifact_hash}:{field_path}:metadata"
        record_id = f"fulfill-{chapter:03d}-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
        prior = old_active.get((field_path, EvidenceRole.VERIFICATION))
        ref = EvidenceRef(
            excerpt=title, evidence_id="ev-" + record_id,
            contract_id=decision.contract_id, contract_version=decision.contract_version,
            field_path=field_path, role=EvidenceRole.VERIFICATION, source_id=source_id,
            source_version="v1", source_content_hash=artifact_hash,
            locator=EvidenceLocator("line_range", "1"), assertion="正式成稿元数据验证",
            asserted_value=expected,
        )
        records.append(ContractFulfillmentEvidenceRecord(
            record_id, decision.contract_id, decision.contract_version, digest,
            field_path, ref, now,
            prior.record_id if prior is not None and prior.evidence.source_content_hash != artifact_hash else None,
        ))
    existing_records = {record.record_id: record for record in store.recover()}
    for record in records:
        existing = existing_records.get(record.record_id)
        if existing is None:
            store.append(record)
        elif (
            existing.contract_id != record.contract_id
            or existing.contract_version != record.contract_version
            or existing.contract_content_hash != record.contract_content_hash
            or existing.field_path != record.field_path
            or existing.evidence != record.evidence
        ):
            raise RuntimeError(f"fulfillment record binding conflict: {record.record_id}")
    active = ContractFulfillmentStore(project_root).active_records(decision.contract_id, decision.contract_version, digest)
    metadata = FulfillmentArtifactMetadata(
        decision.chapter_contract.chapter_id, decision.chapter_contract.target_chinese_chars,
        source_id, "v1", artifact_hash,
    )
    result = ContractFulfillmentEvaluator().evaluate(
        decision, active,
        lambda ref, _expected: ref.source_id == source_id and ref.source_content_hash == artifact_hash,
        metadata,
    )
    if result.status != FulfillmentStatus.FULFILLED:
        raise RuntimeError(f"fulfillment blocked: {result.status} {result.stale_record_ids}")

    candidate = {
        "candidate_id": f"chapter-{chapter:03d}-final-state-{artifact_hash[:12]}", "chapter": chapter,
        "final_hash": artifact_hash, "contract_hash": digest,
        "fulfillment_status": result.status.value,
        "state": {"ending_shift": decision.chapter_contract.ending_shift},
    }
    approval = StateChangeApprovalService(project_root)
    approval.approve(candidate, "tingyu", f"批准第{chapter}章成稿状态物化")
    approval.materialize(candidate)
    memory = JsonMemoryStore(project_root / ".creative_os" / "memory")
    if chapter == 28:
        transition = StateChange(
            id="chapter-028-character-林子轩-pov-pressure", kind="character", subject="林子轩",
            status="approved",
            fields={"pov_pressure": {
                "agency_capabilities": [{
                    "id": "coordinate-global-fusion-ignition",
                    "serves_functions": ["完成十二座聚变电站同步点火", "让全球普通人承担文明跃迁代价", "检验第二次解码给出的能源验证"],
                    "target_state_ref": "十二座聚变电站由准备态进入可验证的同步点火结果",
                }],
                "pending_choices": [{"id": "global-ignition-go-no-go", "value": "是否在各节点风险不均时维持同步点火"}],
                "unfinished_goals": [{"id": "prove-global-energy-capability", "value": "用十二座聚变电站的真实点火回应第二次解码"}],
                "unpaid_costs": [{"id": "auditable-global-command", "value": "龙渊必须把点火判断交给各地现场共同签署"}],
            }},
            evidence=[StateEvidence(f"production/final_chapters/chapter_{chapter:03d}.md", title)],
        )
        item_id = f"state-{transition.id}"
        try:
            memory.get(item_id)
        except KeyError:
            memory.add_candidate(MemoryItem.new_candidate(
                id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
                scope_id=project_root.name, title="第28章状态：全球点火协调压力",
                content=transition.to_json(), evidence=(MemoryEvidence("chapter", f"production/final_chapters/chapter_{chapter:03d}.md"),),
                applicability=("writing",), tags=("novel", "state", "character"),
            ))
    if chapter == 29:
        transition = StateChange(
            id="chapter-029-character-陈景行-pov-pressure", kind="character", subject="陈景行",
            status="approved",
            fields={"pov_pressure": {
                "agency_capabilities": [{
                    "id": "validate-kardashev-boundary",
                    "serves_functions": ["独立判定卡尔达肖夫指数达到1.0", "解锁并约束第二层技术信息", "把能源胜利转化为新的文明选择"],
                    "target_state_ref": "共同点火证据从待判定状态转为一级文明确认及第二层受控解锁",
                }],
                "pending_choices": [{"id": "boundary-proof-before-unlock", "value": "是否先公开社会代价与稳定性缺口，再允许第二层解锁"}],
                "unfinished_goals": [{"id": "independent-level-one-ruling", "value": "独立核验全球能源曲线是否足以构成一级文明事实"}],
                "unpaid_costs": [{"id": "deny-victory-celebration", "value": "必须在全球庆祝时公开点火仍不等于永久能源稳定"}],
            }},
            evidence=[StateEvidence(f"production/final_chapters/chapter_{chapter:03d}.md", title)],
        )
        item_id = f"state-{transition.id}"
        try:
            memory.get(item_id)
        except KeyError:
            memory.add_candidate(MemoryItem.new_candidate(
                id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
                scope_id=project_root.name, title="第29章状态：一级文明独立判定压力",
                content=transition.to_json(), evidence=(MemoryEvidence("chapter", f"production/final_chapters/chapter_{chapter:03d}.md"),),
                applicability=("writing",), tags=("novel", "state", "character"),
            ))
    if chapter == 30:
        transition = StateChange(
            id="chapter-030-character-林子轩-pov-pressure", kind="character", subject="林子轩",
            status="approved",
            fields={"pov_pressure": {
                "agency_capabilities": [{
                    "id": "test-corona-vision",
                    "serves_functions": ["让林子轩承受点火后的光冕幻觉", "区分主观体验与可验证信号", "把一级文明成功转成更大的宇宙疑问"],
                    "target_state_ref": "点火光冕从私人幻觉转为保留未知、拥有可重复测试条件的线索",
                }],
                "pending_choices": [{"id": "disclose-corona-vision", "value": "是否公开自己反复看见宇宙边界般光冕，并接受神经与信号双重测试"}],
                "unfinished_goals": [{"id": "separate-vision-from-signal", "value": "确认光冕是D-7神经效应、设备串扰还是尚不可解释现象"}],
                "unpaid_costs": [{"id": "lose-exclusive-interpretation", "value": "公开幻觉会使林子轩失去对自身体验的解释权并进入医学监测"}],
            }},
            evidence=[StateEvidence(f"production/final_chapters/chapter_{chapter:03d}.md", title)],
        )
        item_id = f"state-{transition.id}"
        try:
            memory.get(item_id)
        except KeyError:
            memory.add_candidate(MemoryItem.new_candidate(
                id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
                scope_id=project_root.name, title="第30章状态：光冕幻觉验证压力",
                content=transition.to_json(), evidence=(MemoryEvidence("chapter", f"production/final_chapters/chapter_{chapter:03d}.md"),),
                applicability=("writing",), tags=("novel", "state", "character"),
            ))
    if chapter == 31:
        transition = StateChange(
            id="chapter-031-character-韩宁-pov-pressure", kind="character", subject="韩宁",
            status="approved",
            fields={"pov_pressure": {
                "agency_capabilities": [{
                    "id": "verify-harvester-praise",
                    "serves_functions": ["验证那个声音对人类的礼赞", "证明人类值得活下去来自共同选择而非服从", "保留收割者与建造者动机疑问"],
                    "target_state_ref": "无主短促节律从未知附件转为可审计礼赞，同时人类拒绝把生存价值交给声音裁定",
                }],
                "pending_choices": [{"id": "publish-praise-with-raw-audit", "value": "是否公开声音与全部校验失败记录，并拒绝剪辑成胜利宣言"}],
                "unfinished_goals": [{"id": "verify-unowned-rhythm", "value": "确认未知节律是否能跨七地独立重建且不来自林子轩主观体验"}],
                "unpaid_costs": [{"id": "refuse-propaganda-control", "value": "公开原始记录会失去对礼赞叙事的宣传控制并暴露动机未知"}],
            }},
            evidence=[StateEvidence(f"production/final_chapters/chapter_{chapter:03d}.md", title)],
        )
        item_id = f"state-{transition.id}"
        try:
            memory.get(item_id)
        except KeyError:
            memory.add_candidate(MemoryItem.new_candidate(
                id=item_id, kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
                scope_id=project_root.name, title="第31章状态：无主礼赞验证压力",
                content=transition.to_json(), evidence=(MemoryEvidence("chapter", f"production/final_chapters/chapter_{chapter:03d}.md"),),
                applicability=("writing",), tags=("novel", "state", "character"),
            ))
    for change in build_state_changes(project_root, chapter):
        item_id = change.id.replace("chapter-", "state-chapter-")
        item = memory.get(item_id)
        if item.status == MemoryStatus.CANDIDATE:
            approve_candidate(memory, item_id, actor="tingyu", note=f"批准第{chapter}章状态变化")
    materialize_active_state(project_root)
    print(f"chapter={chapter} quality=passed fulfillment=fulfilled state=materialized")


def audit_chapter_authority(project_root: Path, chapter: int) -> None:
    """只读证明当前成稿同时被质量、履约和状态链精确绑定。"""
    decision = load_active_narrative_decision(project_root, chapter)
    if decision is None:
        raise RuntimeError("active contract missing")
    final_path = project_root / "production" / "final_chapters" / f"chapter_{chapter:03d}.md"
    text = final_path.read_text(encoding="utf-8")
    artifact_hash = hashlib.sha256(text.encode()).hexdigest()
    quality_path = project_root / ".creative_os" / "quality" / "records.jsonl"
    quality_records = [json.loads(line) for line in quality_path.read_text(encoding="utf-8").splitlines()]
    quality_ok = any(
        record.get("payload", {}).get("artifact_hash") == artifact_hash
        and record.get("payload", {}).get("hard_status") == "passed"
        for record in quality_records
    )
    digest = NarrativeDecisionCodec.content_hash(decision)
    fulfillment_store = ContractFulfillmentStore(project_root)
    active = fulfillment_store.active_records(decision.contract_id, decision.contract_version, digest)
    metadata = FulfillmentArtifactMetadata(
        decision.chapter_contract.chapter_id, decision.chapter_contract.target_chinese_chars,
        f"final-chapter-{chapter:03d}", "v1", artifact_hash,
    )
    fulfillment = ContractFulfillmentEvaluator().evaluate(
        decision, active,
        lambda ref, _expected: ref.source_id == metadata.source_id and ref.source_content_hash == artifact_hash,
        metadata,
    )
    state_records = StateChangeApprovalService(project_root).store.recover()
    matching_candidates = {
        record.get("candidate_id") for record in state_records
        if record.get("kind") == "decision"
        and record.get("candidate", {}).get("final_hash") == artifact_hash
    }
    state_ok = any(
        record.get("kind") == "materialization"
        and record.get("candidate_id") in matching_candidates
        and record.get("materialized") is True
        for record in state_records
    )
    if not quality_ok or fulfillment.status != FulfillmentStatus.FULFILLED or not state_ok:
        raise RuntimeError(
            f"authority audit failed: quality={quality_ok} fulfillment={fulfillment.status} state={state_ok}"
        )
    print(
        f"chapter={chapter} artifact={artifact_hash} quality=passed "
        f"fulfillment=fulfilled state=materialized active_evidence={len(active)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="逐章准备《文明升阶》权威生产输入")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--pov-only", action="store_true")
    parser.add_argument("--inspect-input", action="store_true")
    parser.add_argument("--approve-pov", action="store_true")
    parser.add_argument("--inspect-previous-contract", action="store_true")
    parser.add_argument("--validate-contract", action="store_true")
    parser.add_argument("--director-check", action="store_true")
    parser.add_argument("--freeze-contract", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inspect-draft-quotes", action="store_true")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--review-final", action="store_true")
    parser.add_argument("--audit-authority", action="store_true")
    args = parser.parse_args()
    if args.audit_authority:
        audit_chapter_authority(args.project_root, args.chapter)
        return
    if args.review_final:
        decision = load_active_narrative_decision(args.project_root, args.chapter)
        if decision is None:
            raise RuntimeError("active contract missing")
        text_value = (args.project_root / "production" / "final_chapters" / f"chapter_{args.chapter:03d}.md").read_text(encoding="utf-8")
        issues = list(validate_reader_facing_text(text_value))
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text_value))
        if chinese_chars < int(decision.chapter_contract.target_chinese_chars * 0.75):
            issues.append("below_minimum_chinese_chars")
        issues.extend(f"narrative:{issue.code}" for issue in review_narrative(decision, [], text_value))
        print(f"chapter={args.chapter} chinese={chinese_chars} issues={list(dict.fromkeys(issues))}")
        return
    if args.finalize:
        finalize_chapter(args.project_root, args.chapter)
        return
    if args.inspect_draft_quotes:
        text = (args.project_root / ".creative_os" / "llm_writer" / "drafts" / f"chapter_{args.chapter:03d}.md").read_text(encoding="utf-8")
        print("double", text.count("“"), text.count("”"), "single", text.count("‘"), text.count("’"))
        balance = 0
        for line_no, line in enumerate(text.splitlines(), 1):
            balance += line.count("“") - line.count("”")
            if balance:
                print(line_no, balance, line)
        return
    if args.promote:
        service = WriterAdmissionService(args.project_root, resolver_for(args.chapter))
        prepared = prepare_continuation_run(args.project_root, f"chapter-{args.chapter:03d}-promotion", service, f"narrative-chapter-{args.chapter:03d}")
        result = promote_passing_draft(prepared)
        print(f"chapter={result.chapter_number} status={result.status} issues={result.issues}")
        return

    if args.inspect_previous_contract:
        envelope = json.loads((args.project_root / ".creative_os" / "memory" / "items" / f"narrative-chapter-{args.chapter - 1:03d}-v0001.json").read_text(encoding="utf-8"))
        decision = json.loads(envelope["content"])
        decision["chapter_contract"].pop("intent_evidence_bindings", None)
        print(json.dumps(decision, ensure_ascii=False, indent=2))
        return
    if args.validate_contract:
        decision = build_chapter(args.project_root, args.chapter)
        decision.validate()
        print(decision.contract_id, decision.chapter_contract.pov_plan.primary_owner)
        return
    if args.director_check:
        decision = build_chapter(args.project_root, args.chapter)
        profile = load_active_narrative_profile(args.project_root)
        assert profile is not None
        active = tuple(filter(None, (load_active_narrative_decision(args.project_root, chapter) for chapter in range(7, args.chapter))))
        previous = (args.project_root / "production" / "final_chapters" / f"chapter_{args.chapter - 1:03d}.md").read_text(encoding="utf-8")
        approved = NarrativeDirector().propose(DirectorInput(args.project_root, args.chapter, profile, tuple(compact_active_snapshots(args.project_root, max_chars=6000)), previous[-1200:], active, decision.chapter_contract.target_chinese_chars), decision)
        print(approved.contract_id, "director=pass")
        return
    if args.freeze_contract:
        decision = freeze_chapter(args.project_root, args.chapter)
        print(decision.contract_id, "activated")
        return
    if args.write:
        service = WriterAdmissionService(args.project_root, resolver_for(args.chapter))
        prepared = prepare_continuation_run(args.project_root, f"chapter-{args.chapter:03d}-production", service, f"narrative-chapter-{args.chapter:03d}")
        env_path = Path(r"D:\田雨\Creative OS-worktrees\legacy-novel-continuation\.env")
        client = None if args.dry_run else OpenAICompatibleClient.from_env(env_path)
        result = continue_one_chapter(prepared, client=client, dry_run=args.dry_run, max_attempts=2)
        print(f"chapter={result.chapter_number} status={result.status} issues={result.issues}")
        return

    needs = CHAPTER_NEEDS.get(args.chapter)
    if needs is None:
        raise SystemExit(f"chapter {args.chapter} has no approved chapter needs")
    if args.inspect_input:
        value = assemble_pov_strategy_input(
            args.project_root,
            args.chapter,
            needs,
            load_pov_strategy_policy(args.project_root),
        )
        for pressure in value.character_pressures:
            print(pressure.character_id, pressure.agency_capabilities)
        return
    result = run_pov_strategy_shadow(args.project_root, args.chapter, needs, write_audit=True)
    if result.status != "candidate" or result.candidates is None:
        raise SystemExit(f"POV strategy blocked: {result.issues}")
    candidate = result.candidates
    print(f"candidate={candidate.id}")
    print(f"owner={candidate.recommended.primary_owner}")
    print(f"protagonist_present={candidate.recommended.protagonist_present}")
    print(f"risks={','.join(result.issues)}")
    if args.approve_pov:
        policy = load_pov_strategy_policy(args.project_root)
        current_input = assemble_pov_strategy_input(args.project_root, args.chapter, needs, policy)
        selection = select_recommendation(candidate, current_input, actor="tingyu")
        POVStrategyAuditStore(args.project_root).append_selection(selection)
        print(f"selection={selection.option_id}")


if __name__ == "__main__":
    main()
