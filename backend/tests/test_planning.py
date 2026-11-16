import json

import pytest

from app import planning


def task(**kw):
    return {"id": "T1", "role": "software", "title": "a", "goal": "g", **kw}


def test_valid_plan_and_alias_roles():
    assert planning.validate_plan({"tasks": [task(role="phần mềm"), task(id="T2", role="media", depends_on=["T1"])]}) == []


@pytest.mark.parametrize("plan,msg", [
    ([], "object"), ({"tasks": []}, "ít nhất một"),
    ({"tasks": [task(role="chef")]}, "role"),
    ({"tasks": [task(), task()]}, "trùng"),
    ({"tasks": [task(depends_on=["X"])]}, "không tồn tại"),
    ({"tasks": [task(depends_on=["T2"]), task(id="T2", depends_on=["T1"])]}, "vòng"),
    ({"tasks": [task(id=f"T{i}") for i in range(9)]}, "Quá nhiều"),
])
def test_invalid_plans(plan, msg):
    assert any(msg in e for e in planning.validate_plan(plan))


def test_ordered_tasks_respects_dependencies_then_declaration_order():
    plan = {"tasks": [task(id="B", depends_on=["A"]), task(id="C"), task(id="A")]}
    assert [t["id"] for t in planning.ordered_tasks(plan)] == ["C", "A", "B"]


def test_json_in_code_fence():
    assert planning.load_json("```json\n{\"a\": 1}\n```") == {"a": 1}


def test_cases_validation():
    ok = {"cases": [{"id": "TC1", "title": "t", "criterion": "c", "steps": ["x"], "expect": {"exit_code": 0}}]}
    assert planning.validate_cases(ok) == []
    assert any("expect" in e for e in planning.validate_cases({"cases": [{"id": "TC1", "title": "t", "criterion": "c", "steps": ["x"]}]}))
    assert any("trùng" in e for e in planning.validate_cases({"cases": [ok["cases"][0], ok["cases"][0]]}))
    assert any("steps" in e for e in planning.validate_cases({"cases": [{"id": "T", "title": "t", "criterion": "c", "steps": [], "expect": {"exit_code": 0}}]}))


def test_evaluate_against_expect():
    c = {"expect": {"exit_code": 0, "stdout_contains": ["XONG"], "stdout_not_contains": ["Traceback"]}}
    assert planning.evaluate(c, 0, "XONG\n")[0]
    assert not planning.evaluate(c, 1, "XONG")[0]
    assert not planning.evaluate(c, 0, "chưa")[0]
    assert not planning.evaluate(c, 0, "XONG Traceback")[0]
    assert planning.machine_checkable(c) and not planning.machine_checkable({"manual_check": "xem"})
