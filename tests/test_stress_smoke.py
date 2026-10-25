"""The stress script runs in the normal suite (small sizes) so it cannot rot, and its safety properties are checked."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_script():
    spec = importlib.util.spec_from_file_location("stress_test", ROOT / "scripts" / "stress_test.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quick_stress_run_passes_every_gate(tmp_path):
    """Engine scale curve, a 300-message burst (order, duplicates, latency), abuse (flood, retries, malformed, groups) and a short soak."""
    out = subprocess.run([sys.executable, "scripts/stress_test.py", "all", "--quick", "--json", str(tmp_path / "r.json")],
                         capture_output=True, text=True, cwd=ROOT, timeout=240)
    results = json.loads((tmp_path / "r.json").read_text())
    failed = [g for g, ok in results["gates"].items() if not ok]
    assert out.returncode == 0 and not failed, f"failed gates: {failed}\n{out.stdout[-3500:]}"
    assert len(results["gates"]) >= 19
    burst = results["metrics"]["burst"]
    assert burst["throughput_msg_per_s"] > 0 and burst["ack_p95_ms"] < 1500                  # the webhook acknowledges fast whatever the work


def test_the_stress_bot_can_never_reach_a_real_waha_or_the_real_inbox():
    """The harness points the bot at its own fake WAHA on localhost and a throwaway inbox, whatever the developer's .env says."""
    st = load_script()
    import os
    os.environ["WAHA_URL"] = "https://real-waha.example.com"           # a real-looking value in the caller's environment must be overridden
    os.environ["UNMATCHED_PATH"] = "data/unmatched.jsonl"
    try:
        waha = st.FakeWaha()
        bot = st.Bot(waha)
        assert bot.env["WAHA_URL"] == f"http://127.0.0.1:{waha.port}" and bot.env["WAHA_API_KEY"] == "stress"
        assert bot.env["UNMATCHED_PATH"].startswith(bot.tmp) and "data/unmatched" not in bot.env["UNMATCHED_PATH"]
        assert bot.port != waha.port
    finally:
        os.environ.pop("WAHA_URL", None)
        os.environ.pop("UNMATCHED_PATH", None)


def test_message_mix_checks_are_correct():
    st = load_script()
    for user in (0, 7, 123):
        for j in range(10):
            text, check = st.make_message(user, j)
            if "+" in text:
                a, b = map(int, text.split("+"))
                assert check(f"🧮 {text} = *{a + b}*") and not check(f"🧮 {text} = *{a + b + 1}*")
    assert st.make_message(1, 1)[1]("pong 🏓") and not st.make_message(1, 1)[1]("pong")


def test_percentiles():
    st = load_script()
    assert st.pct([], .95) == 0 and st.pct([5], .5) == 5 and st.pct(list(range(100)), .95) == 95
