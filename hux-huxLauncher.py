import ctypes
import hashlib
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from logging.handlers import RotatingFileHandler
from threading import Thread
from tkinter import filedialog, messagebox
from xml.sax.saxutils import escape

import customtkinter as ctk
import requests
from PIL import Image, ImageFont, ImageTk

from hux_lang import LANG, LANG_CHOICES

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CURRENT_VERSION = "1.0.9"
GITHUB_REPO = "ky4ka-boroxla/hux-huxLauncher"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

WINDOW_TITLE = "hux-huxLauncher"
MUTEX_NAME = "Local\\hux-huxLauncher-single-instance"
SERVICE_NAME = "zapret"
AUTOSTART_TASK_NAME = "hux-huxLauncher"
STRATEGY_PROCESS = "winws.exe"
WINDIVERT_SERVICES = ("WinDivert", "WinDivert14")
SERVICE_RUNNING = 4
STATUS_POLL_MS = 5000
LAUNCH_GRACE_SECONDS = 8.0
STAGED_EXTENSIONS = {".exe", ".dll", ".bin", ".so", ".dylib", ".pyd"}
UNPACK_DIR_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)-\d+(?:\.\d+)*$")
UNPACK_CLEANUP_DELAY = 30

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
FR_PRIVATE = 0x10
ERROR_ALREADY_EXISTS = 183

C_BG = ("#0a0a1a", "#0d0d2b")
C_PANEL = ("#1a1a2e", "#16213e")
C_TEXT = ("black", "white")
C_CYAN = "#00d4ff"
C_ORANGE = "#f39c12"
C_GREEN = "#48bb78"
C_RED = "#fc8181"
C_MUTED = "#a0aec0"
C_BTN = "#2d3748"
C_BTN_HOVER = "#4a5568"
C_BTN_BORDER = "#4a5568"
C_ACCENT = "#00b894"
C_ACCENT_HOVER = "#00a381"
C_DANGER = "#e53e3e"
C_DANGER_HOVER = "#c53030"
C_WARNING = "#dd6b20"
C_WARNING_HOVER = "#c05621"
C_NEUTRAL = "#4a5568"
C_NEUTRAL_HOVER = "#718096"

BUTTON_STYLES = {
    "default": {"fg_color": C_BTN, "hover_color": C_BTN_HOVER},
    "strategy": {"fg_color": C_BTN, "hover_color": C_ACCENT},
    "accent": {"fg_color": C_ACCENT, "hover_color": C_ACCENT_HOVER},
    "danger": {"fg_color": C_DANGER, "hover_color": C_DANGER_HOVER},
    "warning": {"fg_color": C_WARNING, "hover_color": C_WARNING_HOVER},
    "neutral": {"fg_color": C_NEUTRAL, "hover_color": C_NEUTRAL_HOVER},
}


def prepare_appdata_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    candidates = (
        os.path.join(base, "ky4ka_boroxla", "hux-huxLauncher"),
        os.path.join(tempfile.gettempdir(), "hux-huxLauncher"),
    )
    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError:
            continue
    return tempfile.gettempdir()


APPDATA_DIR = prepare_appdata_dir()
LOG_PATH = os.path.join(APPDATA_DIR, "hux-launcher.log")
SETTINGS_PATH = os.path.join(APPDATA_DIR, "hux-launcher-settings.json")

logger = logging.getLogger("hux-huxLauncher")


def log_unhandled(exc_type, exc, tb):
    logger.error("Необработанное исключение", exc_info=(exc_type, exc, tb))


def log_thread_exception(args):
    name = args.thread.name if args.thread else "?"
    logger.error("Необработанное исключение в потоке %s", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def setup_logging():
    logger.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(LOG_PATH, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    sys.excepthook = log_unhandled
    threading.excepthook = log_thread_exception


setup_logging()


def is_compiled():
    try:
        __compiled__
        return True
    except NameError:
        return bool(getattr(sys, "frozen", False))


def get_executable_path():
    return os.path.abspath(sys.argv[0])


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_old_unpack_dirs():
    if not is_compiled():
        return
    current_name = os.path.basename(BASE_PATH)
    current_match = UNPACK_DIR_PATTERN.match(current_name)
    current_version = parse_version(current_match.group(1)) if current_match else None
    if not current_version:
        return
    parent = os.path.dirname(BASE_PATH)
    try:
        for name in os.listdir(parent):
            found = UNPACK_DIR_PATTERN.match(name)
            full_path = os.path.join(parent, name)
            if not found or name == current_name or not os.path.isdir(full_path):
                continue
            other_version = parse_version(found.group(1))
            if other_version and is_newer_version(current_version, other_version):
                shutil.rmtree(full_path, ignore_errors=True)
    except OSError:
        logger.exception("Ошибка очистки старых распакованных версий")


def delayed_unpack_cleanup():
    time.sleep(UNPACK_CLEANUP_DELAY)
    cleanup_old_unpack_dirs()


def cleanup_update_leftovers():
    if not is_compiled():
        return
    target = get_executable_path()
    for suffix in (".old", ".new"):
        leftover = target + suffix
        if os.path.exists(leftover):
            try:
                os.remove(leftover)
            except OSError:
                logger.warning("Не удалось удалить %s", leftover)


def get_app_path():
    try:
        return __compiled__.containing_dir
    except NameError:
        pass
    if getattr(sys, "frozen", False):
        exe_path = sys.argv[0]
        if "~" in exe_path:
            try:
                buffer = ctypes.create_unicode_buffer(260)
                if ctypes.windll.kernel32.GetLongPathNameW(exe_path, buffer, 260):
                    exe_path = buffer.value
            except Exception:
                pass
        return os.path.dirname(os.path.abspath(exe_path))
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = os.path.dirname(os.path.abspath(__file__))
APP_PATH = get_app_path()
BUILTIN_ZAPRET_DIR = os.path.join(BASE_PATH, "zapret")
CUSTOM_FONT_PATH = os.path.join(BASE_PATH, "fnt_dotumche.ttf")
ICON_PATH = os.path.join(BASE_PATH, "icon.ico")
GIF_PATH = os.path.join(BASE_PATH, "hux.gif")
CUSTOM_FONT_FAMILY = None


def load_custom_font():
    global CUSTOM_FONT_FAMILY
    if not os.path.exists(CUSTOM_FONT_PATH):
        return
    try:
        ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(CUSTOM_FONT_PATH), FR_PRIVATE, 0)
    except Exception:
        logger.exception("Ошибка регистрации шрифта %s", CUSTOM_FONT_PATH)
    try:
        CUSTOM_FONT_FAMILY, _ = ImageFont.truetype(CUSTOM_FONT_PATH, 12).getname()
    except Exception:
        logger.exception("Не удалось определить имя шрифта %s", CUSTOM_FONT_PATH)
        CUSTOM_FONT_FAMILY = None


load_custom_font()


def app_font(size=13, weight="normal"):
    if CUSTOM_FONT_FAMILY:
        return ctk.CTkFont(family=CUSTOM_FONT_FAMILY, size=size, weight=weight)
    return ctk.CTkFont(size=size, weight=weight)


def make_button(master, text, command, style="default", size=13, weight="normal", **kwargs):
    options = dict(BUTTON_STYLES[style])
    options.update(kwargs)
    return ctk.CTkButton(master, text=text, command=command, font=app_font(size=size, weight=weight), **options)


def make_label(master, text, size=13, weight="normal", color=C_TEXT, **kwargs):
    return ctk.CTkLabel(master, text=text, font=app_font(size=size, weight=weight), text_color=color, **kwargs)


def make_panel(master, border=None, radius=12, border_width=1, **kwargs):
    options = {"fg_color": C_PANEL, "corner_radius": radius}
    if border:
        options.update(border_width=border_width, border_color=border)
    options.update(kwargs)
    return ctk.CTkFrame(master, **options)


def set_window_icon(window):
    try:
        if os.path.exists(ICON_PATH):
            window.iconbitmap(ICON_PATH)
    except Exception:
        pass


def center_window(window, width, height):
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


def display_name(name):
    return name[:-4] if name.lower().endswith(".bat") else name


def natural_key(name):
    return re.sub(r"\d+", lambda m: m.group().zfill(10), name)


def build_channel(file_name):
    lowered = file_name.lower()
    if "_alpha" in lowered:
        return "alpha"
    if "_beta" in lowered:
        return "beta"
    return "release"


def parse_version(tag):
    match = re.match(r"^\s*[vV]?(\d+(?:\.\d+)*)", str(tag))
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer_version(candidate, current):
    length = max(len(candidate), len(current))
    padded_candidate = candidate + (0,) * (length - len(candidate))
    padded_current = current + (0,) * (length - len(current))
    return padded_candidate > padded_current


CURRENT_VERSION_TUPLE = parse_version(CURRENT_VERSION)


def load_settings():
    migrate_old_settings()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings):
    tmp_path = SETTINGS_PATH + ".tmp"
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SETTINGS_PATH)
    except Exception:
        logger.exception("Ошибка сохранения настроек")


def migrate_old_settings():
    if os.path.exists(SETTINGS_PATH):
        return
    old_path = os.path.join(APP_PATH, "hux-launcher-settings.json")
    if not os.path.exists(old_path):
        return
    try:
        with open(old_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            save_settings(data)
    except Exception:
        logger.exception("Ошибка миграции старых настроек")


def resolve_zapret_dir(settings):
    if settings.get("zapret_mode") == "custom":
        custom_path = settings.get("zapret_custom_path", "")
        if custom_path and os.path.isdir(custom_path):
            return custom_path
    return BUILTIN_ZAPRET_DIR


def unstage_zapret_files(zapret_dir):
    if not os.path.isdir(zapret_dir):
        return
    try:
        for root, _dirs, files in os.walk(zapret_dir):
            for name in files:
                if not name.lower().endswith(".dat"):
                    continue
                original = name[:-4]
                if os.path.splitext(original)[1].lower() not in STAGED_EXTENSIONS:
                    continue
                destination = os.path.join(root, original)
                if os.path.exists(destination):
                    continue
                try:
                    os.rename(os.path.join(root, name), destination)
                except OSError:
                    logger.exception("Не удалось восстановить файл %s", name)
    except Exception:
        logger.exception("Ошибка восстановления файлов zapret из .dat")


def prepare_zapret_dir(settings):
    zapret_dir = resolve_zapret_dir(settings)
    if zapret_dir == BUILTIN_ZAPRET_DIR:
        unstage_zapret_files(zapret_dir)
    return zapret_dir


def run_hidden(args, timeout=10):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def query_service_state(name=SERVICE_NAME):
    result = run_hidden(["sc", "query", name], timeout=5)
    if result.returncode != 0:
        return None
    match = re.search(r"STATE\s*:\s*(\d+)", result.stdout)
    if match:
        return int(match.group(1))
    return SERVICE_RUNNING if "RUNNING" in result.stdout else 1


def is_process_running(image_name):
    result = run_hidden(["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"], timeout=8)
    return image_name.lower() in result.stdout.lower()


def kill_process(image_name):
    run_hidden(["taskkill", "/F", "/IM", image_name], timeout=10)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def windowless_python():
    executable = sys.executable
    windowless = os.path.join(os.path.dirname(executable), "pythonw.exe")
    if os.path.basename(executable).lower() == "python.exe" and os.path.exists(windowless):
        return windowless
    return executable


def relaunch_elevated():
    args = [arg for arg in sys.argv[1:] if arg != "--elevated"] + ["--elevated"]
    if is_compiled():
        executable = get_executable_path()
        params = subprocess.list2cmdline(args)
    else:
        executable = windowless_python()
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + args)
    try:
        shell_execute = ctypes.windll.shell32.ShellExecuteW
        shell_execute.restype = ctypes.c_void_p
        result = shell_execute(None, "runas", executable, params, APP_PATH, 1)
        return (result or 0) > 32
    except Exception:
        logger.exception("Не удалось перезапустить с правами администратора")
        return False


def autostart_command():
    if is_compiled():
        executable = get_executable_path()
        return executable, "--autostart", os.path.dirname(executable)
    arguments = subprocess.list2cmdline([os.path.abspath(sys.argv[0]), "--autostart"])
    return windowless_python(), arguments, APP_PATH


def current_task_user():
    domain = os.environ.get("USERDOMAIN", "")
    name = os.environ.get("USERNAME", "")
    return f"{domain}\\{name}" if domain and name else name


def build_task_xml(command, arguments, working_dir, user):
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>hux-huxLauncher autostart</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{escape(user)}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(working_dir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def query_autostart():
    return run_hidden(["schtasks", "/Query", "/TN", AUTOSTART_TASK_NAME], timeout=10).returncode == 0


def set_autostart(enabled):
    if not enabled:
        if not query_autostart():
            return True
        result = run_hidden(["schtasks", "/Delete", "/TN", AUTOSTART_TASK_NAME, "/F"], timeout=15)
        if result.returncode != 0:
            logger.error("schtasks /Delete: %s", (result.stderr or result.stdout).strip())
        return result.returncode == 0

    command, arguments, working_dir = autostart_command()
    xml_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")
    xml_path = os.path.join(xml_dir, f"hux-task-{uuid.uuid4().hex}.xml")
    with open(xml_path, "x", encoding="utf-16") as f:
        f.write(build_task_xml(command, arguments, working_dir, current_task_user()))
    try:
        result = run_hidden(["schtasks", "/Create", "/TN", AUTOSTART_TASK_NAME, "/XML", xml_path, "/F"], timeout=15)
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
    if result.returncode != 0:
        logger.error("schtasks /Create: %s", (result.stderr or result.stdout).strip())
    return result.returncode == 0


class SingleInstance:
    def __init__(self, name, wait=0.0):
        self.name = name
        self.wait = wait
        self.handle = None

    def acquire(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        deadline = time.time() + self.wait
        while True:
            handle = kernel32.CreateMutexW(None, False, self.name)
            if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
                self.handle = handle
                return True
            if handle:
                kernel32.CloseHandle(handle)
            if time.time() >= deadline:
                return False
            time.sleep(0.2)


def focus_existing_window():
    try:
        user32 = ctypes.windll.user32
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        logger.exception("Не удалось активировать уже запущенное окно")


class SplashScreen(ctk.CTkToplevel):
    def __init__(self, lang="ru", is_ready=None, min_time=1.5, max_time=5.0):
        super().__init__()
        self.text = LANG[lang]
        self.is_ready = is_ready or (lambda: True)
        self.min_time = min_time
        self.max_time = max_time
        self._closed = False
        self._gif_job = None
        self._progress_job = None
        self._finish_job = None
        self.gif_frames = []
        self.gif_durations = []
        self.current_gif_frame = 0

        self.title("")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=C_BG)
        center_window(self, 400, 480)
        set_window_icon(self)

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True)

        top_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=70)
        top_frame.pack(fill="x", pady=(30, 0))
        top_frame.pack_propagate(False)
        make_label(top_frame, self.text["title"], size=32, weight="bold", color=C_CYAN).pack(pady=(10, 0))
        make_label(top_frame, f"{self.text['version']} {CURRENT_VERSION}").pack()

        center_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        center_frame.pack(fill="both", expand=True)
        self.gif_label = ctk.CTkLabel(center_frame, text="")
        self.gif_label.pack(expand=True)
        if os.path.exists(GIF_PATH):
            self.load_gif(GIF_PATH)

        bottom_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=100)
        bottom_frame.pack(fill="x", pady=(0, 30))
        bottom_frame.pack_propagate(False)
        self.status_label = make_label(bottom_frame, self.text["loading"])
        self.status_label.pack(pady=(0, 8))
        self.progress = ctk.CTkProgressBar(bottom_frame, width=320, height=6, corner_radius=3, fg_color=C_BTN, progress_color=C_CYAN)
        self.progress.pack()
        self.progress.set(0)

        self.steps = self.text["steps"]
        self.current_step = 0
        self.start_time = time.time()
        self.animate_progress()
        self.animate_gif()

    def load_gif(self, gif_path):
        try:
            with Image.open(gif_path) as img:
                while True:
                    frame = img.copy()
                    frame.thumbnail((350, 350), Image.LANCZOS)
                    self.gif_frames.append(ImageTk.PhotoImage(frame))
                    self.gif_durations.append(max(20, img.info.get("duration", 100)))
                    try:
                        img.seek(img.tell() + 1)
                    except EOFError:
                        break
            if self.gif_frames:
                self.gif_label.configure(image=self.gif_frames[0])
        except Exception:
            logger.exception("Ошибка загрузки GIF")
            self.gif_frames = []
            self.gif_durations = []

    def animate_gif(self):
        if self._closed or not self.gif_frames:
            return
        self.current_gif_frame = (self.current_gif_frame + 1) % len(self.gif_frames)
        self.gif_label.configure(image=self.gif_frames[self.current_gif_frame])
        self._gif_job = self.after(self.gif_durations[self.current_gif_frame], self.animate_gif)

    def animate_progress(self):
        if self._closed:
            return
        elapsed = time.time() - self.start_time
        ready = self.is_ready()
        ratio = min(elapsed / self.min_time, 1.0)
        progress = ratio if ready else min(ratio, 0.9)
        self.progress.set(progress)

        step = min(int(progress * len(self.steps)), len(self.steps) - 1)
        if step != self.current_step:
            self.current_step = step
            self.status_label.configure(text=self.steps[step])

        if (ready and elapsed >= self.min_time) or elapsed >= self.max_time:
            self.status_label.configure(text=self.text["ready"])
            self.progress.set(1.0)
            self._finish_job = self.after(300, self.destroy)
            return
        self._progress_job = self.after(20, self.animate_progress)

    def destroy(self):
        self._closed = True
        for job in (self._gif_job, self._progress_job, self._finish_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        super().destroy()


class HelpWindow(ctk.CTkToplevel):
    def __init__(self, master, lang="ru", custom_folder=False):
        super().__init__(master)
        self.text = LANG[lang]
        self.title(self.text["documentation"])
        self.resizable(False, False)
        self.configure(fg_color=C_BG)
        self.attributes("-topmost", True)
        center_window(self, 420, 520 if custom_folder else 450)
        set_window_icon(self)

        make_label(self, self.text["where_to_click"], size=24, weight="bold", color=C_CYAN).pack(pady=(15, 5))
        make_label(self, self.text["doc_instruction"], size=14).pack(pady=(0, 10))

        frame = make_panel(self, border=C_CYAN, radius=10)
        frame.pack(pady=5, padx=20, fill="x")
        for index, (num, desc) in enumerate(self.text["doc_items"]):
            make_label(frame, f"{num} -> {desc}").grid(row=index // 2, column=index % 2, padx=10, pady=3, sticky="w")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        if custom_folder:
            make_label(self, self.text["doc_custom_warning"], size=12, color=C_ORANGE, wraplength=380, justify="center").pack(pady=(10, 0), padx=20)

        make_button(self, self.text["doc_close"], self.destroy, style="accent", size=14, weight="bold", height=40, corner_radius=10).pack(pady=(15, 15), padx=40, fill="x")


class HuxHuxLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self._closing = False
        self._ui_job = None
        self._status_job = None
        self._ui_queue = queue.Queue()
        self._status_busy = False

        self.settings = load_settings()
        lang = self.settings.get("lang", "ru")
        self.lang = lang if lang in LANG else "ru"
        self.text = LANG[self.lang]
        self.zapret_dir = prepare_zapret_dir(self.settings)

        self.strategies = []
        self.strategy_buttons = {}
        self.active_strategy = None
        self.launch_grace_until = 0.0
        self.initial_status_done = False
        self.update_state = None
        self.latest_version = ""
        self.download_url = GITHUB_RELEASES_URL
        self.update_asset = None
        self.update_progress = 0
        self.status_view = ("status_not_installed", C_TEXT, ())

        self.title(WINDOW_TITLE)
        self.geometry("600x930")
        self.resizable(False, False)
        self.configure(fg_color=C_BG)
        set_window_icon(self)

        self.build_ui()
        self.load_strategies()
        self.render_status()
        self.refresh_update_label()

        self._poll_ui_queue()
        Thread(target=self._autostart_query_worker, daemon=True).start()
        self.after(500, self.check_status)
        self.after(1000, self.check_updates)

    def build_ui(self):
        self.top_controls = ctk.CTkFrame(self, fg_color="transparent", height=50)
        self.top_controls.pack(pady=(10, 0), padx=20, fill="x")
        self.top_controls.pack_propagate(False)

        self.lang_frame = ctk.CTkFrame(self.top_controls, fg_color="transparent")
        self.lang_frame.pack(side="right", padx=5)
        make_label(self.lang_frame, "🌐", size=14).pack(side="left", padx=(0, 5))
        self.lang_switch = ctk.CTkOptionMenu(
            self.lang_frame,
            values=list(LANG_CHOICES),
            command=self.change_lang,
            font=app_font(size=12, weight="bold"),
            fg_color=C_BTN,
            button_color=C_CYAN,
            button_hover_color="#0077b6",
            width=80,
            height=30,
        )
        self.lang_switch.pack(side="left")
        current_choice = next((choice for choice, code in LANG_CHOICES.items() if code == self.lang), "RU")
        self.lang_switch.set(current_choice)

        self.zapret_source_btn = make_button(self.top_controls, "📁", self.open_zapret_source_dialog, size=14, width=36, height=30)
        self.zapret_source_btn.pack(side="left", padx=(5, 0))

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(5, 5), fill="x")
        self.title_label = make_label(self.header_frame, self.text["title"], size=30, weight="bold", color=C_CYAN)
        self.title_label.pack()
        self.version_label = make_label(self.header_frame, self.version_text(), size=12)
        self.version_label.pack(pady=(0, 5))

        self.update_frame = make_panel(self, border=C_ORANGE, radius=10)
        self.update_frame.pack(pady=5, padx=25, fill="x")
        self.update_label = make_label(self.update_frame, self.text["update_check"], size=12)
        self.update_label.pack(pady=5)
        self.update_btn = make_button(self.update_frame, self.text["check_updates"], self.check_updates, size=12, weight="bold", height=30, corner_radius=8)
        self.update_btn.pack(pady=(0, 5))

        self.status_frame = make_panel(self, border=C_CYAN, radius=12)
        self.status_frame.pack(pady=5, padx=25, fill="x")
        self.status_label = make_label(self.status_frame, self.text["status_not_installed"], size=14, weight="bold")
        self.status_label.pack(pady=8)

        self.list_frame = make_panel(self, border=C_CYAN, radius=15, border_width=2)
        self.list_frame.pack(pady=10, padx=25, fill="both", expand=True)
        self.list_label = make_label(self.list_frame, self.text["strategies"], size=14, weight="bold")
        self.list_label.pack(pady=(10, 5))
        self.scroll_frame = ctk.CTkScrollableFrame(self.list_frame, fg_color="transparent", height=280)
        self.scroll_frame.pack(pady=5, padx=10, fill="both", expand=True)

        self.settings_frame = make_panel(self, border=C_ORANGE, radius=15, border_width=2)
        self.settings_frame.pack(pady=10, padx=25, fill="x")
        self.settings_label = make_label(self.settings_frame, self.text["settings"], size=14, weight="bold")
        self.settings_label.pack(pady=(8, 5))
        self.settings_btn = make_button(
            self.settings_frame, self.text["open_settings"], self.open_settings,
            size=15, weight="bold", height=45, corner_radius=10, border_width=1, border_color=C_ORANGE,
        )
        self.settings_btn.pack(pady=(5, 8), padx=15, fill="x")
        self.autostart_var = ctk.IntVar(value=0)
        self.autostart_switch = ctk.CTkSwitch(
            self.settings_frame, text=self.text["autostart"], variable=self.autostart_var,
            command=self.toggle_autostart, font=app_font(size=13), text_color=C_TEXT, progress_color=C_ACCENT,
        )
        self.autostart_switch.pack(pady=(0, 10), padx=20, anchor="w")

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=5, padx=25, fill="x")
        self.refresh_btn = make_button(self.btn_frame, self.text["refresh"], self.refresh_strategies, style="neutral", weight="bold", height=35, corner_radius=10)
        self.refresh_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.remove_btn = make_button(self.btn_frame, self.text["remove"], self.remove_service, style="danger", weight="bold", height=35, corner_radius=10, state="disabled")
        self.remove_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.stop_btn = make_button(self.btn_frame, self.text["stop"], self.stop_strategy, style="warning", weight="bold", height=35, corner_radius=10, state="disabled")
        self.stop_btn.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.btn_frame.grid_columnconfigure(0, weight=1)
        self.btn_frame.grid_columnconfigure(1, weight=1)

        self.footer_label = make_label(self, f"{APP_PATH}", size=9)
        self.footer_label.pack(pady=(0, 10))

    def version_text(self):
        return f"{self.text['version']} {CURRENT_VERSION} | {self.text['strategies']}"

    def is_ready(self):
        return self.initial_status_done

    def report_callback_exception(self, exc_type, exc, tb):
        logger.error("Ошибка в обработчике Tk", exc_info=(exc_type, exc, tb))

    def destroy(self):
        self._closing = True
        for job in (self._ui_job, self._status_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        super().destroy()

    def ui(self, func):
        self._ui_queue.put(func)

    def _poll_ui_queue(self):
        if self._closing:
            return
        while True:
            try:
                func = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func()
            except Exception:
                logger.exception("Ошибка в UI-колбэке")
        self._ui_job = self.after(50, self._poll_ui_queue)

    def change_lang(self, choice):
        self.lang = LANG_CHOICES.get(choice, "ru")
        self.text = LANG[self.lang]
        self.settings["lang"] = self.lang
        save_settings(self.settings)
        self.update_ui_text()

    def update_ui_text(self):
        self.title_label.configure(text=self.text["title"])
        self.version_label.configure(text=self.version_text())
        self.list_label.configure(text=self.text["strategies"])
        self.settings_label.configure(text=self.text["settings"])
        self.settings_btn.configure(text=self.text["open_settings"])
        self.autostart_switch.configure(text=self.text["autostart"])
        self.refresh_btn.configure(text=self.text["refresh"])
        self.remove_btn.configure(text=self.text["remove"])
        self.stop_btn.configure(text=self.text["stop"])
        self.refresh_update_label()
        self.render_status()
        self.load_strategies(keep_scroll=True)

    def ensure_admin(self):
        if is_admin():
            return True
        if messagebox.askyesno(self.text["admin_required"], self.text["admin_required_msg"]):
            if relaunch_elevated():
                self.destroy()
        return False

    def set_status(self, key, color, *args):
        self.status_view = (key, color, args)
        self.render_status()

    def render_status(self):
        key, color, args = self.status_view
        text = self.text[key].format(*args) if args else self.text[key]
        self.status_label.configure(text=text, text_color=color)

    def check_status(self):
        if self._closing:
            return
        if not self._status_busy:
            self._status_busy = True
            Thread(target=self._status_worker, daemon=True).start()
        if self._status_job:
            try:
                self.after_cancel(self._status_job)
            except Exception:
                pass
        self._status_job = self.after(STATUS_POLL_MS, self.check_status)

    def _status_worker(self):
        try:
            snapshot = (query_service_state(), is_process_running(STRATEGY_PROCESS))
        except Exception:
            logger.exception("Ошибка проверки статуса сервиса zapret")
            snapshot = None
        self.ui(lambda: self._apply_status(snapshot))

    def _apply_status(self, snapshot):
        self._status_busy = False
        self.initial_status_done = True
        if snapshot is None:
            return
        service_state, process_running = snapshot
        installed = service_state is not None
        service_running = service_state == SERVICE_RUNNING
        in_grace = time.time() < self.launch_grace_until

        if not process_running and self.active_strategy and not in_grace:
            self.active_strategy = None
            self.refresh_strategy_buttons()

        self.remove_btn.configure(state="normal" if installed else "disabled")
        self.stop_btn.configure(state="normal" if process_running else "disabled")

        if not process_running and self.active_strategy and in_grace:
            return

        if service_running:
            self.set_status("status_enabled", C_GREEN)
        elif process_running and self.active_strategy:
            self.set_status("status_strategy_named", C_GREEN, display_name(self.active_strategy))
        elif process_running:
            self.set_status("status_strategy_running", C_GREEN)
        elif installed:
            self.set_status("status_disabled", C_ORANGE)
        else:
            self.set_status("status_not_installed", C_RED)

    def set_update_state(self, state):
        self.update_state = state
        self.refresh_update_label()

    def refresh_update_label(self):
        state = self.update_state
        labels = {
            "available": (self.text["update_available"].format(self.latest_version), C_GREEN),
            "latest": (self.text["update_latest"], C_GREEN),
            "error": (self.text["update_error"], C_RED),
            "rate_limit": (self.text["update_rate_limit"], C_RED),
            "checking": (self.text["update_check"], C_ORANGE),
            "downloading": (self.text["update_downloading"].format(self.update_progress), C_ORANGE),
            "hash_error": (self.text["update_hash_error"], C_RED),
            "download_error": (self.text["update_download_error"], C_RED),
        }
        message, color = labels.get(state, (self.text["update_check"], C_TEXT))
        self.update_label.configure(text=message, text_color=color)
        if state == "available":
            self.update_btn.configure(text=self.text["download_update"], command=self.download_update, state="normal", **BUTTON_STYLES["accent"])
        else:
            self.update_btn.configure(
                text=self.text["check_updates"], command=self.check_updates,
                state="disabled" if state in ("checking", "downloading") else "normal", **BUTTON_STYLES["default"],
            )

    def check_updates(self):
        if self.update_state == "checking":
            return
        self.set_update_state("checking")
        Thread(target=self._check_updates_worker, daemon=True).start()

    def _check_updates_worker(self):
        try:
            response = requests.get(
                GITHUB_API_URL,
                timeout=10,
                headers={"User-Agent": "hux-huxLauncher", "Accept": "application/vnd.github+json"},
            )
            if response.status_code == 200:
                data = response.json()
                latest = parse_version(data.get("tag_name", ""))
                if latest and is_newer_version(latest, CURRENT_VERSION_TUPLE):
                    url = str(data.get("html_url", ""))
                    if not url.startswith("https://github.com/"):
                        url = GITHUB_RELEASES_URL
                    version = ".".join(str(part) for part in latest)
                    asset = self.select_update_asset(data.get("assets", []))
                    self.ui(lambda: self.on_update_available(version, url, asset))
                else:
                    self.ui(lambda: self.set_update_state("latest"))
            elif response.status_code in (403, 429):
                logger.warning("Лимит GitHub API, статус %s", response.status_code)
                self.ui(lambda: self.set_update_state("rate_limit"))
            else:
                logger.warning("GitHub API вернул статус %s", response.status_code)
                self.ui(lambda: self.set_update_state("error"))
        except Exception:
            logger.exception("Ошибка при проверке обновлений")
            self.ui(lambda: self.set_update_state("error"))

    def on_update_available(self, version, url, asset):
        self.latest_version = version
        self.download_url = url
        self.update_asset = asset
        self.set_update_state("available")

    def select_update_asset(self, assets):
        if not isinstance(assets, list):
            return None
        executables = [
            a for a in assets
            if isinstance(a, dict) and str(a.get("name", "")).lower().endswith(".exe")
        ]
        if not executables:
            return None
        current_name = os.path.basename(get_executable_path()).lower()
        same_channel = [a for a in executables if build_channel(a["name"]) == build_channel(current_name)]
        if not same_channel:
            return None
        asset = next((a for a in same_channel if a["name"].lower() == current_name), same_channel[0])
        url = str(asset.get("browser_download_url", ""))
        if not url.startswith("https://github.com/"):
            return None
        sha256 = self.find_asset_hash(assets, asset)
        if not sha256:
            return None
        try:
            size = int(asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        return {"name": asset["name"], "url": url, "sha256": sha256, "size": size}

    def find_asset_hash(self, assets, asset):
        match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(asset.get("digest") or ""))
        if match:
            return match.group(1).lower()
        name = asset["name"].lower()
        per_file = {f"{name}.sha256", f"{name}.sha256sum"}
        aggregated = {"sha256sums.txt", "sha256sums", "checksums.txt"}
        for candidate in assets:
            if not isinstance(candidate, dict):
                continue
            candidate_name = str(candidate.get("name", "")).lower()
            if candidate_name not in per_file | aggregated:
                continue
            url = str(candidate.get("browser_download_url", ""))
            if not url.startswith("https://github.com/"):
                continue
            try:
                response = requests.get(url, timeout=10, headers={"User-Agent": "hux-huxLauncher"})
                response.raise_for_status()
                lines = response.text.splitlines()
            except Exception:
                logger.exception("Не удалось получить контрольную сумму из %s", candidate_name)
                continue
            matched = [line for line in lines if name in line.lower()]
            if not matched and candidate_name in per_file:
                matched = lines[:1]
            for line in matched:
                found = re.search(r"\b[0-9a-fA-F]{64}\b", line)
                if found:
                    return found.group(0).lower()
        return None

    def set_update_progress(self, percent):
        self.update_progress = percent
        self.refresh_update_label()

    def download_update(self):
        asset = self.update_asset
        can_install = bool(asset) and is_compiled() and get_executable_path().lower().endswith(".exe")
        if can_install:
            if messagebox.askyesno(self.text["update_available_title"], self.text["update_install_msg"].format(self.latest_version)):
                self.update_progress = 0
                self.set_update_state("downloading")
                Thread(target=self._install_update_worker, args=(asset,), daemon=True).start()
            return
        if messagebox.askyesno(self.text["update_available_title"], self.text["update_available_msg"].format(self.latest_version)):
            webbrowser.open(self.download_url)

    def _install_update_worker(self, asset):
        new_path = None
        try:
            new_path = get_executable_path() + ".new"
            digest = hashlib.sha256()
            with requests.get(asset["url"], stream=True, timeout=30, headers={"User-Agent": "hux-huxLauncher"}) as response:
                response.raise_for_status()
                if not response.url.startswith("https://"):
                    raise ValueError("Небезопасный адрес загрузки")
                total = int(response.headers.get("Content-Length") or asset["size"] or 0)
                received = 0
                last_percent = -1
                with open(new_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        f.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if total:
                            percent = min(100, received * 100 // total)
                            if percent != last_percent:
                                last_percent = percent
                                self.ui(lambda p=percent: self.set_update_progress(p))
            if received == 0 or (total and received != total):
                raise ValueError("Неполная загрузка обновления")
            if digest.hexdigest() != asset["sha256"]:
                logger.error("Контрольная сумма обновления не совпала")
                os.remove(new_path)
                self.ui(lambda: self.set_update_state("hash_error"))
                return
            self.ui(lambda: self.apply_update(new_path, asset["sha256"]))
        except Exception:
            logger.exception("Ошибка загрузки обновления")
            if new_path and os.path.exists(new_path):
                try:
                    os.remove(new_path)
                except OSError:
                    pass
            self.ui(lambda: self.set_update_state("download_error"))

    def apply_update(self, new_path, expected_sha256):
        target = get_executable_path()
        old_path = target + ".old"
        renamed = False
        try:
            if file_sha256(new_path) != expected_sha256:
                logger.error("Контрольная сумма файла обновления изменилась перед установкой")
                os.remove(new_path)
                self.set_update_state("hash_error")
                return
            if os.path.exists(old_path):
                os.remove(old_path)
            os.rename(target, old_path)
            renamed = True
            os.rename(new_path, target)
            subprocess.Popen([target, "--updated"], cwd=os.path.dirname(target), close_fds=True)
            self.destroy()
        except Exception:
            logger.exception("Ошибка применения обновления")
            if renamed and not os.path.exists(target) and os.path.exists(old_path):
                try:
                    os.rename(old_path, target)
                except OSError:
                    logger.exception("Не удалось откатить обновление")
            self.set_update_state("download_error")


    def get_favorites(self):
        favorites = self.settings.get("favorites", [])
        return list(favorites) if isinstance(favorites, list) else []

    def toggle_favorite(self, name):
        favorites = self.get_favorites()
        if name in favorites:
            favorites.remove(name)
        else:
            favorites.append(name)
        self.settings["favorites"] = favorites
        save_settings(self.settings)
        self.load_strategies(keep_scroll=True)

    def get_all_bat_files(self):
        files = []
        try:
            for f in os.listdir(self.zapret_dir):
                full_path = os.path.join(self.zapret_dir, f)
                if os.path.isfile(full_path) and f.lower().endswith(".bat") and f.lower() != "service.bat":
                    files.append(f)
        except Exception:
            logger.exception("Ошибка при получении списка .bat файлов")

        def sort_key(name):
            lowered = name.lower()
            if lowered == "general.bat":
                return (0, "")
            if lowered.startswith("general ("):
                return (1, natural_key(lowered))
            return (2, natural_key(lowered))

        files.sort(key=sort_key)
        return files

    def strategy_label(self, name):
        marker = "●" if name == self.active_strategy else ">"
        return f"{marker} {display_name(name)}"

    def refresh_strategy_buttons(self):
        for name, button in self.strategy_buttons.items():
            active = name == self.active_strategy
            button.configure(
                text=self.strategy_label(name),
                border_width=2 if active else 1,
                border_color=C_GREEN if active else C_BTN_BORDER,
            )

    def add_section_label(self, text):
        make_label(self.scroll_frame, text, size=11, weight="bold", color=C_MUTED).pack(anchor="w", padx=8, pady=(6, 2))

    def add_strategy_row(self, name, favorited):
        row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        row.pack(pady=2, padx=5, fill="x")
        row.grid_columnconfigure(0, weight=1)

        button = make_button(
            row, self.strategy_label(name), lambda n=name: self.run_strategy(n),
            style="strategy", size=12, height=35, corner_radius=8, anchor="w", border_width=1, border_color=C_BTN_BORDER,
        )
        button.grid(row=0, column=0, sticky="ew")
        self.strategy_buttons[name] = button

        star = make_button(
            row, "★" if favorited else "☆", lambda n=name: self.toggle_favorite(n),
            size=14, weight="bold", width=35, height=35, corner_radius=8,
            text_color=C_ORANGE if favorited else C_MUTED,
        )
        star.grid(row=0, column=1, padx=(5, 0))

    def load_strategies(self, keep_scroll=False):
        canvas = getattr(self.scroll_frame, "_parent_canvas", None)
        position = canvas.yview()[0] if (keep_scroll and canvas is not None) else 0.0

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.strategy_buttons.clear()

        all_files = self.get_all_bat_files()
        favorites = set(self.get_favorites())
        favorite_files = [name for name in all_files if name in favorites]
        other_files = [name for name in all_files if name not in favorites]
        self.strategies = favorite_files + other_files

        if self.strategies:
            if favorite_files:
                self.add_section_label(self.text["favorites"])
                for name in favorite_files:
                    self.add_strategy_row(name, True)
                if other_files:
                    self.add_section_label(self.text["all_strategies"])
            for name in other_files:
                self.add_strategy_row(name, False)
            self.list_label.configure(text=self.text["strategies_found"].format(len(self.strategies)))
            self.refresh_strategy_buttons()
        else:
            make_label(self.scroll_frame, self.text["no_strategies"].format(self.zapret_dir), color=C_RED, justify="center").pack(pady=30)
            self.list_label.configure(text=self.text["strategies_not_found"])

        if keep_scroll and canvas is not None:
            self.update_idletasks()
            canvas.yview_moveto(position)

    def refresh_strategies(self):
        self.load_strategies()
        self.check_status()

    def run_strategy(self, name):
        if not self.ensure_admin():
            return
        full_path = os.path.join(self.zapret_dir, name)
        if not os.path.isfile(full_path):
            messagebox.showerror(self.text["error_title"], self.text["file_not_found"].format(full_path))
            self.load_strategies()
            return
        self.launch_grace_until = time.time() + LAUNCH_GRACE_SECONDS
        self.set_status("starting", C_ORANGE, name)
        Thread(target=self._launch_worker, args=(name, full_path), daemon=True).start()

    def _launch_worker(self, name, full_path):
        try:
            if is_process_running(STRATEGY_PROCESS):
                kill_process(STRATEGY_PROCESS)
                time.sleep(0.7)
            subprocess.Popen(
                ["cmd", "/c", full_path],
                cwd=self.zapret_dir,
                creationflags=CREATE_NEW_CONSOLE,
            )
            self.ui(lambda: self.on_strategy_started(name))
        except Exception as e:
            logger.exception("Ошибка запуска стратегии %s", name)
            message = str(e)[:50]
            self.ui(lambda: self.on_strategy_error(message))

    def on_strategy_started(self, name):
        self.active_strategy = name
        self.refresh_strategy_buttons()
        self.set_status("started", C_GREEN, name)
        self.after(3000, self.check_status)

    def on_strategy_error(self, message):
        self.launch_grace_until = 0.0
        self.set_status("error_msg", C_RED, message)

    def stop_strategy(self):
        if not self.ensure_admin():
            return
        self.stop_btn.configure(state="disabled")
        Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        try:
            kill_process(STRATEGY_PROCESS)
            self.ui(self.on_strategy_stopped)
        except Exception as e:
            logger.exception("Ошибка остановки стратегии")
            message = str(e)[:50]
            self.ui(lambda: self.on_strategy_error(message))

    def on_strategy_stopped(self):
        self.active_strategy = None
        self.launch_grace_until = 0.0
        self.refresh_strategy_buttons()
        self.set_status("stopped", C_ORANGE)
        self.after(1000, self.check_status)

    def apply_zapret_source(self, mode, path=None):
        self.settings["zapret_mode"] = mode
        if mode == "custom":
            self.settings["zapret_custom_path"] = path
        else:
            self.settings.pop("zapret_custom_path", None)
        save_settings(self.settings)
        self.zapret_dir = prepare_zapret_dir(self.settings)
        self.load_strategies()

    def open_zapret_source_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.text["zapret_source_title"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.configure(fg_color=C_BG)
        x = self.winfo_x() + (self.winfo_width() // 2) - 210
        y = self.winfo_y() + (self.winfo_height() // 2) - 110
        dialog.geometry(f"420x220+{x}+{y}")
        dialog.grab_set()

        current_mode = self.settings.get("zapret_mode", "builtin")

        make_label(dialog, self.text["zapret_source_heading"], size=16, weight="bold", color=C_CYAN).pack(pady=(15, 10))
        make_label(dialog, self.text["zapret_source_current"].format(self.zapret_dir), size=11, wraplength=380).pack(pady=(0, 15))

        def use_builtin():
            self.apply_zapret_source("builtin")
            dialog.destroy()

        def use_custom():
            folder = filedialog.askdirectory(title=self.text["zapret_source_pick_folder"], parent=dialog)
            if not folder:
                return
            self.apply_zapret_source("custom", folder)
            dialog.destroy()

        builtin_prefix = "✅ " if current_mode != "custom" else ""
        custom_prefix = "✅ " if current_mode == "custom" else ""
        make_button(dialog, builtin_prefix + self.text["zapret_source_builtin"], use_builtin, style="strategy", height=38).pack(pady=5, padx=30, fill="x")
        make_button(dialog, custom_prefix + self.text["zapret_source_custom"], use_custom, style="strategy", height=38).pack(pady=5, padx=30, fill="x")

    def _autostart_query_worker(self):
        try:
            enabled = query_autostart()
        except Exception:
            logger.exception("Ошибка проверки автозапуска")
            return
        self.ui(lambda: self.autostart_var.set(1 if enabled else 0))

    def toggle_autostart(self):
        wanted = bool(self.autostart_var.get())
        if not self.ensure_admin():
            self.autostart_var.set(0 if wanted else 1)
            return
        self.autostart_switch.configure(state="disabled")
        Thread(target=self._autostart_worker, args=(wanted,), daemon=True).start()

    def _autostart_worker(self, wanted):
        try:
            success = set_autostart(wanted)
        except Exception:
            logger.exception("Ошибка изменения автозапуска")
            success = False
        try:
            actual = query_autostart()
        except Exception:
            actual = wanted if success else not wanted
        self.ui(lambda: self.on_autostart_done(success, actual))

    def on_autostart_done(self, success, actual):
        self.autostart_var.set(1 if actual else 0)
        self.autostart_switch.configure(state="normal")
        if not success:
            messagebox.showerror(self.text["error_title"], self.text["autostart_error"])

    def open_settings(self):
        if not self.ensure_admin():
            return
        service_path = os.path.join(self.zapret_dir, "service.bat")
        if not os.path.isfile(service_path):
            messagebox.showerror(self.text["error_title"], self.text["service_not_found"].format(self.zapret_dir))
            return
        try:
            subprocess.Popen(
                ["cmd", "/c", service_path, "admin"],
                cwd=self.zapret_dir,
                creationflags=CREATE_NEW_CONSOLE,
            )
            custom_folder = self.zapret_dir != BUILTIN_ZAPRET_DIR
            HelpWindow(self, self.lang, custom_folder).focus()
        except Exception as e:
            logger.exception("Ошибка открытия настроек")
            messagebox.showerror(self.text["error_title"], str(e))

    def remove_service(self):
        if not self.ensure_admin():
            return
        if not messagebox.askyesno(self.text["remove_confirm"], self.text["remove_confirm_msg"]):
            return
        self.remove_btn.configure(state="disabled")
        Thread(target=self._remove_worker, daemon=True).start()

    def _remove_worker(self):
        try:
            run_hidden(["net", "stop", SERVICE_NAME], timeout=15)
            run_hidden(["sc", "delete", SERVICE_NAME], timeout=10)
            kill_process(STRATEGY_PROCESS)
            for service in WINDIVERT_SERVICES:
                run_hidden(["net", "stop", service], timeout=15)
                run_hidden(["sc", "delete", service], timeout=10)
            self.ui(self.on_service_removed)
        except Exception as e:
            logger.exception("Ошибка удаления сервиса zapret")
            message = str(e)
            self.ui(lambda: self.on_remove_failed(message))

    def on_service_removed(self):
        self.active_strategy = None
        self.launch_grace_until = 0.0
        self.refresh_strategy_buttons()
        self.set_status("status_removed", C_RED)
        self.after(1000, self.check_status)

    def on_remove_failed(self, message):
        messagebox.showerror(self.text["error_title"], message)
        self.check_status()


def main():
    argv = sys.argv[1:]
    settings = load_settings()
    skip_flags = {"--elevated", "--updated", "--autostart", "--no-elevate"}
    if not is_admin() and settings.get("auto_elevate", True) and not skip_flags.intersection(argv):
        if relaunch_elevated():
            return

    instance = SingleInstance(MUTEX_NAME, wait=8.0 if {"--elevated", "--updated"}.intersection(argv) else 0.0)
    if not instance.acquire():
        focus_existing_window()
        return

    cleanup_update_leftovers()
    Thread(target=delayed_unpack_cleanup, daemon=True).start()
    app = HuxHuxLauncher()
    if "--autostart" in argv:
        app.iconify()
        app.mainloop()
        return
    splash = SplashScreen(app.lang, app.is_ready)
    splash.update()

    def show_main():
        app.deiconify()
        app.attributes("-topmost", True)
        app.attributes("-topmost", False)

    def wait_for_splash():
        try:
            if splash.winfo_exists():
                app.after(100, wait_for_splash)
                return
        except Exception:
            pass
        show_main()

    app.after(100, wait_for_splash)
    app.mainloop()


if __name__ == "__main__":
    main()
