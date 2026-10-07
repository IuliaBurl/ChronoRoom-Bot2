import unittest

from config import MAX_DAILY_ROLLS
from database import Database


def add_profiled_user(db, user_id, username="user", name="Name"):
    db.add_user(user_id, username, f"Full {user_id}")
    db.create_profile(user_id, name, [1, 2, 3, 4, 5], ["a", "b", "c", "d", "e"])


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def tearDown(self):
        self.db.close()

    def test_add_user_upserts_username(self):
        self.db.add_user(1, "old", "Name")
        self.db.add_user(1, "new", "Name")
        row = self.db.conn.execute("SELECT username FROM users WHERE user_id = 1").fetchone()
        self.assertEqual(row["username"], "new")

    def test_create_profile_replaces_previous(self):
        add_profiled_user(self.db, 1, name="First")
        add_profiled_user(self.db, 1, name="Second")
        self.assertEqual(self.db.get_profile(1)["name"], "Second")
        count = self.db.conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        self.assertEqual(count, 1)

    def test_photo_and_username_are_joined_into_profile(self):
        add_profiled_user(self.db, 1, username="alice")
        self.db.update_user_photo(1, "photo123")
        profile = self.db.get_profile(1)
        self.assertEqual(profile["photo_id"], "photo123")
        self.assertEqual(profile["username"], "alice")

    def test_random_profile_excludes_self_inactive_and_banned(self):
        for uid in (1, 2, 3, 4):
            add_profiled_user(self.db, uid)
        self.db.deactivate_profile(2)
        self.db.conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = 3")
        self.db.conn.commit()
        for _ in range(30):
            self.assertEqual(self.db.get_random_profile(exclude_user_id=1)["user_id"], 4)

    def test_random_profile_none_when_alone(self):
        add_profiled_user(self.db, 1)
        self.assertIsNone(self.db.get_random_profile(exclude_user_id=1))

    def test_daily_rolls_run_out_and_refund_is_capped(self):
        self.db.add_user(1, "u", "U")
        can, left = self.db.can_roll_today(1)
        self.assertTrue(can)
        self.assertEqual(left, MAX_DAILY_ROLLS)

        for _ in range(MAX_DAILY_ROLLS):
            self.assertTrue(self.db.use_roll(1))
        self.assertFalse(self.db.use_roll(1))
        self.assertFalse(self.db.can_roll_today(1)[0])

        self.db.refund_roll(1)
        self.assertEqual(self.db.can_roll_today(1), (True, 1))

        for _ in range(10):
            self.db.refund_roll(1)
        self.assertEqual(self.db.can_roll_today(1)[1], MAX_DAILY_ROLLS)

    def test_unknown_user_cannot_roll(self):
        self.assertEqual(self.db.can_roll_today(999), (False, 0))

    def test_sql_injection_in_username_is_stored_literally(self):
        evil = "x'); DROP TABLE users;--"
        self.db.add_user(1, evil, evil)
        row = self.db.conn.execute("SELECT username FROM users WHERE user_id = 1").fetchone()
        self.assertEqual(row["username"], evil)

    def test_dead_matches_table_is_gone(self):
        tables = {r[0] for r in self.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables - {"sqlite_sequence"}, {"users", "profiles"})


if __name__ == "__main__":
    unittest.main()
