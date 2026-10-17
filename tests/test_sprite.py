from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from procbox.core.models import AppInfo
from procbox.ui.sprite import AppSprite


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


def make_sprite() -> AppSprite:
    app = AppInfo(
        app_id="/Applications/Test.app",
        name="Test",
        pids=(10, 11),
        bundle_path="/Applications/Test.app",
    )
    sprite = AppSprite(app)
    sprite.place(120.0, 240.0)
    return sprite


def test_sprite_layers_lower_icons_on_top(qapp: QApplication) -> None:
    sprite = make_sprite()
    assert sprite.zValue() == sprite.y() + sprite.icon_size

    sprite.place(120.0, 340.0)
    assert sprite.zValue() == sprite.y() + sprite.icon_size


def test_sprite_dies_and_revives(qapp: QApplication) -> None:
    sprite = make_sprite()

    sprite.die()
    assert not sprite.is_alive
    assert sprite._gray_pixmap is not None

    sprite.revive()
    assert sprite.is_alive
    assert sprite._gray_pixmap is None
