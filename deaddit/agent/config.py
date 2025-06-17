"""
Agent configuration management.
"""

import json
from typing import Any, Optional

from deaddit.models import Setting


class AgentConfig:
    """Centralized agent configuration management"""

    DEFAULT_CONFIG = {
        "global_settings": {
            "max_agents_concurrent": 10,
            "min_cycle_interval": 5,
            "max_cycle_interval": 30,
            "rate_limit_delay": 1.0,
            "max_daily_posts_per_agent": 3,
            "max_daily_comments_per_agent": 15,
        },
        "personality_defaults": {
            "engagement_threshold": 0.6,
            "response_probability": 0.8,
            "post_creation_rate": 0.1,
            "mood_change_probability": 0.1,
        },
        "content_generation": {
            "min_comment_length": 10,
            "max_comment_length": 500,
            "min_post_length": 50,
            "max_post_length": 2000,
            "temperature_range": [0.6, 1.2],
        },
    }

    @classmethod
    def get_config(cls, key: Optional[str] = None) -> Any:
        """Get agent configuration from settings or defaults"""
        config_json = Setting.get_value("agent_config")

        if config_json:
            try:
                config = json.loads(config_json)
            except (json.JSONDecodeError, TypeError):
                config = cls.DEFAULT_CONFIG.copy()
        else:
            config = cls.DEFAULT_CONFIG.copy()

        if key:
            return config.get(key, cls.DEFAULT_CONFIG.get(key))

        return config

    @classmethod
    def update_config(cls, updates: dict[str, Any]) -> None:
        """Update agent configuration"""
        current_config = cls.get_config()
        current_config.update(updates)

        Setting.set_value(
            "agent_config", json.dumps(current_config), "Agent system configuration"
        )

    @classmethod
    def get_personality_default(cls, key: str, default: Any = None) -> Any:
        """Get a personality default value"""
        personality_config = cls.get_config("personality_defaults")
        return personality_config.get(key, default)

    @classmethod
    def get_global_setting(cls, key: str, default: Any = None) -> Any:
        """Get a global setting value"""
        global_config = cls.get_config("global_settings")
        return global_config.get(key, default)
