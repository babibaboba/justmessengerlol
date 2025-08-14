import socket
import threading
import json
import os
import sys

# Добавляем корневую папку проекта в sys.path
# чтобы можно было импортировать plugin_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from plugin_manager import PluginManager
except ImportError as e:
    print(f"Fatal Error: Could not import PluginManager. {e}")
    print("Make sure 'plugin_manager.py' is in the 'VoiceChat' directory.")
    sys.exit(1)


class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.clients = []
        self.client_lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.config = self.load_config()
        
        # Инициализация менеджера плагинов
        self.plugin_manager = None
        if self.config.get("plugins", {}).get("enabled", False):
            plugin_dir = self.config.get("plugins", {}).get("directory", "VoiceChat/plugins")
            self.plugin_manager = PluginManager(plugin_folder=plugin_dir)
            self.plugin_manager.discover_plugins()

    def load_config(self):
        """Загружает конфигурацию сервера из JSON файла."""
        try:
            with open('VoiceChat/server/server_config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Error: server_config.json not found. Using default settings.")
            return {"host": "0.0.0.0", "port": 12345, "mode": "relay"}
        except json.JSONDecodeError:
            print("Error: Could not decode server_config.json. Check its format.")
            return {"host": "0.0.0.0", "port": 12345, "mode": "relay"}

    def start(self):
        """Запускает сервер."""
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.config.get("max_clients", 100))
        print(f"Server started on {self.host}:{self.port} in '{self.config.get('mode')}' mode.")
        
        if self.plugin_manager:
            print(f"Loaded plugins: {list(self.plugin_manager.plugins.keys())}")

        while True:
            client_socket, address = self.sock.accept()
            print(f"New connection from {address}")
            
            client_thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
            client_thread.daemon = True
            client_thread.start()

    def handle_client(self, client_socket, address):
        """Обрабатывает подключение одного клиента."""
        with self.client_lock:
            self.clients.append(client_socket)
            
        # Отправляем приветственное сообщение
        welcome_msg = self.config.get("welcome_message", "Welcome!")
        self.send_to_client(client_socket, {"type": "info", "payload": welcome_msg})

        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                # В режиме ретранслятора просто пересылаем данные всем остальным
                self.broadcast(data, sender_socket=client_socket)

        except (ConnectionResetError, ConnectionAbortedError):
            print(f"Connection lost with {address}")
        finally:
            with self.client_lock:
                self.clients.remove(client_socket)
            client_socket.close()
            print(f"Connection closed with {address}")

    def broadcast(self, message, sender_socket=None):
        """Рассылает сообщение всем клиентам, кроме отправителя."""
        
        # --- Plugin Hook: on_server_broadcast ---
        if self.plugin_manager:
            # Мы должны декодировать сообщение, чтобы плагины могли его прочитать
            try:
                msg_dict = json.loads(message.decode('utf-8'))
                modified_message = self.plugin_manager.trigger_hook(
                    'on_server_broadcast', 
                    message_data=msg_dict, 
                    clients=self.clients
                )
                if modified_message is False:
                    print("Broadcast cancelled by a plugin.")
                    return
                # Если плагин изменил сообщение, кодируем его обратно
                if modified_message is not None:
                    message = json.dumps(modified_message).encode('utf-8')

            except (json.JSONDecodeError, UnicodeDecodeError):
                # Если это не JSON, плагины не смогут его обработать
                pass
        # --- End Plugin Hook ---

        with self.client_lock:
            for client in self.clients:
                if client is not sender_socket:
                    try:
                        client.sendall(message)
                    except socket.error:
                        # Клиент мог отключиться, его обработчик удалит его из списка
                        pass
                        
    def send_to_client(self, client_socket, message_dict):
        """Отправляет JSON-сообщение конкретному клиенту."""
        try:
            client_socket.sendall(json.dumps(message_dict).encode('utf-8'))
        except socket.error:
            pass


if __name__ == "__main__":
    config = Server.load_config(None) # Загружаем конфиг статически для получения порта/хоста
    server = Server(host=config.get("host"), port=config.get("port"))
    server.start()