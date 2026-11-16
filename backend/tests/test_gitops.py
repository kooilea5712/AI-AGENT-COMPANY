import subprocess
from pathlib import Path

import pytest

from app import gitops
from app.gitops import GitError


def g(p, *a):
    return subprocess.run(["git", *a], cwd=p, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def test_init_and_commit_every_run_even_when_empty(tmp_path):
    gitops.init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("1")
    c1 = gitops.commit_all(tmp_path, "[studio] run 1")
    assert c1["files"] == 1 and not c1["empty"]
    c2 = gitops.commit_all(tmp_path, "[studio] run 2 (không đổi gì)")   # vẫn phải có commit: mỗi lần chạy đều có dấu vết
    assert c2["empty"] and c2["hash"] != c1["hash"]
    assert [x["subject"] for x in gitops.history(tmp_path)][:2] == ["[studio] run 2 (không đổi gì)", "[studio] run 1"]


def test_workspace_gets_own_branch_and_main_untouched(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    gitops.init_repo(ws)
    (ws / "x.py").write_text("print(1)")
    g(ws, "add", "-A"); g(ws, "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-m", "init")
    main = g(ws, "rev-parse", "--abbrev-ref", "HEAD")
    gitops.prepare_workspace(ws, "job-1")
    assert gitops.current_branch(ws) == "studio/job-1"
    (ws / "x.py").write_text("print(2)")
    gitops.commit_all(ws, "[studio] job-1 T1")
    assert g(ws, "show", f"{main}:x.py") == "print(1)"                  # nhánh gốc nguyên vẹn


def test_workspace_must_be_clean(tmp_path):
    ws = tmp_path / "proj"; ws.mkdir()
    gitops.init_repo(ws)
    (ws / "wip.txt").write_text("viec do", encoding="utf-8")
    with pytest.raises(GitError, match="chưa commit"):
        gitops.prepare_workspace(ws, "job-2")


def test_non_repo_folder_is_initialised_with_root_commit(tmp_path):
    ws = tmp_path / "plain"; ws.mkdir()
    (ws / "old.txt").write_text("co san", encoding="utf-8")
    note = gitops.prepare_workspace(ws, "job-3")
    assert "git init" in note and gitops.current_branch(ws) == "studio/job-3"
    assert "old.txt" in g(ws, "ls-tree", "-r", "--name-only", "main")


def test_subfolder_of_bigger_repo_rejected(tmp_path):
    outer = tmp_path / "outer"; (outer / "inner").mkdir(parents=True)
    gitops.init_repo(outer)
    with pytest.raises(GitError, match="BÊN TRONG"):
        gitops.prepare_workspace(outer / "inner", "job-4")


@pytest.mark.parametrize("bad", [Path.home(), Path(Path.home().anchor), Path("C:/Windows"), Path("C:/Program Files"), Path.home() / "AppData" / "Roaming"])
def test_dangerous_workspaces_refused(bad):
    with pytest.raises(GitError):
        gitops.check_workspace_allowed(bad)


def test_parse_path_strips_quotes_from_windows_copy_as_path(tmp_path):
    d = tmp_path / "VID COMMENT THREAD"
    d.mkdir()
    for raw in (f'"{d}"', f"'{d}'", f"  {d}  ", f"\u201c{d}\u201d"):
        assert gitops.parse_path(raw) == d
    with pytest.raises(GitError, match="đầy đủ"):
        gitops.parse_path("relative\\folder")                 # không bao giờ hiểu theo thư mục của backend
    with pytest.raises(GitError, match="Không tìm thấy"):
        gitops.parse_path(str(tmp_path / "khong-co"))
    with pytest.raises(GitError, match="Chưa nhập"):
        gitops.parse_path('  ""  ')


def test_any_project_folder_outside_the_studio_dir_is_allowed(tmp_path):
    # Thư mục project ở bất kỳ đâu đều dùng được (khác ổ, khác thư mục dự án); chỉ thư mục hệ thống bị chặn.
    other = tmp_path / "elsewhere" / "my-app"
    other.mkdir(parents=True)
    gitops.check_workspace_allowed(other)
    assert "studio/job-9" in (gitops.prepare_workspace(other, "job-9") and gitops.current_branch(other))
