import datetime
import sqlite3
from typing import Dict, Optional, Tuple, List

from config import MAX_DAILY_ROLLS


class Database:
    def __init__(self, db_name: str = "chronoroom_bot.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                photo_id TEXT,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                daily_rolls_left INTEGER DEFAULT {int(MAX_DAILY_ROLLS)},
                last_roll_date DATE,
                is_banned INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                is_active INTEGER DEFAULT 1,
                name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                question1_id INTEGER,
                answer1 TEXT,
                question2_id INTEGER,
                answer2 TEXT,
                question3_id INTEGER,
                answer3 TEXT,
                question4_id INTEGER,
                answer4 TEXT,
                question5_id INTEGER,
                answer5 TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        self.conn.commit()

    def add_user(self, user_id: int, username: Optional[str], full_name: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        ''', (user_id, username, full_name))
        self.conn.commit()

    def update_user_photo(self, user_id: int, photo_id: Optional[str]):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET photo_id = ? WHERE user_id = ?
        ''', (photo_id, user_id))
        self.conn.commit()

    def create_profile(self, user_id: int, name: str,
                       questions_ids: List[int], answers: List[str]):
        cursor = self.conn.cursor()

        cursor.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))

        cursor.execute('''
            INSERT INTO profiles
            (user_id, name, question1_id, answer1, question2_id, answer2,
             question3_id, answer3, question4_id, answer4, question5_id, answer5)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name,
              questions_ids[0], answers[0],
              questions_ids[1], answers[1],
              questions_ids[2], answers[2],
              questions_ids[3], answers[3],
              questions_ids[4], answers[4]))

        self.conn.commit()

    def get_profile(self, user_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.*, u.photo_id, u.username
            FROM profiles p
            LEFT JOIN users u ON p.user_id = u.user_id
            WHERE p.user_id = ? AND p.is_active = 1
        ''', (user_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return dict(row)

    def get_random_profile(self, exclude_user_id: int) -> Optional[Dict]:
        """Get a random active profile, excluding the specified user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.*, u.photo_id, u.username
            FROM profiles p
            LEFT JOIN users u ON p.user_id = u.user_id
            WHERE p.user_id != ? AND p.is_active = 1 AND COALESCE(u.is_banned, 0) = 0
            ORDER BY RANDOM()
            LIMIT 1
        ''', (exclude_user_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return dict(row)

    def deactivate_profile(self, user_id: int):
        """Deactivate a profile (when the bot is blocked)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE profiles SET is_active = 0 WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()

    def can_roll_today(self, user_id: int) -> Tuple[bool, int]:
        """Check whether the user can roll the dice today"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT daily_rolls_left, last_roll_date
            FROM users WHERE user_id = ?
        ''', (user_id,))

        row = cursor.fetchone()
        if not row:
            return False, 0

        rolls_left = row['daily_rolls_left']
        last_date = row['last_roll_date']
        today = datetime.date.today().isoformat()

        if last_date != today:
            rolls_left = MAX_DAILY_ROLLS
            cursor.execute('''
                UPDATE users SET daily_rolls_left = ?, last_roll_date = ?
                WHERE user_id = ?
            ''', (rolls_left, today, user_id))
            self.conn.commit()

        return rolls_left > 0, rolls_left

    def use_roll(self, user_id: int) -> bool:
        """Use one roll"""
        cursor = self.conn.cursor()
        today = datetime.date.today().isoformat()
        cursor.execute('''
            UPDATE users
            SET daily_rolls_left = daily_rolls_left - 1,
                last_roll_date = ?
            WHERE user_id = ? AND daily_rolls_left > 0
        ''', (today, user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def refund_roll(self, user_id: int):
        """Refund a roll (if the profile is unavailable)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users
            SET daily_rolls_left = MIN(daily_rolls_left + 1, ?)
            WHERE user_id = ?
        ''', (MAX_DAILY_ROLLS, user_id))
        self.conn.commit()

    def close(self):
        self.conn.close()
