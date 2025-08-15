import socket
import threading
import time
import json
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QMetaObject, Qt, Q_ARG
import stun
from kademlia.network import Server as KademliaServer

P2P_PORT = 12346
BROADCAST_ADDR = '<broadcast>'
STUN_SERVER = "stun.l.google.com"
STUN_PORT = 19302

class P2PManager(QObject):
    peer_discovered = pyqtSignal(str, str)
    peer_lost = pyqtSignal(str)
    message_received = pyqtSignal(dict)
    incoming_p2p_call = pyqtSignal(str, int) # username, sample_rate
    p2p_call_response = pyqtSignal(str, str)
    p2p_hang_up = pyqtSignal(str)
    hole_punch_successful = pyqtSignal(str, tuple) # username, public_address
    message_deleted = pyqtSignal(str) # msg_id
    message_edited = pyqtSignal(str, str) # msg_id, new_text

    def __init__(self, username, udp_socket, mode='internet'):
        super().__init__()
        self.username = username
        self.udp_socket = udp_socket
        self.mode = mode
        self.peers = {} # {username: {'local_ip': str, 'public_addr': (ip, port), 'last_seen': float}}
        self.running = True
        self.dht_node = None
        self.dht_thread = None
        self.dht_loop = None
        
        self.my_local_ip = self._get_local_ip()
        self.my_public_addr = None # (ip, port)

        if self.mode == 'local':
            self.dht_node = None
            self.dht_thread = None
            self.broadcast_thread = threading.Thread(target=self.send_discovery_broadcast)
            self.listen_thread = threading.Thread(target=self.listen_for_peers)
            self.check_thread = threading.Thread(target=self.check_peers)
        else: # internet mode
            self.broadcast_thread = None
            self.listen_thread = None
            self.check_thread = None
            self.dht_node = KademliaServer()
            self.dht_thread = threading.Thread(target=self._run_dht)

        if self.broadcast_thread: self.broadcast_thread.daemon = True
        if self.listen_thread: self.listen_thread.daemon = True
        if self.check_thread: self.check_thread.daemon = True
        if self.dht_thread: self.dht_thread.daemon = True

    def start(self):
        if self.mode == 'local':
            if self.listen_thread: self.listen_thread.start()
            if self.broadcast_thread: self.broadcast_thread.start()
            if self.check_thread: self.check_thread.start()
        else:
            if self.dht_thread: self.dht_thread.start()

    def stop(self):
        self.running = False
        if self.dht_loop and self.dht_loop.is_running():
            self.dht_loop.call_soon_threadsafe(self.dht_loop.stop)
        print("P2P Manager stopped.")

    def _get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def _get_public_address(self):
        """Использует STUN для определения внешнего IP и порта."""
        print("Attempting to get public IP from STUN server...")
        try:
            nat_type, external_ip, external_port = stun.get_ip_info(
                stun_host=STUN_SERVER, stun_port=STUN_PORT
            )
            self.my_public_addr = (external_ip, external_port)
            print(f"STUN Result: NAT Type={nat_type}, Public Address={self.my_public_addr}")
        except Exception as e:
            print(f"STUN request failed: {e}. Falling back to local IP.")
            self.my_public_addr = (self.my_local_ip, P2P_PORT)

    def send_discovery_broadcast(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        message = json.dumps({'command': 'discovery', 'username': self.username}).encode('utf-8')
        while self.running:
            sock.sendto(message, (BROADCAST_ADDR, P2P_PORT))
            time.sleep(5)
        sock.close()

    def listen_for_peers(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', P2P_PORT))
        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                if addr[0] == self.my_local_ip:
                    continue
                message = json.loads(data.decode('utf-8'))
                self.process_p2p_command(message, addr)
            except Exception as e:
                if self.running:
                    print(f"Error in P2P listener: {e}")
        sock.close()

    def process_p2p_command(self, message, addr):
        """Обрабатывает входящие P2P команды (локальные и через NAT)."""
        command = message.get('command')
        username = message.get('username')
        payload = message.get('payload')

        if command == 'discovery':
            if username and username not in self.peers:
                self.peer_discovered.emit(username, addr[0])
            if username:
                self.peers[username] = {'local_ip': addr[0], 'public_addr': None, 'last_seen': time.time()}
        elif command == 'message':
            # The payload is the entire message dictionary
            if username and payload:
                self.message_received.emit(payload)
        elif command == 'delete_message':
            msg_id = payload.get('id')
            if msg_id:
                self.message_deleted.emit(msg_id)
        elif command == 'edit_message':
            msg_id = payload.get('id')
            new_text = payload.get('text')
            if msg_id and new_text is not None:
                self.message_edited.emit(msg_id, new_text)
        elif command == 'p2p_call_request':
            sample_rate = payload.get('sample_rate')
            if sample_rate:
                self.incoming_p2p_call.emit(username, sample_rate)
        elif command == 'p2p_call_response':
            response = payload.get('response')
            self.p2p_call_response.emit(username, response)
        elif command == 'p2p_hang_up':
            self.p2p_hang_up.emit(username)
        elif command == 'hole_punch_syn':
            # Получили SYN, отвечаем ACK на тот же адрес
            print(f"Received hole punch SYN from {username} at {addr}. Sending ACK.")
            self.send_peer_command(username, 'hole_punch_ack', {}, force_address=addr)
        elif command == 'hole_punch_ack':
            # Получили ACK, соединение установлено!
            print(f"Received hole punch ACK from {username} at {addr}. Hole punch successful!")
            self.hole_punch_successful.emit(username, addr)

    def check_peers(self):
        while self.running:
            time.sleep(15)
            now = time.time()
            lost_peers = [uname for uname, data in self.peers.items() if now - data['last_seen'] > 12]
            for username in lost_peers:
                if username in self.peers:
                    del self.peers[username]
                    self.peer_lost.emit(username)

    def broadcast_message(self, message_dict):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # The message_dict is now the payload
        message_data = {'command': 'message', 'username': self.username, 'payload': message_dict}
        message_bytes = json.dumps(message_data).encode('utf-8')
        # No need for a lock if we're just iterating over a dictionary copy
        for username, data in list(self.peers.items()):
            addr = data.get('public_addr') or (data.get('local_ip'), P2P_PORT)
            try:
                sock.sendto(message_bytes, addr)
            except Exception as e:
                print(f"Could not send message to {username}: {e}")
        sock.close()

    def broadcast_delete_message(self, msg_id):
        """Sends a command to all peers to delete a message."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        message_data = {'command': 'delete_message', 'username': self.username, 'payload': {'id': msg_id}}
        message_bytes = json.dumps(message_data).encode('utf-8')
        for username, data in list(self.peers.items()):
            addr = data.get('public_addr') or (data.get('local_ip'), P2P_PORT)
            try:
                sock.sendto(message_bytes, addr)
            except Exception as e:
                print(f"Could not send delete command to {username}: {e}")
        sock.close()

    def broadcast_edit_message(self, msg_id, new_text):
        """Sends a command to all peers to edit a message."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = {'id': msg_id, 'text': new_text}
        message_data = {'command': 'edit_message', 'username': self.username, 'payload': payload}
        message_bytes = json.dumps(message_data).encode('utf-8')
        for username, data in list(self.peers.items()):
            addr = data.get('public_addr') or (data.get('local_ip'), P2P_PORT)
            try:
                sock.sendto(message_bytes, addr)
            except Exception as e:
                print(f"Could not send edit command to {username}: {e}")
        sock.close()

    def send_peer_command(self, target_username, command, payload, force_address=None):
        if not force_address and target_username not in self.peers:
            print(f"Error: peer {target_username} not found.")
            return
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        message_data = {'command': command, 'username': self.username, 'payload': payload}
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        addr = force_address
        if not addr:
            peer_data = self.peers[target_username]
            addr = peer_data.get('public_addr') or (peer_data.get('local_ip'), P2P_PORT)

        try:
            print(f"Sending command '{command}' to {target_username} at {addr}")
            sock.sendto(message_bytes, addr)
        except Exception as e:
            print(f"Could not send command to peer {target_username}: {e}")
        finally:
            sock.close()

    def _run_dht(self):
        self.dht_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.dht_loop)
        self.dht_loop.run_until_complete(self._dht_main())

    async def _dht_main(self):
        # Сначала получаем наш публичный адрес
        await self.dht_loop.run_in_executor(None, self._get_public_address)
        
        bootstrap_nodes = [
            ("router.utorrent.com", 6881),
            ("router.bittorrent.com", 6881),
            ("dht.transmissionbt.com", 6881),
            ("dht.aelitis.com", 6881)
        ]
        await self.dht_node.listen(P2P_PORT)
        
        print("[DHT] Bootstrapping with nodes:", bootstrap_nodes)
        found_neighbors = await self.dht_node.bootstrap(bootstrap_nodes)
        print(f"[DHT] Bootstrap complete. Found {len(found_neighbors)} neighbors.")

        while self.running:
            my_address_info = json.dumps({
                'local_ip': self.my_local_ip,
                'public_addr': self.my_public_addr
            })
            await self.dht_node.set(self.username, my_address_info)
            await asyncio.sleep(60)

    def find_peer(self, username):
        if self.dht_loop and self.dht_loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_find_peer(username), self.dht_loop)

    async def _async_find_peer(self, username):
        print(f"[DHT] Searching for {username}...")
        found_value = await self.dht_node.get(username)
        if found_value:
            print(f"[DHT] Found {username} with data: {found_value}")
            try:
                peer_info = json.loads(found_value)
                self.peers[username] = {
                    'local_ip': peer_info.get('local_ip'),
                    'public_addr': tuple(peer_info.get('public_addr')) if peer_info.get('public_addr') else None,
                    'last_seen': time.time()
                }
                # Отправляем в GUI только основной IP для отображения
                display_ip = (peer_info.get('public_addr') or [peer_info.get('local_ip')])[0]
                QMetaObject.invokeMethod(
                    self, "emit_peer_discovered", Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, username), Q_ARG(str, display_ip)
                )
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"Error parsing data for {username}: {e}")
        else:
            print(f"[DHT] User {username} not found.")

    def initiate_hole_punch(self, target_username):
        """Начинает процесс UDP hole punching."""
        if target_username not in self.peers:
            print(f"Cannot hole punch: {target_username} not found in peers.")
            return

        peer_info = self.peers[target_username]
        public_addr = peer_info.get('public_addr')
        local_addr = (peer_info.get('local_ip'), P2P_PORT)

        if not public_addr:
            print("Peer does not have a public address, trying local.")
            # Если нет публичного, возможно, мы в одной сети
            self.hole_punch_successful.emit(target_username, local_addr)
            return

        # Начинаем отправлять SYN пакеты для "пробивки" NAT
        def puncher():
            for i in range(5):
                if not self.running: break
                print(f"Sending SYN to {target_username} at {public_addr} (attempt {i+1})")
                syn_packet = json.dumps({'command': 'hole_punch_syn', 'username': self.username}).encode('utf-8')
                try:
                    self.udp_socket.sendto(syn_packet, public_addr)
                    self.udp_socket.sendto(syn_packet, local_addr) # И на локальный на всякий случай
                except Exception as e:
                    print(f"Error sending SYN: {e}")
                time.sleep(0.5)

        punch_thread = threading.Thread(target=puncher)
        punch_thread.daemon = True
        punch_thread.start()

    @pyqtSlot(str, str)
    def emit_peer_discovered(self, username, address):
        self.peer_discovered.emit(username, address)

    def send_p2p_call_request(self, target_username, sample_rate):
        """Отправляет запрос на звонок указанному пользователю с указанием частоты дискретизации."""
        self.send_peer_command(target_username, 'p2p_call_request', {'sample_rate': sample_rate})

    def send_p2p_call_response(self, target_username, response):
        """Отправляет ответ на запрос о звонке ('accept', 'reject', 'busy')."""
        self.send_peer_command(target_username, 'p2p_call_response', {'response': response})

    def send_p2p_hang_up(self, target_username):
        """Сообщает другому пиру о завершении звонка."""
        self.send_peer_command(target_username, 'p2p_hang_up', {})

    def get_peer_username_by_addr(self, address):
        """Находит имя пользователя по его адресу."""
        for uname, data in self.peers.items():
            peer_addr = data.get('public_addr') or (data.get('local_ip'), P2P_PORT)
            if peer_addr == address:
                return uname
        return None