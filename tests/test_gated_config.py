from pydantic import SecretStr

from src.utils.config import Settings


def _s(**over):
    base = dict(anthropic_api_key=SecretStr("sk-ant-test"))
    base.update(over)
    return Settings(**base)


def test_gate_defaults():
    s = _s()
    assert s.match_gate_threshold == 40
    assert s.gate_scrape_cap_mult == 3
    assert s.browserbase_max_sessions == 8


def test_gate_overrides():
    s = _s(match_gate_threshold=55, gate_scrape_cap_mult=4, browserbase_max_sessions=12)
    assert (s.match_gate_threshold, s.gate_scrape_cap_mult, s.browserbase_max_sessions) == (55, 4, 12)
