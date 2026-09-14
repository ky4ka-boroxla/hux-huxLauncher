import customtkinter as ctk
import subprocess
import os
import sys
import ctypes
import time
import requests
import webbrowser
import logging
import json
from tkinter import messagebox, filedialog
from threading import Thread
from PIL import Image, ImageTk
import re
import tempfile

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CURRENT_VERSION = "1.0.8"

CREATE_NEW_CONSOLE = 0x00000010

def get_log_path():
    try:
        return os.path.join(get_app_path(), "hux-launcher.log")
    except Exception:
        return os.path.join(tempfile.gettempdir(), "hux-launcher.log")

logger = logging.getLogger("hux-huxLauncher")
logger.setLevel(logging.INFO)
GITHUB_REPO = "ky4ka-boroxla/hux-huxLauncher"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def get_app_path():
    try:
        return __compiled__.containing_dir
    except NameError:
        if getattr(sys, 'frozen', False):
            exe_path = sys.argv[0]
            if '~' in exe_path:
                try:
                    buffer = ctypes.create_unicode_buffer(260)
                    ret = ctypes.windll.kernel32.GetLongPathNameW(exe_path, buffer, 260)
                    if ret:
                        exe_path = buffer.value
                except Exception:
                    pass
            return os.path.dirname(os.path.abspath(exe_path))
        else:
            return os.path.dirname(os.path.abspath(__file__))

def get_base_path():
    return os.path.dirname(os.path.abspath(__file__))

APP_PATH = get_app_path()
BASE_PATH = get_base_path()
BUILTIN_ZAPRET_DIR = os.path.join(BASE_PATH, "zapret")
SETTINGS_PATH = os.path.join(APP_PATH, "hux-launcher-settings.json")

CUSTOM_FONT_PATH = os.path.join(BASE_PATH, "fnt_dotumche.ttf")
CUSTOM_FONT_FAMILY = None

FR_PRIVATE = 0x10
FR_NOT_ENUM = 0x20

def load_custom_font():
    global CUSTOM_FONT_FAMILY
    if not os.path.exists(CUSTOM_FONT_PATH):
        return None
    try:
        ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(CUSTOM_FONT_PATH), FR_PRIVATE, 0)
    except Exception:
        logger.exception("Ошибка регистрации шрифта %s", CUSTOM_FONT_PATH)
    try:
        from PIL import ImageFont
        family, _ = ImageFont.truetype(CUSTOM_FONT_PATH, 12).getname()
        CUSTOM_FONT_FAMILY = family
    except Exception:
        logger.exception("Не удалось определить имя шрифта %s", CUSTOM_FONT_PATH)
        CUSTOM_FONT_FAMILY = None
    return CUSTOM_FONT_FAMILY

load_custom_font()

def app_font(size=13, weight="normal"):
    if CUSTOM_FONT_FAMILY:
        return ctk.CTkFont(family=CUSTOM_FONT_FAMILY, size=size, weight=weight)
    return ctk.CTkFont(size=size, weight=weight)

def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Ошибка сохранения настроек")

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
        for root, dirs, files in os.walk(zapret_dir):
            for f in files:
                if f.endswith(".dat"):
                    original_name = f[:-4]
                    src = os.path.join(root, f)
                    dst = os.path.join(root, original_name)
                    if not os.path.exists(dst):
                        os.rename(src, dst)
    except Exception:
        logger.exception("Ошибка восстановления файлов zapret из .dat")

try:
    _log_handler = logging.FileHandler(os.path.join(APP_PATH, "hux-launcher.log"), encoding="utf-8")
    _log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_log_handler)
except Exception:
    pass

LANG = {
    "ru": {
        "title": "HUX-HUX LAUNCHER",
        "version": "Версия",
        "status_not_installed": "Статус: Не установлен",
        "status_installed": "Статус: Установлен",
        "status_enabled": "Статус: ВКЛЮЧЕН",
        "status_disabled": "Статус: ВЫКЛЮЧЕН",
        "status_removed": "Сервис удалён",
        "strategies": "СТРАТЕГИИ",
        "strategies_found": "СТРАТЕГИИ ({})",
        "strategies_not_found": "СТРАТЕГИИ НЕ НАЙДЕНЫ",
        "settings": "НАСТРОЙКИ",
        "open_settings": "ОТКРЫТЬ НАСТРОЙКИ",
        "refresh": "ОБНОВИТЬ СПИСОК",
        "remove": "УДАЛИТЬ СЕРВИС",
        "update_check": "Проверка обновлений...",
        "update_available": "Доступна версия: {}",
        "update_latest": "У вас последняя версия",
        "update_error": "Не удалось проверить обновления",
        "update_error2": "Ошибка проверки обновлений",
        "check_updates": "ПРОВЕРИТЬ ОБНОВЛЕНИЯ",
        "download_update": "СКАЧАТЬ ОБНОВЛЕНИЕ",
        "no_strategies": "Нет стратегий!\n\nПоложи .bat файлы в папку:\n{}\n\nи нажми 'Обновить список'",
        "admin_required": "Права администратора",
        "admin_required_msg": "Для запуска стратегии нужны права администратора.\n\nРазрешить запуск от имени администратора?",
        "settings_admin": "Внимание!",
        "settings_admin_msg": "Для настроек нужны права администратора!\nПерезапустите программу от имени администратора.",
        "service_not_found": "Файл service.bat не найден!\n\nПуть: {}",
        "remove_confirm": "Подтверждение",
        "remove_confirm_msg": "Вы уверены, что хотите удалить сервис Zapret?",
        "update_available_title": "Обновление",
        "update_available_msg": "Доступна новая версия {}\n\nОткрыть страницу загрузки?",
        "loading": "Загрузка...",
        "ready": "Готово!",
        "steps": ["Загрузка иконок...", "Проверка обновлений...", "Загрузка конфигурации...", "Подготовка интерфейса...", "Запуск..."],
        "documentation": "Документация",
        "where_to_click": "КУДА ТЫКАТЬ",
        "doc_instruction": "В открывшейся консоли введите цифру и нажмите Enter:",
        "doc_close": "ПОНЯЛ, ЗАКРЫТЬ",
        "doc_items": [
            ("1", "Установить сервис"),
            ("2", "Удалить сервис"),
            ("3", "Проверить статус"),
            ("4", "Game Filter"),
            ("5", "IPSet Filter"),
            ("6", "Auto-Update"),
            ("7", "Обновить IPSet"),
            ("8", "Обновить Hosts"),
            ("9", "Проверить обновления"),
            ("10", "Диагностика"),
            ("11", "Тесты")
        ],
        "zapret_source_title": "Zapret",
        "zapret_source_heading": "Источник zapret",
        "zapret_source_current": "Сейчас: {}",
        "zapret_source_builtin": "Встроенный (из exe)",
        "zapret_source_custom": "Своя папка...",
        "zapret_source_pick_folder": "Выбери папку zapret"
    },
    "en": {
        "title": "HUX-HUX LAUNCHER",
        "version": "Version",
        "status_not_installed": "Status: Not installed",
        "status_installed": "Status: Installed",
        "status_enabled": "Status: ENABLED",
        "status_disabled": "Status: DISABLED",
        "status_removed": "Service removed",
        "strategies": "STRATEGIES",
        "strategies_found": "STRATEGIES ({})",
        "strategies_not_found": "STRATEGIES NOT FOUND",
        "settings": "SETTINGS",
        "open_settings": "OPEN SETTINGS",
        "refresh": "REFRESH LIST",
        "remove": "REMOVE SERVICE",
        "update_check": "Checking for updates...",
        "update_available": "Version {} available",
        "update_latest": "You have the latest version",
        "update_error": "Failed to check updates",
        "update_error2": "Update check error",
        "check_updates": "CHECK UPDATES",
        "download_update": "DOWNLOAD UPDATE",
        "no_strategies": "No strategies!\n\nPut .bat files in folder:\n{}\n\nand click 'Refresh list'",
        "admin_required": "Administrator rights",
        "admin_required_msg": "Administrator rights are required to run strategy.\n\nAllow running as administrator?",
        "settings_admin": "Attention!",
        "settings_admin_msg": "Administrator rights required for settings!\nRestart the program as administrator.",
        "service_not_found": "service.bat file not found!\n\nPath: {}",
        "remove_confirm": "Confirmation",
        "remove_confirm_msg": "Are you sure you want to remove the Zapret service?",
        "update_available_title": "Update",
        "update_available_msg": "New version {} available\n\nOpen download page?",
        "loading": "Loading...",
        "ready": "Ready!",
        "steps": ["Loading icons...", "Checking updates...", "Loading configuration...", "Preparing interface...", "Starting..."],
        "documentation": "Documentation",
        "where_to_click": "WHERE TO CLICK",
        "doc_instruction": "In the opened console, enter the number and press Enter:",
        "doc_close": "GOT IT, CLOSE",
        "doc_items": [
            ("1", "Install service"),
            ("2", "Remove service"),
            ("3", "Check status"),
            ("4", "Game Filter"),
            ("5", "IPSet Filter"),
            ("6", "Auto-Update"),
            ("7", "Update IPSet"),
            ("8", "Update Hosts"),
            ("9", "Check updates"),
            ("10", "Diagnostics"),
            ("11", "Run Tests")
        ],
        "zapret_source_title": "Zapret",
        "zapret_source_heading": "Zapret source",
        "zapret_source_current": "Current: {}",
        "zapret_source_builtin": "Built-in (from exe)",
        "zapret_source_custom": "Custom folder...",
        "zapret_source_pick_folder": "Pick zapret folder"
    },
    "uk": {
        "title": "HUX-HUX LAUNCHER",
        "version": "Версія",
        "status_not_installed": "Статус: Не встановлено",
        "status_installed": "Статус: Встановлено",
        "status_enabled": "Статус: УВІМКНЕНО",
        "status_disabled": "Статус: ВИМКНЕНО",
        "status_removed": "Сервіс видалено",
        "strategies": "СТРАТЕГІЇ",
        "strategies_found": "СТРАТЕГІЇ ({})",
        "strategies_not_found": "СТРАТЕГІЇ НЕ ЗНАЙДЕНО",
        "settings": "НАЛАШТУВАННЯ",
        "open_settings": "ВІДКРИТИ НАЛАШТУВАННЯ",
        "refresh": "ОНОВИТИ СПИСОК",
        "remove": "ВИДАЛИТИ СЕРВІС",
        "update_check": "Перевірка оновлень...",
        "update_available": "Доступна версія: {}",
        "update_latest": "У вас остання версія",
        "update_error": "Не вдалося перевірити оновлення",
        "update_error2": "Помилка перевірки оновлень",
        "check_updates": "ПЕРЕВІРИТИ ОНОВЛЕННЯ",
        "download_update": "ЗАВАНТАЖИТИ ОНОВЛЕННЯ",
        "no_strategies": "Немає стратегій!\n\nПоклади .bat файли в папку:\n{}\n\nі натисни 'Оновити список'",
        "admin_required": "Права адміністратора",
        "admin_required_msg": "Для запуску стратегії потрібні права адміністратора.\n\nДозволити запуск від імені адміністратора?",
        "settings_admin": "Увага!",
        "settings_admin_msg": "Для налаштувань потрібні права адміністратора!\nПерезапустіть програму від імені адміністратора.",
        "service_not_found": "Файл service.bat не знайдено!\n\nШлях: {}",
        "remove_confirm": "Підтвердження",
        "remove_confirm_msg": "Ви впевнені, що хочете видалити сервіс Zapret?",
        "update_available_title": "Оновлення",
        "update_available_msg": "Доступна нова версія {}\n\nВідкрити сторінку завантаження?",
        "loading": "Завантаження...",
        "ready": "Готово!",
        "steps": ["Завантаження іконок...", "Перевірка оновлень...", "Завантаження конфігурації...", "Підготовка інтерфейсу...", "Запуск..."],
        "documentation": "Документація",
        "where_to_click": "КУДИ ТИКАТИ",
        "doc_instruction": "У відкритій консолі введіть цифру і натисніть Enter:",
        "doc_close": "ЗРОЗУМІВ, ЗАКРИТИ",
        "doc_items": [
            ("1", "Встановити сервіс"),
            ("2", "Видалити сервіс"),
            ("3", "Перевірити статус"),
            ("4", "Game Filter"),
            ("5", "IPSet Filter"),
            ("6", "Auto-Update"),
            ("7", "Оновити IPSet"),
            ("8", "Оновити Hosts"),
            ("9", "Перевірити оновлення"),
            ("10", "Діагностика"),
            ("11", "Тести")
        ],
        "zapret_source_title": "Zapret",
        "zapret_source_heading": "Джерело zapret",
        "zapret_source_current": "Зараз: {}",
        "zapret_source_builtin": "Вбудований (з exe)",
        "zapret_source_custom": "Своя папка...",
        "zapret_source_pick_folder": "Обери папку zapret"
    },
    "be": {
        "title": "HUX-HUX LAUNCHER",
        "version": "Версія",
        "status_not_installed": "Статус: Не ўсталявана",
        "status_installed": "Статус: Усталявана",
        "status_enabled": "Статус: УКЛЮЧАНА",
        "status_disabled": "Статус: ВЫКЛЮЧАНА",
        "status_removed": "Сэрвіс выдалены",
        "strategies": "СТРАТЭГІІ",
        "strategies_found": "СТРАТЭГІІ ({})",
        "strategies_not_found": "СТРАТЭГІІ НЕ ЗНОЙДЗЕНЫ",
        "settings": "НАЛАДКІ",
        "open_settings": "АДКРЫЦЬ НАЛАДКІ",
        "refresh": "АБНАВІЦЬ СПІС",
        "remove": "ВЫДАЛІЦЬ СЭРВІС",
        "update_check": "Праверка абнаўленняў...",
        "update_available": "Даступная версія: {}",
        "update_latest": "У вас апошняя версія",
        "update_error": "Не ўдалося праверыць абнаўленні",
        "update_error2": "Памылка праверкі абнаўленняў",
        "check_updates": "ПРАВЕРЫЦЬ АБНАЎЛЕННІ",
        "download_update": "СЦЯГНУЦЬ АБНАЎЛЕННЕ",
        "no_strategies": "Няма стратэгій!\n\nПакладзі .bat файлы ў папку:\n{}\n\nі націсні 'Абнавіць спіс'",
        "admin_required": "Правы адміністратара",
        "admin_required_msg": "Для запуску стратэгіі патрэбны правы адміністратара.\n\nДазволіць запуск ад імя адміністратара?",
        "settings_admin": "Увага!",
        "settings_admin_msg": "Для наладак патрэбны правы адміністратара!\nПеразапусціце праграму ад імя адміністратара.",
        "service_not_found": "Файл service.bat не знойдзены!\n\nШлях: {}",
        "remove_confirm": "Пацверджанне",
        "remove_confirm_msg": "Вы ўпэўнены, што хочаце выдаліць сэрвіс Zapret?",
        "update_available_title": "Абнаўленне",
        "update_available_msg": "Даступная новая версія {}\n\nАдкрыць старонку загрузкі?",
        "loading": "Загрузка...",
        "ready": "Гатова!",
        "steps": ["Загрузка іконак...", "Праверка абнаўленняў...", "Загрузка канфігурацыі...", "Падрыхтоўка інтэрфейсу...", "Запуск..."],
        "documentation": "Дакументацыя",
        "where_to_click": "КУДЫ ТЫКАЦЬ",
        "doc_instruction": "У адкрытай кансолі ўвядзіце лічбу і націсніце Enter:",
        "doc_close": "ЗРАЗУМЕЎ, ЗАКРЫЦЬ",
        "doc_items": [
            ("1", "Усталяваць сэрвіс"),
            ("2", "Выдаліць сэрвіс"),
            ("3", "Праверыць статус"),
            ("4", "Game Filter"),
            ("5", "IPSet Filter"),
            ("6", "Auto-Update"),
            ("7", "Абнавіць IPSet"),
            ("8", "Абнавіць Hosts"),
            ("9", "Праверыць абнаўленні"),
            ("10", "Дыягностыка"),
            ("11", "Тэсты")
        ],
        "zapret_source_title": "Zapret",
        "zapret_source_heading": "Крыніца zapret",
        "zapret_source_current": "Зараз: {}",
        "zapret_source_builtin": "Убудаваны (з exe)",
        "zapret_source_custom": "Свая папка...",
        "zapret_source_pick_folder": "Абяры папку zapret"
    },
    "brat": {
        "title": "HUX-HUX LAUNCHER",
        "version": "Версия",
        "status_not_installed": "Статус: Не врублен",
        "status_installed": "Статус: Врублен",
        "status_enabled": "Статус: ЗАПУЩЕН",
        "status_disabled": "Статус: ЗАГЛУШЕН",
        "status_removed": "Сервис вырезан",
        "strategies": "СТРАТЕГИИ",
        "strategies_found": "СТРАТЕГИИ ({})",
        "strategies_not_found": "СТРАТЕГИЙ НЕТ, БРАТ",
        "settings": "НАСТРОЙКИ",
        "open_settings": "ГЛЯНУТЬ НАСТРОЙКИ",
        "refresh": "ОБНОВИТЬ СПИСОК",
        "remove": "ВЫРУБИТЬ СЕРВИС",
        "update_check": "Проверка обнов...",
        "update_available": "ты не в теме брат: {} ",
        "update_latest": "Ты в теме, брат!",
        "update_error": "Не пробит",
        "update_error2": "танк подорвали",
        "check_updates": "проверить что сейчас в теме",
        "download_update": "скачать обнову",
        "no_strategies": "йоу\n\nты забыл закинуть кидай в :\n{}\n\n",
        "admin_required": "Права админа",
        "admin_required_msg": "Для запуска стратегии нужны права админа.\n\nРазрешишь запуск от админа?",
        "settings_admin": "Внимание!",
        "settings_admin_msg": "Для настроек нужны права админа!\nПерезапусти прогу от админа.",
        "service_not_found": "Файл service.bat не найден!\n\nПуть: {}",
        "remove_confirm": "Подтверди",
        "remove_confirm_msg": "Точно хочешь вырубить сервис Zapret?",
        "update_available_title": "Обнова",
        "update_available_msg": "Есть новая версия {}\n\nОткрыть страницу загрузки?",
        "loading": "Грузим...",
        "ready": "Готово, брат!",
        "steps": ["Грузим иконки...", "Пьём пиво...", "Грузим конфиг...", "Готовим интерфейс...", "Взрыв вселеной...", "Погнали..."],
        "documentation": "Документация",
        "where_to_click": "КУДА ТЫКАТЬ БРАТ",
        "doc_instruction": "В открывшейся консоли введи цифру и жми Enter:",
        "doc_close": "понял? закрырыть",
        "doc_items": [
            ("1", "Врубить сервис"),
            ("2", "Вырубить сервис"),
            ("3", "Проверить статус"),
            ("4", "Game Filter"),
            ("5", "IPSet Filter"),
            ("6", "Auto-Update"),
            ("7", "Обновить IPSet"),
            ("8", "Обновить Hosts"),
            ("9", "Проверить обновы"),
            ("10", "Диагностика"),
            ("11", "Тесты")
        ],
        "zapret_source_title": "Zapret",
        "zapret_source_heading": "Откуда запрет, братан",
        "zapret_source_current": "Щас: {}",
        "zapret_source_builtin": "Зашитый (из exe)",
        "zapret_source_custom": "Своя папка, братиш...",
        "zapret_source_pick_folder": "Выбери папку с запретом"
    }
}

class SplashScreen(ctk.CTkToplevel):
    def __init__(self, lang="ru"):
        super().__init__()
        self.lang = lang
        self.text = LANG[lang]
        self.title("")
        self.geometry("400x480")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.configure(fg_color=("#0a0a1a", "#0d0d2b"))
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 200
        y = (self.winfo_screenheight() // 2) - 240
        self.geometry(f"+{x}+{y}")
        try:
            icon_path = os.path.join(BASE_PATH, "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        self.top_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=70)
        self.top_frame.pack(fill="x", pady=(30, 0))
        self.top_frame.pack_propagate(False)

        self.title_label = ctk.CTkLabel(self.top_frame, text=self.text["title"], font=app_font(size=32, weight="bold"), text_color="#00d4ff")
        self.title_label.pack(pady=(10, 0))

        self.version_label = ctk.CTkLabel(self.top_frame, text=f"{self.text['version']} {CURRENT_VERSION}", font=app_font(size=13), text_color=("black", "white"))
        self.version_label.pack()

        self.center_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.center_frame.pack(fill="both", expand=True)

        self.gif_label = ctk.CTkLabel(self.center_frame, text="")
        self.gif_label.pack(expand=True)

        gif_path = os.path.join(BASE_PATH, "hux.gif")

        if os.path.exists(gif_path):
            self.load_gif(gif_path)
        else:
            self.gif_label.configure(text="", font=app_font(size=80))

        self.bottom_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=100)
        self.bottom_frame.pack(fill="x", pady=(0, 30))
        self.bottom_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(self.bottom_frame, text=self.text["loading"], font=app_font(size=13), text_color=("black", "white"))
        self.status_label.pack(pady=(0, 8))

        self.progress = ctk.CTkProgressBar(self.bottom_frame, width=320, height=6, corner_radius=3, fg_color="#2d3748", progress_color="#00d4ff")
        self.progress.pack()
        self.progress.set(0)

        self.steps = self.text["steps"]
        self.current_step = 0
        self.start_time = time.time()
        self.animate_progress()
        self.animate_gif()

    def load_gif(self, gif_path):
        try:
            self.gif_frames = []
            self.gif_durations = []
            with Image.open(gif_path) as img:
                while True:
                    frame = img.copy()
                    frame.thumbnail((350, 350), Image.LANCZOS)
                    self.gif_frames.append(ImageTk.PhotoImage(frame))
                    self.gif_durations.append(img.info.get('duration', 100))
                    try:
                        img.seek(img.tell() + 1)
                    except EOFError:
                        break
            if self.gif_frames:
                self.gif_label.configure(image=self.gif_frames[0])
                self.current_gif_frame = 0
        except Exception as e:
            logger.exception("Ошибка загрузки GIF")
            self.gif_label.configure(text="", font=app_font(size=80))

    def animate_gif(self):
        if hasattr(self, 'gif_frames') and self.gif_frames:
            self.current_gif_frame = (self.current_gif_frame + 1) % len(self.gif_frames)
            self.gif_label.configure(image=self.gif_frames[self.current_gif_frame])
            duration = self.gif_durations[self.current_gif_frame] if self.current_gif_frame < len(self.gif_durations) else 100
            self.after(duration, self.animate_gif)
        else:
            self.after(100, self.animate_gif)

    def animate_progress(self):
        elapsed = time.time() - self.start_time
        total_time = 5.0
        progress = min(elapsed / total_time, 1.0)
        self.progress.set(progress)

        step_index = int(progress * len(self.steps))
        if step_index >= len(self.steps):
            step_index = len(self.steps) - 1
        if step_index != self.current_step:
            self.current_step = step_index
            self.status_label.configure(text=self.steps[step_index])

        if progress < 1.0:
            self.after(20, self.animate_progress)
        else:
            self.status_label.configure(text=self.text["ready"])
            self.progress.set(1.0)
            self.after(300, self.destroy)

class HelpWindow(ctk.CTkToplevel):
    def __init__(self, lang="ru"):
        super().__init__()
        self.lang = lang
        self.text = LANG[lang]
        self.title(self.text["documentation"])
        self.geometry("420x450")
        self.resizable(False, False)
        self.configure(fg_color=("#0a0a1a", "#0d0d2b"))
        self.attributes('-topmost', True)

        x = (self.winfo_screenwidth() // 2) - 210
        y = (self.winfo_screenheight() // 2) - 225
        self.geometry(f"+{x}+{y}")

        try:
            icon_path = os.path.join(BASE_PATH, "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.title_label = ctk.CTkLabel(self, text=self.text["where_to_click"], font=app_font(size=24, weight="bold"), text_color="#00d4ff")
        self.title_label.pack(pady=(15, 5))

        self.info_label = ctk.CTkLabel(self, text=self.text["doc_instruction"], font=app_font(size=14), text_color=("black", "white"))
        self.info_label.pack(pady=(0, 10))

        frame = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#16213e"), corner_radius=10, border_width=1, border_color="#00d4ff")
        frame.pack(pady=5, padx=20, fill="x")

        for i, (num, desc) in enumerate(self.text["doc_items"]):
            row = i // 2
            col = i % 2
            label = ctk.CTkLabel(frame, text=f"{num} -> {desc}", font=app_font(size=13), text_color=("black", "white"))
            label.grid(row=row, column=col, padx=10, pady=3, sticky="w")

        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        self.close_btn = ctk.CTkButton(self, text=self.text["doc_close"], command=self.destroy, font=app_font(size=14, weight="bold"), height=40, corner_radius=10, fg_color="#00b894", hover_color="#00a381")
        self.close_btn.pack(pady=(15, 15), padx=40, fill="x")

class HuxHuxLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.lang = "ru"
        self.text = LANG[self.lang]
        self.withdraw()
        self.title("hux-huxLauncher")
        self.geometry("600x850")
        self.resizable(False, False)
        self.configure(fg_color=("#0a0a1a", "#0d0d2b"))

        try:
            icon_path = os.path.join(BASE_PATH, "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self.strategies = []
        self.update_available = False
        self.latest_version = ""
        self.download_url = ""
        self.update_state = None
        self.settings = load_settings()
        self.zapret_dir = resolve_zapret_dir(self.settings)
        unstage_zapret_files(self.zapret_dir)

        self.top_controls = ctk.CTkFrame(self, fg_color="transparent", height=50)
        self.top_controls.pack(pady=(10, 0), padx=20, fill="x")
        self.top_controls.pack_propagate(False)

        self.lang_frame = ctk.CTkFrame(self.top_controls, fg_color="transparent")
        self.lang_frame.pack(side="right", padx=5)

        self.lang_label = ctk.CTkLabel(self.lang_frame, text="🌐", font=app_font(size=14))
        self.lang_label.pack(side="left", padx=(0, 5))

        self.lang_switch = ctk.CTkOptionMenu(
            self.lang_frame,
            values=["RU", "EN", "UA", "BE", "BRAT"],
            command=self.change_lang,
            font=app_font(size=12, weight="bold"),
            fg_color="#2d3748",
            button_color="#00d4ff",
            button_hover_color="#0077b6",
            width=80,
            height=30
        )
        self.lang_switch.pack(side="left")
        self.lang_switch.set("RU")

        self.zapret_source_btn = ctk.CTkButton(
            self.top_controls,
            text="📁",
            width=36,
            height=30,
            font=app_font(size=14),
            fg_color="#2d3748",
            hover_color="#4a5568",
            command=self.open_zapret_source_dialog,
        )
        self.zapret_source_btn.pack(side="left", padx=(5, 0))

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(pady=(5, 5), fill="x")
        self.title_label = ctk.CTkLabel(self.header_frame, text=self.text["title"], font=app_font(size=30, weight="bold"), text_color="#00d4ff")
        self.title_label.pack()
        self.version_label = ctk.CTkLabel(self.header_frame, text=f"{self.text['version']} {CURRENT_VERSION} | {self.text['strategies']}", font=app_font(size=12), text_color=("black", "white"))
        self.version_label.pack(pady=(0, 5))

        self.update_frame = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#16213e"), corner_radius=10, border_width=1, border_color="#f39c12")
        self.update_frame.pack(pady=5, padx=25, fill="x")
        self.update_label = ctk.CTkLabel(self.update_frame, text=self.text["update_check"], font=app_font(size=12), text_color=("black", "white"))
        self.update_label.pack(pady=5)
        self.update_btn = ctk.CTkButton(self.update_frame, text=self.text["check_updates"], command=self.check_updates, font=app_font(size=12, weight="bold"), height=30, corner_radius=8, fg_color="#2d3748", hover_color="#4a5568")
        self.update_btn.pack(pady=(0, 5))

        self.status_frame = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#16213e"), corner_radius=12, border_width=1, border_color="#00d4ff")
        self.status_frame.pack(pady=5, padx=25, fill="x")
        self.status_label = ctk.CTkLabel(self.status_frame, text=self.text["status_not_installed"], font=app_font(size=14, weight="bold"), text_color=("black", "white"))
        self.status_label.pack(pady=8)

        self.list_frame = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#16213e"), corner_radius=15, border_width=2, border_color="#00d4ff")
        self.list_frame.pack(pady=10, padx=25, fill="both", expand=True)
        self.list_label = ctk.CTkLabel(self.list_frame, text=self.text["strategies"], font=app_font(size=14, weight="bold"), text_color=("black", "white"))
        self.list_label.pack(pady=(10, 5))
        self.scroll_frame = ctk.CTkScrollableFrame(self.list_frame, fg_color="transparent", height=280)
        self.scroll_frame.pack(pady=5, padx=10, fill="both", expand=True)
        
        self.load_strategies()

        self.settings_frame = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#16213e"), corner_radius=15, border_width=2, border_color="#f39c12")
        self.settings_frame.pack(pady=10, padx=25, fill="x")
        self.settings_label = ctk.CTkLabel(self.settings_frame, text=self.text["settings"], font=app_font(size=14, weight="bold"), text_color=("black", "white"))
        self.settings_label.pack(pady=(8, 5))
        self.settings_btn = ctk.CTkButton(self.settings_frame, text=self.text["open_settings"], command=self.open_settings, font=app_font(size=15, weight="bold"), height=45, corner_radius=10, fg_color="#2d3748", hover_color="#4a5568", border_width=1, border_color="#f39c12")
        self.settings_btn.pack(pady=(5, 10), padx=15, fill="x")

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=5, padx=25, fill="x")
        self.refresh_btn = ctk.CTkButton(self.btn_frame, text=self.text["refresh"], command=self.refresh_strategies, font=app_font(size=13, weight="bold"), height=35, corner_radius=10, fg_color="#4a5568", hover_color="#718096")
        self.refresh_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.remove_btn = ctk.CTkButton(self.btn_frame, text=self.text["remove"], command=self.remove_service, font=app_font(size=13, weight="bold"), height=35, corner_radius=10, fg_color="#e53e3e", hover_color="#c53030", state="disabled")
        self.remove_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.btn_frame.grid_columnconfigure(0, weight=1)
        self.btn_frame.grid_columnconfigure(1, weight=1)

        self.footer_label = ctk.CTkLabel(self, text=f"{APP_PATH}", font=app_font(size=9), text_color=("black", "white"))
        self.footer_label.pack(pady=(0, 10))

        self.after(1000, self.check_updates)
        self.after(500, self.check_status)

    def change_lang(self, choice):
        lang_map = {
            "RU": "ru",
            "EN": "en",
            "UA": "uk",
            "BE": "be",
            "BRAT": "brat"
        }
        self.lang = lang_map.get(choice, "ru")
        self.text = LANG[self.lang]
        self.update_ui_text()

    def update_ui_text(self):
        self.title_label.configure(text=self.text["title"])
        self.version_label.configure(text=f"{self.text['version']} {CURRENT_VERSION} | {self.text['strategies']}")
        self.refresh_update_label()
        self.status_label.configure(text=self.text["status_not_installed"])
        self.list_label.configure(text=self.text["strategies"])
        self.settings_label.configure(text=self.text["settings"])
        self.settings_btn.configure(text=self.text["open_settings"])
        self.refresh_btn.configure(text=self.text["refresh"])
        self.remove_btn.configure(text=self.text["remove"])
        self.load_strategies()
        self.check_status()

    def compare_versions(self, v1, v2):
        v1_parts = [int(x) for x in v1.split('.')]
        v2_parts = [int(x) for x in v2.split('.')]

        for i in range(max(len(v1_parts), len(v2_parts))):
            v1_val = v1_parts[i] if i < len(v1_parts) else 0
            v2_val = v2_parts[i] if i < len(v2_parts) else 0
            if v1_val < v2_val:
                return True
            elif v1_val > v2_val:
                return False
        return False

    def refresh_update_label(self):
        state = self.update_state
        if state == "available":
            self.update_label.configure(text=self.text["update_available"].format(self.latest_version), text_color="#48bb78")
            self.update_btn.configure(text=self.text["download_update"], fg_color="#00b894", hover_color="#00a381", command=self.download_update)
        elif state == "latest":
            self.update_label.configure(text=self.text["update_latest"], text_color="#48bb78")
            self.update_btn.configure(text=self.text["check_updates"], fg_color="#2d3748", hover_color="#4a5568", command=self.check_updates)
        elif state == "error":
            self.update_label.configure(text=self.text["update_error"], text_color="#fc8181")
            self.update_btn.configure(text=self.text["check_updates"], fg_color="#2d3748", hover_color="#4a5568", command=self.check_updates)
        elif state == "error2":
            self.update_label.configure(text=self.text["update_error2"], text_color="#fc8181")
            self.update_btn.configure(text=self.text["check_updates"], fg_color="#2d3748", hover_color="#4a5568", command=self.check_updates)
        elif state == "checking":
            self.update_label.configure(text=self.text["update_check"], text_color="#f39c12")
            self.update_btn.configure(text=self.text["check_updates"])
        else:
            self.update_label.configure(text=self.text["update_check"], text_color=("black", "white"))
            self.update_btn.configure(text=self.text["check_updates"], fg_color="#2d3748", hover_color="#4a5568", command=self.check_updates)

    def ui(self, func):
        self.after(0, func)

    def check_updates(self):
        def check():
            self.update_state = "checking"
            self.ui(lambda: self.update_label.configure(text=self.text["update_check"], text_color="#f39c12"))
            try:
                response = requests.get(
                    GITHUB_API_URL,
                    timeout=10,
                    headers={"User-Agent": "hux-huxLauncher"},
                )
                if response.status_code == 200:
                    data = response.json()
                    latest = data.get("tag_name", "").replace("v", "")

                    if latest and self.compare_versions(CURRENT_VERSION, latest):
                        self.update_available = True
                        self.latest_version = latest
                        self.download_url = data.get("html_url", "")
                        self.update_state = "available"
                        self.ui(lambda: (
                            self.update_label.configure(text=self.text["update_available"].format(latest), text_color="#48bb78"),
                            self.update_btn.configure(text=self.text["download_update"], fg_color="#00b894", hover_color="#00a381", command=self.download_update)
                        ))
                    else:
                        self.update_state = "latest"
                        self.ui(lambda: (
                            self.update_label.configure(text=self.text["update_latest"], text_color="#48bb78"),
                            self.update_btn.configure(text=self.text["check_updates"], fg_color="#2d3748", hover_color="#4a5568", command=self.check_updates)
                        ))
                else:
                    logger.warning("GitHub API вернул статус %s", response.status_code)
                    self.update_state = "error"
                    self.ui(lambda: self.update_label.configure(text=self.text["update_error"], text_color="#fc8181"))
            except Exception:
                logger.exception("Ошибка при проверке обновлений")
                self.update_state = "error2"
                self.ui(lambda: self.update_label.configure(text=self.text["update_error2"], text_color="#fc8181"))

        Thread(target=check, daemon=True).start()

    def download_update(self):
        if self.download_url:
            if messagebox.askyesno(self.text["update_available_title"], self.text["update_available_msg"].format(self.latest_version)):
                webbrowser.open(self.download_url)

    def get_all_bat_files(self):
        files = []
        try:
            for f in os.listdir(self.zapret_dir):
                full_path = os.path.join(self.zapret_dir, f)
                if os.path.isfile(full_path) and f.endswith('.bat') and f.lower() != 'service.bat':
                    files.append(f)
            def natural(name):
                return re.sub(r'\d+', lambda m: m.group().zfill(10), name)

            def sort_key(x):
                name = x.lower()
                if name == 'general.bat':
                    return (0, '')
                if name.startswith('general ('):
                    return (1, natural(name))
                return (2, natural(name))
            files.sort(key=sort_key)
        except Exception:
            logger.exception("Ошибка при получении списка .bat файлов")
        return files

    def load_strategies(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.strategies = self.get_all_bat_files()
        if self.strategies:
            for name in self.strategies:
                display_name = name.replace('.bat', '')
                btn = ctk.CTkButton(self.scroll_frame, text=f"> {display_name}", command=lambda n=name: self.run_strategy(n), font=app_font(size=12), height=35, corner_radius=8, fg_color="#2d3748", hover_color="#00b894", anchor="w", border_width=1, border_color="#4a5568")
                btn.pack(pady=2, padx=5, fill="x")
            self.list_label.configure(text=self.text["strategies_found"].format(len(self.strategies)))
        else:
            label = ctk.CTkLabel(self.scroll_frame, text=self.text["no_strategies"].format(self.zapret_dir), font=app_font(size=13), text_color="#fc8181", justify="center")
            label.pack(pady=30)
            self.list_label.configure(text=self.text["strategies_not_found"])

    def refresh_strategies(self):
        self.load_strategies()
        self.check_status()

    def run_strategy(self, name):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            if not messagebox.askyesno(self.text["admin_required"], self.text["admin_required_msg"]):
                return
            script = os.path.abspath(sys.argv[0])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", script, "", None, 1)
            self.destroy()
            sys.exit(0)
        self.status_label.configure(text=f"Запуск: {name}...", text_color="#f39c12")
        try:
            full_path = os.path.join(self.zapret_dir, name)
            subprocess.Popen(
                ["cmd", "/c", full_path],
                cwd=self.zapret_dir,
                creationflags=CREATE_NEW_CONSOLE,
            )
            self.status_label.configure(text=f"Запущена: {name}", text_color="#48bb78")
            self.after(3000, self.check_status)
        except Exception as e:
            logger.exception("Ошибка запуска стратегии %s", name)
            self.status_label.configure(text=f"Ошибка: {str(e)[:50]}", text_color="#fc8181")

    def open_zapret_source_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.text["zapret_source_title"])
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=("#0a0a1a", "#0d0d2b"))

        x = self.winfo_x() + (self.winfo_width() // 2) - 210
        y = self.winfo_y() + (self.winfo_height() // 2) - 110
        dialog.geometry(f"+{x}+{y}")

        current_mode = self.settings.get("zapret_mode", "builtin")
        current_custom = self.settings.get("zapret_custom_path", "")

        label = ctk.CTkLabel(dialog, text=self.text["zapret_source_heading"], font=app_font(size=16, weight="bold"), text_color="#00d4ff")
        label.pack(pady=(15, 10))

        current_label = ctk.CTkLabel(
            dialog,
            text=self.text["zapret_source_current"].format(self.zapret_dir),
            font=app_font(size=11),
            text_color=("black", "white"),
            wraplength=380,
        )
        current_label.pack(pady=(0, 15))

        def use_builtin():
            self.settings["zapret_mode"] = "builtin"
            self.settings.pop("zapret_custom_path", None)
            save_settings(self.settings)
            self.zapret_dir = resolve_zapret_dir(self.settings)
            unstage_zapret_files(self.zapret_dir)
            self.load_strategies()
            dialog.destroy()

        def use_custom():
            folder = filedialog.askdirectory(title=self.text["zapret_source_pick_folder"])
            if not folder:
                return
            self.settings["zapret_mode"] = "custom"
            self.settings["zapret_custom_path"] = folder
            save_settings(self.settings)
            self.zapret_dir = resolve_zapret_dir(self.settings)
            unstage_zapret_files(self.zapret_dir)
            self.load_strategies()
            dialog.destroy()

        builtin_btn = ctk.CTkButton(
            dialog, text=("✅ " if current_mode != "custom" else "") + self.text["zapret_source_builtin"],
            command=use_builtin, height=38, fg_color="#2d3748", hover_color="#00b894",
            font=app_font(size=13),
        )
        builtin_btn.pack(pady=5, padx=30, fill="x")

        custom_btn = ctk.CTkButton(
            dialog, text=("✅ " if current_mode == "custom" else "") + self.text["zapret_source_custom"],
            command=use_custom, height=38, fg_color="#2d3748", hover_color="#00b894",
            font=app_font(size=13),
        )
        custom_btn.pack(pady=5, padx=30, fill="x")

    def open_settings(self):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showwarning(self.text["settings_admin"], self.text["settings_admin_msg"])
            return

        try:
            service_path = os.path.join(self.zapret_dir, "service.bat")
            if not os.path.exists(service_path):
                messagebox.showerror("Ошибка", self.text["service_not_found"].format(self.zapret_dir))
                return

            subprocess.Popen(
                ["cmd", "/c", service_path, "admin"],
                cwd=self.zapret_dir,
                creationflags=CREATE_NEW_CONSOLE,
            )

            help_window = HelpWindow(self.lang)
            help_window.focus()

        except Exception as e:
            logger.exception("Ошибка открытия настроек")
            messagebox.showerror("Ошибка", str(e))

    def check_status(self):
        try:
            result = subprocess.run(
                ["sc", "query", "zapret"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                self.remove_btn.configure(state="normal")
                if "RUNNING" in result.stdout:
                    self.status_label.configure(text=self.text["status_enabled"], text_color="#48bb78")
                else:
                    self.status_label.configure(text=self.text["status_disabled"], text_color="#f39c12")
            else:
                self.remove_btn.configure(state="disabled")
                self.status_label.configure(text=self.text["status_not_installed"], text_color="#fc8181")
        except Exception:
            logger.exception("Ошибка проверки статуса сервиса zapret")

    def remove_service(self):
        if not messagebox.askyesno(self.text["remove_confirm"], self.text["remove_confirm_msg"]):
            return
        if not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showwarning(self.text["settings_admin"], self.text["settings_admin_msg"])
            return
        try:
            subprocess.run(["net", "stop", "zapret"], capture_output=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW)
            subprocess.run(["sc", "delete", "zapret"], capture_output=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW)
            self.status_label.configure(text=self.text["status_removed"], text_color="#fc8181")
            self.after(1000, self.check_status)
        except Exception as e:
            logger.exception("Ошибка удаления сервиса zapret")
            messagebox.showerror("Ошибка", str(e))

if __name__ == "__main__":
    app = HuxHuxLauncher()
    splash = SplashScreen()
    splash.update()
    def show_main():
        app.deiconify()
        app.attributes('-topmost', True)
        app.attributes('-topmost', False)
    def check_splash():
        try:
            if not splash.winfo_exists():
                show_main()
                return
            app.after(100, check_splash)
        except Exception:
            show_main()
    app.after(100, check_splash)
    app.mainloop()
