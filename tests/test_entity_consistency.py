from creative_os.domains.entity_consistency import canonical_entities_from_baseline, entity_aliases_from_baseline, find_entity_warnings


def test_entity_checker_flags_nearby_name_without_rejecting_text():
    entities = {"character": ("林子轩",)}

    warnings = find_entity_warnings("刘子轩推开了门。", entities)

    assert len(warnings) == 1
    assert warnings[0].canonical == "林子轩"
    assert warnings[0].observed == "刘子轩"
    assert warnings[0].position == 0


def test_entity_checker_accepts_explicit_aliases_and_extracts_frontmatter():
    baseline = {
        "characters": [
            {"title": "Protagonist", "content": "---\nname: 林子轩\naliases: 解码者\n---"},
        ],
        "locations": [
            {"title": "龙渊", "content": "---\nname: 龙渊\naliases: []\n---"},
        ],
    }

    entities = canonical_entities_from_baseline(baseline)
    aliases = entity_aliases_from_baseline(baseline)

    assert entities == {"character": ("林子轩",), "location": ("龙渊",)}
    assert aliases == {"character": ("解码者",)}
    assert find_entity_warnings("解码者进入龙渊。", entities, aliases=aliases) == []


def test_entity_checker_does_not_fuzzy_match_role_labels():
    entities = {"character": ("能源局长", "军方代表", "胖阿姨")}

    warnings = find_entity_warnings("能源局的人与能源局副局长参加了会议。", entities)

    assert warnings == []
