from creative_os.workspace_presentation import command_label, diagnostic_label, event_label, is_internal_identifier, status_label


def test_presentation_maps_internal_statuses_to_chinese_product_labels():
    assert status_label("partial") == "部分可用"
    assert status_label("unavailable") == "暂不可用"
    assert event_label("UserRevised") == "作者修改了章节"
    assert event_label("TaskFailed") == "本次运行失败"
    assert command_label("start_chapter_run") == "开始生成本章"


def test_presentation_hides_trace_ids_and_internal_paths_from_normal_surface():
    assert is_internal_identifier("trace-abc")
    assert is_internal_identifier(".creative_os/runtime/events.jsonl")
    assert not is_internal_identifier("第七十九章")
    assert diagnostic_label("operations_usage_unavailable") == "暂时没有用量统计"

