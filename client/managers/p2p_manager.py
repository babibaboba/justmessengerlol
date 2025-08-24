import socket
import threading
import time
import json
import asyncio
import stun
import msgpack
import zstandard as zstd
import sys
from kademlia.network import Server as KademliaServer
from .encryption_manager import EncryptionManager

P2P_PORT = 12346
BROADCAST_ADDR = '<broadcast>'
STUN_SERVER = "stun.l.google.com"
STUN_PORT = 19302


class P2PManager:
    def __init__(self, username, chat_history, mode='internet'):
        self.username = username
        self.udp_socket = None
        self.chat_history = chat_history
        self.mode = mode
        self.my_port = P2P_PORT
        # {username: {'local_ip': str, 'public_addr': (ip, port), 'last_seen': float, 'port': int}}
        self.peers = {}
        self.groups = {}  # {group_id: {'name': str, 'members': {username}, 'admin': username}}
        self.running = True
        self.dht_node = None
        self.dht_thread = None
        self.dht_loop = None
        self.pending_session_acks = {}

        self.encryption_manager = EncryptionManager()
        self.zstd_c = zstd.ZstdCompressor()
        self.zstd_d = zstd.ZstdDecompressor()

        self.callbacks = {
            'peer_discovered': [],
            'peer_lost': [],
            'message_received': [],
            'incoming_p2p_call': [],
            'p2p_call_response': [],
            'p2p_hang_up': [],
            'hole_punch_successful': [],
            'peer_not_found': [],
            'incoming_contact_request': [],
            'contact_request_response': [],
            'message_deleted': [],
            'message_edited': [],
            'incoming_file_request': [],
            'file_request_response': [],
            'secure_channel_established': [],
            'group_created': [],
            'group_joined': [],
            'group_left': [],
            'group_message_received': [],
            'history_received': [],
            'incoming_group_invite': [],
            'group_invite_response': [],
            'incoming_group_call': [],
            'group_call_response': [],
            'group_call_hang_up': [],
            'user_kicked': [],
            'webrtc_signal': [],
        }

        self.my_local_ip = self._get_local_ip()
        self.my_public_addr = None  # (ip, port)

        if self.mode == 'local':
            self.dht_node = None
            self.dht_thread = None
            self.broadcast_thread = threading.Thread(
                target=self.send_discovery_broadcast)
            self.listen_thread = threading.Thread(target=self.listen_for_peers)
            self.check_thread = threading.Thread(target=self.check_peers)
        else:  # internet mode
            self.broadcast_thread = None
            self.listen_thread = None
            self.check_thread = None
            self.dht_node = KademliaServer()
            self.dht_thread = threading.Thread(target=self._run_dht)

        if self.broadcast_thread: self.broadcast_thread.daemon = True
        if self.listen_thread: self.listen_thread.daemon = True
        if self.check_thread: self.check_thread.daemon = True
        if self.dht_thread: self.dht_thread.daemon = True

    def register_callback(self, event_name, callback):
        if event_name in self.callbacks:
            self.callbacks[event_name].append(callback)

    def _emit(self, event_name, *args):
        if event_name in self.callbacks:
            for callback in self.callbacks[event_name]:
                callback(*args)

    def start(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Use exclusive address use on Windows to prevent multiple clients from
        # binding to the same port, which is necessary for the dynamic port
        # allocation to work correctly.
        if sys.platform == 'win32':
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else: # For other OSes, REUSEADDR is the standard.
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if self.mode == 'local':
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Try to bind to P2P_PORT, but find an open one if it's taken.
            port_found = False
            port = P2P_PORT
            while not port_found and port < P2P_PORT + 50:
                try:
                    self.udp_socket.bind(('', port))
                    port_found = True
                    self.my_port = port
                    print(f"P2P Manager bound to local port {self.my_port}")
                except OSError:
                    print(f"Port {port} is busy, trying next one...")
                    port += 1
            if not port_found:
                print(f"FATAL: Could not find any free port for P2P.")
                return
        else:  # internet
            self.udp_socket.bind(('', 0))
            self.my_port = self.udp_socket.getsockname()[1]
            print(f"P2P Manager bound to internet port {self.my_port}")

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

    def _pack_data(self, data):
        return self.zstd_c.compress(msgpack.packb(data, use_bin_type=True))

    def _unpack_data(self, packed_data):
        return msgpack.unpackb(self.zstd_d.decompress(packed_data), raw=False)

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
        print("Attempting to get public IP from STUN server...")
        try:
            nat_type, external_ip, external_port = stun.get_ip_info(
                stun_host=STUN_SERVER, stun_port=STUN_PORT)
            self.my_public_addr = (external_ip, external_port)
            print(
                f"STUN Result: NAT Type={nat_type}, Public Address={self.my_public_addr}")
        except Exception as e:
            print(f"STUN request failed: {e}. Falling back to local IP.")
            self.my_public_addr = (self.my_local_ip, P2P_PORT)

    def send_discovery_broadcast(self):
        message = self._pack_data({
            'command': 'discovery',
            'username': self.username,
            'port': self.my_port
        })
        while self.running:
            # In local mode, iterate through a range of ports to find other clients.
            for port in range(P2P_PORT, P2P_PORT + 50):
                try:
                    self.udp_socket.sendto(message, (BROADCAST_ADDR, port))
                except Exception as e:
                    print(f"Broadcast error on port {port}: {e}")
            time.sleep(5)

    def listen_for_peers(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(
                    4096)  # Increased buffer for history
                if addr[0] == self.my_local_ip or not data:
                    continue
                message = self._unpack_data(data)
                if not message:
                    print(f"Received empty or corrupted packet from {addr}")
                    continue
                self.process_p2p_command(message, addr)
            except Exception as e:
                if self.running:
                    print(f"Error in P2P listener: {e}")

    def process_p2p_command(self, message, addr):
        if not message:
            print(f"process_p2p_command received an empty message from {addr}. Ignoring.")
            return
        command = message.get('command')
        username = message.get('username')
        payload = message.get('payload')

        if not username or username == self.username:
            return
        
        print(f"[RECV] Command '{command}' from {username}@{addr}")

        # This is the core of reliable NAT traversal and P2P communication.
        # The listening port can be in the top-level message OR in the payload.
        # This handles both 'discovery' (top-level) and 'contact_request' (payload).
        peer_port = message.get('port')
        if peer_port is None and isinstance(payload, dict):
            peer_port = payload.get('port')

        # Fallback to the source address port if not specified in the message.
        if peer_port is None:
            peer_port = addr[1]

        peer_addr = (addr[0], peer_port)

        if username in self.peers:
            self.peers[username]['public_addr'] = peer_addr
            self.peers[username]['last_seen'] = time.time()
            self.peers[username]['port'] = peer_port
        
        if command == 'discovery':
            if username not in self.peers:
                self._emit('peer_discovered', username, peer_addr[0])
            # Always update address information and attempt key exchange on discovery.
            self.peers[username] = {
                'local_ip': peer_addr[0],
                'public_addr': peer_addr,
                'last_seen': time.time(),
                'port': peer_port
            }
            # Only start a key exchange if we don't already have a secure channel.
            # This prevents the endless handshake loop.
            if not self.encryption_manager.has_session_key(username):
                self.send_public_key(username)
        elif command == 'public_key':
            if payload.get('key'):
                if self.encryption_manager.add_peer_public_key(username, payload['key']):
                    print(f"Added public key for {username}.")
                    # Respond with our own public key if they requested it.
                    if payload.get('request', True):
                        self.send_public_key(username, request_key=False)

                    # To prevent a race condition where both peers initiate a session key
                    # exchange simultaneously, we use a tie-breaker. The peer with the
                    # lexicographically greater username is responsible for initiating.
                    if self.username > username:
                        print(f"Public key for {username} is registered. Initiating session key exchange (I am initiator).")
                        self.initiate_session_key_exchange(username)
                    else:
                        print(f"Public key for {username} is registered. Waiting for peer to initiate session key exchange.")
        elif command == 'session_key':
            handshake_id = payload.get('handshake_id')
            if payload.get('key') and handshake_id:
                if self.encryption_manager.receive_session_key(username, payload['key']):
                    self._emit('secure_channel_established', username)
                    self.request_history(username, 'global')
                    # Acknowledge the receipt of the session key
                    self.send_peer_command(username, 'session_key_ack', {'handshake_id': handshake_id})
        elif command == 'session_key_ack':
            handshake_id = payload.get('handshake_id')
            if handshake_id in self.pending_session_acks:
                print(f"Received session key ACK for handshake {handshake_id}")
                self.pending_session_acks.pop(handshake_id, None)
        elif command == 'encrypted_message':
            if username and payload:
                decrypted_payload = self.encryption_manager.decrypt_message(username, payload)
                if decrypted_payload:
                    inner_message = json.loads(decrypted_payload)
                    self.process_p2p_command(inner_message, addr)
        elif command == 'request_history':
            chat_id = payload.get('chat_id')
            if chat_id and username:
                history = self.chat_history.get(chat_id, [])
                self._send_encrypted_command(username, 'history_response', {'chat_id': chat_id, 'history': history})
        elif command == 'history_response':
            chat_id = payload.get('chat_id')
            history = payload.get('history')
            if chat_id and history:
                self._emit('history_received', chat_id, history)
        elif command == 'message':
            if username and payload:
                self._emit('message_received', payload)
        elif command == 'group_message':
            group_id = payload.get('group_id')
            message_data = payload.get('message_data')
            if group_id and message_data and self.username in self.groups.get(group_id, {}).get('members', set()):
                self._emit('group_message_received', group_id, message_data)
                if self.groups[group_id]['admin'] == self.username:
                    self.relay_group_message(group_id, message_data)
        elif command == 'create_group':
            group_id = payload.get('group_id')
            group_name = payload.get('name')
            if group_id and group_name and username:
                self.groups[group_id] = {'name': group_name, 'members': {username}, 'admin': username}
                self._emit('group_created', group_id, group_name, username)
        elif command == 'join_group':
            group_id = payload.get('group_id')
            if group_id in self.groups and username:
                self.groups[group_id]['members'].add(username)
                self._emit('group_joined', group_id, username)
        elif command == 'leave_group':
            group_id = payload.get('group_id')
            if group_id in self.groups and username in self.groups[group_id]['members']:
                self.groups[group_id]['members'].remove(username)
                self._emit('group_left', group_id, username)
        elif command == 'group_invite':
            group_id = payload.get('group_id')
            group_name = payload.get('group_name')
            if group_id and group_name and username:
                self._emit('incoming_group_invite', group_id, group_name, username)
        elif command == 'group_invite_response':
            group_id = payload.get('group_id')
            accepted = payload.get('accepted')
            if group_id and accepted and username:
                # Admin receives the acceptance, adds member, and notifies others
                self.groups[group_id]['members'].add(username)
                self._emit('group_joined', group_id, username) # Notify admin's UI
                # Notify the new member that they have officially joined
                self._send_encrypted_command(username, 'user_joined_group', {'group_id': group_id, 'group_info': self.groups[group_id]})
                # Notify existing members
                for member in self.groups[group_id]['members']:
                    if member != self.username and member != username:
                        self._send_encrypted_command(member, 'user_joined_group', {'group_id': group_id, 'username': username})
            elif group_id and not accepted:
                self._emit('group_invite_response', group_id, username, False)
        elif command == 'user_joined_group':
            group_id = payload.get('group_id')
            new_username = payload.get('username')
            group_info = payload.get('group_info')
            if group_id and group_info: # For the user who just joined
                self.groups[group_id] = group_info
                self._emit('group_joined', group_id, self.username)
            elif group_id and new_username: # For existing members
                self.groups[group_id]['members'].add(new_username)
                self._emit('group_joined', group_id, new_username)
        elif command == 'delete_message':
            msg_id = payload.get('id')
            if msg_id:
                self._emit('message_deleted', msg_id)
        elif command == 'edit_message':
            msg_id = payload.get('id')
            new_text = payload.get('text')
            if msg_id and new_text is not None:
                self._emit('message_edited', msg_id, new_text)
        elif command == 'p2p_call_request':
            sample_rate = payload.get('sample_rate')
            if sample_rate:
                self._emit('incoming_p2p_call', username, sample_rate)
        elif command == 'p2p_call_response':
            response = payload.get('response')
            self._emit('p2p_call_response', username, response)
        elif command == 'p2p_hang_up':
            self._emit('p2p_hang_up', username)
        elif command == 'hole_punch_syn':
            print(f"Received hole punch SYN from {username} at {addr}. Sending ACK.")
            self.send_peer_command(username, 'hole_punch_ack', {})
        elif command == 'hole_punch_ack':
            print(f"Received hole punch ACK from {username} at {addr}. Hole punch successful!")
            self._emit('hole_punch_successful', username, addr)
        elif command == 'file_transfer_request':
            filename = payload.get('filename')
            filesize = payload.get('filesize')
            port = payload.get('port')
            ip = addr[0]
            if filename and filesize and ip and port:
                self._emit('incoming_file_request', username, filename, filesize, ip, port)
        elif command == 'file_transfer_response':
            accepted = payload.get('accepted')
            if accepted is not None:
                self._emit('file_request_response', username, accepted)
        elif command == 'group_call_request':
            group_id = payload.get('group_id')
            sample_rate = payload.get('sample_rate')
            if group_id and sample_rate and username:
                self._emit('incoming_group_call', group_id, username, sample_rate)
        elif command == 'group_call_response':
            group_id = payload.get('group_id')
            response = payload.get('response')
            if group_id and response and username:
                self._emit('group_call_response', group_id, username, response)
        elif command == 'group_call_hang_up':
            group_id = payload.get('group_id')
            if group_id and username:
                self._emit('group_call_hang_up', group_id, username)
        elif command == 'group_kick':
            group_id = payload.get('group_id')
            kicked_user = payload.get('kicked_user')
            admin_user = payload.get('admin')
            if group_id and kicked_user and admin_user and group_id in self.groups:
                # Verify the sender is the admin
                if self.groups[group_id]['admin'] == username:
                    if kicked_user in self.groups[group_id]['members']:
                        self.groups[group_id]['members'].remove(kicked_user)
                    self._emit('user_kicked', group_id, kicked_user, admin_user)
        elif command == 'contact_request':
            if username:
                if username not in self.peers:
                    self._emit('peer_discovered', username, peer_addr[0])
                # Always update address with the explicit port from payload if available.
                self.peers[username] = {
                    'local_ip': peer_addr[0],
                    'public_addr': peer_addr,
                    'last_seen': time.time(),
                    'port': peer_port
                }
            self._emit('incoming_contact_request', username, payload) # Pass the whole payload
        elif command == 'contact_response':
            accepted = payload.get('accepted')
            self._emit('contact_request_response', username, accepted)
            if accepted:
                print(f"Contact request accepted by {username}, initiating key exchange.")
                # The peer's address was already updated by the logic at the start of this function.
                # Use the same tie-breaker logic to avoid a handshake race condition.
                if self.username > username:
                    self.send_public_key(username)

        elif command == 'webrtc_signal':
            if username and payload:
                signal_type = payload.get('type')
                data = payload.get('data')
                self._emit('webrtc_signal', username, signal_type, data)

    def check_peers(self):
        while self.running:
            time.sleep(15)
            now = time.time()
            lost_peers = [uname for uname, data in self.peers.items() if now - data['last_seen'] > 12]
            for username in lost_peers:
                if username in self.peers:
                    del self.peers[username]
                    self._emit('peer_lost', username)

    def _send_encrypted_command(self, target_username, command, payload):
        message_str = json.dumps({'command': command, 'username': self.username, 'payload': payload})
        encrypted_payload = self.encryption_manager.encrypt_message(target_username, message_str)
        if encrypted_payload:
            self.send_peer_command(target_username, 'encrypted_message', encrypted_payload)
        else:
            print(f"Could not encrypt message for {target_username}")

    def broadcast_message(self, message_dict):
        for username in list(self.peers.keys()):
            self._send_encrypted_command(username, 'message', message_dict)

    def send_private_message(self, target_username, message_dict):
        """Sends an encrypted message to a single peer."""
        self._send_encrypted_command(target_username, 'message', message_dict)

    def broadcast_delete_message(self, msg_id):
        for username in list(self.peers.keys()):
            self._send_encrypted_command(username, 'delete_message', {'id': msg_id})

    def broadcast_edit_message(self, msg_id, new_text):
        payload = {'id': msg_id, 'text': new_text}
        for username in list(self.peers.keys()):
            self._send_encrypted_command(username, 'edit_message', payload)

    def send_peer_command(self, target_username, command, payload):
        if target_username == self.username:
            return
        
        if target_username not in self.peers:
            print(f"Error: peer {target_username} not found.")
            self._emit('peer_not_found', target_username)
            return

        peer_data = self.peers.get(target_username, {})
        # The public_addr now correctly stores the specific listening port of the peer.
        addr = peer_data.get('public_addr')

        if not addr:
            print(f"Error: No address found for peer {target_username}.")
            return

        message_data = {'command': command, 'username': self.username, 'payload': payload}
        message_bytes = self._pack_data(message_data)

        try:
            if self.udp_socket:
                print(f"Sending command '{command}' to {target_username} at {addr}")
                self.udp_socket.sendto(message_bytes, addr)
            else:
                print("Error: UDP socket is not initialized.")
        except Exception as e:
            print(f"Could not send command to peer {target_username} at {addr}: {e}")

    def _run_dht(self):
        self.dht_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.dht_loop)
        self.dht_loop.run_until_complete(self._dht_main())

    async def _dht_main(self):
        await self.dht_loop.run_in_executor(None, self._get_public_address)
        
        bootstrap_nodes = [
            ("router.utorrent.com", 6881),
            ("router.bittrent.com", 6881),
            ("dht.transmissionbt.com", 6881),
            ("dht.aelitis.com", 6881)
        ]
        await self.dht_node.listen(P2P_PORT)
        
        print("[DHT] Bootstrapping with nodes:", bootstrap_nodes)
        try:
            found_neighbors = await self.dht_node.bootstrap(bootstrap_nodes)
            print(f"[DHT] Bootstrap complete. Found {len(found_neighbors)} neighbors.")
        except Exception as e:
            print(f"[DHT] Bootstrap failed: {e}")

        while self.running:
            try:
                my_address_info = json.dumps({
                    'local_ip': self.my_local_ip,
                    'public_addr': self.my_public_addr
                })
                print(f"[DHT] Setting my info: {my_address_info}")
                await self.dht_node.set(self.username, my_address_info)
                print(f"[DHT] Successfully set info for {self.username}")
            except Exception as e:
                print(f"[DHT] Error setting DHT value: {e}")
            await asyncio.sleep(60)

    def find_peer(self, username):
        if self.dht_loop and self.dht_loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_find_peer(username), self.dht_loop)

    async def _async_find_peer(self, username):
        print(f"[DHT] Searching for {username}...")
        try:
            found_value = await self.dht_node.get(username)
            if found_value:
                print(f"[DHT] Found {username} with data: {found_value}")
                peer_info = json.loads(found_value)
                
                # Ensure public_addr is a tuple if it exists
                public_addr = peer_info.get('public_addr')
                if public_addr and isinstance(public_addr, list):
                    public_addr = tuple(public_addr)

                self.peers[username] = {
                    'local_ip': peer_info.get('local_ip'),
                    'public_addr': public_addr,
                    'last_seen': time.time()
                }
                
                display_ip = (public_addr[0] if public_addr else peer_info.get('local_ip'))
                self._emit('peer_discovered', username, display_ip)
                self.send_public_key(username) # Start key exchange
            else:
                print(f"[DHT] User {username} not found.")
                self._emit('peer_not_found', username)
        except Exception as e:
            print(f"[DHT] Error during find_peer for {username}: {e}")
            self._emit('peer_not_found', username)

    def initiate_hole_punch(self, target_username):
        if target_username not in self.peers:
            print(f"Cannot hole punch: {target_username} not found in peers.")
            return

        peer_info = self.peers[target_username]
        public_addr = peer_info.get('public_addr')
        peer_port = peer_info.get('port', P2P_PORT)
        local_addr = (peer_info.get('local_ip'), peer_port)

        if not public_addr:
            print("Peer does not have a public address, trying local.")
            self._emit('hole_punch_successful', target_username, local_addr)
            return

        def puncher():
            for i in range(5):
                if not self.running: break
                print(f"Sending SYN to {target_username} at {public_addr} (attempt {i+1})")
                syn_packet = self._pack_data({'command': 'hole_punch_syn', 'username': self.username})
                try:
                    self.udp_socket.sendto(syn_packet, public_addr)
                    self.udp_socket.sendto(syn_packet, local_addr)
                except Exception as e:
                    print(f"Error sending SYN: {e}")
                time.sleep(0.5)

        punch_thread = threading.Thread(target=puncher)
        punch_thread.daemon = True
        punch_thread.start()

    def send_public_key(self, target_username, request_key=True):
        key_pem = self.encryption_manager.get_public_key_pem()
        self.send_peer_command(target_username, 'public_key', {'key': key_pem, 'request': request_key})

    def initiate_session_key_exchange(self, target_username):
        _, encrypted_key = self.encryption_manager.generate_session_key(target_username)
        if not encrypted_key:
            print(f"Failed to generate session key for {target_username}. Do we have their public key?")
            return

        handshake_id = str(time.time())
        payload = {'key': encrypted_key, 'handshake_id': handshake_id}

        def retry_send():
            retry_count = 0
            while self.running and handshake_id in self.pending_session_acks and retry_count < 5:
                print(f"Sending session key to {target_username} (attempt {retry_count + 1})")
                self.send_peer_command(target_username, 'session_key', payload)
                time.sleep(1)
                retry_count += 1
            if handshake_id in self.pending_session_acks:
                print(f"Session key exchange with {target_username} timed out.")
                self.pending_session_acks.pop(handshake_id, None)

        self.pending_session_acks[handshake_id] = True # Mark as pending
        retry_thread = threading.Thread(target=retry_send)
        retry_thread.daemon = True
        retry_thread.start()

    def send_p2p_call_request(self, target_username, sample_rate):
        self._send_encrypted_command(target_username, 'p2p_call_request', {'sample_rate': sample_rate})

    def send_p2p_call_response(self, target_username, response):
        self._send_encrypted_command(target_username, 'p2p_call_response', {'response': response})

    def send_p2p_hang_up(self, target_username):
        self._send_encrypted_command(target_username, 'p2p_hang_up', {})

    def send_file_transfer_request(self, target_username, filename, filesize, port):
        payload = {
            'filename': filename,
            'filesize': filesize,
            'port': port
        }
        self._send_encrypted_command(target_username, 'file_transfer_request', payload)

    def send_file_transfer_response(self, target_username, accepted):
        self._send_encrypted_command(target_username, 'file_transfer_response', {'accepted': accepted})

    def get_peer_username_by_addr(self, address):
        for uname, data in self.peers.items():
            peer_addr = data.get('public_addr') or (data.get('local_ip'), P2P_PORT)
            if peer_addr == address:
                return uname
        return None

    def create_group(self, group_name):
        group_id = str(time.time())
        self.groups[group_id] = {'name': group_name, 'members': {self.username}, 'admin': self.username}
        self._emit('group_created', group_id, group_name, self.username)

    def join_group(self, group_id, admin_username):
        self._send_encrypted_command(admin_username, 'join_group', {'group_id': group_id})

    def leave_group(self, group_id):
        admin = self.groups[group_id]['admin']
        self._send_encrypted_command(admin, 'leave_group', {'group_id': group_id})

    def send_group_message(self, group_id, message_data):
        admin = self.groups[group_id]['admin']
        payload = {'group_id': group_id, 'message_data': message_data}
        self._send_encrypted_command(admin, 'group_message', payload)

    def relay_group_message(self, group_id, message_data):
        for member in self.groups[group_id]['members']:
            if member != self.username and member != message_data['sender']:
                self._send_encrypted_command(member, 'group_message', {'group_id': group_id, 'message_data': message_data})

    def request_history(self, target_username, chat_id):
        self._send_encrypted_command(target_username, 'request_history', {'chat_id': chat_id})

    def send_group_invite(self, group_id, target_username):
        if self.groups[group_id]['admin'] != self.username:
            print("Error: Only admin can invite users.")
            return
        group_name = self.groups[group_id]['name']
        payload = {'group_id': group_id, 'group_name': group_name}
        self._send_encrypted_command(target_username, 'group_invite', payload)

    def send_group_invite_response(self, group_id, admin_username, accepted):
        payload = {'group_id': group_id, 'accepted': accepted}
        self._send_encrypted_command(admin_username, 'group_invite_response', payload)

    def start_group_call(self, group_id, sample_rate):
        if self.groups[group_id]['admin'] != self.username:
            print("Error: Only admin can start a group call.")
            return
        payload = {'group_id': group_id, 'sample_rate': sample_rate}
        for member in self.groups[group_id]['members']:
            if member != self.username:
                self._send_encrypted_command(member, 'group_call_request', payload)

    def send_group_call_response(self, group_id, response):
        payload = {'group_id': group_id, 'response': response}
        for member in self.groups[group_id]['members']:
            if member != self.username:
                self._send_encrypted_command(member, 'group_call_response', payload)

    def send_group_hang_up(self, group_id):
        payload = {'group_id': group_id}
        for member in self.groups[group_id]['members']:
            if member != self.username:
                self._send_encrypted_command(member, 'group_call_hang_up', payload)

    def kick_user_from_group(self, group_id, username_to_kick):
        if group_id not in self.groups:
            print(f"Error: Group {group_id} not found.")
            return
        if self.groups[group_id]['admin'] != self.username:
            print("Error: Only the admin can kick users.")
            return
        if username_to_kick == self.username:
            print("Error: Admin cannot kick themselves.")
            return

        print(f"Admin {self.username} kicking {username_to_kick} from {group_id}")
        payload = {
            'group_id': group_id,
            'kicked_user': username_to_kick,
            'admin': self.username
        }
        
        # Notify all members, including the one being kicked
        members_to_notify = list(self.groups[group_id]['members'])
        for member in members_to_notify:
            if member != self.username: # Admin already knows
                 self._send_encrypted_command(member, 'group_kick', payload)

        # Locally remove the user and emit the event for the admin's UI
        if username_to_kick in self.groups[group_id]['members']:
            self.groups[group_id]['members'].remove(username_to_kick)
        self._emit('user_kicked', group_id, username_to_kick, self.username)

    def send_contact_request(self, target_username):
        """Sends a contact request to a user."""
        payload = {'port': self.my_port}
        # Contact requests are not encrypted with session keys as they are pre-session.
        self.send_peer_command(target_username, 'contact_request', payload)

    def send_contact_response(self, target_username, accepted):
        """Responds to a contact request (plain-text; session keys may not exist yet)."""
        payload = {'accepted': accepted}
        # Send unencrypted because secure channel might not be established at this stage.
        self.send_peer_command(target_username, 'contact_response', payload)
        if accepted:
            # If we accept, we kick off the key exchange from our side.
            print(f"Accepted contact request from {target_username}, sending public key.")
            self.send_public_key(target_username)

    def send_webrtc_signal(self, target_username, signal_type, data):
        """Sends a WebRTC signaling message to a peer."""
        payload = {'type': signal_type, 'data': data}
        self._send_encrypted_command(target_username, 'webrtc_signal', payload)