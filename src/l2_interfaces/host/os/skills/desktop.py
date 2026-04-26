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
                filename = f"download/{filename}"

            safe_path = self.host_os.validate_path(filename, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            def _grab():
                img = ImageGrab.grab()
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
