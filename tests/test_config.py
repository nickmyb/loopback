from pathlib import Path

import pytest

from loopback.config import DEFAULT_MODEL, ConfigError, Settings


def test_defaults_are_official_claude(tmp_path: Path) -> None:
    s = Settings.from_env({"LOOPBACK_HOME": str(tmp_path)})
    assert s.model == DEFAULT_MODEL
    assert s.base_url is None
    assert s.home == tmp_path.resolve()
    assert s.profile.official and s.profile.vision and s.profile.server_tools
    assert s.provider == "Anthropic 官方"


def test_explicit_official_base_url_keeps_official_profile() -> None:
    s = Settings.from_env({"ANTHROPIC_BASE_URL": "https://api.anthropic.com"})
    assert s.profile.official


def test_compatible_provider_turns_claude_only_features_off() -> None:
    s = Settings.from_env(
        {"ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic", "MODEL_ID": "deepseek-chat"}
    )
    assert s.model == "deepseek-chat"
    assert s.profile.official is False
    assert s.profile.vision is False
    assert s.profile.server_tools is False
    assert s.provider == "api.deepseek.com"


def test_capability_can_be_turned_on_per_flag() -> None:
    s = Settings.from_env(
        {"ANTHROPIC_BASE_URL": "https://api.moonshot.cn/anthropic", "LOOPBACK_VISION": "1"}
    )
    assert s.profile.vision is True
    assert s.profile.server_tools is False


@pytest.mark.parametrize(
    "env",
    [
        {"LOOPBACK_EFFORT": "ultra"},
        {"LOOPBACK_LOG_LEVEL": "LOUD"},
        {"LOOPBACK_VISION": "maybe"},
    ],
)
def test_invalid_values_raise_config_error(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_role_models_come_from_env_and_fall_back_to_model_id() -> None:
    s = Settings.from_env(
        {"MODEL_ID": "base", "LOOPBACK_TEACHER_MODEL": "teach", "LOOPBACK_TA_MODEL": ""}
    )
    assert s.model_for("teacher") == "teach"
    assert s.model_for("ta") == "base" and s.model_for("interviewer") == "base"  # 空值不算
