"""Keep host session policy out of unit/integration fixtures."""
import pytest


@pytest.fixture(autouse=True)
def isolated_session_policy(monkeypatch, tmp_path):
    # Tests that exercise explicit configuration override this fixture themselves.
    monkeypatch.setenv("TOKEN_REDUCE_CONFIG_PATH", str(tmp_path / "absent-host-config.json"))
    monkeypatch.delenv("TOKEN_REDUCE_DISCOVERY_MODE", raising=False)
    for name in ("RTK", "SEARCH_QMD", "MEMORY", "HEADROOM_COMPRESS", "HEADROOM_RETRIEVE", "MCP_TRIM", "CONTEXT_AUDIT"):
        monkeypatch.delenv(f"TOKEN_REDUCE_LAYER_{name}", raising=False)
