import importlib.util
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dependency_health", SCRIPTS / "token-reduce-dependency-health.py")
health = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = health
spec.loader.exec_module(health)


def test_headroom_freshness_uses_upstream_not_install_pin(monkeypatch):
    dep = next(dep for dep in health.CONDITIONAL_DEPENDENCIES if dep.name == "headroom")
    monkeypatch.setattr(health, "read_local_version", lambda _: (True, "headroom, version 0.39.1"))
    urls = []
    def fetch(url):
        urls.append(url)
        return {"info": {"version": "0.40.0"}}
    monkeypatch.setattr(health, "fetch_json", fetch)
    row = health.dependency_status(dep)
    assert row["state"] == "outdated"
    assert urls == ["https://pypi.org/pypi/headroom-ai/json"]
    assert "0.40.0" in row["update_hint"]


def test_pypi_missing_version_is_unknown(monkeypatch):
    dep = next(dep for dep in health.CONDITIONAL_DEPENDENCIES if dep.name == "headroom")
    monkeypatch.setattr(health, "read_local_version", lambda _: (True, "0.39.1"))
    monkeypatch.setattr(health, "fetch_json", lambda _: None)
    assert health.dependency_status(dep)["state"] == "unknown"


def test_headroom_explicit_install_and_setup_share_pin(monkeypatch):
    calls = []
    monkeypatch.setattr(health.shutil, "which", lambda name: "/fake/uv" if name == "uv" else None)
    monkeypatch.setattr(health, "run_install", lambda argv: (calls.append(argv) or (0, "ok", "")))
    actions = health.apply_updates([{"name": "headroom", "state": "outdated"}])
    assert calls[0][-1] == "headroom-ai[proxy]==0.40.0"
    assert actions[0]["status"] == "updated"
    assert "headroom-ai[proxy]==0.40.0" in (SCRIPTS / "setup.sh").read_text()


def test_rtk_update_does_not_pipe_unpinned_remote_script(monkeypatch):
    calls = []
    monkeypatch.setattr(health.shutil, "which", lambda name: "/fake/cargo" if name == "cargo" else None)
    monkeypatch.setattr(health, "run_install", lambda argv: (calls.append(argv) or (0, "ok", "")))
    health.apply_updates([{"name": "rtk", "state": "outdated"}])
    assert calls[0] == ["cargo", "install", "--force", "--git", "https://github.com/rtk-ai/rtk", "--tag", "v0.51.0", "--locked"]


def test_held_qmd_and_unqualified_headroom_never_install(monkeypatch):
    monkeypatch.setattr(health, "run_install", lambda _: (_ for _ in ()).throw(AssertionError("unqualified install")))
    actions = health.apply_updates([{"name": "qmd", "state": "outdated", "latest_version": "2.8.3"},
                                    {"name": "headroom", "state": "outdated", "latest_version": "0.41.0"}])
    assert [a["status"] for a in actions] == ["skipped", "skipped"]
