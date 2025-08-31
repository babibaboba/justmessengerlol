import socket
import threading
import msgpack
import zstandard as zstd
import os
import sys
import json
import uuid
from datetime import datetime
import argparse

# Add project root to sys.path for plugin_manager import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from plugin_manager import PluginManager
except ImportError as e:
    print(f"Fatal Error: Could not import PluginManager. {e}")
    sys.exit(1)

class Server:
    def __init__(self, host, port, password=None):
        self.host = host
        self.port = port
        self.password = password
        self.clients = {}  # {client_socket: {'username': str, 'address': tuple, 'udp_addr': (ip, port)}}
        self.groups = {}   # {group_id: {'name': str, 'members': {client_socket}, 'admin': str}}
        self.active_calls = {} # {group_id: {client_socket}}
        self.chat_history = {'global': []} # {chat_id: [messages]}
        self.client_lock = threading.Lock()
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.config = self.load_config()
        self.zstd_c = zstd.ZstdCompressor()
        self.zstd_d = zstd.ZstdDecompressor()
        
        self.plugin_manager = None
        if self.config.get("plugins", {}).get("enabled", False):
            plugin_dir = self.config.get("plugins", {}).get("directory", "VoiceChat/plugins")
            self.plugin_manager = PluginManager(plugin_folder=plugin_dir)
            self.plugin_manager.discover_plugins()

    @staticmethod
    def load_config():
        try:
            with open('VoiceChat/server/server_config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("Warning: server_config.json not found or invalid. Using default settings.")
            return {"host": "0.0.0.0", "port": 12345, "max_clients": 100, "welcome_message": "Welcome!"}

    def start(self):
        self.tcp_sock.bind((self.host, self.port))
        self.udp_sock.bind((self.host, self.port))
        self.tcp_sock.listen(self.config.get("max_clients", 100))
        print(f"TCP Server started on {self.host}:{self.port}.")
        if self.password:
            print("Server is password protected.")
        print(f"UDP Server listening on {self.host}:{self.port}.")

        if self.plugin_manager:
            print(f"Loaded plugins: {list(self.plugin_manager.plugins.keys())}")

        udp_thread = threading.Thread(target=self.handle_udp_audio, daemon=True)
        udp_thread.start()

        while True:
            client_socket, address = self.tcp_sock.accept()
            print(f"New connection from {address}")
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
            client_thread.daemon = True
            client_thread.start()

    def handle_client(self, client_socket, address):
        unpacker = msgpack.Unpacker(raw=False)
        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                try:
                    decompressed_data = self.zstd_d.decompress(data)
                    unpacker.feed(decompressed_data)
                    for unpacked in unpacker:
                        self.process_command(client_socket, unpacked)
                except zstd.ZstdError:
                    print(f"Zstd decompression error from {address}. Might be a partial frame.")
                    continue

        except (ConnectionResetError, ConnectionAbortedError):
            print(f"Connection lost with {address}")
        finally:
            self.disconnect_client(client_socket)

    def process_command(self, sender_socket, message):
        command = message.get('command')
        payload = message.get('payload')
        
        handlers = {
            'login': self.handle_login,
            'create_group': self.handle_create_group,
            'invite_to_group': self.handle_invite_to_group,
            'group_invite_response': self.handle_group_invite_response,
            'group_message': self.handle_group_message,
            'request_history': self.handle_request_history,
            'start_group_call': self.handle_start_group_call,
            'join_group_call': self.handle_join_group_call,
            'leave_group_call': self.handle_leave_group_call,
            'kick_from_group': self.handle_kick_from_group,
        }
        
        handler = handlers.get(command)
        if handler:
            handler(sender_socket, payload)
        else:
            print(f"Unknown command received: {command}")

    def disconnect_client(self, client_socket):
        with self.client_lock:
            if client_socket in self.clients:
                username = self.clients[client_socket]['username']
                print(f"User '{username}' disconnected.")
                del self.clients[client_socket]
                
                # Remove from all groups
                groups_to_leave = []
                for group_id, group_data in self.groups.items():
                    if client_socket in group_data['members']:
                        groups_to_leave.append(group_id)
                
                for group_id in groups_to_leave:
                    self.groups[group_id]['members'].remove(client_socket)
                    if group_id in self.active_calls and client_socket in self.active_calls[group_id]:
                        self.active_calls[group_id].remove(client_socket)
                        self.broadcast_call_hang_up(group_id, username)

                self.broadcast_user_list()
        try:
            client_socket.close()
        except socket.error:
            pass

    def _send_to_client(self, client_socket, command, payload=None):
        try:
            message = {'command': command, 'payload': payload or {}}
            packed = msgpack.packb(message, use_bin_type=True)
            compressed = self.zstd_c.compress(packed)
            client_socket.sendall(compressed)
        except socket.error:
            self.disconnect_client(client_socket)

    def broadcast_user_list(self):
        with self.client_lock:
            user_list = [data['username'] for data in self.clients.values()]
            for client in self.clients.keys():
                self._send_to_client(client, 'user_list_update', {'users': user_list})

    # --- Command Handlers ---

    def handle_login(self, client_socket, payload):
        username = payload.get('username')
        password = payload.get('password')

        if self.password and self.password != password:
            self._send_to_client(client_socket, 'login_failed', {'reason': 'Invalid password'})
            self.disconnect_client(client_socket)
            return

        if not username:
            return
        udp_addr = payload.get('udp_addr')
        # Если udp_addr не предоставлен или невалиден, установим его в None или адрес по умолчанию
        if isinstance(udp_addr, list) and len(udp_addr) == 2:
            udp_addr = tuple(udp_addr)
        else:
            udp_addr = None # Или можно установить дефолтный адрес, например ('0.0.0.0', 0)
            
        with self.client_lock:
            self.clients[client_socket] = {'username': username, 'address': client_socket.getpeername(), 'udp_addr': udp_addr}
        print(f"User '{username}' logged in.")
        
        self._send_to_client(client_socket, 'login_success')

        # Send welcome message and initial data
        welcome_msg = self.config.get("welcome_message", "Welcome!")
        self._send_to_client(client_socket, 'info', {'message': welcome_msg})
        
        # Send existing groups and user list
        groups_info = {gid: {'name': g['name'], 'admin': g['admin'], 'members': [self.clients[m]['username'] for m in g['members']]} for gid, g in self.groups.items()}
        user_list = [data['username'] for data in self.clients.values()]
        self._send_to_client(client_socket, 'initial_data', {'groups': groups_info, 'users': user_list})

        self.broadcast_user_list()

    def handle_create_group(self, sender_socket, payload):
        group_name = payload.get('group_name')
        with self.client_lock:
            admin_username = self.clients.get(sender_socket, {}).get('username')
        if not group_name or not admin_username:
            return
            
        group_id = str(uuid.uuid4())
        self.groups[group_id] = {
            'name': group_name,
            'members': {sender_socket},
            'admin': admin_username
        }
        self.chat_history[group_id] = []
        print(f"Group '{group_name}' created by '{admin_username}'.")
        self._send_to_client(sender_socket, 'group_created', {'group_id': group_id, 'group_name': group_name, 'admin': admin_username})

    def handle_invite_to_group(self, sender_socket, payload):
        group_id = payload.get('group_id')
        target_username = payload.get('username')
        
        with self.client_lock:
            admin_username = self.clients.get(sender_socket, {}).get('username')
            group = self.groups.get(group_id)
            if not group or group['admin'] != admin_username:
                return # Not admin or group doesn't exist
            
            target_socket = None
            for sock, data in self.clients.items():
                if data['username'] == target_username:
                    target_socket = sock
                    break
            
            if target_socket and target_socket not in group['members']:
                self._send_to_client(target_socket, 'group_invite', {
                    'group_id': group_id,
                    'group_name': group['name'],
                    'admin': admin_username
                })

    def handle_group_invite_response(self, sender_socket, payload):
        group_id = payload.get('group_id')
        accepted = payload.get('accepted')
        
        with self.client_lock:
            group = self.groups.get(group_id)
            username = self.clients.get(sender_socket, {}).get('username')
            if not group or not username:
                return

            admin_socket = None
            for sock, data in self.clients.items():
                if data['username'] == group['admin']:
                    admin_socket = sock
                    break
            
            if accepted:
                group['members'].add(sender_socket)
                # Notify admin
                if admin_socket:
                    self._send_to_client(admin_socket, 'group_invite_response', {'group_id': group_id, 'username': username, 'accepted': True})
                # Notify all members of the new user
                for member_socket in group['members']:
                    self._send_to_client(member_socket, 'user_joined_group', {'group_id': group_id, 'username': username})
            else:
                # Notify admin of rejection
                if admin_socket:
                    self._send_to_client(admin_socket, 'group_invite_response', {'group_id': group_id, 'username': username, 'accepted': False})

    def handle_group_message(self, sender_socket, payload):
        group_id = payload.get('group_id')
        message_data = payload.get('message_data')
        
        with self.client_lock:
            group = self.groups.get(group_id)
            if not group or sender_socket not in group['members']:
                return
            
            # Add to history
            self.chat_history.setdefault(group_id, []).append(message_data)
            
            # Relay to other members
            for member_socket in group['members']:
                if member_socket != sender_socket:
                    self._send_to_client(member_socket, 'group_message', {'group_id': group_id, 'message_data': message_data})

    def handle_request_history(self, sender_socket, payload):
        chat_id = payload.get('chat_id')
        if chat_id in self.chat_history:
            self._send_to_client(sender_socket, 'history_response', {
                'chat_id': chat_id,
                'history': self.chat_history[chat_id]
            })

    def handle_kick_from_group(self, sender_socket, payload):
        group_id = payload.get('group_id')
        username_to_kick = payload.get('username')

        with self.client_lock:
            admin_username = self.clients.get(sender_socket, {}).get('username')
            group = self.groups.get(group_id)

            if not group or group['admin'] != admin_username:
                # Silently fail if not admin or group doesn't exist
                return

            socket_to_kick = None
            for sock, data in self.clients.items():
                if data['username'] == username_to_kick:
                    socket_to_kick = sock
                    break
            
            if socket_to_kick and socket_to_kick in group['members']:
                group['members'].remove(socket_to_kick)
                print(f"User '{username_to_kick}' was kicked from group '{group['name']}' by admin '{admin_username}'.")

                # Notify all original members (including the kicked one)
                notification_payload = {
                    'group_id': group_id,
                    'kicked_user': username_to_kick,
                    'admin': admin_username
                }
                # Create a temporary list of members to notify before the kick
                members_to_notify = list(group['members']) + [socket_to_kick]
                for member_socket in members_to_notify:
                    self._send_to_client(member_socket, 'user_kicked', notification_payload)

    def handle_start_group_call(self, sender_socket, payload):
        group_id = payload.get('group_id')
        sample_rate = payload.get('sample_rate')
        with self.client_lock:
            group = self.groups.get(group_id)
            admin_username = self.clients.get(sender_socket, {}).get('username')
            if not group or group['admin'] != admin_username:
                return
            
            self.active_calls[group_id] = {sender_socket}
            
            for member_socket in group['members']:
                if member_socket != sender_socket:
                    self._send_to_client(member_socket, 'incoming_group_call', {
                        'group_id': group_id,
                        'group_name': group['name'],
                        'admin': admin_username,
                        'sample_rate': sample_rate
                    })

    def handle_join_group_call(self, sender_socket, payload):
        group_id = payload.get('group_id')
        udp_addr = tuple(payload.get('udp_addr'))
        with self.client_lock:
            if group_id not in self.active_calls:
                return
            
            self.clients[sender_socket]['udp_addr'] = udp_addr
            self.active_calls[group_id].add(sender_socket)
            username = self.clients[sender_socket]['username']
            
            # Notify others in the call that this user has joined
            for member_socket in self.active_calls[group_id]:
                if member_socket != sender_socket:
                    self._send_to_client(member_socket, 'user_joined_call', {'group_id': group_id, 'username': username})

    def handle_leave_group_call(self, sender_socket, payload):
        group_id = payload.get('group_id')
        with self.client_lock:
            username = self.clients.get(sender_socket, {}).get('username')
            if group_id in self.active_calls and sender_socket in self.active_calls[group_id]:
                self.active_calls[group_id].remove(sender_socket)
                if username:
                    self.broadcast_call_hang_up(group_id, username)

    def broadcast_call_hang_up(self, group_id, username):
        # This can be called from disconnect or leave_group_call
        with self.client_lock:
            if group_id in self.active_calls:
                for member_socket in self.active_calls[group_id]:
                    self._send_to_client(member_socket, 'user_left_call', {'group_id': group_id, 'username': username})

    def handle_udp_audio(self):
        while True:
            try:
                data, sender_addr = self.udp_sock.recvfrom(2048)
                
                with self.client_lock:
                    sender_socket = None
                    for sock, client_data in self.clients.items():
                        if client_data['udp_addr'] == sender_addr:
                            sender_socket = sock
                            break
                    
                    if not sender_socket:
                        continue

                    # Find which call this user is in
                    active_group_id = None
                    for group_id, members in self.active_calls.items():
                        if sender_socket in members:
                            active_group_id = group_id
                            break
                    
                    if not active_group_id:
                        continue

                    # Relay audio to other call members
                    for member_socket in self.active_calls[active_group_id]:
                        if member_socket != sender_socket and self.clients[member_socket]['udp_addr']:
                            self.udp_sock.sendto(data, self.clients[member_socket]['udp_addr'])

            except Exception as e:
                print(f"Error in UDP handler: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Chat Server")
    parser.add_argument('--host', default=None, help='Host to bind the server to.')
    parser.add_argument('--port', type=int, default=None, help='Port to bind the server to.')
    parser.add_argument('--password', default=None, help='Password for the server.')
    args = parser.parse_args()

    config = Server.load_config()
    host = args.host or config.get("host")
    port = args.port or config.get("port")
    
    server = Server(host=host, port=port, password=args.password)
    server.start()