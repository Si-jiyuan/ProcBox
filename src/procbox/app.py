from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from procbox.platforms.base import PlatformError
from procbox.platforms.factory import create_platform_adapter
from procbox.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ProcBox")
    app.setApplicationDisplayName("ProcBox")
    app.setOrganizationName("ProcBox")

    try:
        adapter = create_platform_adapter()
    except PlatformError as exc:
        print(f"ProcBox: {exc}", file=sys.stderr)
        return 1

    window = MainWindow(adapter)
    window.show()
    return app.exec()
