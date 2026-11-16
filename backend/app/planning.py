"""Kế hoạch (plan.json) và bộ testcase (qa/testcases.json): kiểm tra định dạng bằng code, không tin model.

Giám đốc và Kiểm định là model, đôi khi trả JSON thiếu trường hay trỏ phụ thuộc vào task không tồn tại. Các hàm validate_* trả
DANH SÁCH LỖI bằng tiếng Việt; máy trạng thái đưa nguyên danh sách đó lại cho model để nó sửa (tối đa vài lần).
"""
import json
from graphlib import CycleError, TopologicalSorter

MAX_TASKS = 8
MAX_CASES = 25
ROLE_ALIASES = {"software": "software", "phần mềm": "software", "phan mem": "software", "engineer": "software",
                "media": "media", "đồ họa": "media", "do hoa": "media"}


def normalize_role(r: str) -> str | None:
    return ROLE_ALIASES.get(str(r).strip().lower())


def load_json(text: str):
    """Model hay bọc JSON trong ```json ...```. Gỡ lớp bọc đó rồi parse."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return json.loads(t)


def validate_plan(obj) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["plan.json phải là một object JSON có các khoá summary và tasks"]
    tasks = obj.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return ["Thiếu danh sách tasks (phải có ít nhất một task)"]
    if len(tasks) > MAX_TASKS:
        errs.append(f"Quá nhiều task ({len(tasks)}), tối đa {MAX_TASKS}. Gộp bớt: giữ ít task nhất có thể")
    ids = []
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            errs.append(f"tasks[{i}] phải là object")
            continue
        tid = str(t.get("id", "")).strip()
        if not tid:
            errs.append(f"tasks[{i}] thiếu id")
        elif tid in ids:
            errs.append(f"id trùng: {tid}")
        ids.append(tid)
        if normalize_role(t.get("role", "")) is None:
            errs.append(f"{tid or i}: role '{t.get('role')}' không hợp lệ (chỉ 'software' hoặc 'media')")
        for k in ("title", "goal"):
            if not str(t.get(k, "")).strip():
                errs.append(f"{tid or i}: thiếu {k}")
        for k in ("outputs", "acceptance", "depends_on", "inputs"):
            if k in t and not isinstance(t[k], list):
                errs.append(f"{tid or i}: {k} phải là danh sách")
    if errs:
        return errs
    graph = {}
    for t in tasks:
        deps = [str(d) for d in t.get("depends_on", [])]
        for d in deps:
            if d not in ids:
                errs.append(f"{t['id']}: depends_on trỏ tới task không tồn tại: {d}")
        graph[str(t["id"])] = set(deps)
    if not errs:
        try:
            list(TopologicalSorter(graph).static_order())
        except CycleError:
            errs.append("depends_on tạo vòng lặp (task chờ nhau)")
    return errs


def ordered_tasks(plan: dict) -> list[dict]:
    """Task theo thứ tự thực hiện được (phụ thuộc xong trước), giữ thứ tự khai báo khi không ràng buộc."""
    tasks = {str(t["id"]): t for t in plan["tasks"]}
    order = list(TopologicalSorter({k: set(map(str, v.get("depends_on", []))) for k, v in tasks.items()}).static_order())
    pos = {str(t["id"]): i for i, t in enumerate(plan["tasks"])}
    # static_order không đảm bảo thứ tự khai báo giữa các task độc lập: sắp lại ổn định theo (độ sâu, vị trí khai báo).
    depth: dict[str, int] = {}
    for k in order:
        depth[k] = 1 + max((depth[d] for d in map(str, tasks[k].get("depends_on", []))), default=0)
    return [tasks[k] for k in sorted(order, key=lambda k: (depth[k], pos[k]))]


def validate_cases(obj) -> list[str]:
    errs: list[str] = []
    cases = obj.get("cases") if isinstance(obj, dict) else None
    if not isinstance(cases, list) or not cases:
        return ['Thiếu "cases": danh sách testcase (ít nhất một)']
    if len(cases) > MAX_CASES:
        errs.append(f"Quá nhiều testcase ({len(cases)}), tối đa {MAX_CASES}")
    seen = set()
    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            errs.append(f"cases[{i}] phải là object")
            continue
        cid = str(c.get("id", "")).strip()
        if not cid or cid in seen:
            errs.append(f"cases[{i}]: id thiếu hoặc trùng ({cid!r})")
        seen.add(cid)
        for k in ("title", "criterion"):
            if not str(c.get(k, "")).strip():
                errs.append(f"{cid or i}: thiếu {k} (criterion = tiêu chí nghiệm thu trong brief mà case này kiểm)")
        steps = c.get("steps")
        if not isinstance(steps, list) or not steps or not all(isinstance(s, str) and s.strip() for s in steps):
            errs.append(f"{cid or i}: steps phải là danh sách lệnh shell (chuỗi), ít nhất một")
        if "setup" in c and not (isinstance(c["setup"], list) and all(isinstance(s, str) for s in c["setup"])):
            errs.append(f"{cid or i}: setup phải là danh sách chuỗi")
        ex = c.get("expect")
        if ex is not None:
            if not isinstance(ex, dict):
                errs.append(f"{cid or i}: expect phải là object")
            else:
                if "exit_code" in ex and not isinstance(ex["exit_code"], int):
                    errs.append(f"{cid or i}: expect.exit_code phải là số nguyên")
                for k in ("stdout_contains", "stdout_not_contains"):
                    if k in ex and not (isinstance(ex[k], list) and all(isinstance(s, str) for s in ex[k])):
                        errs.append(f"{cid or i}: expect.{k} phải là danh sách chuỗi")
        if not ex and not str(c.get("manual_check", "")).strip():
            errs.append(f"{cid or i}: cần expect (kiểm được bằng máy) hoặc manual_check (mô tả điều người chạy phải quan sát)")
    return errs


def machine_checkable(case: dict) -> bool:
    ex = case.get("expect") or {}
    return any(k in ex for k in ("exit_code", "stdout_contains", "stdout_not_contains"))


def evaluate(case: dict, code: int, stdout: str, stderr: str = "") -> tuple[bool, str]:
    """So kết quả chạy thật với `expect`. Trả (đạt?, giải thích)."""
    ex = case.get("expect") or {}
    out = stdout + ("\n" + stderr if stderr else "")
    fails = []
    if "exit_code" in ex and code != ex["exit_code"]:
        fails.append(f"exit_code={code}, mong đợi {ex['exit_code']}")
    for s in ex.get("stdout_contains", []):
        if s not in out:
            fails.append(f"đầu ra thiếu '{s}'")
    for s in ex.get("stdout_not_contains", []):
        if s in out:
            fails.append(f"đầu ra không được chứa '{s}'")
    return (not fails, "; ".join(fails) or "khớp expect")
