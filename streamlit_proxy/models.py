from pydantic import BaseModel
from typing import Optional

class AppConfig(BaseModel):
    name: str
    path: str
    slug: str
    desired_port: Optional[int] = None
    run_by_default: bool = False
