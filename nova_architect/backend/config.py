"""
Nova Architect — Centralized Configuration
All environment variables are validated here at startup.
Import `settings` from this module instead of using os.getenv() directly.
"""

import os
from typing import Optional


class Settings:
    """Reads configuration from environment variables with sensible defaults."""

    def __init__(self):
        self.aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.aws_region: str = os.getenv("AWS_REGION", "us-east-1")
        self.nova_act_api_key: Optional[str] = os.getenv("NOVA_ACT_API_KEY")
        self.nova_act_headless: bool = os.getenv("NOVA_ACT_HEADLESS", "false").lower() == "true"
        self.nova_sonic_voice: str = os.getenv("NOVA_SONIC_VOICE", "Matthew")
        self.demo_mode: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
        self.cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:8000")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.database_url: str = os.getenv("DATABASE_URL", os.path.join(os.path.dirname(__file__), "..", "nova-architect.db"))

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate(self) -> list[str]:
        """Return a list of validation warnings (not errors — missing keys use defaults)."""
        warnings = []
        if not self.aws_access_key_id:
            warnings.append("AWS_ACCESS_KEY_ID not set — Bedrock/Nova Act calls will fail")
        if not self.aws_secret_access_key:
            warnings.append("AWS_SECRET_ACCESS_KEY not set")
        return warnings


settings = Settings()
