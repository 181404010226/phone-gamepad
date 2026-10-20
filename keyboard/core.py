"""Platform-independent keyboard -> two XInput report calculation."""
from copy import deepcopy
import json
import math
from pathlib import Path

ACTIONS = {
    'lx_up': '左摇杆 ↑', 'lx_down': '左摇杆 ↓',
    'lx_left': '左摇杆 ←', 'lx_right': '左摇杆 →',
    'A': 'A / 确认', 'B': 'B / 返回', 'X': 'X', 'Y': 'Y',
    'LB': 'LB / 左肩', 'RB': 'RB / 右肩', 'LT': 'LT / 左扳机', 'RT': 'RT / 右扳机',
    'START': 'Start / 加入 / 暂停', 'BACK': 'Back / 选择',
    'LS': '左摇杆按下', 'RS': '右摇杆按下',
    'du': '十字键 ↑', 'dd': '十字键 ↓', 'dl': '十字键 ←', 'dr': '十字键 →',
    'rx_up': '右摇杆 ↑', 'rx_down': '右摇杆 ↓',
    'rx_left': '右摇杆 ←', 'rx_right': '右摇杆 →',
}
BUTTONS = dict(A=0x1000, B=0x2000, X=0x4000, Y=0x8000,
               LB=0x100, RB=0x200, START=0x10, BACK=0x20,
               LS=0x40, RS=0x80, du=1, dd=2, dl=4, dr=8)
RESERVED = {0x57, 0x58}  # Physical F11, F12


def default_config():
    players = [{action: None for action in ACTIONS} for _ in range(2)]
    players[0].update(lx_up=0x11, lx_down=0x1f, lx_left=0x1e, lx_right=0x20,
                      A=0x22, B=0x23, X=0x14, Y=0x15, LB=0x10, RB=0x12,
                      LT=0x2c, RT=0x2d, START=0x02, BACK=0x03)
    players[1].update(lx_up=0x148, lx_down=0x150, lx_left=0x14b, lx_right=0x14d,
                      A=0x24, B=0x25, X=0x17, Y=0x18, LB=0x16, RB=0x19,
                      LT=0x31, RT=0x32, START=0x0b, BACK=0x0a)
    return dict(version=1, suppress=True, diagonal=True, players=players)


def validate_config(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('配置格式或版本不正确。')
    players = data.get('players')
    if not isinstance(players, list) or len(players) != 2:
        raise ValueError('配置必须包含两名玩家。')
    result = default_config()
    for option in ('suppress', 'diagonal'):
        if type(data.get(option)) is not bool:
            raise ValueError(f'{option} 必须为 true / false。')
        result[option] = data[option]
    for index, player in enumerate(players):
        if not isinstance(player, dict) or set(player) != set(ACTIONS):
            raise ValueError(f'玩家 {index + 1} 的按键配置不完整。')
        for action, code in player.items():
            if code is not None and (type(code) is not int or not 1 <= code <= 0x1ff or code in RESERVED):
                raise ValueError(f'{action} 的按键无效，F11 / F12 为保留快捷键。')
        result['players'][index] = deepcopy(player)
    return result


def save_config(path, config):
    data = validate_config(config)
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def report_for(mapping, pressed, diagonal=True):
    active = {action for action, code in mapping.items() if code is not None and code in pressed}
    buttons = 0
    for action, mask in BUTTONS.items():
        if action in active:
            buttons |= mask
    # Opposing directions cancel, including the D-pad.
    if {'du', 'dd'} <= active:
        buttons &= ~3
    if {'dl', 'dr'} <= active:
        buttons &= ~12
    axes = []
    for stick in ('lx', 'rx'):
        x = int(stick + '_right' in active) - int(stick + '_left' in active)
        y = int(stick + '_up' in active) - int(stick + '_down' in active)
        scale = 32767 / (math.sqrt(2) if diagonal and x and y else 1)
        axes.extend((round(x * scale), round(y * scale)))
    return (buttons, 255 if 'LT' in active else 0, 255 if 'RT' in active else 0, *axes)


def send_report(pad, report):
    buttons, lt, rt, lx, ly, rx, ry = report
    pad.reset()
    if buttons:
        pad.press_button(buttons)
    pad.left_trigger(lt)
    pad.right_trigger(rt)
    pad.left_joystick(lx, ly)
    pad.right_joystick(rx, ry)
    pad.update()
