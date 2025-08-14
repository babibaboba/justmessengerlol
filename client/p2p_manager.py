import socket
import threading
import time
import json
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt

from kademlia.network import Server as KademliaServer

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

    def __init__(self, username, mode='internet'):
        super().__init__()
        self.username = username
        self.mode = mode # 'internet' or 'local'
        self.peers = {} # {username: (address, last_seen_time)}
        self.running = True
        self.dht_node = None
        self.dht_thread = None
        self.dht_loop = None
        
        # Находим свой локальный IP, чтобы не добавлять себя в пиры
        self.my_ip = self._get_local_ip()

        if self.mode == 'local':
            self.dht_node = None
            self.dht_thread = None
            # Потоки для локальной сети
            self.broadcast_thread = threading.Thread(target=self.send_discovery_broadcast)
            self.listen_thread = threading.Thread(target=self.listen_for_peers)
            self.check_thread = threading.Thread(target=self.check_peers)
        else: # internet mode
            self.broadcast_thread = None
            self.listen_thread = None
            self.check_thread = None
            # Для интернет-режима инициализируем DHT
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
            # Запускаем поток для DHT
            if self.dht_thread: self.dht_thread.start()

    def stop(self):
        self.running = False
        if self.dht_node:
            # Kademlia работает в asyncio, поэтому остановка должна быть неблокирующей
            # В реальной реализации может потребоваться более сложная логика
            print("Остановка DHT узла...")
            # self.dht_node.stop() # У реальной библиотеки может быть такой метод

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

    # --- Методы для работы с DHT (для режима P2P-Интернет) ---

    def _run_dht(self):
        """Запускает и управляет event loop'ом для asyncio DHT."""
        self.dht_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.dht_loop)
        self.dht_loop.run_until_complete(self._dht_main())

    async def _dht_main(self):
        """Основная асинхронная задача для работы с DHT."""
        # TODO: Заменить на реальные bootstrap-узлы
        bootstrap_nodes = [("127.0.0.1", 8468)]
        
        # Запускаем прослушивание на случайном порту
        await self.dht_node.listen(P2P_PORT)
        # Подключаемся к сети
        await self.dht_node.bootstrap(bootstrap_nodes)

        # Периодически публикуем информацию о себе и ищем других
        while self.running:
            # Публикуем свой адрес. Значение должно быть сериализуемым.
            my_address_info = json.dumps((self.my_ip, P2P_PORT))
            await self.dht_node.set(self.username, my_address_info)
            
            await asyncio.sleep(30) # Перепубликация каждые 30 секунд
        
        # await self.dht_node.stop() # У Kademlia нет stop(), она останавливается с event loop

    def find_peer(self, username):
        """
        Инициирует поиск пира в DHT.
        Так как поиск - асинхронная операция, мы запускаем ее в потоке DHT.
        """
        if self.dht_loop and self.dht_loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_find_peer(username), self.dht_loop)

    async def _async_find_peer(self, username):
        """Асинхронная часть поиска пира."""
        print(f"[DHT] Ищем пользователя {username}...")
        found_value = await self.dht_node.get(username)
        if found_value:
            print(f"[DHT] Найден {username} с данными: {found_value}")
            try:
                # Данные хранятся как JSON-строка "(ip, port)"
                user_ip, user_port = json.loads(found_value)
                
                # Обновляем наш локальный список пиров
                self.peers[username] = (user_ip, time.time())
                
                # Безопасно отправляем сигнал в главный поток GUI
                QMetaObject.invokeMethod(
                    self, "emit_peer_discovered", Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, username), Q_ARG(str, user_ip)
                )
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"Ошибка парсинга данных для {username}: {e}")
        else:
            print(f"[DHT] Пользователь {username} не найден.")
            # TODO: Сообщить пользователю в GUI, что пир не найден

    @pyqtSlot(str, str)
    def emit_peer_discovered(self, username, address):
        """Слот для безопасного вызова сигнала из другого потока."""
        self.peer_discovered.emit(username, address)