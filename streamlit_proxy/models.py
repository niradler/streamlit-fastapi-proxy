from typing import Optional

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Configuration for a Streamlit application."""

    name: str = Field(..., description="Display name of the application")
    path: str = Field(..., description="Absolute path to the Streamlit app file")
    slug: str = Field(..., description="Unique identifier for the application")
    desired_port: Optional[int] = Field(
        None, description="Preferred port for the application"
    )
    run_by_default: bool = Field(
        False, description="Whether to start this app by default"
    )
