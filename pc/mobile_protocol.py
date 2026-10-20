"""Four automatically assigned LAN controller sessions, protocol version 2."""
from dataclasses import dataclass
import math
import re

PORT = 26761
VERSION = 2
MAX_PLAYERS = 4
NEUTRAL = (0, 0, 0, 0, 0, 0, 0)
BUTTON_MASK = 0xf3ff
RELEASE_AFTER = .6
EXPIRE_AFTER = 3.0


def finite_axis(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Invalid axis')
    return value


def parse_report(data):
    buttons = data.get('buttons')
    if type(buttons) is not int or buttons < 0 or buttons & ~BUTTON_MASK:
        raise ValueError('Invalid buttons')
    if buttons & 3 == 3:
        buttons &= ~3
    if buttons & 12 == 12:
        buttons &= ~12
    lt, rt = (round(finite_axis(data.get(k), 0, 1) * 255) for k in ('lt', 'rt'))
    axes = [round(finite_axis(data.get(k), -1, 1) * 32767) for k in ('lx', 'ly', 'rx', 'ry')]
    return buttons, lt, rt, *axes


@dataclass
class Lease:
    client: str
    session: str
    address: tuple
    name: str
    seq: int
    seen: float
    report: tuple = NEUTRAL


class Sessions:
    def __init__(self):
        self.slots = [None] * MAX_PLAYERS
        self.retired = {}

    def receive(self, data, address, now):
        if not isinstance(data, dict) or data.get('v') != VERSION:
            raise ValueError('Unsupported protocol')
        client, session = data.get('client'), data.get('session')
        if not all(isinstance(s, str) and re.fullmatch(r'[a-zA-Z0-9-]{8,64}', s) for s in (client, session)):
            raise ValueError('Invalid identity')
        seq = data.get('seq')
        if type(seq) is not int or not 0 <= seq < 2**53:
            raise ValueError('Invalid sequence')
        identity = (client, session)
        self.retired = {key: until for key, until in self.retired.items() if until > now}
        if identity in self.retired:
            return {'ok': False, 'error': 'retired', 'seq': seq}, None
        slot = next((i for i, lease in enumerate(self.slots) if lease is not None and lease.client == client), None)
        lease = self.slots[slot] if slot is not None else None
        same = lease is not None and (lease.session, lease.address) == (session, address)
        if data.get('type') == 'bye':
            if same:
                if seq <= lease.seq:
                    return {'ok': True, 'seq': seq}, None
                self.retired[identity] = now + 60
                self.slots[slot] = None
                return {'ok': True, 'seq': seq, 'player': slot + 1}, (slot, NEUTRAL)
            return {'ok': True, 'seq': seq}, None
        if data.get('type') != 'state':
            raise ValueError('Invalid message')
        report = parse_report(data)
        if slot is None:
            slot = next((i for i, item in enumerate(self.slots) if item is None), None)
            if slot is None:
                return {'ok': False, 'error': 'full', 'seq': seq}, None
        elif not same and lease.session != session:
            self.retired[(lease.client, lease.session)] = now + 60
        elif not same:
            return {'ok': False, 'error': 'session', 'seq': seq}, None
        if same and seq <= lease.seq:
            return {'ok': True, 'seq': seq, 'player': slot + 1}, None
        self.slots[slot] = Lease(client, session, address, str(data.get('name', '手机'))[:32], seq, now, report)
        return {'ok': True, 'seq': seq, 'player': slot + 1}, (slot, report)

    def expire(self, now):
        changes = []
        for slot, lease in enumerate(self.slots):
            if lease is None:
                continue
            if now - lease.seen > RELEASE_AFTER and lease.report != NEUTRAL:
                lease.report = NEUTRAL
                changes.append((slot, NEUTRAL))
            if now - lease.seen > EXPIRE_AFTER:
                self.slots[slot] = None
        return changes
