import socket
import threading
import json
from database_manager import DatabaseManager

HOST = '0.0.0.0'
PORT = 12345

class Server:
    def __init__(self):
        self.db = DatabaseManager()
        self.clients = {}  # {conn: username}
        self.lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((HOST, PORT))

    def start(self):
        self.server_socket.listen()
        print(f"Сервер запущен на {HOST}:{PORT}")
        try:
            while True:
                conn, addr = self.server_socket.accept()
                thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                thread.start()
        except KeyboardInterrupt:
            print("Сервер останавливается...")
        finally:
            self.db.close()
            self.server_socket.close()

    def handle_client(self, conn, addr):
        print(f"Новое подключение от {addr}")
        is_authenticated = False
        username = None
        
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                
                try:
                    request = json.loads(data.decode('utf-8'))
                    command = request.get('command')
                    payload = request.get('payload')

                    if not is_authenticated:
                        if command == 'login':
                            username, is_authenticated = self.login_user(conn, payload)
                        elif command == 'register':
                            self.register_user(conn, payload)
                        else:
                            self.send_response(conn, 'error', 'Требуется аутентификация.')
                    else:
                        # Обработка команд для аутентифицированных пользователей
                        if command == 'send_message':
                            self.process_new_message(conn, username, payload)
                        elif command == 'list_users':
                            self.list_users(conn)
                        elif command == 'call_request':
                            self.handle_call_request(username, payload, conn.getpeername())
                        elif command == 'call_response':
                            self.handle_call_response(username, payload, conn.getpeername())
                        elif command == 'set_status':
                           self.handle_set_status(username, payload)
                        else:
                            self.send_response(conn, 'error', f'Неизвестная команда: {command}')

                except (json.JSONDecodeError, KeyError):
                    self.send_response(conn, 'error', 'Неверный формат запроса.')

        except (socket.error, ConnectionResetError):
            print(f"Соединение с {addr} потеряно.")
        finally:
            with self.lock:
                if conn in self.clients:
                    disconnected_user = self.clients.pop(conn)
                    self.broadcast_user_list_update() # Отправляем обновленный список пользователей
            conn.close()
            print(f"Соединение с {addr} закрыто.")

    def login_user(self, conn, payload):
        username = payload.get('username')
        password = payload.get('password')
        if self.db.check_credentials(username, password):
            with self.lock:
                # Проверяем, не вошел ли пользователь уже с другого устройства
                if username in self.clients.values():
                    self.send_response(conn, 'error', 'Этот пользователь уже в сети.')
                    return None, False
                self.clients[conn] = username
            
            self.send_response(conn, 'login_success', {'username': username})
            print(f"Пользователь {username} вошел в систему.")
            # Оповещаем всех о новом пользователе и обновляем списки
            self.broadcast_user_list_update()
            return username, True
        else:
            self.send_response(conn, 'error', 'Неверное имя пользователя или пароль.')
            return None, False

    def register_user(self, conn, payload):
        username = payload.get('username')
        password = payload.get('password')
        success, message = self.db.register_user(username, password)
        if success:
            self.send_response(conn, 'register_success', message)
        else:
            self.send_response(conn, 'error', message)

    def send_response(self, conn, status, data):
        """Отправляет стандартизированный ответ клиенту."""
        response = {'status': status, 'data': data}
        try:
            conn.sendall(json.dumps(response).encode('utf-8'))
        except socket.error:
            print("Не удалось отправить ответ.")

    def broadcast(self, response, sender_conn=None):
        """Рассылает ответ всем аутентифицированным клиентам, опционально исключая отправителя."""
        with self.lock:
            for conn in self.clients:
                if conn != sender_conn:
                    try:
                        conn.sendall(json.dumps(response).encode('utf-8'))
                    except socket.error:
                        print(f"Не удалось отправить сообщение клиенту {self.clients[conn]}")

    def process_new_message(self, conn, username, payload):
       """Обрабатывает входящее сообщение (текст или GIF) и рассылает его."""
       msg_type = payload.get('type', 'text')
       message_data = {'sender': username, 'type': msg_type}

       if msg_type == 'text':
           text = payload.get('text')
           if not text:
               self.send_response(conn, 'error', 'Текстовое сообщение не может быть пустым.')
               return
           message_data['text'] = text
           print(f"Сообщение от {username}: {text}")
       elif msg_type == 'gif':
           gif_path = payload.get('gif_path')
           if not gif_path:
               self.send_response(conn, 'error', 'Сообщение GIF не содержит путь.')
               return
           message_data['gif_path'] = gif_path
           print(f"GIF от {username}: {gif_path}")
       else:
           self.send_response(conn, 'error', 'Неизвестный тип сообщения.')
           return

       response = {'status': 'new_message', 'data': message_data}
       self.broadcast(response, sender_conn=conn)

    def find_connection_by_username(self, username):
        """Находит соединение по имени пользователя."""
        with self.lock:
            for conn, user in self.clients.items():
                if user == username:
                    return conn
        return None

    def list_users(self, conn=None):
       """
       Собирает список онлайн-пользователей с их статусами.
       Если conn указан, отправляет список только этому клиенту.
       Иначе, возвращает список для использования в broadcast.
       """
       with self.lock:
           online_usernames = list(self.clients.values())
       
       users_with_statuses = []
       for username in online_usernames:
           user_data = self.db.get_user(username)
           if user_data:
               # user_data -> (id, username, password_hash, status_emoji, storage_used)
               status_emoji = user_data[3] if user_data[3] else '😀'
               users_with_statuses.append({'username': username, 'status': status_emoji})

       if conn:
           self.send_response(conn, 'user_list', {'users': users_with_statuses})
       return users_with_statuses

    def broadcast_user_list_update(self):
       """Рассылает всем клиентам обновленный список пользователей."""
       print("Рассылка обновленного списка пользователей...")
       users = self.list_users()
       response = {'status': 'user_list', 'data': {'users': users}}
       self.broadcast(response)

    def handle_call_request(self, from_user, payload, addr):
        """Обрабатывает запрос на звонок, включая информацию для UDP."""
        to_user = payload.get('to_user')
        udp_port = payload.get('udp_port')
        to_conn = self.find_connection_by_username(to_user)

        if to_conn and udp_port:
            caller_ip = addr[0]
            print(f"Пересылаю запрос на звонок от {from_user} ({caller_ip}:{udp_port}) к {to_user}")
            
            self.send_response(to_conn, 'incoming_call', {
                'from_user': from_user,
                'caller_addr': (caller_ip, udp_port)
            })
        elif not to_conn:
            from_conn = self.find_connection_by_username(from_user)
            self.send_response(from_conn, 'error', f'Пользователь {to_user} не найден или не в сети.')
        else: # not udp_port
             from_conn = self.find_connection_by_username(from_user)
             self.send_response(from_conn, 'error', 'Не указан UDP порт для звонка.')

    def handle_call_response(self, from_user, payload, addr):
        """Обрабатывает ответ на звонок, включая информацию для UDP."""
        to_user = payload.get('to_user')
        answer = payload.get('answer')  # 'accept' or 'reject'
        udp_port = payload.get('udp_port') # Порт отвечающего
        to_conn = self.find_connection_by_username(to_user)

        if to_conn:
            response_payload = {'from_user': from_user, 'answer': answer}
            if answer == 'accept' and udp_port:
                callee_ip = addr[0]
                response_payload['callee_addr'] = (callee_ip, udp_port)
                print(f"Ответ 'accept' от {from_user} для {to_user} с адресом {callee_ip}:{udp_port}")
            else:
                print(f"Пересылаю ответ '{answer}' от {from_user} к {to_user}")

            self.send_response(to_conn, 'call_response', response_payload)


    def handle_set_status(self, username, payload):
       """Обрабатывает смену эмодзи-статуса."""
       emoji = payload.get('status_emoji')
       if emoji:
           if self.db.update_user_status(username, emoji):
               print(f"Пользователь {username} установил статус: {emoji}")
               self.send_response(self.find_connection_by_username(username), 'status_update_success', {'status_emoji': emoji})
               self.broadcast_user_list_update()
           else:
               self.send_response(self.find_connection_by_username(username), 'error', 'Не удалось обновить статус.')
       else:
           self.send_response(self.find_connection_by_username(username), 'error', 'Не указан эмодзи для статуса.')


if __name__ == "__main__":
    server = Server()
    server.start()