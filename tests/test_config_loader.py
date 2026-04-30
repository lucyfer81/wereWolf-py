import pytest
from pathlib import Path

from src.config_loader import GameConfig, RoleConfig, load_config, render_template, validate_config


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestLoadConfig:
    def test_load_8p_config(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert config.total_players == 8

    def test_roles_parsed(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert "werewolf" in config.roles
        assert "villager" in config.roles
        assert "seer" in config.roles
        assert "guard" in config.roles
        assert config.roles["werewolf"].count == 3
        assert config.roles["seer"].count == 1
        assert config.roles["guard"].count == 1
        assert config.roles["villager"].count == 3

    def test_voting_styles_parsed(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert "conservative" in config.voting_styles
        assert "pressure" in config.voting_styles

    def test_style_assignment_parsed(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert config.style_assignment[1] == "conservative"
        assert config.style_assignment[4] == "pressure"

    def test_prompts_parsed(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert "system_header" in config.prompts
        assert "speech_task" in config.prompts

    def test_settings_parsed(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert config.settings["llm_timeout"] == 60

    def test_role_fields(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        wolf = config.roles["werewolf"]
        assert wolf.team == "werewolves"
        assert wolf.night_action is True
        assert wolf.shared_memory is True
        assert wolf.night_priority == 1
        assert wolf.role_info_template
        assert wolf.night_action_template

    def test_role_on_death_template_default_none(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        assert config.roles["villager"].on_death_template is None

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config(Path("nonexistent.yaml"))


class TestRenderTemplate:
    def test_simple_var(self):
        result = render_template("hello {{ name }}", name="world")
        assert result == "hello world"

    def test_list_join(self):
        result = render_template("{{ items | join(', ') }}", items=["a", "b", "c"])
        assert result == "a, b, c"

    def test_conditional(self):
        tpl = "{% if is_wolf %}你是狼人{% else %}你是村民{% endif %}"
        assert "狼人" in render_template(tpl, is_wolf=True)
        assert "村民" in render_template(tpl, is_wolf=False)


class TestValidateConfig:
    def test_valid_8p(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        errors = validate_config(config)
        assert errors == []

    def test_role_count_mismatch(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        config.total_players = 99
        errors = validate_config(config)
        assert any("角色人数" in e for e in errors)

    def test_no_werewolf_team(self):
        config = load_config(FIXTURE_DIR / "default-8p.yaml")
        config.roles = {k: v for k, v in config.roles.items() if v.team != "werewolves"}
        errors = validate_config(config)
        assert any("狼人" in e for e in errors)


def test_load_9p_config():
    config = load_config(FIXTURE_DIR / "classic-9p.yaml")
    assert config.total_players == 9
    assert "seer" in config.roles
    assert "witch" in config.roles
    assert "guard" in config.roles
    assert config.roles["werewolf"].count == 3
    assert config.roles["seer"].night_action is True
    assert config.roles["guard"].night_action is True
    assert config.roles["guard"].night_priority == 3
    assert config.roles["witch"].night_priority == 4
    errors = validate_config(config)
    assert errors == []
