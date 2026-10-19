#!/usr/bin/env python3
"""Diem vao app FolderSync (port Python/Qt cua FolderSyncApp C#)."""
import argparse
import sys

from PyQt6.QtWidgets import QApplication

from qfluentwidgets import Theme, setTheme

from foldersync.ui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="FolderSync - dong bo thu muc theo lich")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Khoi dong an xuong khay he thong (dung cho tu khoi dong)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("FolderSync")
    app.setOrganizationName("FolderSyncApp")
    app.setQuitOnLastWindowClosed(False)  # dong cua so van chay nen o tray
    setTheme(Theme.AUTO)

    window = MainWindow()
    if not args.minimized:
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
