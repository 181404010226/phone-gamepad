from pathlib import Path
import ctypes
import json
import math
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import default_config, report_for, send_report, validate_config, save_config
from native_input import KeyboardHook, KBD
from app import Engine, NEUTRAL


class FakePad:
    def __init__(self):
        self.history = []
        self.reset()

    def reset(self):
        self.buttons = 0
        self.lt = self.rt = 0
        self.left = self.right = (0, 0)

    def press_button(self, value): self.buttons = value
    def left_trigger(self, value): self.lt = value
    def right_trigger(self, value): self.rt = value
    def left_joystick(self, x, y): self.left = (x, y)
    def right_joystick(self, x, y): self.right = (x, y)
    def update(self): self.history.append((self.buttons, self.lt, self.rt, *self.left, *self.right))


class HookForTest(KeyboardHook):
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
        self.last_pump = time.monotonic()

    def event(self, scan, down=True, flags=0, vk=0):
        data = KBD(vk, scan & 0xff, flags | (1 if scan & 0x100 else 0), 0, 0)
        return self._callback(0, 0x100 if down else 0x101, ctypes.addressof(data))


class MappingTests(unittest.TestCase):
    def test_two_people_can_move_and_press_buttons_independently(self):
        cfg = default_config()
        held = {0x11, 0x22, 0x14d, 0x24}
        one = report_for(cfg['players'][0], held)
        two = report_for(cfg['players'][1], held)
        self.assertEqual(one, (0x1000, 0, 0, 0, 32767, 0, 0))
        self.assertEqual(two, (0x1000, 0, 0, 32767, 0, 0, 0))
        self.assertEqual(report_for(cfg['players'][0], {0x14d, 0x24}), NEUTRAL)

    def test_opposite_axes_and_dpad_cancel(self):
        mapping = default_config()['players'][0]
        mapping.update(du=10, dd=11, dl=12, dr=13)
        self.assertEqual(report_for(mapping, {0x11, 0x1f, 0x1e, 0x20, 10, 11, 12, 13}), NEUTRAL)

    def test_diagonal_never_exceeds_full_stick_speed(self):
        mapping = default_config()['players'][0]
        report = report_for(mapping, {0x11, 0x20})
        self.assertLessEqual(math.hypot(report[3], report[4]), 32768)
        self.assertEqual(report_for(mapping, {0x11, 0x20}, False)[3:5], (32767, 32767))

    def test_button_release_and_trigger_release(self):
        pad = FakePad()
        mapping = default_config()['players'][0]
        send_report(pad, report_for(mapping, {0x22, 0x2c, 0x2d}))
        self.assertEqual(pad.history[-1], (0x1000, 255, 255, 0, 0, 0, 0))
        send_report(pad, report_for(mapping, set()))
        self.assertEqual(pad.history[-1], NEUTRAL)

    def test_config_roundtrip_and_invalid_configs(self):
        cfg = default_config()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            save_config(path, cfg)
            self.assertEqual(validate_config(json.loads(path.read_text(encoding='utf-8'))), cfg)
        for bad in (True, 0x57, 0x58, -1, 512, 'W'):
            cfg['players'][0]['A'] = bad
            with self.assertRaises(ValueError): validate_config(cfg)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.hook = HookForTest()
        self.mock_user = patch('native_input.user32').start()
        self.addCleanup(patch.stopall)
        self.mock_user.CallNextHookEx.return_value = 0
        self.mock_user.GetAsyncKeyState.return_value = 0

    def test_intercept_only_mapped_keys_and_release_after_pause(self):
        self.hook.configure(True, {0x11}, True)
        self.assertEqual(self.hook.event(0x11), 1)
        self.assertEqual(self.hook.event(0x24), 0)
        self.hook.configure(False)
        self.assertEqual(self.hook.event(0x11, False), 1)
        self.assertEqual(self.hook.event(0x24, False), 0)
        self.assertFalse(self.hook.pressed)
        self.assertFalse(self.hook.swallowed)

    def test_hotkey_repeat_does_not_toggle_after_pressed_state_reset(self):
        self.hook.event(0x57)
        self.hook.configure(True)
        self.hook.event(0x57)  # Windows autorepeat.
        self.assertEqual(self.hook.events.qsize(), 1)
        self.assertTrue(self.hook.running)
        self.hook.event(0x57, False)
        self.hook.event(0x57)
        self.assertEqual(self.hook.events.qsize(), 2)
        self.assertFalse(self.hook.running)

    def test_f12_disables_output_before_ui_handles_it(self):
        self.hook.configure(True, {0x11})
        self.hook.event(0x11)
        self.hook.event(0x58)
        self.assertFalse(self.hook.snapshot()[1])
        self.assertEqual(self.hook.events.get_nowait(), ('hotkey', 'stop'))

    def test_capture_extended_key_and_ignore_injected_input(self):
        self.hook.set_capture(True)
        self.assertEqual(self.hook.event(0x148), 1)
        self.assertEqual(self.hook.events.get_nowait(), ('capture', 0x148))
        self.assertEqual(self.hook.event(0x20, flags=0x10), 0)
        self.assertNotIn(0x20, self.hook.pressed)

    def test_system_shortcuts_can_pass_through(self):
        self.mock_user.GetAsyncKeyState.return_value = -32768
        self.hook.configure(True, {0x0f}, True)
        self.assertEqual(self.hook.event(0x0f), 0)
        self.assertNotIn(0x0f, self.hook.pressed)
        self.assertEqual(self.hook.event(0x0f, False), 0)

    def test_mapped_alt_still_reaches_windows_for_alt_tab(self):
        self.hook.configure(True, {0x38}, True)
        self.assertEqual(self.hook.event(0x38, vk=0xa4), 0)
        self.assertIn(0x38, self.hook.pressed)


class EngineTests(unittest.TestCase):
    def test_worker_sends_two_reports_then_neutral_on_emergency_and_exit(self):
        hook = HookForTest()
        created = []
        def create():
            pad = FakePad()
            created.append(pad)
            return pad
        fake_module = type('VGamepad', (), {'VX360Gamepad': staticmethod(create)})()
        with patch.dict(sys.modules, {'vgamepad': fake_module}):
            engine = Engine(hook, default_config())
            try:
                engine.connect.set()
                self.assertEqual(engine.events.get(timeout=2)[0], 'connected')
                hook.configure(True)
                with hook.lock:
                    hook.pressed.update({0x22, 0x24, 0x11, 0x14d})
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline and not all(p.history and p.history[-1][0] == 0x1000 for p in created):
                    time.sleep(.005)
                self.assertEqual(len(created), 2)
                self.assertEqual(created[0].history[-1][4], 32767)
                self.assertEqual(created[1].history[-1][3], 32767)
                hook.configure(False)
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline and any(p.history[-1] != NEUTRAL for p in created):
                    time.sleep(.005)
                self.assertTrue(all(p.history[-1] == NEUTRAL for p in created))
            finally:
                engine.close()
            self.assertFalse(engine.thread.is_alive())
            self.assertTrue(all(p.history[-1] == NEUTRAL for p in created))


if __name__ == '__main__':
    unittest.main()
