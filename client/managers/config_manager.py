import os
import json
from cryptography.fernet import Fernet

class ConfigManager:
    def __init__(self, key_path='secret.key', config_path='config.dat'):
        self.key_path = key_path
        self.config_path = config_path
        self.chat_history_path = 'chat_history.dat'  # Separate file for chat history
        self.key = self.load_or_generate_key()
        self.cipher = Fernet(self.key)

    def load_or_generate_key(self):
        """Загружает ключ шифрования или генерирует новый, если он не найден."""
        if os.path.exists(self.key_path):
            with open(self.key_path, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            return key

    def save_config(self, config_data):
        """Шифрует и сохраняет данные конфигурации."""
        try:
            # Сериализуем словарь в JSON-строку, затем в байты
            data_bytes = json.dumps(config_data).encode('utf-8')
            encrypted_data = self.cipher.encrypt(data_bytes)
            with open(self.config_path, 'wb') as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении конфигурации: {e}")
            return False

    def load_config(self):
        """Загружает и расшифровывает данные конфигурации."""
        if not os.path.exists(self.config_path):
            return {}  # Возвращаем пустой словарь, если конфига нет

        try:
            with open(self.config_path, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data_bytes = self.cipher.decrypt(encrypted_data)
            # Десериализуем из байтов в JSON-строку, затем в словарь
            config_data = json.loads(decrypted_data_bytes.decode('utf-8'))
            return config_data
        except Exception as e:
            print(f"Ошибка при загрузке или расшифровке конфигурации: {e}")
            # Если расшифровка не удалась (например, ключ изменился), возвращаем пустой конфиг
            return {}

    def save_chat_history(self, chat_history_data):
        """
        Шифрует и сохраняет данные истории чата в отдельном файле.
        Используется для больших структур данных, чтобы не перегружать основной конфиг.
        """
        try:
            # Сериализуем словарь истории чата в JSON-строку, затем в байты
            data_bytes = json.dumps(chat_history_data).encode('utf-8')
            encrypted_data = self.cipher.encrypt(data_bytes)
            with open(self.chat_history_path, 'wb') as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении истории чата: {e}")
            return False

    def load_chat_history(self):
        """Загружает и расшифровывает данные истории чата."""
        if not os.path.exists(self.chat_history_path):
            return {}  # Возвращаем пустой словарь, если файла истории нет

        try:
            with open(self.chat_history_path, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data_bytes = self.cipher.decrypt(encrypted_data)
            # Десериализуем из байтов в JSON-строку, затем в словарь
            chat_history_data = json.loads(decrypted_data_bytes.decode('utf-8'))
            return chat_history_data
        except Exception as e:
            print(f"Ошибка при загрузке или расшифровке истории чата: {e}")
            # Если расшифровка не удалась, возвращаем пустую историю
            return {}


# Пример использования:
if __name__ == '__main__':
    # Этот код выполнится, только если запустить этот файл напрямую
    manager = ConfigManager()

    # Сохранение данных
    user_settings = {'username': 'Roo', 'theme': 'dark'}
    print(f"Сохраняем: {user_settings}")
    manager.save_config(user_settings)

    # Пример сохранения истории чата
    sample_chat_history = {
        'global': [
            {'sender': 'System', 'text': 'Welcome to VoiceChat!', 'timestamp': '2025-01-01T00:00:00'}
        ]
    }
    manager.save_chat_history(sample_chat_history)
    print(f"Сохранена история чата: {list(sample_chat_history.keys())}")

    # Загрузка данных
    loaded_settings = manager.load_config()
    print(f"Загружено: {loaded_settings}")

    # Загрузка истории чата
    loaded_chat_history = manager.load_chat_history()
    print(f"Загружена история чата: {list(loaded_chat_history.keys())}")

    if loaded_settings and loaded_settings.get('username') == 'Roo':
        print("Тест пройден успешно!")
    else:
        print("Тест не пройден.")