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
    Навыки для взаимодействия с графическим интерфейсом (Desktop) хост-машины.
    Написаны кроссплатформенно. На headless-серверах (VPS) безопасно возвращают fail.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_url_in_browser(self, url: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Открывает указанную ссылку в дефолтном веб-браузере ОС.
        """

        try:
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            success = await asyncio.to_thread(webbrowser.open, url)
            if success:
                return SkillResult.ok(f"Ссылка {url} успешно открыта в браузере.")
            return SkillResult.fail(
                "Браузер не найден или ОС не поддерживает данную операцию."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при открытии браузера: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def open_path_in_explorer(self, path: str = ".") -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Открывает указанную директорию или файл в графическом проводнике (Explorer/Finder).
        """
        try:
            safe_path = self.host_os.validate_path(path, is_write=False)
            if not safe_path.exists():
                return SkillResult.fail(f"Ошибка: Путь не существует ({path}).")

            def _open_native():
                if sys.platform == "win32":
                    os.startfile(str(safe_path))
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(safe_path)])
                else:
                    subprocess.run(["xdg-open", str(safe_path)])

            await asyncio.to_thread(_open_native)
            return SkillResult.ok(
                f"Объект '{safe_path.name}' успешно открыт в графическом интерфейсе ОС."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при открытии окна: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def send_notification(self, title: str, message: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Отправляет системное Push-уведомление.
        """
        try:

            def _notify():
                if sys.platform == "win32":
                    # Используем встроенный PowerShell для отправки Toast-уведомления без сторонних либ
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
                    # Нативный AppleScript
                    apple_script = f'display notification "{message}" with title "{title}"'
                    subprocess.run(["osascript", "-e", apple_script])
                else:
                    # Нативный Linux notify-send
                    subprocess.run(["notify-send", title, message])

            # Запускаем как фоновую задачу, так как вызов может блокироваться на пару секунд
            asyncio.create_task(asyncio.to_thread(_notify))
            return SkillResult.ok("Уведомление успешно отправлено.")

        except FileNotFoundError:
            return SkillResult.fail(
                "Служба уведомлений недоступна в данной ОС (вероятно, сервер без GUI)."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка отправки уведомления: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def take_screenshot(
        self, filename: str, with_grid: bool = False, grid_step: int = 100
    ) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Делает скриншот главного экрана и сохраняет его в песочницу.

        with_grid: Накладывает контрастную координатную сетку поверх скриншота.
        grid_step: Шаг сетки в пикселях. Если нужна большая точность клика - поставить 40.
        """
        try:
            if "/" not in filename and "\\" not in filename:
                filename = f"_system/download/{filename}"

            safe_path = self.host_os.validate_path(filename, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _grab():
                # Убрано all_screens=True, чтобы снимать только основной монитор.
                # Иначе 3 монитора сжимаются LLM в мыло, и координаты ломаются.
                img = ImageGrab.grab(all_screens=False)
                img.save(safe_path)

                if with_grid:
                    draw_image_grid(safe_path, step=grid_step)

            await asyncio.to_thread(_grab)
            return SkillResult.ok(
                f"Скриншот успешно сделан и сохранен по пути: {safe_path.resolve()}"
            )

        except OSError:
            return SkillResult.fail(
                "Не удалось сделать скриншот. Графический интерфейс недоступен (headless-сервер)."
            )
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании скриншота: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def lock_screen(self) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Блокирует экран (переводит на окно ввода пароля).
        """
        try:

            def _lock():
                if sys.platform == "win32":
                    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
                elif sys.platform == "darwin":
                    subprocess.run(["pmset", "displaysleepnow"])
                else:
                    # Пробуем несколько популярных Linux-локкеров
                    if shutil.which("xdg-screensaver"):
                        subprocess.run(["xdg-screensaver", "lock"])
                    elif shutil.which("gnome-screensaver-command"):
                        subprocess.run(["gnome-screensaver-command", "-l"])
                    else:
                        raise FileNotFoundError("Команда блокировки экрана не найдена.")

            await asyncio.to_thread(_lock)
            return SkillResult.ok("Экран успешно заблокирован.")

        except FileNotFoundError as e:
            return SkillResult.fail(f"Не удалось заблокировать экран (GUI недоступен): {e}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при блокировке экрана: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def click_coordinates(self, x: int, y: int) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Перемещает курсор и кликает левой кнопкой мыши по указанным абсолютным координатам основного экрана.
        """

        def _click():
            if sys.platform == "win32":
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)
                return True, f"Клик по координатам ({x}, {y}) выполнен."

            elif sys.platform == "darwin":
                script = f'tell application "System Events"\nclick at {{{x}, {y}}}\nend tell'
                subprocess.run(["osascript", "-e", script], check=True)
                return True, f"Клик по координатам ({x}, {y}) выполнен."

            else:
                if shutil.which("xdotool"):
                    subprocess.run(
                        ["xdotool", "mousemove", str(x), str(y), "click", "1"], check=True
                    )
                    return True, f"Клик по координатам ({x}, {y}) выполнен."

                else:
                    raise FileNotFoundError("Для управления мышью установите 'xdotool'.")

        try:
            success, msg = await asyncio.to_thread(_click)
            return SkillResult.ok(msg) if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при клике мыши: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def type_text(self, text: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Печатает переданный текст (эмулирует ввод с клавиатуры).
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
                return True, f"Текст '{text}' успешно напечатан."

            elif sys.platform == "darwin":
                escaped_text = text.replace('"', '\\"')
                script = f'tell application "System Events" to keystroke "{escaped_text}"'
                subprocess.run(["osascript", "-e", script], check=True)
                return True, f"Текст '{text}' успешно напечатан."

            else:
                if shutil.which("xdotool"):
                    subprocess.run(["xdotool", "type", text], check=True)
                    return True, f"Текст '{text}' успешно напечатан."
                else:
                    raise FileNotFoundError("Для эмуляции клавиатуры установите 'xdotool'.")

        try:
            success, msg = await asyncio.to_thread(_type)
            return SkillResult.ok(msg) if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при вводе текста: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def play_audio(self, filepath: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Воспроизводит аудиофайл (mp3, wav). Выполняется в фоновом режиме.
        """
        try:
            # Пропускаем через гейткипер (только из sandbox/)
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Аудиофайл не найден ({safe_path.name}).")

            def _play():
                if sys.platform == "win32":
                    # Нативная функция Windows, открывает файл в плеере по умолчанию
                    os.startfile(str(safe_path))
                elif sys.platform == "darwin":
                    # Нативный консольный плеер macOS, не открывает UI
                    subprocess.Popen(["afplay", str(safe_path)])
                else:
                    # Linux: пробуем консольные плееры, иначе открываем в UI
                    if shutil.which("paplay"):
                        subprocess.Popen(["paplay", str(safe_path)])
                    elif shutil.which("mpg123"):
                        subprocess.Popen(["mpg123", str(safe_path)])
                    else:
                        subprocess.Popen(["xdg-open", str(safe_path)])

            # Вызываем в отдельном потоке, хотя Popen и startfile не блокируют выполнение
            await asyncio.to_thread(_play)
            return SkillResult.ok(f"Аудиофайл {safe_path.name} успешно запущен.")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except OSError:
            return SkillResult.fail(
                "Не удалось запустить аудио. Отсутствует плеер по умолчанию."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при воспроизведении аудио: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def get_clipboard(self) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Считывает текущий текстовый контент из системного буфера обмена.
        """
        import base64

        try:

            def _read_clipboard():
                if sys.platform == "win32":
                    # Читаем буфер в PS, переводим в UTF-8 байты, а затем в Base64.
                    # Это полностью исключает консольные проблемы с кодировками.
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
                    "Буфер обмена пуст (или содержит не текстовые данные, например файл/картинку)."
                )

            from src.utils._tools import truncate_text

            clean_content = truncate_text(content, 10000)

            return SkillResult.ok(f"Содержимое буфера обмена:\n```\n{clean_content}\n```")

        except FileNotFoundError:
            return SkillResult.fail(
                "Не удалось прочитать буфер. В Linux убедитесь, что установлен 'xclip' или 'xsel'."
            )
        except Exception as e:
            return SkillResult.fail(f"Не удалось получить доступ к буферу обмена: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def set_clipboard(self, text: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Помещает указанный текст в системный буфер обмена.
        """
        import base64

        try:

            def _write_clipboard():
                if sys.platform == "win32":
                    # Кодируем текст в Base64 на стороне Python, а PowerShell декодирует и кладет в буфер
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
                            raise FileNotFoundError("xclip/xsel не найдены")

            await asyncio.to_thread(_write_clipboard)
            return SkillResult.ok(
                f"Текст успешно скопирован в буфер обмена (Длина: {len(text)} симв.)."
            )

        except FileNotFoundError:
            return SkillResult.fail(
                "Не удалось изменить буфер. В Linux убедитесь, что установлен 'xclip' или 'xsel'."
            )
        except Exception as e:
            return SkillResult.fail(f"Ошибка записи в буфер обмена: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def list_active_windows(self) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Возвращает список заголовков видимых и активных окон операционной системы.
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
                    raise FileNotFoundError("Для получения списка окон установите 'wmctrl'.")

            return titles

        try:
            windows = await asyncio.to_thread(_list)
            if not windows:
                return SkillResult.ok("Активных графических окон не найдено.")
            unique_windows = list(dict.fromkeys(windows))

            return SkillResult.ok("Список открытых окон:\n- " + "\n- ".join(unique_windows))

        except FileNotFoundError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка окон: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def maximize_active_window(self) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Разворачивает текущее активное окно (на переднем плане) на весь экран.
        """

        def _maximize():
            if sys.platform == "win32":
                import win32gui
                import win32con

                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                    return True, "Активное окно успешно развернуто на весь экран."
                return False, "Активное окно не найдено."

            elif sys.platform == "darwin":
                script = """tell application "System Events"
                    set frontApp to first application process whose frontmost is true
                    set frontWindow to front window of frontApp
                    set value of attribute "AXFullScreen" of frontWindow to true
                end tell"""
                subprocess.run(["osascript", "-e", script], check=True)
                return True, "Активное окно развернуто на весь экран."

            else:
                if shutil.which("xdotool"):
                    subprocess.run(
                        ["xdotool", "getactivewindow", "windowsize", "100%", "100%"],
                        check=True,
                    )
                    return True, "Активное окно развернуто на весь экран."
                return False, "Для Linux требуется утилита xdotool."

        try:
            success, msg = await asyncio.to_thread(_maximize)
            return SkillResult.ok(msg) if success else SkillResult.fail(msg)
        except Exception as e:
            return SkillResult.fail(f"Ошибка при развертывании окна: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def focus_window(self, title_substring: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Переключает фокус на окно, заголовок которого содержит указанную подстроку.
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
                    # Хак Windows для перехвата фокуса
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
                    win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(target_hwnd)
                    return True, f"Фокус переключен на окно '{title_substring}'."
                return False, f"Окно с текстом '{title_substring}' не найдено."

            elif sys.platform == "darwin":
                script = f"""tell application "System Events"
                    set targetProc to first process whose name of every window contains "{title_substring}"
                    set frontmost of targetProc to true
                end tell"""
                subprocess.run(["osascript", "-e", script], check=True)
                return True, "Фокус переключен."

            else:
                if shutil.which("wmctrl"):
                    subprocess.run(["wmctrl", "-a", title_substring], check=True)
                    return True, "Фокус переключен."

                else:
                    raise FileNotFoundError("Для переключения окон установите 'wmctrl'.")

        try:
            success, msg = await asyncio.to_thread(_focus)
            return SkillResult.ok(msg) if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при переключении фокуса: {e}")

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def press_hotkey(self, hotkey: str) -> SkillResult:
        """[Графический интерфейс хост-машины]
        Эмулирует нажатие горячих клавиш.
        Примеры: 'alt+tab', 'win+d', 'ctrl+c', 'enter', 'shift+a'.
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
                        return False, f"Неизвестная клавиша для Windows: {k}"

                for vk in vks:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)

                time.sleep(0.05)
                for vk in reversed(vks):
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

                return True, f"Комбинация '{hotkey}' успешно нажата."

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
                    return False, "Не указана основная клавиша."

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
                return True, f"Комбинация '{hotkey}' успешно нажата."

            else:
                if shutil.which("xdotool"):
                    linux_hk = hk.replace("win", "super").replace("cmd", "super")
                    subprocess.run(["xdotool", "key", linux_hk], check=True)
                    return True, f"Комбинация '{hotkey}' успешно нажата."

                else:
                    raise FileNotFoundError("Установите 'xdotool'.")

        try:
            success, msg = await asyncio.to_thread(_press)
            return SkillResult.ok(msg) if success else SkillResult.fail(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при эмуляции нажатия: {e}")
