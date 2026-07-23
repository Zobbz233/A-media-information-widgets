"""
Windows 音乐信息桌面小组件
实时显示当前播放的音乐信息（歌曲名、艺术家、播放状态）
通过读取媒体播放器窗口标题获取信息，支持所有主流播放器
"""

import tkinter as tk
from tkinter import font as tkfont
import ctypes
import threading

# ── 系统托盘 ──────────────────────────────────────────────────────
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── 通过 win32gui 读取窗口标题 ───────────────────────────────────
try:
    import win32gui
    HAS_WIN32GUI = True
except ImportError:
    HAS_WIN32GUI = False
    print("[WARN] win32gui 未安装，将使用备用方式")

# ── Windows API (窗口透明、圆角、置顶) ────────────────────────────
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

# 窗口样式常量
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_APPWINDOW = 0x40000
GWL_EXSTYLE = -20

# DWM 圆角 (Windows 11)
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

# 透明度
LWA_ALPHA = 0x2
LWA_COLORKEY = 0x1

# 媒体控制虚拟键码
VK_MEDIA_PREV_TRACK = 0xB0
VK_MEDIA_NEXT_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

# 设置窗口圆角
def set_rounded_corners(hwnd, width=None, height=None):
    """为窗口设置圆角（仅用 DWM，避免 SetWindowRgn 的黑边问题）"""
    try:
        # Windows 11: DWM 圆角偏好
        pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref)
        )
    except:
        pass

# ── 媒体信息获取（通过窗口标题） ──────────────────────────────────
class MediaInfo:
    """封装媒体信息"""

    def __init__(self):
        self.title = "未播放"
        self.artist = "等待音乐..."
        self.album = ""
        self.is_playing = False
        self.source = ""
        self.status = "stopped"  # playing / paused / stopped

    def __bool__(self):
        return self.status != "stopped"


class MediaController:
    """通过枚举窗口标题获取当前播放媒体信息"""

    # 已知媒体播放器的窗口类名（严格匹配）
    PLAYER_CLASSES = {
        "SpotifyMainWindow": "Spotify",       # Spotify 桌面端
        "OrpheusBrowserHost": "网易云音乐",    # 网易云音乐
        "QMusicPlayer": "QQ音乐",             # QQ音乐
        "MediaPlayerClassicW": "MPC-HC",      # MPC-HC
        "PotPlayer64": "PotPlayer",           # PotPlayer
        "PotPlayer32": "PotPlayer",
        "TTPlayer": "千千静听",               # 千千静听
        "VlcWindow": "VLC",                   # VLC
        "Winamp v1.x": "Winamp",              # Winamp
    }

    # 浏览器类名（需要额外校验是否在播放媒体）
    BROWSER_CLASSES = {
        "Chrome_WidgetWin_1": "浏览器",
        "Chrome_WidgetWin_0": "浏览器",
        "MozillaWindowClass": "Firefox",
    }

    # 浏览器中已知的流媒体平台关键词
    STREAMING_KEYWORDS = [
        "YouTube", "Spotify", "NetEase", "网易云",
        "QQ音乐", "Bilibili", "bilibili", "SoundCloud",
        "Tidal", "Apple Music", "Pandora", "Deezer",
    ]

    def __init__(self):
        self._last_info = MediaInfo()
        self._stale_count = 0  # 缓存失效计数器
        self._current_play_state = True  # 当前播放状态（默认播放）
        self._current_title = ""  # 当前歌曲标题（用于判断是否切换歌曲）

    def toggle_play_state(self):
        """切换播放/暂停状态"""
        self._current_play_state = not self._current_play_state
        return self._current_play_state

    def get_play_state(self) -> bool:
        """获取当前播放状态"""
        return self._current_play_state

    def get_current_media(self) -> MediaInfo:
        """获取当前播放媒体信息"""
        info = MediaInfo()

        if not HAS_WIN32GUI:
            return info

        try:
            candidates = []

            def enum_callback(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd) or ""
                title = title.strip()
                if not title or len(title) < 2 or len(title) > 200:
                    return
                cls = win32gui.GetClassName(hwnd)
                candidates.append((hwnd, cls, title))

            win32gui.EnumWindows(enum_callback, None)

            # ── 第一轮：已知音乐播放器（严格匹配类名） ──
            for hwnd, cls, title in candidates:
                app = self._match_player_class(cls)
                if app:
                    parsed = self._parse_title(title)
                    if parsed and parsed.status != "stopped":
                        parsed.source = app
                        # 检测播放状态：从窗口标题或上次状态推断
                        self._detect_play_state(title, parsed)
                        self._last_info = parsed
                        self._stale_count = 0
                        self._current_title = parsed.title
                        return parsed

            # ── 第二轮：浏览器标签（需校验是否在播放媒体） ──
            for hwnd, cls, title in candidates:
                app = self._match_browser_class(cls)
                if app and self._is_streaming_media(title):
                    parsed = self._parse_title(title)
                    if parsed and parsed.status != "stopped":
                        parsed.source = app
                        self._detect_play_state(title, parsed)
                        self._last_info = parsed
                        self._stale_count = 0
                        self._current_title = parsed.title
                        return parsed

            # ── 第三轮：系统媒体控件窗口 ──
            for hwnd, cls, title in candidates:
                if "Media" in cls or "Transport" in cls:
                    parsed = self._parse_title(title)
                    if parsed and parsed.status != "stopped":
                        parsed.source = "系统媒体控件"
                        self._detect_play_state(title, parsed)
                        self._last_info = parsed
                        self._stale_count = 0
                        self._current_title = parsed.title
                        return parsed

            # ── 缓存保护：保留上次信息最多2次刷新 ──
            if self._last_info.status != "stopped" and self._stale_count < 2:
                self._stale_count += 1
                return self._last_info

        except Exception:
            pass

        # 恢复默认
        info.title = "未播放"
        info.artist = "等待音乐..."
        info.status = "stopped"
        self._last_info = info
        self._stale_count = 0
        return info

    def _match_player_class(self, cls: str) -> str:
        """检查是否为已知播放器类名"""
        for key, val in self.PLAYER_CLASSES.items():
            if cls.startswith(key) or cls == key:
                return val
        return ""

    def _match_browser_class(self, cls: str) -> str:
        """检查是否为浏览器类名"""
        for key, val in self.BROWSER_CLASSES.items():
            if key in cls:
                return val
        return ""

    def _detect_play_state(self, title: str, info: MediaInfo):
        """从窗口标题检测播放/暂停状态"""
        title_lower = title.lower()

        # 检测标题中的暂停关键词
        paused_keywords = ["(paused)", " [paused]", "— paused", "· paused",
                          "(暂停)", "【暂停】", "已暂停"]
        playing_keywords = ["(playing)", "(直播)", "(live)"]

        is_paused = any(kw in title_lower for kw in paused_keywords)
        is_playing = any(kw in title_lower for kw in playing_keywords)

        if is_paused:
            self._current_play_state = False
        elif is_playing:
            self._current_play_state = True
        # 如果是新歌曲，默认为播放中
        elif info.title != self._current_title:
            self._current_play_state = True

        info.is_playing = self._current_play_state
        info.status = "playing" if self._current_play_state else "paused"

    def _is_streaming_media(self, title: str) -> bool:
        """检查浏览器标题是否包含流媒体关键词"""
        return any(kw in title for kw in self.STREAMING_KEYWORDS)

    def _parse_title(self, title: str) -> MediaInfo:
        """解析窗口标题，尝试提取歌曲名和艺术家"""
        info = MediaInfo()

        # 移除应用标识后缀
        clean = title
        app_suffixes = [
            " - Spotify", " — Spotify", " · Spotify",
            " - Chrome", " — Chrome",
            " - Microsoft​ Edge", " — Microsoft​ Edge",
            " - 网易云音乐", " — 网易云音乐",
            " - QQ音乐", " — QQ音乐",
            " - YouTube Music", " — YouTube Music",
            " - Mozilla Firefox", " — Mozilla Firefox",
            " - VLC", " — VLC",
            " - PotPlayer", " — PotPlayer",
        ]
        for suffix in app_suffixes:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]
                break

        # 移除 YouTube 前缀等
        if clean.startswith("YouTube - "):
            clean = clean[len("YouTube - "):]
        if clean.startswith("YouTube Music - "):
            clean = clean[len("YouTube Music - "):]

        clean = clean.strip()
        if not clean:
            return info

        # 尝试多种分隔符解析 "歌曲名 - 艺术家"
        separators = [" — ", " - ", " · ", " • ", " / ", " | "]

        for sep in separators:
            if sep in clean:
                parts = clean.split(sep, 1)
                left = parts[0].strip()
                right = parts[1].strip()
                if left and right:
                    info.title = left
                    info.artist = right
                    info.status = "playing"
                    return info

        # 无法分隔，整个作为歌曲名
        info.title = clean
        info.artist = ""
        info.status = "playing"
        return info


# ── 桌面小组件 UI ────────────────────────────────────────────────
class MusicWidget:
    """桌面音乐信息悬浮窗"""

    # 颜色方案 — 轻量半透明风格
    COLORS = {
        "bg": "#f5f5f5",            # 浅灰背景
        "bg_accent": "#f0f0f0",     # 顶部栏浅灰
        "text_primary": "#2d2d2d",  # 深灰文字
        "text_secondary": "#8a8a8a", # 浅灰文字
        "text_accent": "#21bbf3",   # 亮蓝强调
        "playing_dot": "#34c759",   # 播放绿
        "paused_dot": "#ff9f0a",    # 暂停橙
        "stop_dot": "#c7c7c7",      # 停止灰
        "border": "#dcdcdc",        # 边框浅灰
        "btn_hover": "#21bbf3",     # 按钮悬停蓝
        "btn_text": "#555555",      # 按钮文字灰
        "btn_text_active": "#333333", # 播放按钮文字
    }

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("音乐信息小组件")

        # 窗口设置
        self.root.overrideredirect(True)  # 无边框
        self.root.attributes("-topmost", True)  # 置顶
        self.root.attributes("-alpha", 0.88)  # 半透明

        # 窗口大小与位置
        self.WIDTH = 380
        self.HEIGHT = 150
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.x_pos = screen_w - self.WIDTH - 30
        self.y_pos = screen_h - self.HEIGHT - 80
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{self.x_pos}+{self.y_pos}")

        # 拖拽状态
        self._drag_data = {"x": 0, "y": 0, "dragging": False}

        # 控制器
        self.controller = MediaController()
        self.current_info = MediaInfo()
        self.running = True

        # 设置窗口样式 (工具窗口 + 透明)
        self._setup_window_style()

        # 构建 UI
        self._build_ui()

        # 绑定事件
        self._bind_events()

        # 启动更新线程
        self._start_update_loop()

        # 创建系统托盘图标
        if HAS_TRAY:
            self._tray_icon = None
            self._tray_thread = None
            self._start_tray()

    def _create_tray_image(self):
        """创建系统托盘图标（音乐音符）"""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 绘制一个简单的音乐音符图标
        # 音符头（椭圆）
        draw.ellipse([8, 28, 24, 44], fill="#21bbf3")
        draw.ellipse([34, 38, 50, 54], fill="#21bbf3")
        # 音符杆（竖线）
        draw.rectangle([22, 12, 26, 42], fill="#21bbf3")
        draw.rectangle([48, 8, 52, 50], fill="#21bbf3")
        # 音符旗（弧线）
        draw.pieslice([22, 8, 42, 28], 180, 0, fill="#21bbf3")
        draw.pieslice([48, 4, 68, 24], 180, 0, fill="#21bbf3")

        return img

    def _start_tray(self):
        """在后台线程启动系统托盘"""
        def run_tray():
            icon_img = self._create_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("显示小组件", self._show_from_tray, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._quit_from_tray),
            )
            self._tray_icon = pystray.Icon("music_widget", icon_img, "音乐信息小组件", menu)

            # 由于 pystray 运行在自己的事件循环中，
            # 我们需要用 run() 而不是 run_detached() 或 threading
            # 但 tkinter 已经在主线程运行了 mainloop
            # 使用 run_detached 在新线程运行
            self._tray_icon.run_detached()

        self._tray_thread = threading.Thread(target=run_tray, daemon=True)
        self._tray_thread.start()

    def _show_from_tray(self):
        """从托盘恢复窗口"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except:
            pass

    def _quit_from_tray(self):
        """从托盘退出程序"""
        self._cleanup_tray()
        self._quit()

    def _cleanup_tray(self):
        """清理托盘图标"""
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except:
                pass
            self._tray_icon = None

    def _on_close(self):
        """关闭按钮：隐藏到托盘而非退出"""
        if HAS_TRAY and self._tray_icon is not None:
            self.root.withdraw()
        else:
            self._quit()

    def _setup_window_style(self):
        """设置 Windows 窗口样式"""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = ctypes.windll.user32.GetAncestor(
                    self.root.winfo_id(), 2  # GA_ROOT
                )

            # 设置工具窗口样式 (不在任务栏显示)
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = ex_style | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

            # 保留 WS_THICKFRAME 让 DWM 渲染圆角，移除 WS_CAPTION 隐藏标题栏
            # WS_POPUP = 0x80000000, WS_THICKFRAME = 0x00040000, WS_CAPTION = 0x00C00000
            GWL_STYLE = -16
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = style | 0x80040000  # WS_POPUP | WS_THICKFRAME
            style = style & ~0x00C00000  # ~WS_CAPTION
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)

            # Windows 11 圆角（必须在设置样式之后调用）
            set_rounded_corners(hwnd, self.WIDTH, self.HEIGHT)
        except Exception as e:
            pass

    def _build_ui(self):
        """构建 UI 元素"""
        # 主容器
        self.main_frame = tk.Frame(
            self.root,
            bg=self.COLORS["bg"],
            highlightbackground=self.COLORS["border"],
            highlightthickness=1,
        )
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # ── 顶部状态栏 ──
        self.top_bar = tk.Frame(self.main_frame, bg=self.COLORS["bg_accent"], height=24)
        self.top_bar.pack(fill=tk.X)
        self.top_bar.pack_propagate(False)

        # 播放状态指示灯
        self.status_dot = tk.Canvas(
            self.top_bar, width=10, height=10,
            bg=self.COLORS["bg_accent"],
            highlightthickness=0
        )
        self.status_dot.pack(side=tk.LEFT, padx=(8, 4), pady=7)
        self.dot = self.status_dot.create_oval(
            2, 2, 9, 9,
            fill=self.COLORS["stop_dot"],
            outline=""
        )

        # 来源应用名称
        self.source_label = tk.Label(
            self.top_bar,
            text="音乐信息小组件",
            font=("Microsoft YaHei UI", 8),
            fg=self.COLORS["text_secondary"],
            bg=self.COLORS["bg_accent"],
        )
        self.source_label.pack(side=tk.LEFT, padx=(4, 0))

        # 关闭按钮
        self.close_btn = tk.Label(
            self.top_bar,
            text=" ✕ ",
            font=("Segoe UI", 9),
            fg=self.COLORS["text_secondary"],
            bg=self.COLORS["bg_accent"],
            cursor="hand2"
        )
        self.close_btn.pack(side=tk.RIGHT, padx=(0, 6))
        self.close_btn.bind("<Button-1>", lambda e: self._on_close())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg="#ff4444"))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg=self.COLORS["text_secondary"]))

        # ── 主内容区域 ──
        self.content = tk.Frame(self.main_frame, bg=self.COLORS["bg"])
        self.content.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 6))

        # 歌曲标题
        self.title_label = tk.Label(
            self.content,
            text="♫ 未播放",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg=self.COLORS["text_primary"],
            bg=self.COLORS["bg"],
            anchor="w",
        )
        self.title_label.pack(fill=tk.X)

        # 艺术家
        self.artist_label = tk.Label(
            self.content,
            text="等待音乐...",
            font=("Microsoft YaHei UI", 9),
            fg=self.COLORS["text_secondary"],
            bg=self.COLORS["bg"],
            anchor="w",
        )
        self.artist_label.pack(fill=tk.X, pady=(2, 0))

        # ── 底部控制按钮（居中） ──
        self.control_frame = tk.Frame(self.content, bg=self.COLORS["bg"])
        self.control_frame.pack(fill=tk.X, pady=(8, 0))

        # 使用空白占位实现居中
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(4, weight=1)

        # 上一首
        self.prev_btn = tk.Label(
            self.control_frame, text=" ⏮ ",
            font=("Segoe UI", 14),
            fg=self.COLORS["btn_text"],
            bg=self.COLORS["bg"],
            cursor="hand2",
        )
        self.prev_btn.grid(row=0, column=1, padx=(0, 18))

        # 播放/暂停
        self.play_btn = tk.Label(
            self.control_frame, text=" ⏸ ",
            font=("Segoe UI", 15),
            fg=self.COLORS["btn_text_active"],
            bg=self.COLORS["bg"],
            cursor="hand2",
        )
        self.play_btn.grid(row=0, column=2, padx=(18, 18))

        # 下一首
        self.next_btn = tk.Label(
            self.control_frame, text=" ⏭ ",
            font=("Segoe UI", 14),
            fg=self.COLORS["btn_text"],
            bg=self.COLORS["bg"],
            cursor="hand2",
        )
        self.next_btn.grid(row=0, column=3, padx=(18, 0))

    def _bind_events(self):
        """绑定鼠标事件实现拖拽"""
        drag_widgets = [self.main_frame, self.top_bar, self.content,
                        self.title_label, self.artist_label,
                        self.source_label, self.status_dot]

        for w in drag_widgets:
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._stop_drag)

        # 右键菜单退出（有托盘时隐藏到托盘）
        self.main_frame.bind("<Button-3>", lambda e: self._on_close())

        # ── 媒体控制按钮 ──
        self.prev_btn.bind("<Button-1>", lambda e: self._send_media_key(VK_MEDIA_PREV_TRACK))
        self.play_btn.bind("<Button-1>", lambda e: self._on_play_pause())
        self.next_btn.bind("<Button-1>", lambda e: self._send_media_key(VK_MEDIA_NEXT_TRACK))

        # 悬停效果
        for btn in (self.prev_btn, self.play_btn, self.next_btn):
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=self.COLORS["text_accent"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(
                fg=self.COLORS["btn_text_active"] if b == self.play_btn else self.COLORS["btn_text"]
            ))

    def _on_play_pause(self):
        """处理播放/暂停按钮点击"""
        # 发送媒体按键
        self._send_media_key(VK_MEDIA_PLAY_PAUSE)
        # 切换本地播放状态跟踪
        is_playing = self.controller.toggle_play_state()
        self.play_btn.config(text=" ⏸ " if is_playing else " ▶ ")

    @staticmethod
    def _send_media_key(vk_code: int):
        """模拟发送媒体控制键"""
        try:
            user32.keybd_event(vk_code, 0, 0, 0)       # 按下
            user32.keybd_event(vk_code, 0, 2, 0)       # 抬起 (KEYEVENTF_KEYUP)
        except Exception:
            pass

    def _start_drag(self, event):
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root

    def _do_drag(self, event):
        dx = event.x_root - self._drag_data["x"]
        dy = event.y_root - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self._drag_data["x"] = event.x_root
        self._drag_data["y"] = event.y_root

    def _stop_drag(self, event):
        # 保存位置
        self.x_pos = self.root.winfo_x()
        self.y_pos = self.root.winfo_y()

    def _update_media(self):
        """更新媒体信息显示"""
        if not self.running:
            return

        try:
            info = self.controller.get_current_media()

            if info.status == "stopped":
                # 无播放内容
                self.title_label.config(text="♫ 未播放", fg=self.COLORS["text_secondary"])
                self.artist_label.config(text="等待音乐...")
                self.source_label.config(text="音乐信息小组件")
                self.status_dot.itemconfig(self.dot, fill=self.COLORS["stop_dot"])
                self.play_btn.config(text=" ⏸ ")
            else:
                # 有播放内容
                title = info.title
                if len(title) > 28:
                    title = title[:26] + "…"
                self.title_label.config(text=title, fg=self.COLORS["text_primary"])

                if info.artist:
                    artist = info.artist
                    if len(artist) > 24:
                        artist = artist[:22] + "…"
                    self.artist_label.config(text=artist)
                else:
                    self.artist_label.config(text="")

                src = info.source if info.source else "媒体应用"
                self.source_label.config(text=f"正在播放 · {src}")

                # 播放状态灯 & 按钮
                if info.is_playing:
                    self.status_dot.itemconfig(self.dot, fill=self.COLORS["playing_dot"])
                    self.play_btn.config(text=" ⏸ ")
                else:
                    self.status_dot.itemconfig(self.dot, fill=self.COLORS["paused_dot"])
                    self.play_btn.config(text=" ▶ ")

        except Exception as e:
            pass

        # 每秒刷新
        if self.running:
            self.root.after(1000, self._update_media)

    def _start_update_loop(self):
        """启动 UI 更新循环"""
        self.root.after(500, self._update_media)

    def _quit(self):
        """退出程序"""
        self.running = False
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
        raise SystemExit(0)

    def run(self):
        """运行小组件"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._quit()


# ── 入口 ──────────────────────────────────────────────────────────
def main():
    # 确保在正确的线程
    widget = MusicWidget()
    widget.run()


if __name__ == "__main__":
    main()
