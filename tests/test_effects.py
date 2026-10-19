from custom_components.duoco_stripx.effects import EFFECTS, effects_for, effect_by_label, effect_by_id


def test_counts_and_uniqueness():
    assert len(EFFECTS) == 213  # groups 0-7 from the app arrays; scene group excluded
    assert len({e.id for e in EFFECTS}) == 213
    assert len({e.label for e in EFFECTS}) == 213
    assert {e.group for e in EFFECTS} == {"Basic", "Curtain", "Trans", "Water", "Flow", "Tail", "Run", "RunBack"}
    assert "Scenes" not in {e.group for e in EFFECTS}


def test_known_ids():
    assert effect_by_id(0).label == "Auto Play"
    assert effect_by_id(212).label == "7-Color Energy"
    assert effect_by_id(77).label == "7-Color Race"
    assert effect_by_id(78).label == "7-Color Race Back"  # app label, no invented direction


def test_strobe_hidden_by_default():
    default = {e.id for e in effects_for(False)}
    allowed = {e.id for e in effects_for(True)}
    assert not default & {196, 197, 198}
    assert {196, 197, 198} <= allowed
    assert effect_by_label("7-Color Strobe", True).id == 196
    assert effect_by_label("7-Color Strobe", False) is None
    assert all(e.flashing for e in EFFECTS if "Strobe" in e.label)


def test_scene_ids_not_exposed_as_effects():
    assert all(e.id > 0 or e.label == "Auto Play" for e in EFFECTS)
