import sqlite3
import hashlib

class DatabaseManager:
    def __init__(self, db_name='messenger.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Создает таблицы, если они не существуют."""
        # Пользователи
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                status_emoji TEXT,
                storage_used INTEGER DEFAULT 0
            )
        ''')
       # Истории
       self.cursor.execute('''
           CREATE TABLE IF NOT EXISTS stories (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               content_path TEXT NOT NULL,
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY (user_id) REFERENCES users (id)
           )
       ''')
        # TODO: Добавить таблицы для каналов, сообщений, участников и т.д.
        self.conn.commit()

    def _hash_password(self, password):
        """Хэширует пароль для безопасного хранения."""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def register_user(self, username, password):
        """Регистрирует нового пользователя."""
        if self.get_user(username):
            return False, "Пользователь с таким именем уже существует."
        
        password_hash = self._hash_password(password)
        try:
            self.cursor.execute(
                "INSERT INTO users (username, password_hash, status_emoji) VALUES (?, ?, ?)",
                (username, password_hash, '😀') # Статус по умолчанию
            )
            self.conn.commit()
            return True, "Регистрация прошла успешно."
        except sqlite3.IntegrityError:
            return False, "Ошибка при регистрации."

    def check_credentials(self, username, password):
        """Проверяет логин и пароль пользователя."""
        user = self.get_user(username)
        if user:
            password_hash = self._hash_password(password)
            if user[2] == password_hash:
                return True
        return False

    def get_user(self, username):
        """Получает данные пользователя по имени."""
        self.cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        return self.cursor.fetchone()

    def close(self):
        self.conn.close()

    def update_user_status(self, username, emoji):
        """Обновляет эмодзи-статус пользователя."""
        try:
            self.cursor.execute("UPDATE users SET status_emoji = ? WHERE username = ?", (emoji, username))
            self.conn.commit()
            return True
        except sqlite3.Error:
            return False

   def add_story(self, username, content_path):
       """Добавляет новую историю для пользователя."""
       user = self.get_user(username)
       if not user:
           return False, "Пользователь не найден."
       
       user_id = user[0]
       try:
           self.cursor.execute(
               "INSERT INTO stories (user_id, content_path) VALUES (?, ?)",
               (user_id, content_path)
           )
           self.conn.commit()
           return True, "История успешно добавлена."
       except sqlite3.Error as e:
           return False, f"Ошибка добавления истории: {e}"

   def get_active_stories(self):
       """Получает все активные истории (за последние 24 часа)."""
       self.cursor.execute("""
           SELECT u.username, s.content_path, s.created_at
           FROM stories s
           JOIN users u ON s.user_id = u.id
           WHERE s.created_at >= datetime('now', '-24 hours')
           ORDER BY s.created_at DESC
       """)
       return self.cursor.fetchall()

   def delete_expired_stories(self):
       """Удаляет истории старше 24 часов."""
       try:
           self.cursor.execute("DELETE FROM stories WHERE created_at < datetime('now', '-24 hours')")
           deleted_rows = self.cursor.rowcount
           self.conn.commit()
           return deleted_rows
       except sqlite3.Error:
           return 0
