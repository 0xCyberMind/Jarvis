from planner import _quick_classify, _classify_planning_mode_heuristic, PlanningDecision


def test_quick_classify_build():
    assert _quick_classify("Please build a small site for me") == "build"


def test_heuristic_simple():
    d = _classify_planning_mode_heuristic("What time is it?")
    assert isinstance(d, PlanningDecision)
    assert d.task_type == "simple"


def test_heuristic_fix_missing_info():
    d = _classify_planning_mode_heuristic("Fix the error in my project")
    assert d.task_type == "fix"
    assert d.needs_planning is True
