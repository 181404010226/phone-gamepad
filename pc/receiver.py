"""Phone Gamepad Windows receiver: UDP + a visible desktop status panel."""
import json
import logging
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PhoneGamepad'
DATA.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(BASE / 'vendor'))
from core import send_report
from mobile_protocol import PORT, VERSION, MAX_PLAYERS, NEUTRAL, Sessions


def local_addresses():
    addresses = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = item[4][0]
            if not ip.startswith(('127.', '169.254.')):
                addresses.add(ip)
    except OSError:
        pass
    return sorted(addresses, key=lambda ip: (not ip.startswith('192.168.'), ip))


class Receiver:
    def __init__(self, port=PORT, preview=False):
        self.port = port
        self.preview = preview
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.sessions = Sessions()
        self.lock = threading.Lock()
        self.mode = 'starting'
        self.driver_error = ''
        self.history = [NEUTRAL] * MAX_PLAYERS
        self.controller_errors = [''] * MAX_PLAYERS
        self.thread = threading.Thread(target=self.run, name='PhoneGamepadUDP', daemon=True)
        self.thread.start()

    def run(self):
        pads = [None] * MAX_PLAYERS
        retry_after = [0.] * MAX_PLAYERS
        last_sent = [0.] * MAX_PLAYERS
        vg = None
        sock = None
        try:
            if not self.preview:
                try:
                    import vgamepad as vg
                    self.mode = 'xinput'
                except Exception as exc:
                    self.driver_error = str(exc)
                    self.mode = 'preview'
            else:
                self.mode = 'preview'
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Exclusive binding prevents another receiver from stealing packets.
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('0.0.0.0', self.port))
            self.port = sock.getsockname()[1]
            sock.settimeout(.02)
            self.events.put(('ready', self.mode))

            def apply(slot, report):
                if vg is not None:
                    try:
                        if pads[slot] is None:
                            if time.monotonic() < retry_after[slot]:
                                return False
                            pads[slot] = vg.VX360Gamepad()
                        if report != self.history[slot] or self.controller_errors[slot] or time.monotonic() - last_sent[slot] >= .1:
                            send_report(pads[slot], report)
                            last_sent[slot] = time.monotonic()
                        self.controller_errors[slot] = ''
                    except Exception as exc:
                        self.controller_errors[slot] = str(exc)
                        retry_after[slot] = time.monotonic() + 2
                        return False
                self.history[slot] = report
                return True

            while not self.stop.is_set():
                with self.lock:
                    changes = self.sessions.expire(time.monotonic())
                for change in changes:
                    apply(*change)
                try:
                    packet, address = sock.recvfrom(2048)
                    if len(packet) > 1500:
                        continue
                    data = json.loads(packet)
                    if isinstance(data, dict) and data.get('v') == VERSION and data.get('type') == 'discover':
                        with self.lock:
                            available = sum(item is None for item in self.sessions.slots)
                            assigned = next((i + 1 for i, lease in enumerate(self.sessions.slots)
                                             if lease is not None and lease.client == data.get('client')), 0)
                        response = dict(v=VERSION, type='host', name=socket.gethostname(), port=self.port,
                                        max_players=MAX_PLAYERS, available=available, player=assigned)
                    else:
                        with self.lock:
                            response, change = self.sessions.receive(data, address, time.monotonic())
                        if change and not apply(*change):
                            response.update(ok=False, error='controller_unavailable')
                        response.update(v=VERSION, mode=self.mode)
                    sock.sendto(json.dumps(response).encode(), address)
                except socket.timeout:
                    pass
                except (ValueError, UnicodeError, TypeError, OverflowError):
                    continue
                except (ConnectionResetError, ConnectionRefusedError):
                    pass  # A phone may close its UDP socket while an ACK is in flight.
        except Exception as exc:
            logging.exception('Receiver stopped')
            self.events.put(('error', str(exc)))
        finally:
            for slot, pad in enumerate(pads):
                if pad is not None:
                    try:
                        send_report(pad, NEUTRAL)
                    except Exception:
                        logging.exception('Controller reset failed')
                self.history[slot] = NEUTRAL
            pads.clear()
            if sock:
                sock.close()

    def snapshot(self):
        with self.lock:
            return [(lease.name, lease.address[0], time.monotonic() - lease.seen, lease.report)
                    if lease else None for lease in self.sessions.slots]

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)


class Panel:
    def __init__(self, root, preview=False, port=PORT):
        self.root = root
        self.preview = preview
        self.port = port
        self.server = Receiver(port=self.port, preview=preview)
        root.title('四人手机手柄 · 电脑接收端')
        root.geometry('810x620')
        root.minsize(760, 600)
        main = ttk.Frame(root, padding=24)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='四人手机手柄', font=('Microsoft YaHei UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(main, text='打开手机应用即可自动匹配；按连接顺序分配玩家 1～4。').pack(anchor='w', pady=8)
        ttk.Label(main, text='电脑 IP：' + '  /  '.join(local_addresses()), font=('Consolas', 13)).pack(anchor='w', pady=8)
        ttk.Label(main, text=f'自动分配玩家 · 无需配对码 · UDP {self.server.port}', font=('Microsoft YaHei UI', 16, 'bold'), foreground='#007f88').pack(anchor='w', pady=8)
        self.status = tk.StringVar(value='正在启动接收器…')
        ttk.Label(main, textvariable=self.status, wraplength=675).pack(anchor='w', pady=12)
        self.players = [tk.StringVar(value=f'玩家 {i + 1}：等待自动连接') for i in range(MAX_PLAYERS)]
        grid = ttk.Frame(main)
        grid.pack(fill='both', expand=True)
        grid.columnconfigure((0, 1), weight=1)
        for index, value in enumerate(self.players):
            box = ttk.LabelFrame(grid, text=f'玩家 {index + 1}', padding=12)
            box.grid(row=index // 2, column=index % 2, sticky='nsew', padx=4, pady=6)
            ttk.Label(box, textvariable=value, wraplength=330).pack(anchor='w')
        row = ttk.Frame(main)
        row.pack(fill='x', pady=16)
        ttk.Button(row, text='安装手柄驱动', command=self.install_driver).pack(side='left')
        ttk.Button(row, text='重新检测驱动', command=self.restart).pack(side='left', padx=8)
        ttk.Button(row, text='检查 Xbox 手柄', command=lambda: subprocess.Popen(['control.exe', 'joy.cpl'])).pack(side='left')
        ttk.Label(main, text='手机与电脑连接同一 Wi-Fi。Windows 防火墙提示时，请允许专用网络。\n'
                  '手机切到后台或断线后自动松开全部按钮；关闭本窗口会断开虚拟手柄。', wraplength=675).pack(anchor='w')
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(50, self.tick)

    def install_driver(self):
        subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(BASE / 'InstallDriver.ps1')], cwd=BASE, creationflags=subprocess.CREATE_NO_WINDOW)

    def restart(self):
        self.server.close()
        for name in list(sys.modules):
            if name == 'vgamepad' or name.startswith('vgamepad.'):
                del sys.modules[name]
        self.server = Receiver(port=self.port, preview=self.preview)
        self.status.set('重新检测中，手机将自动重连…')

    def tick(self):
        while True:
            try:
                kind, value = self.server.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'ready':
                self.status.set('接收器已就绪 · 连接手机后将创建 Xbox 360 手柄。' if value == 'xinput' else
                                '手机连接测试可用；未连接虚拟手柄。请安装 ViGEmBus 驱动，再点「重新检测驱动」。')
            elif kind == 'error':
                self.status.set('接收器已停止：' + value)
        for index, lease in enumerate(self.server.snapshot()):
            if lease:
                name, ip, age, report = lease
                state = '在线' if age < .6 else '断线，已回中'
                error = self.server.controller_errors[index]
                self.players[index].set(f'{name} · {ip}\n{state}' + (' · 系统手柄位不足，请关闭旧映射工具' if error else '') +
                                       f'\n按钮 {report[0]:04X}  左摇杆 {report[3:5]}\n右摇杆 {report[5:7]}')
            else:
                self.players[index].set(f'玩家 {index + 1}：等待手机连接')
        self.root.after(50, self.tick)

    def close(self):
        self.server.close()
        self.root.destroy()


def main():
    import argparse
    args = argparse.ArgumentParser()
    args.add_argument('--preview', action='store_true', help='Test LAN without a driver')
    args.add_argument('--port', type=int, default=PORT, help='UDP port (default: 26761)')
    args.add_argument('--smoke-test', action='store_true', help='Close automatically after 8 seconds for packaging checks')
    options = args.parse_args()
    if not 0 <= options.port <= 65535:
        args.error('--port must be between 0 and 65535')
    logging.basicConfig(filename=DATA / 'receiver.log', level=logging.INFO, encoding='utf-8')
    root = tk.Tk()
    ttk.Style().theme_use('vista')
    panel = Panel(root, options.preview, options.port)
    if options.smoke_test:
        root.after(8000, panel.close)
    root.mainloop()


if __name__ == '__main__':
    main()
