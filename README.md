# A-media-information-widgets
A Windows media widgets by Python
What is this?
A lightweight Windows desktop overlay widget that displays your currently playing music information in real time. It sits in the corner of your screen so you can see the song title and artist without switching to your media player.

✨ Features
Feature	Description
Live song info	Song title, artist, playback source
Playback indicator	🟢 Green = playing / 🟡 Orange = paused / ⚫ Gray = stopped
Media controls	⏮ Previous / ⏸ Play-Pause / ⏭ Next
14+ player support	Spotify, NetEase Cloud Music, QQ Music, Chrome/Edge (YouTube, etc.), Firefox, VLC, PotPlayer, MPC-HC…
System tray	Minimizes to tray on close; right-click menu to show or exit
Translucent rounded UI	Light glassmorphism style, 88% opacity, native Windows 11 rounded corners
Drag to move	Click and drag anywhere on the widget to reposition
Play state detection	Auto-detects song changes; toggle state manually via button
⚙️ How it works
Window title scanning — Enumerates all visible Windows windows once per second
Player identification — Matches known window class names (SpotifyMainWindow, Chrome_WidgetWin_1, OrpheusBrowserHost, etc.)
Title parsing — Extracts "Song Title - Artist" from window titles
Browser filtering — Browser tabs only match when they contain streaming keywords (YouTube, Spotify, Bilibili, etc.)
Key simulation — Button clicks send multimedia keys (VK_MEDIA_PLAY_PAUSE, etc.) via user32.keybd_event()
State tracking — Maintains a local play/pause state toggled on button press

<img width="475" height="188" alt="image" src="https://github.com/user-attachments/assets/c4f9bc2a-0a86-4e97-9ad6-1aa41a69739e" />

这是什么？
一个 轻量级 Windows 桌面悬浮窗，基于Python，实时显示当前电脑正在播放的音乐信息。放在桌面右下角，无需打开播放器就能看到歌曲名和艺术家。

✨ 功能一览
功能	说明
实时显示歌曲信息	歌曲名、艺术家、播放来源
播放状态指示	🟢 绿色 = 播放中 / 🟡 橙色 = 暂停 / ⚫ 灰色 = 无播放
媒体控制按钮	⏮ 上一首 / ⏸ 播放暂停 / ⏭ 下一首
支持 14+ 播放器	Spotify、网易云音乐、QQ音乐、Chrome/Edge/Firefox（YouTube等）、VLC、PotPlayer……
系统托盘驻留	关闭窗口后隐藏到托盘，右键菜单可恢复或退出
半透明圆角 UI	浅色玻璃风格，88% 透明度，Windows 11 原生圆角
拖拽移动	鼠标按住任意位置拖动到桌面任意位置
播放状态智能检测	自动识别切歌，手动点击按钮切换状态
⚙️ 工作原理
窗口标题扫描 — 每秒遍历一次 Windows 所有可见窗口
播放器识别 — 通过窗口类名（SpotifyMainWindow、Chrome_WidgetWin_1、OrpheusBrowserHost 等）匹配已知播放器
标题解析 — 从窗口标题中提取「歌曲名 - 艺术家」
浏览器过滤 — 浏览器标签仅当包含 YouTube/Spotify/Bilibili 等流媒体关键词时才识别
按键模拟 — 点击按钮通过 user32.keybd_event() 发送多媒体键（VK_MEDIA_PLAY_PAUSE 等）
状态跟踪 — 本地维护播放/暂停状态，按钮点击时同步切换
📁 文件结构

