import os
import json
from cryptography.fernet import Fernet

class ConfigManager:
    def __init__(self, key_path='secret.key', config_path='config.dat'):
        self.key_path = key_path
        self.config_path = config_path
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

# Пример использования:
if __name__ == '__main__':
    # Этот код выполнится, только если запустить этот файл напрямую
    manager = ConfigManager()

    # Сохранение данных
    user_settings = {'username': 'Roo', 'theme': 'dark'}
    print(f"Сохраняем: {user_settings}")
    manager.save_config(user_settings)

    # Загрузка данных
    loaded_settings = manager.load_config()
    print(f"Загружено: {loaded_settings}")

    if loaded_settings and loaded_settings.get('username') == 'Roo':
        print("Тест пройден успешно!")
    else:
        print("Тест не пройден.")