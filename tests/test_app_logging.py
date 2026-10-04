"""Tests for app/app_logging.py: the app's one logging level/on-off knob,
tied to the admin Settings view's mode and a separate "enable logging"
toggle (app/models.py: AppSettings.mode, AppSettings.logging_enabled).
"""

from __future__ import annotations

import logging

from app.app_logging import configure_logging


def test_disabling_logging_blocks_even_critical_records():
    configure_logging("production", enabled=False)
    assert not logging.getLogger("app.test").isEnabledFor(logging.CRITICAL)


def test_re_enabling_logging_restores_the_configured_level():
    configure_logging("production", enabled=False)
    configure_logging("debug", enabled=True)
    logger = logging.getLogger("app.test")
    assert logger.isEnabledFor(logging.DEBUG)


def test_production_mode_is_info_level_when_enabled():
    configure_logging("debug", enabled=True)  # start from DEBUG to prove it changes
    configure_logging("production", enabled=True)
    logger = logging.getLogger("app.test")
    assert logger.isEnabledFor(logging.INFO)
    assert not logger.isEnabledFor(logging.DEBUG)
