"""
Unit tests for database.py and analytics.py
"""

import os
import tempfile
import unittest
from database import init_db, get_all_heroes, save_battle_result, get_db_connection
from battle_engine import roll_team, simulate_battle
from analytics import (
    get_overview_stats,
    get_hero_analytics,
    get_composition_analytics,
    get_recent_matches,
    get_match_detail,
)


class TestDatabaseAndAnalytics(unittest.TestCase):
    def setUp(self):
        # Tạo file database tạm thời cho test để không ảnh hưởng dữ liệu thật
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        init_db(self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_database_initialization_and_heroes(self):
        """Kiểm tra khởi tạo database và danh sách tướng mẫu không bị nhân bản."""
        heroes = get_all_heroes(self.temp_db_path)
        self.assertGreaterEqual(len(heroes), 6)

        # Chạy lại init_db xem có bị duplicate không
        init_db(self.temp_db_path)
        heroes_again = get_all_heroes(self.temp_db_path)
        self.assertEqual(len(heroes), len(heroes_again))

    def test_empty_analytics_safe_division(self):
        """Kiểm tra Analytics khi chưa có trận đấu nào: không bị lỗi chia cho 0."""
        overview = get_overview_stats(self.temp_db_path)
        self.assertEqual(overview["total_matches"], 0)
        self.assertEqual(overview["player_wins"], 0)
        self.assertEqual(overview["player_win_rate"], 0.0)
        self.assertIsNone(overview["most_picked_hero"])
        self.assertIsNone(overview["highest_winrate_hero"])

        hero_stats = get_hero_analytics(self.temp_db_path)
        for h in hero_stats:
            self.assertEqual(h["total_picks"], 0)
            self.assertEqual(h["win_rate"], 0.0)
            self.assertEqual(h["avg_damage"], 0.0)

        comps = get_composition_analytics(db_path=self.temp_db_path)
        self.assertEqual(len(comps), 0)

    def test_save_battle_and_analytics_calculation(self):
        """Mô phỏng trận đấu, lưu vào SQLite và kiểm tra tính toán Analytics qua SQL."""
        heroes = get_all_heroes(self.temp_db_path)
        blue_team = roll_team(heroes)
        red_team = roll_team(heroes)

        result = simulate_battle(blue_team, red_team)
        match_id = save_battle_result(result, self.temp_db_path)
        self.assertIsInstance(match_id, int)
        self.assertGreater(match_id, 0)

        # Kiểm tra bảng matches
        overview = get_overview_stats(self.temp_db_path)
        self.assertEqual(overview["total_matches"], 1)

        # Kiểm tra chi tiết trận đấu
        detail = get_match_detail(match_id, self.temp_db_path)
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail["blue_participants"]), 3)
        self.assertEqual(len(detail["red_participants"]), 3)
        self.assertGreater(len(detail["events"]), 0)

        # Kiểm tra hero analytics
        hero_stats = get_hero_analytics(self.temp_db_path)
        active_picks = [h for h in hero_stats if h["total_picks"] > 0]
        self.assertGreater(len(active_picks), 0)

        # Kiểm tra team composition analytics
        comps = get_composition_analytics(db_path=self.temp_db_path)
        self.assertGreater(len(comps), 0)

    def test_composition_order_independence(self):
        """
        Kiểm tra tính chuẩn hóa của đội hình:
        2 trận đấu có cùng 3 tướng nhưng khác thứ tự slot phải được nhóm thành 1 đội hình duy nhất.
        """
        heroes = get_all_heroes(self.temp_db_path)
        h1, h2, h3 = heroes[0], heroes[1], heroes[2]
        dummy_red = [heroes[3], heroes[4], heroes[5]]

        # Trận 1: Blue slot [h1, h2, h3]
        blue_order_1 = [
            {"id": h1["id"], "name": h1["name"], "role": h1["role"], "hp": 150, "atk": 25, "emoji": h1["emoji"], "base_hp": 150, "base_atk": 25, "skill_name": "S1", "skill_description": ""},
            {"id": h2["id"], "name": h2["name"], "role": h2["role"], "hp": 150, "atk": 25, "emoji": h2["emoji"], "base_hp": 150, "base_atk": 25, "skill_name": "S2", "skill_description": ""},
            {"id": h3["id"], "name": h3["name"], "role": h3["role"], "hp": 150, "atk": 25, "emoji": h3["emoji"], "base_hp": 150, "base_atk": 25, "skill_name": "S3", "skill_description": ""}
        ]
        res1 = simulate_battle(blue_order_1, roll_team(dummy_red))
        save_battle_result(res1, self.temp_db_path)

        # Trận 2: Blue slot đảo ngược [h3, h1, h2]
        blue_order_2 = [
            {"id": h3["id"], "name": h3["name"], "role": h3["role"], "hp": 150, "atk": 25, "emoji": h3["emoji"], "base_hp": 150, "base_atk": 25, "skill_name": "S3", "skill_description": ""},
            {"id": h1["id"], "name": h1["name"], "role": h1["role"], "hp": 150, "atk": 25, "emoji": h1["emoji"], "base_hp": 150, "base_atk": 25, "skill_name": "S1", "skill_description": ""},
            {"id": h2["id"], "name": h2["name"], "role": h2["role"], "hp": 150, "atk": 25, "emoji": h2["emoji"], "base_hp": 150, "base_atk": 25, "skill_name": "S2", "skill_description": ""}
        ]
        res2 = simulate_battle(blue_order_2, roll_team(dummy_red))
        save_battle_result(res2, self.temp_db_path)

        comps = get_composition_analytics(db_path=self.temp_db_path)
        # Tìm comp của h1, h2, h3
        sorted_names = sorted([h1["name"], h2["name"], h3["name"]])
        expected_comp_name = " + ".join(sorted_names)

        target_comp = next((c for c in comps if c["comp_name"] == expected_comp_name), None)
        self.assertIsNotNone(target_comp, f"Không tìm thấy đội hình chuẩn hóa {expected_comp_name}")
        self.assertEqual(target_comp["total_matches"], 2, "Đội hình đảo slot phải được gộp thành 2 lần xuất hiện!")


if __name__ == "__main__":
    unittest.main()
