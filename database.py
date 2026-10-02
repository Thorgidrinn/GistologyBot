import sqlite3
import json
from datetime import datetime
import logging
import hashlib
import os

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=None):
        # На Render путь можно вынести в переменную DATABASE_PATH и указать
        # его внутри Persistent Disk, например /var/data/users.db.
        self.db_path = db_path or os.environ.get('DATABASE_PATH', 'users.db')
        db_directory = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(db_directory, exist_ok=True)
        self.init_database()
    
    def get_connection(self):
        """Создание подключения к базе данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Инициализация базы данных и таблиц - упрощенная версия"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей (упрощенная, без токенов и рефералов)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица истории просмотров препаратов (для статистики)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drug_views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    drug_id INTEGER,
                    view_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица тестирования (для отслеживания прогресса)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    drug_id INTEGER,
                    correct BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Список пользователей, которым разрешён доступ к боту.
            # Администратор добавляется автоматически при каждом запуске,
            # поэтому его нельзя случайно потерять при создании новой БД.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_list (
                    user_id INTEGER PRIMARY KEY,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by INTEGER
                )
            ''')

            import config
            cursor.execute('''
                INSERT OR IGNORE INTO access_list (user_id, added_by)
                VALUES (?, ?)
            ''', (config.ADMIN_USER_ID, config.ADMIN_USER_ID))
            
            conn.commit()
            logger.info("База данных инициализирована (упрощенная версия)")
    
    def register_user(self, user_id, username, first_name, last_name):
        """Регистрация нового пользователя - упрощенная"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            existing_user = cursor.fetchone()
            
            if not existing_user:
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                
                conn.commit()
                logger.info(f"Зарегистрирован новый пользователь: {user_id}")
                return True
            else:
                cursor.execute('''
                    UPDATE users SET last_active = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (user_id,))
                conn.commit()
                return False
    
    def record_drug_view(self, user_id, drug_id, view_type):
        """Записать факт просмотра препарата"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO drug_views (user_id, drug_id, view_type)
                VALUES (?, ?, ?)
            ''', (user_id, drug_id, view_type))
            
            conn.commit()
    
    def record_test_result(self, user_id, drug_id, correct):
        """Записать результат тестирования"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO test_results (user_id, drug_id, correct)
                VALUES (?, ?, ?)
            ''', (user_id, drug_id, correct))
            
            conn.commit()
    
    def get_user_stats(self, user_id):
        """Получить статистику пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(DISTINCT drug_id) as studied_drugs
                FROM drug_views 
                WHERE user_id = ?
            ''', (user_id,))
            
            studied = cursor.fetchone()['studied_drugs'] if cursor.fetchone() else 0
            
            cursor.execute('''
                SELECT COUNT(*) as total_tests,
                       SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct_tests
                FROM test_results 
                WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            total_tests = result['total_tests'] if result else 0
            correct_tests = result['correct_tests'] if result else 0
            
            return {
                'studied_drugs': studied,
                'total_tests': total_tests,
                'correct_tests': correct_tests,
                'accuracy': (correct_tests / total_tests * 100) if total_tests > 0 else 0
            }
    
    def is_admin(self, user_id):
        """Проверить, является ли пользователь администратором"""
        import config
        return user_id == config.ADMIN_USER_ID

    def is_allowed(self, user_id):
        """Проверить, есть ли пользователь в списке доступа."""
        import config

        # Эти ID задаются в Render и не зависят от локального users.db.
        if user_id == config.ADMIN_USER_ID or user_id in config.ALLOWED_USER_IDS:
            return True

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT 1 FROM access_list WHERE user_id = ?',
                (user_id,)
            )
            return cursor.fetchone() is not None

    def add_to_access_list(self, user_id, added_by):
        """Добавить пользователя в список доступа.

        Возвращает True, если пользователь был добавлен впервые.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO access_list (user_id, added_by)
                VALUES (?, ?)
            ''', (user_id, added_by))
            conn.commit()
            return cursor.rowcount > 0

    def remove_from_access_list(self, user_id):
        """Удалить пользователя из списка доступа.

        Администратор защищён от удаления.
        """
        if self.is_admin(user_id):
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM access_list WHERE user_id = ?',
                (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_access_list(self):
        """Получить список разрешённых пользователей."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.user_id, a.added_at, a.added_by,
                       u.username, u.first_name, u.last_name
                FROM access_list a
                LEFT JOIN users u ON u.user_id = a.user_id
                ORDER BY a.added_at ASC, a.user_id ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_info(self, user_id):
        """Получить информацию о пользователе"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.*, 
                       (SELECT COUNT(*) FROM drug_views dv WHERE dv.user_id = u.user_id) as total_views,
                       (SELECT COUNT(*) FROM test_results tr WHERE tr.user_id = u.user_id) as total_tests
                FROM users u
                WHERE u.user_id = ?
            ''', (user_id,))
            
            user = cursor.fetchone()
            if user:
                return dict(user)
            return None
    
    def get_top_users(self, limit=10):
        """Получить топ пользователей по активности"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name,
                       (SELECT COUNT(*) FROM drug_views dv WHERE dv.user_id = u.user_id) as activity,
                       (SELECT COUNT(*) FROM test_results tr WHERE tr.user_id = u.user_id) as tests_count
                FROM users u
                ORDER BY activity DESC, tests_count DESC
                LIMIT ?
            ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_users(self):
        """Получить список всех пользователей"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, username, first_name, last_name, 
                       created_at, last_active
                FROM users
                ORDER BY last_active DESC
            ''')
            
            return [dict(row) for row in cursor.fetchall()]

# Глобальный экземпляр базы данных
db = Database()
