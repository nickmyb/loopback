from loopback.config import Settings
from loopback.llm import build_request, sanitize_proxy_env
from loopback.pricing import cache_hit_rate, estimate_usd

MSGS = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


def test_official_profile_adds_caching_and_effort() -> None:
    s = Settings.from_env({})
    req = build_request(s, system="sys", messages=MSGS, tools=[], max_tokens=100, effort="low")
    assert req["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"] == {"effort": "low"}
    assert "tools" not in req  # 空工具列表不发


def test_compatible_profile_sends_only_portable_fields() -> None:
    s = Settings.from_env({"ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"})
    req = build_request(s, system="sys", messages=MSGS, tools=[{"name": "x"}], max_tokens=100)
    assert set(req) == {"model", "max_tokens", "system", "messages", "tools"}


def test_unsupported_all_proxy_is_dropped_but_http_proxies_kept() -> None:
    env = {
        "ALL_PROXY": "socks://127.0.0.1:7890/",
        "all_proxy": "socks://127.0.0.1:7890/",
        "HTTPS_PROXY": "http://127.0.0.1:7890/",
    }
    assert sanitize_proxy_env(env) == ["ALL_PROXY", "all_proxy"]
    assert env == {"HTTPS_PROXY": "http://127.0.0.1:7890/"}
    keep = {"ALL_PROXY": "http://127.0.0.1:7890/"}
    assert sanitize_proxy_env(keep) == [] and "ALL_PROXY" in keep


def test_pricing_and_cache_rate() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 1_000_000}
    assert estimate_usd("claude-opus-5-5", usage) == 4.0 + 0.2
    assert estimate_usd("some-unknown-model", usage) is None
    assert cache_hit_rate(usage) == 0.5
