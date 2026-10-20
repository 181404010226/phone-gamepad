"""一块键盘，两个 Xbox 360 手柄。Windows / Python 3.10+."""
import ctypes
from copy import deepcopy
import json
import logging
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'vendor'))
from core import ACTIONS, RESERVED, default_config, validate_config, save_config, report_for, send_report
from native_input import KeyboardHook, key_name

DRIVER_URL = 'https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0'
NEUTRAL = (0, 0, 0, 0, 0, 0, 0)


class Engine:
    """Reports are sent off the GUI thread, including neutral reports on pause."""
    def __init__(self, hook, config):
        self.hook = hook
        self.config = deepcopy(config)
        self.lock = threading.Lock()
        self.events = queue.Queue()
        self.connect = threading.Event()
        self.quit = threading.Event()
        self.reports = [NEUTRAL, NEUTRAL]
        self.thread = threading.Thread(target=self._run, name='XInputOutput', daemon=True)
        self.thread.start()

    def set_config(self, config):
        with self.lock:
            self.config = deepcopy(config)

    def _run(self):
        pads = []
        previous = [None, None]
        try:
            while not self.quit.is_set():
                if self.connect.is_set():
                    self.connect.clear()
                    if not pads:
                        try:
                            import vgamepad
                            for _ in range(2):
                                pads.append(vgamepad.VX360Gamepad())
                            previous = [None, None]
                            self.events.put(('connected', None))
                        except Exception as exc:
                            for pad in pads:
                                try:
                                    send_report(pad, NEUTRAL)
                                except Exception:
                                    pass
                            pads.clear()
                            pad = None
                            # Permit retry after a driver install in the same app.
                            for name in list(sys.modules):
                                if name == 'vgamepad' or name.startswith('vgamepad.'):
                                    del sys.modules[name]
                            self.events.put(('connect_error', str(exc)))
                pressed, running = self.hook.snapshot()
                if time.monotonic() - self.hook.last_pump > .75:
                    if running:
                        self.hook.configure(False)
                        self.events.put(('error', '键盘监听无响应，已暂停输出。'))
                    running = False
                with self.lock:
                    config = self.config
                reports = [report_for(player, pressed, config['diagonal']) if running else NEUTRAL
                           for player in config['players']]
                if pads:
                    for index, pad in enumerate(pads):
                        if reports[index] != previous[index]:
                            send_report(pad, reports[index])
                            previous[index] = reports[index]
                self.reports = reports
                self.quit.wait(.008)
        except Exception as exc:
            logging.exception('Output worker failed')
            self.hook.configure(False)
            self.events.put(('error', str(exc)))
        finally:
            for pad in pads:
                try:
                    send_report(pad, NEUTRAL)
                except Exception:
                    logging.exception('Could not reset a controller')
            pads.clear()  # vgamepad destructor detaches the devices.

    def close(self):
        self.hook.configure(False)
        self.quit.set()
        self.thread.join(timeout=3)


class App:
    def __init__(self, root):
        self.root = root
        root.title('双人键盘手柄 · Keyboard Dual Pad')
        root.geometry('1000x790')
        root.minsize(860, 700)
        self.config_path = BASE / 'config.json'
        self.config = default_config()
        warning = None
        if self.config_path.exists():
            try:
                self.config = validate_config(json.loads(self.config_path.read_text(encoding='utf-8-sig')))
            except Exception as exc:
                warning = f'配置未载入，已使用默认值。原文件保留。\n{exc}'
        self.hook = KeyboardHook()
        self.engine = Engine(self.hook, self.config)
        self.running = False
        self.connected = False
        self.connecting = False
        self.pending_stop = False
        self.capture_target = None
        self.capture_window = None
        self.closed = False
        self.suppress = tk.BooleanVar(value=self.config['suppress'])
        self.diagonal = tk.BooleanVar(value=self.config['diagonal'])
        self.status = tk.StringVar(value='已暂停 · 先改键，然后点击「启动两个手柄」')
        self.bindings = {}
        self.meters = [tk.StringVar(value='等待启动'), tk.StringVar(value='等待启动')]
        style = ttk.Style()
        style.theme_use('vista')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 18, 'bold'))
        style.configure('TButton', padding=(8, 5))
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        main = ttk.Frame(root, padding=18)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='一块键盘，两名玩家', style='Title.TLabel').pack(anchor='w')
        ttk.Label(main, text='模拟两个 Xbox 360 手柄 · F11 启动 / 暂停 · F12 紧急暂停').pack(anchor='w', pady=(3, 10))
        toolbar = ttk.Frame(main)
        toolbar.pack(fill='x')
        self.start_button = ttk.Button(toolbar, text='启动两个手柄', command=self.toggle)
        self.start_button.pack(side='left')
        ttk.Button(toolbar, text='保存配置', command=self.save).pack(side='left', padx=6)
        ttk.Button(toolbar, text='导入配置', command=self.load).pack(side='left')
        ttk.Button(toolbar, text='恢复默认', command=self.defaults).pack(side='left', padx=6)
        ttk.Button(toolbar, text='检查手柄', command=lambda: subprocess.Popen(['control.exe', 'joy.cpl'])).pack(side='right')
        ttk.Button(toolbar, text='安装驱动', command=self.install_driver).pack(side='right', padx=6)
        ttk.Label(main, textvariable=self.status, foreground='#176c8c', wraplength=900).pack(anchor='w', pady=10)
        options = ttk.Frame(main)
        options.pack(fill='x', pady=(0, 8))
        ttk.Checkbutton(options, text='拦截已映射按键，减少游戏重复收到键盘输入', variable=self.suppress,
                        command=self.options_changed).pack(side='left')
        ttk.Checkbutton(options, text='斜向速度归一化', variable=self.diagonal,
                        command=self.options_changed).pack(side='right')
        notebook = ttk.Notebook(main)
        notebook.pack(fill='both', expand=True)
        for player in range(2):
            page = ttk.Frame(notebook, padding=12)
            notebook.add(page, text=f'  玩家 {player + 1}  ')
            ttk.Label(page, text='点击按键按钮后，按一次要绑定的键；右键点击可清除。').grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 6))
            for index, (action, label) in enumerate(ACTIONS.items()):
                column = (index // 12) * 2
                row = index % 12 + 1
                ttk.Label(page, text=label).grid(row=row, column=column, sticky='w', padx=(0, 12), pady=2)
                value = tk.StringVar(value=key_name(self.config['players'][player][action]))
                self.bindings[player, action] = value
                button = ttk.Button(page, textvariable=value, width=19,
                                    command=lambda p=player, a=action: self.capture(p, a))
                button.grid(row=row, column=column + 1, sticky='ew', padx=(0, 22), pady=2)
                button.bind('<Button-3>', lambda event, p=player, a=action: self.bind_key(p, a, None))
            page.columnconfigure(1, weight=1)
            page.columnconfigure(3, weight=1)
        for player in range(2):
            ttk.Label(main, textvariable=self.meters[player], foreground='#555555').pack(anchor='w', pady=(6, 0))
        ttk.Label(main, text='使用：先启动映射，再启动游戏。切回游戏后，按 1 / 0（Start）或 G / J（A）加入。\n'
                  '默认移动：玩家 1 = WASD；玩家 2 = 方向键。改键和导入配置会暂停映射。',
                  wraplength=910).pack(anchor='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(30, self.tick)
        if warning:
            root.after(100, lambda: messagebox.showwarning('配置提示', warning, parent=root))

    def sync_config(self):
        self.config['suppress'] = self.suppress.get()
        self.config['diagonal'] = self.diagonal.get()
        self.engine.set_config(self.config)

    def options_changed(self):
        self.pause()
        self.sync_config()
        self.status.set('选项已修改并暂停；点击启动后生效，点击保存配置可保留。')

    def pause(self):
        if self.connecting:
            self.pending_stop = True
        self.running = False
        self.hook.configure(False)
        self.start_button.configure(text='继续映射' if self.connected else '启动两个手柄')
        self.status.set('已暂停 · 两个手柄已回中，键盘正常输入')

    def activate(self):
        self.sync_config()
        used = {key for player in self.config['players'] for key in player.values() if key is not None}
        self.hook.configure(True, used, self.config['suppress'])
        self.running = True
        self.start_button.configure(text='暂停映射')
        self.status.set('运行中 · 两个虚拟手柄已连接 · 切回游戏，按各自 Start 或 A 加入 · F12 可随时暂停')

    def toggle(self):
        if self.capture_target is not None or self.connecting:
            return
        if not self.engine.thread.is_alive():
            messagebox.showerror('输出线程已停止', '请关闭并重新启动本程序。', parent=self.root)
            return
        if self.running:
            self.pause()
        elif self.connected:
            self.activate()
        else:
            self.pending_stop = False
            self.connecting = True
            self.start_button.configure(state='disabled')
            self.status.set('正在连接两个 Xbox 360 虚拟手柄…')
            self.engine.connect.set()

    def capture(self, player, action):
        self.pause()
        self.capture_target = (player, action)
        popup = self.capture_window = tk.Toplevel(self.root)
        popup.title('设置按键')
        popup.transient(self.root)
        popup.resizable(False, False)
        ttk.Label(popup, text=f'玩家 {player + 1} · {ACTIONS[action]}', padding=15).pack()
        ttk.Label(popup, text='请按一个键（左右修饰键、数字小键盘可区分）\nF11 / F12 为保留快捷键，无法绑定。', padding=15).pack()
        ttk.Button(popup, text='取消', command=self.end_capture).pack(pady=12)
        popup.protocol('WM_DELETE_WINDOW', self.end_capture)
        popup.grab_set()
        popup.focus_force()
        self.hook.set_capture(True)

    def end_capture(self):
        self.hook.set_capture(False)
        self.capture_target = None
        if self.capture_window is not None:
            self.capture_window.destroy()
            self.capture_window = None

    def bind_key(self, player, action, scan):
        self.pause()
        if scan in RESERVED:
            return
        conflicts = [f'玩家 {p + 1} {ACTIONS[a]}' for p, mapping in enumerate(self.config['players'])
                     for a, code in mapping.items() if scan is not None and code == scan and (p, a) != (player, action)]
        if conflicts and not messagebox.askyesno('按键重复', f'{key_name(scan)} 已用于：\n' + '\n'.join(conflicts) + '\n\n仍然绑定？这个键会同时触发这些动作。', parent=self.root):
            return
        self.config['players'][player][action] = scan
        self.bindings[player, action].set(key_name(scan))
        self.sync_config()
        self.status.set('按键已修改 · 点击「保存配置」保留，再继续映射')

    def refresh_bindings(self):
        self.suppress.set(self.config['suppress'])
        self.diagonal.set(self.config['diagonal'])
        for (player, action), value in self.bindings.items():
            value.set(key_name(self.config['players'][player][action]))
        self.sync_config()

    def save(self):
        self.sync_config()
        try:
            save_config(self.config_path, self.config)
            self.status.set('配置已保存到 config.json' + (' · 映射继续运行' if self.running else ' · 当前已暂停'))
        except Exception as exc:
            messagebox.showerror('保存失败', str(exc), parent=self.root)

    def load(self):
        self.pause()
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('JSON 配置', '*.json')])
        if path:
            try:
                config = validate_config(json.loads(Path(path).read_text(encoding='utf-8-sig')))
                self.config = config
                self.refresh_bindings()
                self.status.set('配置已导入，点击保存可设为下次启动配置。')
            except Exception as exc:
                messagebox.showerror('导入失败', str(exc), parent=self.root)

    def defaults(self):
        self.pause()
        self.config = default_config()
        self.refresh_bindings()
        self.status.set('已恢复默认按键，点击保存配置可保留。')

    def install_driver(self):
        self.pause()
        installer = BASE / 'InstallDriver.ps1'
        subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(installer)], cwd=BASE)

    def tick(self):
        if self.closed:
            return
        for source in (self.hook.events, self.engine.events):
            while True:
                try:
                    kind, value = source.get_nowait()
                except queue.Empty:
                    break
                if kind == 'hotkey':
                    if self.capture_target is not None:
                        self.end_capture()
                        self.pause()
                    elif value == 'stop':
                        self.pause()
                    else:
                        self.toggle()
                elif kind == 'capture' and self.capture_target is not None:
                    player, action = self.capture_target
                    self.end_capture()
                    self.bind_key(player, action, value)
                elif kind == 'connected':
                    self.connected = True
                    self.connecting = False
                    self.start_button.configure(state='normal')
                    # A stop during connection cancels activation.
                    if self.pending_stop:
                        self.pause()
                    else:
                        self.activate()
                elif kind == 'connect_error':
                    self.connecting = False
                    self.start_button.configure(state='normal')
                    self.pause()
                    self.status.set('连接失败 · 请安装 ViGEmBus 驱动，必要时重启 Windows 后重试。')
                    logging.error('Controller connection failed: %s', value)
                    messagebox.showerror('虚拟手柄尚未连接', '无法创建两个 Xbox 手柄。请点击「安装驱动」，完成后重新启动本程序。\n\n'
                                         f'详细信息：{value}\n官方驱动：{DRIVER_URL}', parent=self.root)
                elif kind == 'error':
                    self.pause()
                    self.status.set(f'已暂停：{value}；若无法恢复请重新启动本程序。')
        for player, report in enumerate(self.engine.reports):
            buttons, lt, rt, lx, ly, rx, ry = report
            self.meters[player].set(f'玩家 {player + 1}  |  左摇杆 ({lx:6}, {ly:6})  右摇杆 ({rx:6}, {ry:6})  '
                                   f'LT {lt:3}  RT {rt:3}  按钮 0x{buttons:04X}')
        self.root.after(30, self.tick)

    def close(self):
        self.closed = True
        self.hook.configure(False)
        self.engine.close()
        self.hook.close()
        self.root.destroy()


def main():
    if sys.platform != 'win32':
        raise SystemExit('本程序仅支持 Windows。')
    # Prevent a second instance from creating two additional gamepads.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\KeyboardDualPad_2026')
    if not mutex or ctypes.get_last_error() == 183:
        ctypes.windll.user32.MessageBoxW(None, '双人键盘手柄已经运行，请查看任务栏。', '提示', 0)
        return
    logging.basicConfig(filename=BASE / 'app.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    root = tk.Tk()
    try:
        app = App(root)
        if '--smoke-test' in sys.argv:
            root.after(500, app.close)
        root.mainloop()
    except Exception:
        logging.exception('Application startup failed')
        messagebox.showerror('启动失败', '请查看程序目录中的 app.log。', parent=root)
        raise
    finally:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
