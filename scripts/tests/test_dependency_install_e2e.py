"""One filesystem/process installer flow; external installers only record argv."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parents[1]


def test_setup_and_update_keep_qmd_held_and_use_only_pinned_rtk(tmp_path):
    home = tmp_path / "home"
    binary = tmp_path / "bin"
    home.mkdir()
    binary.mkdir()
    # Whitelist ordinary filesystem tools; no host qmd/cargo/npm can escape in.
    for name in ["bash", "git", "tr", "head", "mkdir", "cp", "cat", "chmod",
                 "rm", "ln", "sha1sum", "cut", "uv"]:
        path = shutil.which(name)
        assert path, f"installer e2e requires {name}"
        (binary / name).symlink_to(path)
    install_log = tmp_path / "installs.log"
    forbidden = tmp_path / "forbidden.log"
    probes = {
        "cargo": 'printf "%s\\n" "$*" >> "$INSTALL_LOG"\n',
        "gh-axi": "exit 0\n",
        "chrome-devtools-axi": "exit 0\n",
        "curl": 'printf "curl\\n" >> "$FORBIDDEN_LOG"\nexit 97\n',
        "npm": 'printf "npm %s\\n" "$*" >> "$FORBIDDEN_LOG"\nexit 97\n',
        "bun": 'printf "bun %s\\n" "$*" >> "$FORBIDDEN_LOG"\nexit 97\n',
    }
    for name, body in probes.items():
        path = binary / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": str(binary),
           "INSTALL_LOG": str(install_log), "FORBIDDEN_LOG": str(forbidden),
           "UV_PYTHON": sys.executable, "UV_PYTHON_DOWNLOADS": "never", "UV_OFFLINE": "1",
           "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
           "TOKEN_REDUCE_SETUP_DELEGATE_SKILL": "0", "TOKEN_REDUCE_SETUP_TELEMETRY_PROMPT": "0",
           "TOKEN_REDUCE_INSTALL_EXTENDED_STACK": "0"}
    for name in ["CODEX_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "VIRTUAL_ENV"]:
        env.pop(name, None)
    setup = subprocess.run([str(binary / "bash"), str(SCRIPTS / "setup.sh")],
                           cwd=SCRIPTS.parent, env=env, capture_output=True, text=True, timeout=30)
    assert setup.returncode == 0, setup.stderr
    assert "candidate held" in setup.stdout
    settings = json.loads((home / ".claude/settings.json").read_text())
    assert len(settings["hooks"]["PreToolUse"]) == 4
    for entry in settings["hooks"]["PreToolUse"]:
        command = entry["hooks"][0]["command"]
        assert '$T' in command and '$?' in command and '$ec' in command
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == str(
        home / ".claude/hooks/token-reduce/token-reduce-update-check.sh")
    assert (home / ".claude/hooks/token-reduce/enforce-token-reduce-first.py").is_file()
    assert (home / ".codex/skills/token-reduce").resolve() == SCRIPTS.parent
    assert not (home / ".local/bin/qmd").exists()

    # Run the real update installer in a separate process, with explicit intake
    # results rather than contacting changing upstream version services.
    statuses = [{"name": "qmd", "state": "outdated", "latest_version": "2.8.3"},
                {"name": "rtk", "state": "missing", "latest_version": "0.51.0"},
                {"name": "headroom", "state": "outdated", "latest_version": "0.41.0"}]
    update = subprocess.run([sys.executable, "-c",
                            "import json,runpy,sys; m=runpy.run_path(sys.argv[1]); "
                            "print(json.dumps(m['apply_updates'](json.load(sys.stdin))))",
                            str(SCRIPTS / "token-reduce-dependency-health.py")],
                           input=json.dumps(statuses), env=env, capture_output=True, text=True, timeout=15)
    assert update.returncode == 0, update.stderr
    actions = {item["target"]: item for item in json.loads(update.stdout)}
    assert actions["qmd"]["status"] == actions["headroom"]["status"] == "skipped"
    assert actions["qmd"]["command"] == actions["headroom"]["command"] == "none"
    assert actions["rtk"]["status"] == "updated"
    assert [shlex.split(line) for line in install_log.read_text().splitlines()] == [
        ["install", "--git", "https://github.com/rtk-ai/rtk", "--tag", "v0.51.0", "--locked"],
        ["install", "--force", "--git", "https://github.com/rtk-ai/rtk", "--tag", "v0.51.0", "--locked"],
    ]
    assert not forbidden.exists(), forbidden.read_text() if forbidden.exists() else ""
