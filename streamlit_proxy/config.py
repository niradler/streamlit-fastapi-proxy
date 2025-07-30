import os
from typing import Final

# Configuration constants
APP_REGISTRY_PATH: Final[str] = os.getenv("APP_REGISTRY_PATH", "app_registry.json")
STARTING_PORT: Final[int] = int(os.getenv("STARTING_PORT", "8503"))
MAX_PORT: Final[int] = int(os.getenv("MAX_PORT", "8550"))

# Validate configuration
if STARTING_PORT >= MAX_PORT:
    raise ValueError(
        f"STARTING_PORT ({STARTING_PORT}) must be less than MAX_PORT ({MAX_PORT})"
    )

if STARTING_PORT < 1024 or MAX_PORT > 65535:
    raise ValueError("Ports must be between 1024 and 65535")
