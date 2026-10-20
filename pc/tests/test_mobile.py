import json
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch
import types
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mobile_protocol import Sessions, NEUTRAL, parse_report
from receiver import Receiver


def packet(**overrides):
    data=dict(v=2,type='state',client='client-1234',session='session-1234',seq=1,
              name='Test phone',buttons=0,lx=0,ly=0,rx=0,ry=0,lt=0,rt=0)
    data.update(overrides)
    return data


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.sessions=Sessions()
        self.address=('192.168.1.2',32001)

    def join(self,index,**overrides):
        return self.sessions.receive(packet(client=f'client-{index:04}',session=f'session-{index:04}',**overrides),
                                     ('192.168.1.'+str(index+2),32001+index),1)

    def test_four_phones_get_independent_automatic_slots_without_pin(self):
        for index in range(4):
            reply,change=self.join(index,buttons=0x1000<<index,lx=index/3)
            self.assertTrue(reply['ok'])
            self.assertEqual(reply['player'],index+1)
            self.assertEqual(change[0],index)
            self.assertEqual(change[1][0],0x1000<<index)
            self.assertEqual(change[1][3],round(index/3*32767))
        self.assertEqual(len(self.sessions.slots),4)

    def test_player_number_is_assigned_by_server(self):
        reply,_=self.sessions.receive(packet(player=4),self.address,1)
        self.assertEqual(reply['player'],1)

    def test_fifth_phone_waits_without_stealing_a_slot(self):
        for index in range(4):self.join(index)
        clients=[item.client for item in self.sessions.slots]
        reply,change=self.join(4)
        self.assertEqual(reply['error'],'full')
        self.assertIsNone(change)
        self.assertEqual([item.client for item in self.sessions.slots],clients)

    def test_same_phone_reconnect_keeps_slot_and_retires_old_session(self):
        self.join(0)
        reply,_=self.sessions.receive(packet(client='client-0000',session='session-new1',seq=1,buttons=4096),('192.168.1.2',33000),1.1)
        self.assertEqual(reply['player'],1)
        reply,change=self.sessions.receive(packet(client='client-0000',session='session-0000',seq=99),('192.168.1.2',32001),1.2)
        self.assertEqual(reply['error'],'retired')
        self.assertIsNone(change)
        self.assertEqual(self.sessions.slots[0].report[0],4096)
        self.assertEqual(sum(item is not None for item in self.sessions.slots),1)

    def test_remaining_phones_keep_their_numbers_when_a_slot_is_reused(self):
        for index in range(4):self.join(index)
        self.sessions.receive(packet(client='client-0001',session='session-0001',type='bye',seq=2),('192.168.1.3',32002),1.1)
        reply,_=self.join(4)
        self.assertEqual(reply['player'],2)
        self.assertEqual(self.sessions.slots[2].client,'client-0002')
        self.assertEqual(self.sessions.slots[3].client,'client-0003')

    def test_reordered_packet_does_not_restore_an_old_button(self):
        self.sessions.receive(packet(seq=20),self.address,1)
        _,change=self.sessions.receive(packet(seq=19,buttons=4096),self.address,1.1)
        self.assertIsNone(change)
        self.assertEqual(self.sessions.slots[0].report,NEUTRAL)

    def test_loss_releases_inputs_then_frees_slot(self):
        self.sessions.receive(packet(lx=1,rt=1,buttons=4096),self.address,1)
        self.assertEqual(self.sessions.expire(1.61),[(0,NEUTRAL)])
        self.sessions.expire(4.01)
        self.assertEqual(self.sessions.slots,[None]*4)

    def test_bye_releases_and_late_packets_cannot_reclaim_slot(self):
        self.sessions.receive(packet(lx=1),self.address,1)
        _,change=self.sessions.receive(packet(type='bye',seq=2),self.address,1.1)
        self.assertEqual(change,(0,NEUTRAL))
        reply,late=self.sessions.receive(packet(seq=1,buttons=4096),self.address,1.2)
        self.assertEqual(reply['error'],'retired')
        self.assertIsNone(late)
        self.assertIsNone(self.sessions.slots[0])

    def test_old_bye_cannot_cancel_newer_state(self):
        self.sessions.receive(packet(seq=5,buttons=4096),self.address,1)
        _,change=self.sessions.receive(packet(type='bye',seq=4),self.address,1.1)
        self.assertIsNone(change)
        self.assertEqual(self.sessions.slots[0].report[0],4096)

    def test_unclaimed_bye_does_not_allocate_a_slot(self):
        _,change=self.sessions.receive(packet(type='bye'),self.address,1)
        self.assertIsNone(change)
        self.assertEqual(self.sessions.slots,[None]*4)

    def test_malformed_states_cannot_claim_a_slot(self):
        for bad in (float('nan'),float('inf'),1.1,-1.1,True,'1',None):
            with self.assertRaises(ValueError):self.sessions.receive(packet(lx=bad),self.address,1)
        for bad in (True,-1,0x400,0x10000):
            with self.assertRaises(ValueError):parse_report(packet(buttons=bad))
        self.assertEqual(self.sessions.slots,[None]*4)

    def test_opposite_dpad_is_neutralized(self):
        self.assertEqual(parse_report(packet(buttons=15)),NEUTRAL)

    def test_old_protocol_is_rejected(self):
        with self.assertRaises(ValueError):self.sessions.receive(packet(v=1),self.address,1)


class NetworkTests(unittest.TestCase):
    def make_server(self,preview=True):
        server=Receiver(port=0,preview=preview)
        self.addCleanup(server.close)
        self.assertEqual(server.events.get(timeout=2)[0],'ready')
        return server

    def make_client(self):
        client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        client.settimeout(1)
        self.addCleanup(client.close)
        return client

    def exchange(self,client,server,data):
        client.sendto(json.dumps(data).encode(),('127.0.0.1',server.port))
        return json.loads(client.recv(1500))

    def test_udp_discovery_auto_assignment_and_timeout(self):
        server=self.make_server();client=self.make_client()
        found=self.exchange(client,server,dict(v=2,type='discover'))
        self.assertEqual(found['max_players'],4)
        self.assertEqual(found['available'],4)
        self.assertNotIn('pin',found)
        ack=self.exchange(client,server,packet(buttons=4096,lx=.5))
        self.assertEqual(ack['player'],1)
        self.assertEqual(server.snapshot()[0][3],(4096,0,0,16384,0,0,0))
        time.sleep(.7)
        self.assertEqual(server.snapshot()[0][3],NEUTRAL)

    def test_four_udp_clients_and_fifth_waiting_client(self):
        server=self.make_server();clients=[self.make_client() for _ in range(5)]
        for index in range(4):
            ack=self.exchange(clients[index],server,packet(client=f'client-{index:04}',session=f'session-{index:04}',buttons=0x1000<<index))
            self.assertEqual(ack['player'],index+1)
        full=self.exchange(clients[4],server,packet(client='client-0004',session='session-0004'))
        self.assertEqual(full['error'],'full')
        self.exchange(clients[1],server,packet(client='client-0001',session='session-0001',seq=2,type='bye'))
        joined=self.exchange(clients[4],server,packet(client='client-0004',session='session-0004',seq=2))
        self.assertEqual(joined['player'],2)

    def test_full_room_advertises_existing_phone_slot_for_reconnect(self):
        server=self.make_server();clients=[self.make_client() for _ in range(4)]
        for index,client in enumerate(clients):
            self.exchange(client,server,packet(client=f'client-{index:04}',session=f'session-{index:04}'))
        found=self.exchange(clients[0],server,dict(v=2,type='discover',client='client-0002'))
        self.assertEqual(found['available'],0)
        self.assertEqual(found['player'],3)

    def test_controller_allocation_failure_does_not_stop_other_players(self):
        class Pad:
            def __getattr__(self,name):return lambda *args:None
        attempts=[]
        def create():
            attempts.append(1)
            if len(attempts)==1:raise RuntimeError('XInput slots occupied')
            return Pad()
        with patch.dict(sys.modules,{'vgamepad':types.SimpleNamespace(VX360Gamepad=create)}):
            server=self.make_server(preview=False)
            first=self.make_client();second=self.make_client()
            failed=self.exchange(first,server,packet())
            self.assertEqual(failed['error'],'controller_unavailable')
            joined=self.exchange(second,server,packet(client='client-other',session='session-other',buttons=8192))
            self.assertTrue(joined['ok'])
            self.assertEqual(joined['player'],2)
            self.assertTrue(server.thread.is_alive())
            server.close()


if __name__=='__main__':unittest.main()
