import os
import sys
import asyncio
import subprocess
import webbrowser
import shutil
from PIL import ImageGrab

from src.l2_interfaces.host.os.client import HostOSClient
from src.l3_agent.skills.registry import SkillResult, skill


class HostOSDesktop:
    """
    Навыки для взаимодействия с графическим интерфейсом (Desktop) хост-машины.
    Написаны кроссплатформенно. На headless-серверах (VPS) безопасно возвращают fail.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    async def open_url_in_browser(self, url: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Открывает указанную ссылку в дефолтном веб-браузере.
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
    async def take_screenshot(self, filename: str) -> SkillResult:
        """
        [Графический интерфейс хост-машины]
        Делает скриншот главного экрана и сохраняет его в директорию.
        Если передано только имя (например, screen.png), сохранит в sandbox/download/.
        """
        try:
            if "/" not in filename and "\\" not in filename:
                filename = f"_system/download/{filename}"

            safe_path = self.host_os.validate_path(filename, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _grab():
                img = ImageGrab.grab(all_screens=True)
                img.save(safe_path)

            await asyncio.to_thread(_grab)
            return SkillResult.ok(
                f"Скриншот успешно сделан и сохранен по пути: {safe_path.resolve()}"
            )

        except OSError:
            # Ошибка OS, как правило, означает, что X11/Wayland/Дисплей не найден (VPS сервер)
            return SkillResult.fail(
                "Не удалось сделать скриншот. Графический интерфейс/монитор недоступен (вероятно, это headless-сервер)."
            )
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании скриншота: {e}")

    @skill()
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