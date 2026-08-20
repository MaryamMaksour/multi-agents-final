"""Shared base for controllers.

Same role as mini_rag's BaseController: settings and shared clients are
reached through the instance, not through module globals, so a
controller can be constructed against a different configuration in a
test.
"""
from __future__ import annotations

from helpers.config import Settings, get_settings


class BaseController:

    def __init__(self, config: Settings | None = None):
        self.app_settings = config or get_settings()
