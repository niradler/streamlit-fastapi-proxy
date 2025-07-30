import json
from typing import List, Optional

from .config import APP_REGISTRY_PATH
from .models import AppConfig


class AppRegistry:
    def __init__(self):
        self._load()

    def _load(self):
        try:
            with open(APP_REGISTRY_PATH, "r") as f:
                self.apps = [AppConfig(**entry) for entry in json.load(f)]
        except FileNotFoundError:
            self.apps = []

    def save(self):
        with open(APP_REGISTRY_PATH, "w") as f:
            json.dump([app.model_dump() for app in self.apps], f, indent=2)

    def get_all(self) -> List[AppConfig]:
        return self.apps

    def register(self, app: AppConfig):
        self.apps.append(app)
        self.save()

    def remove(self, slug: str):
        self.apps = [a for a in self.apps if a.slug != slug]
        self.save()

    def find(self, slug: str) -> Optional[AppConfig]:
        return next((a for a in self.apps if a.slug == slug), None)
