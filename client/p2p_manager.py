import socket
import threading
import time
import json
from PyQt6.QtCore import QObject, pyqtSignal

P2P_PORT = 12346  # Отдельный порт для P2P
BROADCAST_ADDR = '<broadcast>'

class P2PManager(QObject):
    peer_discovered = pyqtSignal(str, str) # username, address
    peer_lost = pyqtSignal(str) # username
    message_received = pyqtSignal(str, str) # username, message
    # Сигналы для P2P звонков
    incoming_p2p_call = pyqtSignal(str, dict) # from_username, payload
    p2p_call_response = pyqtSignal(str, dict) # from_username, payload
    p2p_hang_up = pyqtSignal(str) # from_username

    def __init__(self, username):
        super().__init__()
        self.username = username
        self.peers = {} # {username: (address, last_seen_time)}
        self.running = True
        
        # Находим свой локальный IP, чтобы не добавлять себя в пиры
        self.my_ip = self._get_local_ip()

        # Поток для отправки "приветствий"
        self.broadcast_thread = threading.Thread(target=self.send_discovery_broadcast)
        self.broadcast_thread.daemon = True

        # Поток для прослушивания "приветствий"
        self.listen_thread = threading.Thread(target=self.listen_for_peers)
        self.listen_thread.daemon = True
        
        # Поток для проверки "мертвых" пиров
        self.check_thread = threading.Thread(target=self.check_peers)
        self.check_thread.daemon = True

    def start(self):
        self.listen_thread.start()
        self.broadcast_thread.start()
        self.check_thread.start()

    def stop(self):
        self.running = False

    def _get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Не обязательно должен быть доступен
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def send_discovery_broadcast(self):
        """Периодически рассылает discovery-сообщения."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        message = json.dumps({'command': 'discovery', 'username': self.username}).encode('utf-8')
        
        while self.running:
            sock.sendto(message, (BROADCAST_ADDR, P2P_PORT))
            time.sleep(5) # Отправляем приветствие каждые 5 секунд
        sock.close()

    def listen_for_peers(self):
        """Слушает discovery-сообщения от других пиров."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', P2P_PORT))

        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                if addr[0] == self.my_ip:
                    continue # Игнорируем собственные сообщения

                message = json.loads(data.decode('utf-8'))
                command = message.get('command')
                username = message.get('username')

                if command == 'discovery':
                    if username and username not in self.peers:
                        self.peer_discovered.emit(username, addr[0])
                    if username:
                        self.peers[username] = (addr[0], time.time())
                
                elif command == 'message':
                    text = message.get('text')
                    if username and text:
                        self.message_received.emit(username, text)
                
                # Обработка команд звонков
                elif command == 'p2p_call_request':
                    self.incoming_p2p_call.emit(username, message.get('payload'))
                elif command == 'p2p_call_response':
                    self.p2p_call_response.emit(username, message.get('payload'))
                elif command == 'p2p_hang_up':
                    self.p2p_hang_up.emit(username)


            except Exception as e:
                if self.running:
                    print(f"Ошибка в P2P listener: {e}")
        sock.close()

    def check_peers(self):
        """Проверяет, не отключились ли пиры."""
        while self.running:
            time.sleep(15) # Проверяем каждые 15 секунд
            now = time.time()
            lost_peers = []
            for username, (addr, last_seen) in self.peers.items():
                if now - last_seen > 12: # Если пир молчит больше 12 секунд
                    lost_peers.append(username)
            
            for username in lost_peers:
                if username in self.peers:
                    del self.peers[username]
                    self.peer_lost.emit(username)

    def broadcast_message(self, text):
        """Отправляет текстовое сообщение всем известным пирам."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        message_data = {
            'command': 'message',
            'username': self.username,
            'text': text
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        with threading.Lock(): # На случай, если check_peers изменит словарь
            for username, (addr, last_seen) in self.peers.items():
                try:
                    sock.sendto(message_bytes, (addr, P2P_PORT))
                except Exception as e:
                    print(f"Не удалось отправить сообщение для {username}: {e}")
        sock.close()

    def send_peer_command(self, target_username, command, payload):
        """Отправляет команду конкретному пиру."""
        if target_username not in self.peers:
            print(f"Ошибка: пир {target_username} не найден.")
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        message_data = {
            'command': command,
            'username': self.username,
            'payload': payload
        }
        message_bytes = json.dumps(message_data).encode('utf-8')
        
        peer_address = self.peers[target_username][0]
        try:
            sock.sendto(message_bytes, (peer_address, P2P_PORT))
        except Exception as e:
            print(f"Не удалось отправить команду пиру {target_username}: {e}")
        finally:
            sock.close()