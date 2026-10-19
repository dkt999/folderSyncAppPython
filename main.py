#!/usr/bin/env python3
"""FolderSync entry point (Python/Qt port of FolderSyncApp C#)."""
import argparse
import sys

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from qfluentwidgets import Theme, setTheme

from foldersync.ui.main_window import MainWindow

_SINGLE_INSTANCE_KEY = "foldersync-single-instance"


def _notify_existing_instance() -> bool:
    """Return True if another instance is already running (and notified)."""
    socket = QLocalSocket()
    socket.connectToServer(_SINGLE_INSTANCE_KEY)
    if socket.waitForConnected(500):
        # Ask the running instance to show its window
        socket.write(b"show")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="FolderSync - scheduled folder sync")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start minimized to system tray (for autostart)",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("FolderSync")
    app.setOrganizationName("FolderSyncApp")
    app.setQuitOnLastWindowClosed(False)  # closing window keeps tray running
    setTheme(Theme.AUTO)

    # -- single instance: exit if another copy is already running --
    if _notify_existing_instance():
        QMessageBox.information(
            None, "FolderSync", "FolderSync is already running."
        )
        return 0
    # Clean up stale socket from a crashed previous run, then listen
    QLocalServer.removeServer(_SINGLE_INSTANCE_KEY)
    instance_server = QLocalServer()
    if not instance_server.listen(_SINGLE_INSTANCE_KEY):
        QMessageBox.warning(
            None, "FolderSync", "Could not enforce single instance."
        )
        return 1

    window = MainWindow()
    if not args.minimized:
        window.show()

    # When a second copy is launched, bring this window forward
    def _on_new_connection() -> None:
        sock = instance_server.nextPendingConnection()
        if sock is not None:
            sock.waitForReadyRead(500)
            if bytes(sock.readAll()).strip() == b"show":
                window.show()
                window.raise_()
                window.activateWindow()
            sock.disconnectFromServer()

    instance_server.newConnection.connect(_on_new_connection)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
