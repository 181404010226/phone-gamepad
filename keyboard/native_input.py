"""Windows low-level keyboard hook. No keyboard recordings or network access."""
import ctypes as C
from ctypes import wintypes as W
import queue
import threading
import time

user32 = C.WinDLL('user32', use_last_error=True)
kernel32 = C.WinDLL('kernel32', use_last_error=True)
LRESULT = C.c_ssize_t
HOOKPROC = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)


class KBD(C.Structure):
    _fields_ = [('vkCode', W.DWORD), ('scanCode', W.DWORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', C.c_size_t)]


user32.SetWindowsHookExW.argtypes = [C.c_int, HOOKPROC, W.HINSTANCE, W.DWORD]
user32.SetWindowsHookExW.restype = W.HANDLE
user32.CallNextHookEx.argtypes = [W.HANDLE, C.c_int, W.WPARAM, W.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [W.HANDLE]
user32.UnhookWindowsHookEx.restype = W.BOOL
user32.GetKeyNameTextW.argtypes = [W.LONG, W.LPWSTR, C.c_int]
user32.GetAsyncKeyState.argtypes = [C.c_int]
user32.GetAsyncKeyState.restype = C.c_short
user32.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
user32.TranslateMessage.argtypes = [C.POINTER(W.MSG)]
user32.DispatchMessageW.argtypes = [C.POINTER(W.MSG)]
user32.DispatchMessageW.restype = LRESULT
kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]
kernel32.GetModuleHandleW.restype = W.HMODULE


def key_name(code):
    if code is None:
        return '未设置'
    buffer = C.create_unicode_buffer(80)
    parameter = ((code & 0xff) << 16) | ((code >> 8) << 24)
    return buffer.value if user32.GetKeyNameTextW(parameter, buffer, len(buffer)) else f'Scan {code:03X}'


class KeyboardHook:
    def __init__(self):
        self.lock = threading.RLock()
        self.events = queue.Queue()
        self.pressed = set()
        self.physical_down = set()
        self.used = set()
        self.running = False
        self.suppress = True
        self.capture = False
        self.swallowed = set()
        self.bypass = set()
        self.quit = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.last_pump = time.monotonic()
        self.thread = threading.Thread(target=self._loop, name='KeyboardHook', daemon=True)
        self.thread.start()
        if not self.ready.wait(3) or self.error:
            raise RuntimeError(f'键盘监听启动失败：{self.error or "超时"}')

    def configure(self, running, used=(), suppress=True):
        with self.lock:
            self.running = running
            self.used = set(used)
            self.suppress = suppress
            self.pressed.clear()
            # Keep swallowed keys until their matching key-up arrives.

    def set_capture(self, enabled):
        with self.lock:
            self.capture = enabled
            self.pressed.clear()

    def snapshot(self):
        with self.lock:
            return set(self.pressed), self.running

    def _callback(self, code, message, address):
        if code < 0:
            return user32.CallNextHookEx(None, code, message, address)
        try:
            event = C.cast(address, C.POINTER(KBD)).contents
            # Synthetic keystrokes from other programs are ignored.
            if event.flags & 0x10:
                return user32.CallNextHookEx(None, code, message, address)
            scan = int(event.scanCode) | (0x100 if event.flags & 1 else 0)
            down = message in (0x100, 0x104)
            up = message in (0x101, 0x105)
            if not (down or up):
                return user32.CallNextHookEx(None, code, message, address)
            with self.lock:
                repeated = scan in self.physical_down
                if down:
                    self.physical_down.add(scan)
                    self.pressed.add(scan)
                else:
                    self.physical_down.discard(scan)
                    self.pressed.discard(scan)
                if scan in (0x57, 0x58):
                    if down and not repeated:
                        self.running = False  # Release reports before GUI handles event.
                        self.events.put(('hotkey', 'toggle' if scan == 0x57 else 'stop'))
                    return 1
                if self.capture:
                    if down and not repeated:
                        self.events.put(('capture', scan))
                    if down:
                        self.swallowed.add(scan)
                    else:
                        self.swallowed.discard(scan)
                    return 1
                # Let Alt/Ctrl/Win combinations through, so Alt+Tab and system
                # shortcuts continue to work even if Tab or a letter is mapped.
                modifiers = any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x11, 0x12, 0x5b, 0x5c))
                if down and modifiers and scan not in self.swallowed:
                    self.bypass.add(scan)
                bypass = scan in self.bypass
                if bypass:
                    self.pressed.discard(scan)
                system_modifier = event.vkCode in (0x11, 0x12, 0xa2, 0xa3, 0xa4, 0xa5, 0x5b, 0x5c)
                block = scan in self.swallowed or (self.running and self.suppress and scan in self.used and not bypass and not system_modifier)
                if down and block:
                    self.swallowed.add(scan)
                if up:
                    self.swallowed.discard(scan)
                    self.bypass.discard(scan)
                if block:
                    return 1
        except Exception as exc:
            self.running = False
            self.events.put(('error', str(exc)))
        return user32.CallNextHookEx(None, code, message, address)

    def _loop(self):
        callback = HOOKPROC(self._callback)  # Must remain alive for the entire hook.
        hook = user32.SetWindowsHookExW(13, callback, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self.error = C.WinError(C.get_last_error())
            self.ready.set()
            return
        self.ready.set()
        msg = W.MSG()
        try:
            while not self.quit.is_set():
                while user32.PeekMessageW(C.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(C.byref(msg))
                    user32.DispatchMessageW(C.byref(msg))
                self.last_pump = time.monotonic()
                self.quit.wait(.004)
        finally:
            user32.UnhookWindowsHookEx(hook)

    def close(self):
        self.configure(False)
        self.quit.set()
        self.thread.join(timeout=2)
