import os, sys, traceback, datetime
from config import LOG_DIRECTORY
try:
    os.makedirs(LOG_DIRECTORY, exist_ok=True)
    def early_crash_handler(exc_type, exc_value, exc_tb):
        with open(rf"{LOG_DIRECTORY}\startup_crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] Error before logging init:\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    sys.excepthook = early_crash_handler
except Exception: pass

from typing import Optional
import threading
from threading import Thread
from queue import Queue
from dataclasses import dataclass
import asyncio
import socket
import subprocess
import psutil
from time import monotonic
import re
from requests import get, post
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from io import BytesIO
from PIL import ImageGrab
from base64 import b64encode
from pythoncom import CoInitialize, CoUninitialize
from win32gui import GetForegroundWindow, GetWindowText, WNDCLASS, DefWindowProc, RegisterClass, CreateWindow, PumpMessages, PostQuitMessage
from win32process import GetWindowThreadProcessId
from win32api import GetUserName, GetLastInputInfo, GetTickCount, GetLastError
from win32ts import WTSRegisterSessionNotification, NOTIFY_FOR_THIS_SESSION
import win32event
from winerror import ERROR_ALREADY_EXISTS
from windows_toasts import WindowsToaster, Toast
from uiautomation import SetGlobalSearchTimeout, GetForegroundControl, EditControl
from pyautogui import hotkey
from database import Database
from lockscreen import LockScreenController
from config import APP_ID, API_URLS, headers
from ctypes import wintypes, windll, byref, c_ssize_t, WINFUNCTYPE, Structure, c_int
SetGlobalSearchTimeout(2)


# ==================== SETUP ====================
os.makedirs(LOG_DIRECTORY, exist_ok=True)
DB_FILE = os.path.join(LOG_DIRECTORY, "tracker.db")
LOG_FILE = os.path.join(LOG_DIRECTORY, "tracker.log")

# ==================== Logging config ====================
def log_thread_exception(args):
    logging.error(f"Unhandled exception in thread {args.thread.name}: {args.exc_value}\n"
                  f"{''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))}")

threading.excepthook = log_thread_exception

handler = TimedRotatingFileHandler(
    filename=LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8"
)
handler.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s]: %(message)s"))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(handler)

# ==================== Windows types and constants ====================
user32 = windll.user32
kernel32 = windll.kernel32
wtsapi32 = windll.wtsapi32
LRESULT = c_ssize_t
try: windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
except Exception as e: logging.error(f"Failed to set App User Model ID. Error: {e}")

WinEventProcType = WINFUNCTYPE(
    None,
    wintypes.HANDLE,  # hWinEventHook
    wintypes.DWORD,   # event
    wintypes.HWND,    # hwnd
    wintypes.LONG,    # idObject
    wintypes.LONG,    # idChild
    wintypes.DWORD,   # dwEventThread
    wintypes.DWORD    # dwmsEventTime
)

WNDPROC = WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

class WNDCLASSW(Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClassExtra", c_int),
        ("cbWndExtra", c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_NAMECHANGE = 0x800C
WINEVENT_OUTOFCONTEXT = 0x0000
WM_QUIT = 0x0012
WM_DESTROY = 0x0002
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK   = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

@dataclass
class HookRegistration:
    """
    Stores the information required to register and manage a Windows event hook.
    
    Attributes:
        event_min: Lowest event constant to be captured.
        event_max: Highest event constant to be captured.
        callback: Function invoked when event occurs.
        hook: Windows hook handle returned during registration. Used to unregister the hook during cleanup.
    
    event_min and event_max specify the inclusive range of Windows events monitored by the hook.
    For a list of supported event constants, refer to https://learn.microsoft.com/en-us/windows/win32/winauto/event-constants
    """
    event_min: int
    event_max: int
    callback: object
    hook: int

    @classmethod
    def win_hook(cls, event, callback):
        """
        Helper function to simplify registering Windows event hook.
        
        event: Event constant to be captured. Refer https://learn.microsoft.com/en-us/windows/win32/winauto/event-constants
        callback: Callback function
        """
        return cls(event, event, callback, user32.SetWinEventHook(event, event, 0, callback, 0, 0, WINEVENT_OUTOFCONTEXT))

def get_idle_seconds() -> float:
    """ Returns the duration, in seconds, since the user's last input. """
    last = GetLastInputInfo()
    current = GetTickCount()
    return max((current - last)/1000, 0)

@dataclass
class WindowActivity:
    """
    Stores the cumulative active and idle duration, in seconds, for a tracked window.
    
    Attributes:
        active_time: Total time, in seconds, that the window was active.
        idle_time: Total time, in seconds, that the user was idle while the window was active.
    """
    active_time: float = 0
    idle_time: float = 0

@dataclass
class SystemEvent:
    """
    Base class for all recorded events.
    
    Attributes:
        timestamp: Monotonic timestamp, in seconds, indicating when the event occured.
    """
    timestamp: float

@dataclass
class WindowChanged(SystemEvent):
    """
    Represents a change in the active foreground window.
    
    Attributes:
        window: Process name of the new active foreground window.
        title: Title of the new active foreground window.
    """
    window: str
    title: str

@dataclass
class TitleChanged(SystemEvent):
    """
    Represents a change in the name/title of the open foreground window.
    
    Attributes:
        title: New title of the active foreground window.
    """
    window: str
    title: str

@dataclass
class IdleChanged(SystemEvent):
    """
    Represents a change in user's idle state.
    
    Attributes:
        is_idle: Indicates whether the user is now idle.
    """
    is_idle: bool

@dataclass
class SessionChanged(SystemEvent):
    """
    Represents a change in system session state.
    
    Attributes:
        locked: Indicates whether the system is now locked.
    """
    locked: bool = False

@dataclass
class IdleLockSystemEvent(SystemEvent):
    pass

def get_device_serial() -> str:
    """ Returns local device's serial number """
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        bios = wmi.ExecQuery("SELECT SerialNumber FROM Win32_BIOS")[0]
        return str(bios.SerialNumber)
    except: pass
    
    try:
        return subprocess.check_output(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_BIOS).SerialNumber" ], shell=True, text=True).strip()
    except: pass
    
    try:
        return subprocess.check_output(["wmic", "bios", "get", "serialnumber"], text=True).strip().splitlines()[-1]
    except: pass
    
    return "UNKNOWN_DEVICE"

def get_user_name() -> str:
    """ Returns active user's name"""
    try:
        for proc in psutil.process_iter(["name", "username"]):
            if proc.info["name"] and proc.info["name"].lower() == "explorer.exe":
                if full_user := proc.info["username"]:
                    username = full_user.split("\\")[-1].strip()
                    if username and not username.endswith("$") and username.upper() != "SYSTEM":
                        return username
    except Exception as e:
        logging.error(f"Error while fetching username: {e}")
    
    try:
        user = GetUserName().strip()
        if user and ("$" not in user) and (user.upper() != "SYSTEM"):
            return user
    except Exception as e:
        logging.error(f"Error while fetching username: {e}")
    
    try:
        return subprocess.check_output(["quser"], text=True).strip().splitlines()[-1].split()[0].removeprefix(">")
    except: pass
    
    return "UnknownUser"

def check_internet_connectivity() -> bool:
    """ Returns whether an active internet connection is available.
    
    Connectivity is determined by establishing a socket connection to a known host.
    """
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except:
        return False

def get_location() -> tuple[str, str]:
    """
    Returns local device's location in the format (latitude, longitude) as a tuple of strings.
    """
    try:
        import winsdk.windows.devices.geolocation as wdg
        
        async def get_coords():
            locator = wdg.Geolocator()
            pos = await locator.get_geoposition_async()
            return str(pos.coordinate.latitude), str(pos.coordinate.longitude)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        lat, lon = loop.run_until_complete(get_coords())
        
        return lat, lon
    except: pass
    
    try:
        resp = get("https://ipapi.co/json/", timeout=3)
        data = resp.json()
        lat, lon = str(data["latitude"]), str(data["longitude"])
        return lat, lon
    except: pass
    
    return ("0.0", "0.0")

def ui_get_addressbar_control_value(window:str) -> str|None:
    """
    Returns the UIAutomation Control of the address bar of an open browser window.
    """
    window = window.lower()
    try:
        browserControl = GetForegroundControl()
    except: return None
    
    if window == "chrome.exe":
        try: return browserControl.EditControl(Name="Address and search bar").GetValuePattern().Value
        except: pass
    
    elif window == "msedge.exe":
        try: return browserControl.EditControl(Name="Address and search bar").GetValuePattern().Value
        except: pass
    
    elif window == "firefox.exe":
        try: return browserControl.EditControl(AutomationId="urlbar-input").GetValuePattern().Value
        except:
            try: return browserControl.EditControl(ClassName="urlbar-input textbox-input").GetValuePattern().Value
            except: pass
    
    else:
        try: return EditControl(Name="Address and search bar").GetValuePattern().Value
        except: pass
    return None

def capture_screenshot():
    """ Captures a screenshot of the device. """
    try:
        screenshot = ImageGrab.grab()
        buffer = BytesIO()
        screenshot.save(buffer, format="JPEG", quality=30, optimize=True)
        return b64encode(buffer.getvalue()).decode("utf-8")
    except: return ""

@dataclass
class ActivityState:
    """
    Manages the run-time state of the tracker.
    
    Attributes:
        `current_window` : Application name of the current foreground window.
        `current_title` : Title of the current foreground window.
        `current_domain` : Domain of current website (if any).
        `current_category` : Category of current website (if any).
        `is_browsing` : Whether the foreground window application is a web browser.
        `is_idle` : Whether the user's idle duration has crossed the threshold.
        `is_locked` : Whether the Windows system session is locked.
        `state_start_time` : Monotonic time when the current activity state started.
        `blocked_apps` : List of blocked applications
        `blocked_websites` : List of blocked websites
    """
    blocked_apps: list[str]
    blocked_websites: list[str]
    window: str = ""
    title: str = ""
    domain: str = ""
    current_category: str = ""
    is_browsing: bool = False
    is_idle: bool = False
    is_locked: bool = False
    state_start_time: float = 0
    
    @property
    def current_window(self) -> str:
        return self.window
    
    @property
    def current_title(self) -> str:
        return self.title
    
    @property
    def current_domain(self):
        return self.domain

    @current_window.setter
    def current_window(self, window:str) -> None:
        self.window = window
        
        if window in self.blocked_apps:
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = proc.info["name"]
                    if pname and pname.lower() == window:
                        proc.terminate()
                        logging.info(f"Blocked App process killed: {proc.info["name"]}")
                except: continue
        
        if window in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]:
            self.is_browsing = True
        else:
            self.is_browsing = False
            self.current_domain = ""
    
    @current_title.setter
    def current_title(self, title:str):
        self.title = title
        self.read_domain()

    @current_domain.setter
    def current_domain(self, domain):
        self.domain = domain
        if not domain:
            self.current_category = "N/A"
            return
        
        for blocked_domain in self.blocked_websites:
            if (blocked_domain in domain) or (domain in blocked_domain):
                if not self.is_browsing: return
                hotkey("ctrl", "w")
                logging.info(f"Blocked website closed: {domain}")
        
        if any(url in domain for url in ["youtube", "netflix", "primevideo"]):
            self.current_category = "Entertainment"
        elif any(url in domain for url in ["github", "stack", "gitlab", "chatgpt"]):
            self.current_category = "Development"
        elif any(url in domain for url in ["mail", "outlook", "teams", "whatsapp"]):
            self.current_category = "Communication"
        else:
            self.current_category = "Browsing"
    
    def read_domain(self):
        if not self.is_browsing: return
        
        full_url = ui_get_addressbar_control_value(self.current_window)
        if not full_url: return
        
        if mat:= re.match(r"(https?://)?(www\.)?(?P<domain>[\w\.]+)/?", full_url):
            self.current_domain = mat.group("domain")
        else:
            if "new tab" in self.current_title.lower():
                self.current_domain = "new"
            else:
                self.current_domain = "Unknown"

class Tracker:
    """
    Tracks the user's foreground window, browser activity, session state and idle state.
    
    Call `Tracker.start()` to start the tracker.
    
    Constants:
        `INTERVAL_INPUT` : Interval, in seconds, between consecutive checks of user's idle duration.
        `INTERVAL_LOG` : Interval, in seconds, between activity log generation.
        `IDLE_THRESHOLD` : Duration, in seconds, after which the user is considered idle.
    """
    INTERVAL_INPUT = 1
    INTERVAL_LOG = 60
    IDLE_THRESHOLD = 5 * 60
    STARTUP_GRACE_SECONDS = 60

    def fetch_blocked_apps(self) -> list[str]:
        try:
            response = get(API_URLS["blocked_apps"], headers=headers, timeout=2)
            if response.status_code == 200:
                data = response.json()
                blocked_apps = [item.get("App_name") for item in data.get("data", []) if item.get("App_name")]
                logging.info(f"Fetched {len(blocked_apps)} blocked applications from server. Blocked Apps: {blocked_apps}")
                return blocked_apps
            else:
                logging.warning(f"API status: {response.status_code}")
                return []
        except Exception as e:
            logging.error(f"Failed to fetch blocked apps. Error: {e}")
            return []
    
    def fetch_blocked_websites(self) -> list[str]:
        try:
            response = get(API_URLS["blocked_urls"], headers=headers, timeout=2)
            if response.status_code == 200:
                data = response.json()
                blocked_urls = [item.get("WebSite_URL") for item in data.get("data",[]) if item.get("WebSite_URL")]
                logging.info(f"Fetched {len(blocked_urls)} blocked websites from server. Blocked Websites: {blocked_urls}")
                return blocked_urls
            else:
                logging.warning(f"API status: {response.status_code}")
                return []
        except Exception as e:
            logging.error(f"Failed to fetch blocked websites. Error: {e}")
            return []
    
    def fetch_device_status(self) -> int:
        payload = {"SerialNumber": self.serial}
        try:
            response = get(API_URLS["device_status"], headers=headers, json=payload, timeout=3)
            
            if response.status_code == 200:
                resp = response.json()
                items = resp.get("data", [])
                for item in items:
                    if item.get("SerialNumber") == self.serial:
                        return item.get("Status")
                return 0
            else:
                logging.info(f"API Status Code: {response.status_code}")
                return 0
        except Exception as e:
            logging.error(f"Failed to fetch device status: {e}")
            return 0
    
    def fetch_session_time_limit(self) -> int:
        payload = {"SerialNumber": self.serial}
        try:
            response = get(API_URLS["session_time_limit"], headers=headers, json=payload, timeout=3)
            
            if response.status_code == 200:
                resp = response.json()
                data_list = resp.get("data", [])
                if data_list:
                    session_time = int(data_list[0]["SessionTime"])
                    logging.info(f"Fetched session time limit: {session_time} seconds.")
                    return session_time if session_time > 60 else 1800
                return 1800
            else:
                logging.info(f"API Status Code: {response.status_code}")
                return 1800
        except Exception as e:
            logging.error(f"Failed to fetch device status: {e}")
            return 1800
    
    def __init__(self):
        self.stop_event = threading.Event()
        self.queue = Queue()
        self.activity:dict[str, WindowActivity] = {}
        self.watchdog_proc : Optional[subprocess.Popen] = None
        self.serial = get_device_serial()
        self.username = get_user_name()
        self.latitude, self.longitude = get_location()
        
        self.lock_screen_controller = LockScreenController()
        self.locked = False
        self.reminder_sent = False
        def unlock():
            self.locked = False
            self.reminder_sent = False
        self.lock_screen_controller.lock_screen.add_callback("hide", unlock)
    
    def state_loop(self):
        """ Processes events received in the queue in a separate thread. """
        self.stop_obj = object()
        CoInitialize()
        self.state.state_start_time = monotonic()
        while event := self.queue.get():
            if event is self.stop_obj: break
            self.handle_event(event)
        CoUninitialize()
    
    def handle_event(self, event:SystemEvent):
        """
        Handles `SystemEvents` received from the queue.
        """
        self.update_time()
        
        if isinstance(event, WindowChanged):
            if self.state.current_window == event.window and self.state.current_title == event.title: return
            
            self.state.current_window = event.window
            self.state.current_title = event.title
        
        elif isinstance(event, TitleChanged):
            if not self.state.is_browsing or not self.state.current_window == event.window or event.title == self.state.current_title:
                return
            self.state.current_title = event.title

        elif isinstance(event, IdleChanged):
            self.state.is_idle = event.is_idle
        
        elif isinstance(event, SessionChanged):
            self.state.is_locked = event.locked
            self.queue.put(WindowChanged(monotonic(), "lockscreen", "Lock Screen"))
        
        elif isinstance(event, IdleLockSystemEvent):
            self.locked = True
            #self.lock_screen_controller.show_lock_screen()
    
    def update_time(self):
        """
        Updates current window's activity time.
        """
        t = monotonic()
        if t - self.state.state_start_time < 0.1:
            return
        
        self.activity.setdefault(self.state.current_window, WindowActivity())
        if self.state.is_idle:
            self.activity[self.state.current_window].idle_time += t - self.state.state_start_time
        else:
            self.activity[self.state.current_window].active_time += t - self.state.state_start_time
        
        self.state.state_start_time = monotonic()
    
    def start(self):
        """
        Starts the tracker.
        """
        logging.info("Tracker started")
        self.launch_time = monotonic()
        self.threads:list[Thread] = []
        self.hooks:list[HookRegistration] = []
        def add_thread(tracker): self.threads.append(Thread(target=tracker, daemon=True))
        
        blocked_apps = self.fetch_blocked_apps()
        blocked_websites = self.fetch_blocked_websites()
        self.state = ActivityState(blocked_apps=blocked_apps, blocked_websites=blocked_websites)
        self.device_status = self.fetch_device_status()
        self.session_time_limit = self.fetch_session_time_limit()
        
        self.launch_watchdog()
        Thread(target=self.state_loop, daemon=True).start()
        add_thread(self.poll_last_input)
        add_thread(self.register_win_hooks)
        add_thread(self.poll_log)
        
        for thread in self.threads:
            thread.start()
        try:
            self.lock_screen_controller.root.mainloop()
            #while not self.stop_event.wait(0.5): pass
        except KeyboardInterrupt: pass
        except Exception as e: logging.error(f"[FATAL ERROR] {e}")
        finally: self.stop()
    
    def poll_last_input(self):
        """
        Continuously monitor the user's idle duration in a background thread and update the idle state
        when it crosses the configured threshold (IDLE_THRESHOLD).
        """
        elapsed = monotonic() - self.launch_time
        remaining = self.STARTUP_GRACE_SECONDS - elapsed
        if remaining > 0:
            self.stop_event.wait(remaining)
            
        while not self.stop_event.wait(self.INTERVAL_INPUT):
            idle = get_idle_seconds()
            
            if not self.reminder_sent and (idle > (self.session_time_limit - 60)):
                self.reminder_sent = True
                self.send_reminder()
            
            if idle > self.session_time_limit and not self.locked:
                self.queue.put(IdleLockSystemEvent(timestamp=monotonic()))
            
            if idle > self.IDLE_THRESHOLD and not self.state.is_idle:
                self.queue.put(IdleChanged(is_idle=True, timestamp=monotonic()))
            
            elif idle < self.IDLE_THRESHOLD and self.state.is_idle:
                self.queue.put(IdleChanged(is_idle=False, timestamp=monotonic()))
    
    def register_foreground_hook(self):
        """
        Registers a Windows event hook to detect change in active foreground window.
        
        Enqueues `WindowChanged` to the queue on event callback.
        """
        def process_window_hwnd(hwnd):
            """
            Processes foreground window hwnd and enqueues a `WindowChanged` event.
            """
            try:
                title = GetWindowText(hwnd).strip() or "Desktop"
                _,pid = GetWindowThreadProcessId(hwnd)
                
                try: app_name = psutil.Process(pid).name()
                except: app_name = "System"
                
                if app_name == "explorer.exe" and title == "Task Switching": return
                if title == self.lock_screen_controller.name: return
                
                self.queue.put(
                    WindowChanged(
                        timestamp = monotonic(),
                        window = app_name,
                        title = title,
                    )
                )
            except Exception as e: logging.error(e)
        try:
            hwnd = GetForegroundWindow()
            process_window_hwnd(hwnd)
        except: pass
        
        self.thread_id_foreground = threading.get_native_id()
        
        def foreground_callback(hook, event, hwnd, idObject, idChild, idThread, eventTime):
            process_window_hwnd(hwnd)
            
        cb_foreground = WinEventProcType(foreground_callback)
        self.hooks.append(HookRegistration.win_hook(EVENT_SYSTEM_FOREGROUND, cb_foreground))
    
    def register_namechange_hook(self):
        """
        Registers a Windows event hook to detect changes in name of open applications.
        
        Enqueues `TitleChanged` to the queue on event callback.
        """
        def namechange_callback(hook, event, hwnd, idObject, idChild, idThread, eventTime):
            try:
                _,pid = GetWindowThreadProcessId(hwnd)
                
                try: app_name = psutil.Process(pid).name()
                except: app_name = "System"
                
                title = GetWindowText(hwnd).strip()
                if title:
                    if title.startswith("System Clock"): return
                    
                    self.queue.put(TitleChanged(
                        timestamp= monotonic(),
                        window = app_name,
                        title = title
                    ))
            except: pass
    
        cb_namechange = WinEventProcType(namechange_callback)
        self.hooks.append(HookRegistration.win_hook(EVENT_OBJECT_NAMECHANGE, cb_namechange))
    
    def register_lock_hook(self):
        """
        Registers a windows event hook to detect change in session state.
        
        Enqueues `SessionChanged` to the queue on event callback.
        """
        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_WTSSESSION_CHANGE:
                if wparam == WTS_SESSION_LOCK:
                    self.queue.put(SessionChanged(monotonic(), True))
                elif wparam == WTS_SESSION_UNLOCK:
                    self.queue.put(SessionChanged(monotonic(), False))
                
            elif msg == WM_DESTROY:
                PostQuitMessage(0)
                return 0
            
            return DefWindowProc(hwnd, msg, wparam, lparam)
            
        wc = WNDCLASS()
        wc.lpszClassName = "ActivityMonitor"
        wc.lpfnWndProc = wnd_proc
        self.wnd_class = RegisterClass(wc)
        self.hwnd = CreateWindow(
            self.wnd_class,
            "ActivityMonitor",
            0,
            0,0,0,0,
            0,0,0, None
        )
        WTSRegisterSessionNotification(self.hwnd, NOTIFY_FOR_THIS_SESSION)
        
        def run(): PumpMessages()
        Thread(target=run, daemon=True).start()
    
    def register_win_hooks(self):
        """
        Registers Windows event hooks and starts the Windows message loop.
        """
        self.register_foreground_hook()
        self.register_namechange_hook()
        self.register_lock_hook()
        
        self.msg = wintypes.MSG()
        while user32.GetMessageW(byref(self.msg), 0, 0, 0):
            user32.TranslateMessage(byref(self.msg))
            user32.DispatchMessageW(byref(self.msg))
    
    def poll_log(self):
        """
        Periodically generate and process activity logs.
        
        Uploads each log when internet is available, othervise stores it locally for later upload.
        """
        self.database = Database(DB_FILE)
        
        while not self.stop_event.is_set():
            try:
                next_run = monotonic() + self.INTERVAL_LOG
                
                idle_duration = get_idle_seconds()
                idle_mins = round(idle_duration/60, 2)
                internet = check_internet_connectivity()
                log = {
                    "deviceId": self.serial,
                    "userName": self.username,
                    "appName": self.state.current_window,
                    "windowTitle": self.state.current_title,
                    "domain": self.state.current_domain,
                    "websiteCategory": self.state.current_category,
                    "logTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "idleMinutes": str(idle_mins),
                    "isIdle": str(idle_duration > self.IDLE_THRESHOLD),
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "isSynced": "False",
                    "internetStatus": "ON" if internet else "OFF",
                    "screenshotBase64": capture_screenshot(),   
                }
                
                if internet:
                    if not self.state.blocked_apps:
                        self.state.blocked_apps = self.fetch_blocked_apps()
                    if not self.state.blocked_websites:
                        self.state.blocked_websites = self.fetch_blocked_websites()
                    
                    self.sync_logs()
                    if not self.upload_log(log):
                        self.database.save_log(log)
                else:
                    logging.info("No internet available. Saving log in database.")
                    self.database.save_log(log)
                
                remaining = next_run - monotonic()
                if self.stop_event.wait(max(0, remaining)): break
            
            except Exception as e:
                logging.error(f"Error while uploading log: {e}")
    
    def upload_log(self, log:dict) -> bool:
        """
        Uploads an activity log to the server.
        `log` : Activity log stored in a dictionary to be uploaded to server.
        
        Returns:
            `True` if the upload succeeds, othervise `False`.
        """
        try:
            log["isSynced"] = "True"
            response = post(API_URLS["save"], headers=headers, json=log, timeout=15)
            
            if response.status_code in [200,201]:
                logging.info("Upload successful")
                return True
            logging.warning("Upload failed")
            return False
        except Exception as e:
            logging.error(f"Error while uploading: {e}")
            return False

    def sync_logs(self):
        """
        Syncs the logs saved in local database that previously were not uploaded to the server.
        """
        logs = self.database.fetch_logs()
        synced_log_ids = []
        
        for id, data in logs:
            record = json.loads(data)
            if self.upload_log(record):
                synced_log_ids.append(id)
        
        if len(synced_log_ids) > 0:
            self.database.delete_logs(synced_log_ids)
    
    def launch_watchdog(self):
        try:
            exe_path = sys.executable
            exe_name = os.path.basename(exe_path)
            
            if not exe_name.endswith(".exe") or exe_name == "python.exe":
                return
            
            if self.watchdog_proc and self.watchdog_proc.poll() is None:
                return
            
            ps_script = f"""
            $exePath = '{exe_path}'
            $exeName = '{exe_name.replace(".exe", "")}'
            
            while ($true) {{
                if (-not (Get-Process $exeName -ErrorAction SilentlyContinue))
                {{
                    Start-Process $exePath
                    
                    while ($null -eq (Get-Process $exeName -ErrorAction SilentlyContinue))
                    {{
                        Start-Sleep -Milliseconds 200
                    }}
                    exit
                }}
                Start-Sleep -Seconds 2
            }}
            """
            
            self.watchdog_proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden" ,"-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            try:
                with open(os.path.join(LOG_DIRECTORY, "watchdog.pid"), "w") as f:
                    f.write(str(self.watchdog_proc.pid))
            except Exception: pass
        except Exception as e:
            logging.error(f"Failed to run watchdog process\nError: {e}")
    
    def send_reminder(self):
        try:
            toaster = WindowsToaster("ATL Desk Management System")
            newtoast = Toast()
            newtoast.images
            newtoast.text_fields = ["Warning: System will be locked in one minute. Please resume your activity."]
            toaster.show_toast(newtoast)
        except Exception as e:
            logging.error("Failed to display Windows notification.")
    
    def stop(self):
        """
        Stops the tracker and performs cleanup.
        
        Releases registered Windows event hooks and stops all background threads.
        """
        try:
            try:
                if self.watchdog_proc:
                    self.watchdog_proc.terminate()
            except Exception: pass
            try:
                pid_file = os.path.join(LOG_DIRECTORY, "watchdog.pid")
                if os.path.exists(pid_file):
                    os.remove(pid_file)
            except Exception: pass
            
            try:
                user32.PostThreadMessageW(self.thread_id_foreground, WM_QUIT, 0, 0)
                wtsapi32.WTSUnRegisterSessionNotification(self.hwnd)
                user32.DestroyWindow(self.hwnd)
                for hook_registration in self.hooks:
                    try:
                        user32.UnhookWinEvent(hook_registration.hook)
                    except: pass
            except: pass
        except: pass
        
        self.queue.put(SystemEvent(monotonic()))
        self.stop_event.set()
        self.queue.put(self.stop_obj)
        for thread in self.threads:
            thread.join()
            
        try: self.database.close()
        except Exception as e: logging.error(f"Error while closing database: {e}")
        
        logging.info(self.activity)
        logging.info("Tracker stopped")


MUTEX_NAME = "Global\\ATLDeskManagementTracker_SingleInstance"
def ensure_single_instance():
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    last_error = GetLastError()
    
    if last_error == ERROR_ALREADY_EXISTS:
        logging.info("Another instance is already running.")
        sys.exit(0)
    return mutex

if __name__ == "__main__":
    instance_mutex = ensure_single_instance()
    tracker = Tracker()
    tracker.start()