import httpx
import pytest

from app import context, settings
from app.db import DB
from app.jobs import machine as m
from app.llm.client import BudgetExceeded, LLMClient


@pytest.fixture
def orch(tmp_path, monkeypatch):
    o = m.Orchestrator(DB(tmp_path / "t.sqlite"), object(), tmp_path / "jobs", tmp_path / "l.md")
    # Gắn móc cho test này và gỡ sau đó (móc là thuộc tính cấp lớp, dùng chung toàn tiến trình).
    monkeypatch.setattr(LLMClient, "budget_guard", o.check_budget)
    monkeypatch.setattr(LLMClient, "usage_sink", o.on_usage)
    return o


def fake_post(monkeypatch, usage=None, model="m", counter=None):
    async def post(base_url, body, headers):
        if counter is not None:
            counter.append(body["model"])
        return httpx.Response(200, json={"model": model, "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                                         "usage": usage or {"prompt_tokens": 1000, "completion_tokens": 500}})
    monkeypatch.setattr(LLMClient, "_post", staticmethod(post))


def with_key():
    settings.update({"connections": {"anthropic": {"api_key": "sk-ant-test-0000"}}})


def test_economy_tier_downgrades_claude_only():
    full = {r: [c["model"] for c in settings.candidates(r, tier="full")] for r in ("director", "qa_author", "qa_runner")}
    eco = {r: [c["model"] for c in settings.candidates(r, tier="economy")] for r in ("director", "qa_author", "qa_runner")}
    assert full["director"][0] == "claude-opus-5-5" and eco["director"][0] == "claude-sonnet-5-5"      # Opus -> Sonnet
    assert full["qa_author"][0] == "claude-sonnet-5-5" and eco["qa_author"][0] == "claude-haiku-5-5"    # Sonnet -> Haiku
    assert eco["qa_runner"][0] == "claude-haiku-5-5"                                                    # Haiku không có bậc thấp hơn: giữ
    assert full["director"][1:] == eco["director"][1:]                                                  # OmniRoute/Ollama giữ nguyên


def test_downgrade_table_is_editable_and_tier_comes_from_context():
    settings.update({"downgrade": {"claude-opus-5-5": "claude-haiku-5-5"}})
    context.tier_var.set("economy")
    try:
        assert settings.candidates("director")[0]["model"] == "claude-haiku-5-5"
    finally:
        context.tier_var.set("full")
    assert settings.candidates("director")[0]["model"] == "claude-opus-5-5"


def test_settings_validate_tier_budget_prices():
    for bad in ({"default_tier": "vip"}, {"job_budget_usd": -1}, {"prices": {"x": {"in": "abc", "out": 1}}}, {"prices": {"x": {"in": -1, "out": 1}}}):
        with pytest.raises(ValueError):
            settings.update(bad)
    s = settings.update({"default_tier": "economy", "job_budget_usd": 2.5, "prices": {"claude-opus-5-5": {"in": 15, "out": 75}}})
    assert s["default_tier"] == "economy" and s["job_budget_usd"] == 2.5 and s["prices"]["claude-opus-5-5"]["out"] == 75


def test_job_takes_default_tier_and_rejects_unknown(orch):
    assert orch.get(orch.create_job("a"))["tier"] == "full"
    settings.update({"default_tier": "economy"})
    assert orch.get(orch.create_job("b"))["tier"] == "economy"
    assert orch.get(orch.create_job("c", tier="full"))["tier"] == "full"
    with pytest.raises(ValueError):
        orch.create_job("d", tier="vip")


async def test_cost_counted_from_user_prices_and_economy_uses_cheaper_model(orch, monkeypatch):
    with_key()
    settings.update({"prices": {"claude-opus-5-5": {"in": 15, "out": 75}, "claude-sonnet-5-5": {"in": 3, "out": 15}}})
    served = []
    fake_post(monkeypatch, counter=served)
    full = orch.create_job("quan trọng", tier="full")
    eco = orch.create_job("tiết kiệm", tier="economy")
    for jid in (full, eco):
        context.job_id_var.set(jid)
        context.tier_var.set(orch.get(jid)["tier"])
        await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    assert served == ["claude-opus-5-5", "claude-sonnet-5-5"]
    cf, ce = orch.job_cost(full), orch.job_cost(eco)
    assert cf["tokens_in"] == 1000 and cf["tokens_out"] == 500
    assert cf["cost"] == pytest.approx((1000 * 15 + 500 * 75) / 1e6)        # = 0.0525 USD
    assert ce["cost"] == pytest.approx((1000 * 3 + 500 * 15) / 1e6) and ce["cost"] < cf["cost"] / 4


async def test_unpriced_paid_model_is_flagged_not_invented_and_local_is_free(orch, monkeypatch):
    with_key()                                                              # có khoá nhưng CHƯA nhập đơn giá
    fake_post(monkeypatch)
    jid = orch.create_job("x")
    context.job_id_var.set(jid)
    await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    c = orch.job_cost(jid)
    assert c["cost"] == 0 and c["unpriced_calls"] == 1 and c["by_model"][0]["priced"] == 0     # biết là chưa tính được, không bịa giá
    settings.update({"connections": {"anthropic": {"enabled": False}}})                         # lượt sau rơi xuống OmniRoute (local)
    await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    c = orch.job_cost(jid)
    assert c["calls"] == 2 and c["cost"] == 0 and c["unpriced_calls"] == 1                      # local tính 0 và không bị coi là "chưa có giá"


async def test_budget_blocks_before_the_next_call_and_can_be_raised(orch, monkeypatch):
    with_key()
    settings.update({"prices": {"claude-opus-5-5": {"in": 15, "out": 75}}})
    calls = []
    fake_post(monkeypatch, counter=calls)
    jid = orch.create_job("x", budget=0.05)
    context.job_id_var.set(jid)
    await LLMClient().chat("director", [{"role": "user", "content": "hi"}])      # 0.0525 > 0.05: lượt này chạy, lượt sau bị chặn
    with pytest.raises(BudgetExceeded, match="hạn mức"):
        await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    assert len(calls) == 1                                                       # KHÔNG gọi mạng thêm lượt nào
    orch.set_budget(jid, 1.0)
    await LLMClient().chat("director", [{"role": "user", "content": "hi"}])      # nâng hạn mức thì chạy tiếp
    assert len(calls) == 2
    orch.set_budget(jid, 0)                                                      # 0 = không giới hạn
    await LLMClient().chat("director", [{"role": "user", "content": "hi"}])
    with pytest.raises(m.InvalidAction):
        orch.set_budget(jid, -1)


async def test_global_default_budget_applies_and_warns_at_80_percent(orch, monkeypatch):
    with_key()
    settings.update({"prices": {"claude-opus-5-5": {"in": 15, "out": 75}}, "job_budget_usd": 0.06})
    fake_post(monkeypatch)
    jid = orch.create_job("x")                                                   # không đặt riêng: lấy mặc định 0.06
    context.job_id_var.set(jid)
    await LLMClient().chat("director", [{"role": "user", "content": "hi"}])      # 0.0525 = 87% của 0.06
    assert orch.job_cost(jid)["budget"] == 0.06
    assert len(orch.db.query("SELECT 1 FROM events WHERE job_id=? AND kind='cost' AND message LIKE '%80%%'", (jid,))) == 1


async def test_over_budget_job_is_blocked_with_clear_reason(orch, monkeypatch):
    """Máy trạng thái: lỗi hạn mức từ LLMClient dừng job với lý do dễ hiểu (không phải 'lỗi bất ngờ')."""
    with_key()
    settings.update({"prices": {"claude-opus-5-5": {"in": 15, "out": 75}}})
    fake_post(monkeypatch)
    orch.llm = LLMClient()
    jid = orch.create_job("x", budget=0.01)
    context.job_id_var.set(jid)
    await LLMClient().chat("director", [{"role": "user", "content": "đốt hạn mức"}])     # đã quá 0.01
    await orch.run(jid)                                                                  # bước intake gọi Giám đốc -> bị chặn
    j = orch.get(jid)
    assert j["state"] == m.BLOCKED and "hạn mức chi phí" in j["error"]


def test_usage_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    import importlib
    import app.main as main
    importlib.reload(main)
    monkeypatch.setattr(main.orch, "schedule", lambda job_id: None)
    c = TestClient(main.app)
    jid = c.post("/jobs", data={"description": "x", "tier": "economy", "budget": "1.5"}).json()["id"]
    u = c.get(f"/jobs/{jid}/usage").json()
    assert u["tier"] == "economy" and u["budget"] == 1.5 and u["cost"] == 0
    assert c.put(f"/jobs/{jid}/budget", json={"usd": 3}).json()["budget"] == 3
    assert c.put(f"/jobs/{jid}/budget", json={"usd": -1}).status_code == 422
    assert c.post("/jobs", data={"description": "x", "tier": "vip"}).status_code == 422
    assert c.post("/jobs", data={"description": "x", "budget": "abc"}).status_code == 422
    assert c.get(f"/jobs/{jid}").json()["usage"]["budget"] == 3
    s = c.put("/settings", json={"default_tier": "economy", "job_budget_usd": 2, "prices": {"claude-opus-5-5": {"in": 15, "out": 75}}}).json()
    assert s["default_tier"] == "economy" and s["prices"]["claude-opus-5-5"]["in"] == 15
