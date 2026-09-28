from pathlib import Path

from ai_usage.paths import AppPaths, build_profile_env


def test_profile_home_is_inside_app_data(tmp_path: Path):
    paths = AppPaths(tmp_path)

    assert paths.profile_home("claude-work") == tmp_path / "profiles" / "claude-work" / "home"


def test_build_profile_env_sets_isolated_home(tmp_path: Path):
    home = tmp_path / "profiles" / "claude-work" / "home"
    env = build_profile_env(home, {"HOME": "/home/user", "PATH": "/usr/bin"})

    assert env["HOME"] == str(home)
    assert env["XDG_CONFIG_HOME"] == str(home / ".config")
    assert env["XDG_DATA_HOME"] == str(home / ".local" / "share")
    assert env["XDG_STATE_HOME"] == str(home / ".local" / "state")
    assert env["XDG_CACHE_HOME"] == str(home / ".cache")
    assert env["PATH"] == "/usr/bin"
