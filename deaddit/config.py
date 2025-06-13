"""Configuration management for Deaddit.

This module handles loading configuration from the database with fallback
to environment variables. Only API_TOKEN remains as an environment variable.
"""

import os
from typing import Optional

from deaddit.models import Setting


class Config:
    """Configuration manager that loads from database with environment fallbacks."""

    # Default values for configuration
    DEFAULTS = {
        "OPENAI_API_URL": "http://localhost/v1",
        "OPENAI_KEY": "your_openrouter_api_key",
        "OPENAI_MODEL": "llama3",
        "MODELS": "llama3,gpt-3.5-turbo,gpt-4,claude-3-haiku,mistral-7b",
        "API_BASE_URL": "http://localhost:5000",
        "SECRET_KEY": "dev-secret-key-change-in-production",
        "FLASK_ENV": "development",
        "FLASK_DEBUG": "True",
        "DEFAULT_DATA_LOADED": "false",
    }

    # Descriptions for each setting
    DESCRIPTIONS = {
        "OPENAI_API_URL": "Base URL for AI API service",
        "OPENAI_KEY": "API authentication key for AI service",
        "OPENAI_MODEL": "Default AI model to use for content generation",
        "MODELS": "Comma-separated list of available AI models",
        "API_BASE_URL": "Base URL for the application API",
        "SECRET_KEY": "Flask secret key for session management",
        "FLASK_ENV": "Flask environment (development/production)",
        "FLASK_DEBUG": "Enable Flask debug mode (True/False)",
        "DEFAULT_DATA_LOADED": "Whether default subdeaddits and users have been loaded",
    }

    @classmethod
    def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a configuration value.

        Priority order:
        1. Database setting (if available)
        2. Environment variable (as fallback)
        3. Default value from DEFAULTS
        4. Provided default parameter
        """
        # Special case: API_TOKEN always comes from environment
        if key == "API_TOKEN":
            return os.environ.get(key)

        try:
            # Try to get from database first
            db_value = Setting.get_value(key)
            if db_value is not None:
                return db_value
        except Exception:
            # Database might not be initialized yet, fall back to env
            pass

        # Fall back to environment variable
        env_value = os.environ.get(key)
        if env_value is not None:
            return env_value

        # Fall back to default value
        default_value = cls.DEFAULTS.get(key)
        if default_value is not None:
            return default_value

        return default

    @classmethod
    def set(cls, key: str, value: str) -> None:
        """Set a configuration value in the database."""
        if key == "API_TOKEN":
            raise ValueError(
                "API_TOKEN cannot be set in database, use environment variable"
            )

        description = cls.DESCRIPTIONS.get(key)
        Setting.set_value(key, value, description)

    @classmethod
    def get_all_settings(cls) -> dict:
        """Get all configuration settings with their current values."""
        settings = {}

        # Get all defined keys
        for key in cls.DEFAULTS.keys():
            settings[key] = {
                "value": cls.get(key),
                "description": cls.DESCRIPTIONS.get(key, ""),
                "source": cls._get_source(key),
            }

        # Add API_TOKEN info (but not the actual value for security)
        api_token = os.environ.get("API_TOKEN")
        settings["API_TOKEN"] = {
            "value": "***set***" if api_token else "***not set***",
            "description": "Bearer token for protecting /api/ingest endpoints (environment variable only)",
            "source": "environment",
        }

        return settings

    @classmethod
    def _get_source(cls, key: str) -> str:
        """Determine the source of a configuration value."""
        if key == "API_TOKEN":
            return "environment"

        try:
            db_value = Setting.get_value(key)
            if db_value is not None:
                return "database"
        except Exception:
            pass

        env_value = os.environ.get(key)
        if env_value is not None:
            return "environment"

        if key in cls.DEFAULTS:
            return "default"

        return "none"

    @classmethod
    def initialize_defaults(cls) -> None:
        """Initialize database with default values if not already set."""
        try:
            for key, default_value in cls.DEFAULTS.items():
                # Only set if not already in database
                if Setting.get_value(key) is None:
                    description = cls.DESCRIPTIONS.get(key)
                    Setting.set_value(key, default_value, description)
        except Exception:
            # Database might not be ready yet
            pass

    @classmethod
    def is_configured(cls) -> bool:
        """Check if the application has been configured (has settings in database)."""
        try:
            # Check if we have any settings in the database
            setting_count = Setting.query.count()
            return setting_count > 0
        except Exception:
            # Database might not be ready yet
            return False
