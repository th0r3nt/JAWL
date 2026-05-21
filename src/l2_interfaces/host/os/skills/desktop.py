"""
Skills for physical interaction with the host system's graphical user interface (GUI).
Cross-platform implementation supporting Windows, macOS, and Linux.
Returns failure gracefully on headless servers without crashing the system.
"""

import os
import sys
import asyncio
import subprocess
import webbrowser
import shutil
import ctypes
from PIL import ImageGrab
import time

from src.utils._tools import draw_image_grid

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSDesktop:
    """
    Agent tools for interacting with the host OS Desktop GUI.
    Cross-platform implementation. Safely returns fail on headless servers (VPS).
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_url_in_browser(self, url: str) -> SkillResult:
        """
        [GUI] Opens URL in default OS browser.
        """

        try:
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            success = await asyncio.to_thread(webbrowser.open, url)
            if success:
                return SkillResult.ok("True")
            return SkillResult.fail(
                "Browser not found or the OS does not support this operation."
            )

        except Exception as e:
            return SkillResult.fail(f"Error opening browser: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_path_in_explorer(self, path: str = ".") -> SkillResult:
        """
        [GUI] Opens path in system file explorer.
        """
        try:
            safe_path = self.host_os.validate_path(path, is_write=False)
            if not safe_path.exists():
                return SkillResult.fail(f"Error: Path does not exist ({path}).")

            def _open_native():
                if sys.platform == "win32":
                    os.startfile(str(safe_path))
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(safe_path)])
                else:
                    subprocess.run(["xdg-open", str(safe_path)])

            await asyncio.to_thread(_open_native)
            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error opening window: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def send_notification(self, title: str, message: str) -> SkillResult:
        """
        [GUI] Sends system push notification.
        """
        try:

            def _notify():
                if sys.platform == "win32":
                    ps_script = f"""
                    [Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null;
                    $notify = New-Object System.Windows.Forms.NotifyIcon;
                    $notify.Icon = [System.Drawing.SystemIcons]::Information;
                    $notify.BalloonTipTitle = '{title.replace("'", "''")}';
                    $notify.BalloonTipText = '{message.replace("'", "''")}';
                    $notify.Visible = $True;
                    $notify.ShowBalloonTip(5000);
                    Start-Sleep -Seconds 5;
                    $notify.Dispose();
                    """
                    subprocess.run(
                        ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script]
                    )
                elif sys.platform == "darwin":
                    apple_script = f'display notification "{message}" with title "{title}"'
                    subprocess.run(["osascript", "-e", apple_script])
                else:
                    subprocess.run(["notify-send", title, message])

            asyncio.create_task(asyncio.to_thread(_notify))
            return SkillResult.ok("True")

        except FileNotFoundError:
            return SkillResult.fail(
                "Notification service is unavailable in this OS (likely a headless server)."
            )

        except Exception as e:
            return SkillResult.fail(f"Error sending notification: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def take_screenshot(
        self, filename: str, with_grid: bool = False, grid_step: int = 100
    ) -> SkillResult:
        """
        [GUI] Captures main screen screenshot and saves to sandbox.

        with_grid: Overlays coordinate grid.
        grid_step: Grid step in pixels.
        """
        try:
            if "/" not in filename and "\\" not in filename:
                filename = f"sandbox/_system/download/{filename}"

            safe_path = self.host_os.validate_path(filename, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _grab():
                img = ImageGrab.grab(all_screens=False)
                img.save(safe_path)

                if with_grid:
                    draw_image_grid(safe_path, step=grid_step)

            await asyncio.to_thread(_grab)
            return SkillResult.ok("True")

        except OSError:
            return SkillResult.fail(
                "Failed to take screenshot. Graphical interface is unavailable (headless server)."
            )
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error taking screenshot: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def lock_screen(self) -> SkillResult:
        """
        [GUI] Locks screen.
        """
        try:

            def _lock():
                if sys.platform == "win32":
                    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
                elif sys.platform == "darwin":
                    subprocess.run(["pmset", "displaysleepnow"])
                else:
                    if shutil.which("xdg-screensaver"):
                        subprocess.run(["xdg-screensaver", "lock"])
                    elif shutil.which("gnome-screensaver-command"):
                        subprocess.run(["gnome-screensaver-command", "-l"])
                    else:
                        raise FileNotFoundError("Screen lock command not found.")

            await asyncio.to_thread(_lock)
            return SkillResult.ok("True")

        except FileNotFoundError as e:
            return SkillResult.fail(f"Failed to lock screen (GUI is unavailable): {e}")

        except Exception as e:
            return SkillResult.fail(f"Error locking screen: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def click_coordinates(self, x: int, y: int) -> SkillResult:
        """
        [GUI] Performs left mouse click at monitor coordinates.
        """

        def _click():
            if sys.platform == "win32":
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)
                return True, f"Click at coordinates ({x}, {y}) executed."

            elif sys.platform == "darwin":
                script = f'tell application "System Events"\nclick at {{{x}, {y}}}\nend tell'
                subprocess.run(["osascript", "-e", script], check=True)
                return True, f"Click at coordinates ({x}, {y}) executed."

            else:
                if shutil.which("xdotool"):
                    subprocess.run(
                        ["xdotool", "mousemove", str(x), str(y), "click", "1"], check=True
                    )
                    return True, f"Click at coordinates ({x}, {y}) executed."

                else:
                    raise FileNotFoundError("To control the mouse, please install 'xdotool'.")

        try:
            success, msg = await asyncio.to_thread(_click)
            return SkillResult.ok("True") if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Error executing mouse click: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def type_text(self, text: str) -> SkillResult:
        """
        [GUI] Types specified text via keyboard.
        """

        def _type():
            if sys.platform == "win32":
                escaped = text
                for char in "+^%~()[]{}":
                    escaped = escaped.replace(char, f"{{{char}}}")
                escaped = escaped.replace("'", "''")

                ps_script = f"""
                Add-Type -AssemblyName System.Windows.Forms
                [System.Windows.Forms.SendKeys]::SendWait('{escaped}')
                """

                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=True,
                )
                return True, f"Text '{text}' successfully typed."

            elif sys.platform == "darwin":
                escaped_text = text.replace('"', '\\"')
                script = f'tell application "System Events" to keystroke "{escaped_text}"'
                subprocess.run(["osascript", "-e", script], check=True)
                return True, f"Text '{text}' successfully typed."

            else:
                if shutil.which("xdotool"):
                    subprocess.run(["xdotool", "type", text], check=True)
                    return True, f"Text '{text}' successfully typed."
                else:
                    raise FileNotFoundError(
                        "To emulate keyboard typing, please install 'xdotool'."
                    )

        try:
            success, msg = await asyncio.to_thread(_type)
            return SkillResult.ok("True") if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Error typing text: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def play_audio(self, filepath: str) -> SkillResult:
        """
        [GUI] Plays audio file.
        """
        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Error: Audio file not found ({safe_path.name}).")

            def _play():
                if sys.platform == "win32":
                    os.startfile(str(safe_path))
                elif sys.platform == "darwin":
                    subprocess.Popen(["afplay", str(safe_path)])
                else:
                    if shutil.which("paplay"):
                        subprocess.Popen(["paplay", str(safe_path)])
                    elif shutil.which("mpg123"):
                        subprocess.Popen(["mpg123", str(safe_path)])
                    else:
                        subprocess.Popen(["xdg-open", str(safe_path)])

            await asyncio.to_thread(_play)
            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except OSError:
            return SkillResult.fail("Failed to play audio. No default player found.")

        except Exception as e:
            return SkillResult.fail(f"Error playing audio: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def get_clipboard(self) -> SkillResult:
        """
        [GUI] Reads system clipboard.
        """
        import base64

        try:

            def _read_clipboard():
                if sys.platform == "win32":
                    ps_script = "try { $t = Get-Clipboard -Raw; if ($t) { [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($t)) } } catch {}"
                    b64_str = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command", ps_script],
                        text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    ).strip()

                    return base64.b64decode(b64_str).decode("utf-8") if b64_str else ""
                elif sys.platform == "darwin":
                    return subprocess.check_output(["pbpaste"], text=True).strip()
                else:
                    if shutil.which("xclip"):
                        return subprocess.check_output(
                            ["xclip", "-o", "-selection", "clipboard"], text=True
                        ).strip()
                    elif shutil.which("xsel"):
                        return subprocess.check_output(["xsel", "-ob"], text=True).strip()
                    return ""

            content = await asyncio.to_thread(_read_clipboard)

            if not content:
                return SkillResult.ok(
                    "Clipboard is empty (or contains non-text data, e.g., a file or image)."
                )

            from src.utils._tools import truncate_text

            clean_content = truncate_text(content, 10000)

            return SkillResult.ok(f"Clipboard content:\n```\n{clean_content}\n```")

        except FileNotFoundError:
            return SkillResult.fail(
                "Failed to read clipboard. On Linux, ensure 'xclip' or 'xsel' is installed."
            )
        except Exception as e:
            return SkillResult.fail(f"Failed to access clipboard: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def set_clipboard(self, text: str) -> SkillResult:
        """
        [GUI] Writes text to system clipboard.
        """
        import base64

        try:

            def _write_clipboard():
                if sys.platform == "win32":
                    b64_str = base64.b64encode(text.encode("utf-8")).decode("utf-8")
                    ps_script = f"[System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64_str}')) | Set-Clipboard"

                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_script],
                        check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    text_bytes = text.encode("utf-8")
                    if sys.platform == "darwin":
                        subprocess.run(["pbcopy"], input=text_bytes, check=True)
                    else:
                        if shutil.which("xclip"):
                            subprocess.run(
                                ["xclip", "-selection", "clipboard"],
                                input=text_bytes,
                                check=True,
                            )
                        elif shutil.which("xsel"):
                            subprocess.run(["xsel", "-ib"], input=text_bytes, check=True)
                        else:
                            raise FileNotFoundError("xclip/xsel not found")

            await asyncio.to_thread(_write_clipboard)
            return SkillResult.ok("True")

        except FileNotFoundError:
            return SkillResult.fail(
                "Failed to update clipboard. On Linux, ensure 'xclip' or 'xsel' is installed."
            )
        except Exception as e:
            return SkillResult.fail(f"Error writing to clipboard: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def list_active_windows(self) -> SkillResult:
        """
        [GUI] Lists visible/active OS window titles.
        """

        def _list():
            titles = []
            if sys.platform == "win32":
                import win32gui

                def enum_cb(hwnd, ctx):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title and title not in ["Program Manager", "Settings"]:
                            titles.append(title)

                win32gui.EnumWindows(enum_cb, None)

            elif sys.platform == "darwin":
                script = """tell application "System Events"
                    set windowList to {}
                    repeat with proc in (every process whose background only is false)
                        set windowList to windowList & (name of every window of proc)
                    end repeat
                    return windowList
                end tell"""
                out = subprocess.check_output(["osascript", "-e", script], text=True)
                titles = [
                    t.strip()
                    for t in out.split(",")
                    if t.strip() and t.strip() != "missing value"
                ]

            else:
                if shutil.which("wmctrl"):
                    out = subprocess.check_output(["wmctrl", "-l"], text=True)
                    for line in out.splitlines():
                        parts = line.split(maxsplit=3)
                        if len(parts) >= 4:
                            titles.append(parts[3])
                else:
                    raise FileNotFoundError("To switch windows, please install 'wmctrl'.")

            return titles

        try:
            windows = await asyncio.to_thread(_list)
            if not windows:
                return SkillResult.ok("No active graphical windows found.")
            unique_windows = list(dict.fromkeys(windows))

            return SkillResult.ok("List of open windows:\n- " + "\n- ".join(unique_windows))

        except FileNotFoundError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error getting window list: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def maximize_active_window(self) -> SkillResult:
        """
        [GUI] Maximizes active window.
        """

        def _maximize():
            if sys.platform == "win32":
                import win32gui
                import win32con

                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                    return True, "Active window successfully maximized."
                return False, "Active window not found."

            elif sys.platform == "darwin":
                script = """tell application "System Events"
                    set frontApp to first application process whose frontmost is true
                    set frontWindow to front window of frontApp
                    set value of attribute "AXFullScreen" of frontWindow to true
                end tell"""
                subprocess.run(["osascript", "-e", script], check=True)
                return True, "Active window maximized."

            else:
                if shutil.which("xdotool"):
                    subprocess.run(
                        ["xdotool", "getactivewindow", "windowsize", "100%", "100%"],
                        check=True,
                    )
                    return True, "Active window maximized."
                return False, "Linux requires the xdotool utility."

        try:
            success, msg = await asyncio.to_thread(_maximize)
            return SkillResult.ok("True") if success else SkillResult.fail(msg)
        except Exception as e:
            return SkillResult.fail(f"Error maximizing window: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def focus_window(self, title_substring: str) -> SkillResult:
        """
        [GUI] Focuses window containing title substring.
        """

        def _focus():
            if sys.platform == "win32":
                import win32gui
                import win32con

                target_hwnd = None

                def enum_cb(hwnd, ctx):
                    nonlocal target_hwnd
                    if win32gui.IsWindowVisible(hwnd):
                        if title_substring.lower() in win32gui.GetWindowText(hwnd).lower():
                            target_hwnd = hwnd

                win32gui.EnumWindows(enum_cb, None)

                if target_hwnd:
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(target_hwnd)
                    return True, f"Focus switched to window '{title_substring}'."
                return False, f"Window with title '{title_substring}' not found."

            elif sys.platform == "darwin":
                script = f"""tell application "System Events"
                    set targetProc to first process whose name of every window contains "{title_substring}"
                    set frontmost of targetProc to true
                end tell"""
                subprocess.run(["osascript", "-e", script], check=True)
                return True, "Focus switched."

            else:
                if shutil.which("wmctrl"):
                    subprocess.run(["wmctrl", "-a", title_substring], check=True)
                    return True, "Focus switched."

                else:
                    raise FileNotFoundError("To switch windows, please install 'wmctrl'.")

        try:
            success, msg = await asyncio.to_thread(_focus)
            return SkillResult.ok("True") if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Error switching focus: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def press_hotkey(self, hotkey: str) -> SkillResult:
        """
        [GUI] Emulates hotkey press (e.g., 'alt+tab', 'enter').
        """

        def _press():
            hk = hotkey.lower().replace(" ", "")

            if sys.platform == "win32":
                vk_map = {
                    "ctrl": 0x11,
                    "alt": 0x12,
                    "shift": 0x10,
                    "win": 0x5B,
                    "tab": 0x09,
                    "enter": 0x0D,
                    "esc": 0x1B,
                    "space": 0x20,
                    "up": 0x26,
                    "down": 0x28,
                    "left": 0x25,
                    "right": 0x27,
                }
                for i in range(26):
                    vk_map[chr(0x61 + i)] = 0x41 + i

                for i in range(10):
                    vk_map[str(i)] = 0x30 + i

                keys = hk.split("+")
                vks = []
                for k in keys:
                    if k in vk_map:
                        vks.append(vk_map[k])
                    else:
                        return False, f"Unknown key for Windows: {k}"

                for vk in vks:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)

                time.sleep(0.05)
                for vk in reversed(vks):
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

                return True, f"Combination '{hotkey}' successfully pressed."

            elif sys.platform == "darwin":
                keys = hk.split("+")
                modifiers, main_key = [], ""
                mod_map = {
                    "ctrl": "control down",
                    "alt": "option down",
                    "shift": "shift down",
                    "win": "command down",
                    "cmd": "command down",
                }

                for k in keys:
                    if k in mod_map:
                        modifiers.append(mod_map[k])
                    else:
                        main_key = k

                if not main_key:
                    return False, "Main key not specified."

                using_str = f" using {{{', '.join(modifiers)}}}" if modifiers else ""

                if main_key in ["enter", "return"]:
                    script = f'tell application "System Events" to key code 36{using_str}'

                elif main_key == "tab":
                    script = f'tell application "System Events" to key code 48{using_str}'

                elif main_key == "esc":
                    script = f'tell application "System Events" to key code 53{using_str}'

                elif main_key == "space":
                    script = f'tell application "System Events" to key code 49{using_str}'

                else:
                    script = f'tell application "System Events" to keystroke "{main_key}"{using_str}'

                subprocess.run(["osascript", "-e", script], check=True)
                return True, f"Combination '{hotkey}' successfully pressed."

            else:
                if shutil.which("xdotool"):
                    linux_hk = hk.replace("win", "super").replace("cmd", "super")
                    subprocess.run(["xdotool", "key", linux_hk], check=True)
                    return True, f"Combination '{hotkey}' successfully pressed."

                else:
                    raise FileNotFoundError("Please install 'xdotool'.")

        try:
            success, msg = await asyncio.to_thread(_press)
            return SkillResult.ok(msg) if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Error during keystroke emulation: {e}")
