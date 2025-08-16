import socket
import threading
import msgpack
import zstandard as zstd
import queue

class ServerManager(threading.Thread):
    def __init__(self, host, port, username, password, chat_history):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.chat_history = chat_history # Reference to the main app's history
        self.sock = None
        self.running = True
        self.callbacks = {}
        self.zstd_c = zstd.ZstdCompressor()
        self.zstd_d = zstd.ZstdDecompressor()

    def register_callback(self, event_name, func):
        self.callbacks[event_name] = func

    def _trigger_callback(self, event_name, *args):
        if event_name in self.callbacks:
            self.callbacks[event_name](*args)

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.login()
            self.listen_for_messages()
        except Exception as e:
            print(f"ServerManager Error: {e}")
            self._trigger_callback('connection_failed', str(e))
        finally:
            if self.sock:
                self.sock.close()

    def listen_for_messages(self):
        unpacker = msgpack.Unpacker(raw=False)
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                
                # Decompress the received chunk immediately
                try:
                    decompressed_data = self.zstd_d.decompress(data)
                    unpacker.feed(decompressed_data)
                    for unpacked in unpacker:
                        self.handle_command(unpacked)
                except zstd.ZstdError:
                    # This might happen if we receive a partial compressed frame.
                    # A more robust solution would buffer compressed chunks.
                    # For now, we assume each recv() gets at least one full message.
                    print("Warning: Could not decompress chunk, might be partial.")
                    continue

            except (ConnectionResetError, ConnectionAbortedError):
                print("Connection to server lost.")
                break
            except Exception as e:
                print(f"Error receiving data from server: {e}")
                break
        self._trigger_callback('disconnected')

    def _send_command(self, command, payload=None):
        if not self.sock:
            return
        try:
            message = {'command': command, 'payload': payload or {}}
            packed_message = msgpack.packb(message, use_bin_type=True)
            compressed_message = self.zstd_c.compress(packed_message)
            self.sock.sendall(compressed_message)
        except Exception as e:
            print(f"Error sending command '{command}': {e}")

    def handle_command(self, message):
        try:
            command = message.get('command')
            payload = message.get('payload')

            if command == 'login_success':
                # We don't really need to do anything here, but it's good to have.
                pass
            elif command == 'login_failed':
                self._trigger_callback('login_failed', payload)
            elif command == 'info':
                self._trigger_callback('info_received', payload)
            elif command == 'user_list_update':
                self._trigger_callback('user_list_update', payload.get('users'))
            elif command == 'group_message':
                self._trigger_callback('group_message_received', payload.get('group_id'), payload.get('message_data'))
            elif command == 'group_created':
                 self._trigger_callback('group_created', payload.get('group_id'), payload.get('group_name'), payload.get('admin'))
            elif command == 'group_invite':
                self._trigger_callback('incoming_group_invite', payload.get('group_id'), payload.get('group_name'), payload.get('admin'))
            elif command == 'group_invite_response':
                 self._trigger_callback('group_invite_response', payload.get('group_id'), payload.get('username'), payload.get('accepted'))
            elif command == 'user_joined_group':
                self._trigger_callback('group_joined', payload.get('group_id'), payload.get('username'))
            elif command == 'history_response':
                self._trigger_callback('history_received', payload.get('chat_id'), payload.get('history'))
            elif command == 'initial_data':
                self._trigger_callback('initial_data_received', payload.get('groups'), payload.get('users'))
            elif command == 'incoming_group_call':
                self._trigger_callback('incoming_group_call', payload.get('group_id'), payload.get('admin'), payload.get('sample_rate'))
            elif command == 'user_joined_call':
                self._trigger_callback('user_joined_call', payload.get('group_id'), payload.get('username'))
            elif command == 'user_left_call':
                self._trigger_callback('user_left_call', payload.get('group_id'), payload.get('username'))
            elif command == 'user_kicked':
                self._trigger_callback('user_kicked', payload.get('group_id'), payload.get('kicked_user'), payload.get('admin'))


        except Exception as e:
            print(f"Error handling server command: {e} - Message: {message}")

    def login(self):
        self._send_command('login', {'username': self.username, 'password': self.password})

    def send_group_message(self, group_id, message_data):
        self._send_command('group_message', {'group_id': group_id, 'message_data': message_data})

    def create_group(self, group_name):
        self._send_command('create_group', {'group_name': group_name})

    def invite_to_group(self, group_id, target_username):
        self._send_command('invite_to_group', {'group_id': group_id, 'username': target_username})

    def send_group_invite_response(self, group_id, accepted):
        self._send_command('group_invite_response', {'group_id': group_id, 'accepted': accepted})
        
    def request_history(self, chat_id):
        self._send_command('request_history', {'chat_id': chat_id})

    def start_group_call(self, group_id, sample_rate):
        self._send_command('start_group_call', {'group_id': group_id, 'sample_rate': sample_rate})

    def join_group_call(self, group_id, udp_addr):
        self._send_command('join_group_call', {'group_id': group_id, 'udp_addr': udp_addr})

    def leave_group_call(self, group_id):
        self._send_command('leave_group_call', {'group_id': group_id})

    def kick_user_from_group(self, group_id, username):
        self._send_command('kick_from_group', {'group_id': group_id, 'username': username})

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except OSError:
                pass
        print("ServerManager stopped.")