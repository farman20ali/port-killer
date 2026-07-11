"""
notify.py -- Zero-dependency desktop notification helper for kport.

Sends a desktop notification on state-change events in watch mode.
Uses platform-native fallbacks so no new dependencies are required:

- Linux   : notify-send (libnotify, almost universally installed)
- macOS   : osascript (AppleScript, always available)
- Windows : PowerShell toast notification (Windows 10+)

All notification failures are silently swallowed — a missing notification
must NEVER crash the watcher or block the main operation.

Usage::

    from kport.notify import notify
    notify("kport", "Port 8080 is now free")
"""

from __future__ import annotations

import platform
import shutil
import subprocess


def notify(title: str, message: str) -> None:
    """Fire a best-effort OS desktop notification.

    Non-fatal: all errors are caught and silently ignored.
    The function returns immediately after launching the notification;
    it does not wait for the user to dismiss it.
    """
    try:
        _dispatch(title, message)
    except Exception:
        pass  # Notification failure is always non-fatal


def _dispatch(title: str, message: str) -> None:
    """Route to the appropriate platform backend."""
    system = platform.system()
    if system == "Linux":
        _notify_linux(title, message)
    elif system == "Darwin":
        _notify_macos(title, message)
    elif system == "Windows":
        _notify_windows(title, message)
    # Other platforms: silently skip


def _notify_linux(title: str, message: str) -> None:
    """Use notify-send (libnotify) -- available on most desktop Linux distros."""
    if not shutil.which("notify-send"):
        return
    subprocess.Popen(
        ["notify-send", "--app-name=kport", "--expire-time=5000", title, message],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _notify_macos(title: str, message: str) -> None:
    """Use osascript (AppleScript) -- always available on macOS."""
    safe_title = title.replace('"', '\\"')
    safe_msg = message.replace('"', '\\"')
    script = (
        f'display notification "{safe_msg}" '
        f'with title "{safe_title}" '
        f'subtitle "kport"'
    )
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _notify_windows(title: str, message: str) -> None:
    """Use PowerShell toast notification -- available on Windows 10+.

    Falls back to a no-op if PowerShell is unavailable.
    Uses the Windows.UI.Notifications COM API via PowerShell without
    requiring any third-party packages.
    """
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return

    safe_title = title.replace("'", "''")
    safe_msg = message.replace("'", "''")

    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$template = [Windows.UI.Notifications.ToastNotificationManager]"
        "::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$template.SelectSingleNode('//text[@id=1]').InnerText = '{title}'; "
        "$template.SelectSingleNode('//text[@id=2]').InnerText = '{msg}'; "
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
        "[Windows.UI.Notifications.ToastNotificationManager]"
        "::CreateToastNotifier('kport').Show($toast)"
    ).format(title=safe_title, msg=safe_msg)

    subprocess.Popen(
        [ps, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
         "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
