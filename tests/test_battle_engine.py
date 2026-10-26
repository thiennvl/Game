"""
Unit tests for battle_engine.py
"""

import unittest
from battle_engine import roll_team, simulate_battle


class TestBattleEngine(unittest.TestCase):
    def setUp(self):
        self.sample_heroes = [
            {"id": 1, "name": "Knight", "role": "Hiệp sĩ", "base_hp": 160, "base_atk": 24, "skill_name": "Iron Shield", "skill_description": "Giảm sát thương", "emoji": "🛡️"},
            {"id": 2, "name": "Mage", "role": "Pháp sư", "base_hp": 110, "base_atk": 38, "skill_name": "Arcane Burst", "skill_description": "Phép nổ", "emoji": "🔮"},
            {"id": 3, "name": "Assassin", "role": "Sát thủ", "base_hp": 115, "base_atk": 36, "skill_name": "Shadow Strike", "skill_description": "Chí mạng", "emoji": "🗡️"},
            {"id": 4, "name": "Archer", "role": "Cung thủ", "base_hp": 125, "base_atk": 32, "skill_name": "Double Shot", "skill_description": "Bắn đôi", "emoji": "🏹"},
            {"id": 5, "name": "Guardian", "role": "Hộ vệ", "base_hp": 180, "base_atk": 20, "skill_name": "Holy Barrier", "skill_description": "Phản đòn", "emoji": "🏰"},
            {"id": 6, "name": "Healer", "role": "Trị liệu", "base_hp": 120, "base_atk": 22, "skill_name": "Divine Grace", "skill_description": "Hồi máu", "emoji": "💚"},
        ]

    def test_roll_team_structure_and_no_duplicates(self):
        """Kiểm tra roll team trả về đúng 3 tướng không trùng lặp và chỉ số hợp lý."""
        team = roll_team(self.sample_heroes, variance=0.10)
        self.assertEqual(len(team), 3)

        # Kiểm tra không có tướng trùng lặp trong cùng 1 đội
        hero_ids = [h["id"] for h in team]
        self.assertEqual(len(hero_ids), len(set(hero_ids)))

        # Kiểm tra chỉ số dao động trong khoảng cho phép (+/- 10%)
        for h in team:
            base_hp = h["base_hp"]
            base_atk = h["base_atk"]
            self.assertTrue(0.85 * base_hp <= h["hp"] <= 1.15 * base_hp)
            self.assertTrue(0.85 * base_atk <= h["atk"] <= 1.15 * base_atk)

    def test_roll_team_insufficient_heroes(self):
        """Kiểm tra báo lỗi khi danh sách tướng không đủ 3."""
        with self.assertRaises(ValueError):
            roll_team(self.sample_heroes[:2])

    def test_simulate_battle_completes_and_structure(self):
        """Kiểm tra trận đấu kết thúc hợp lệ và cấu trúc dữ liệu trả về đầy đủ."""
        blue_team = roll_team(self.sample_heroes)
        red_team = roll_team(self.sample_heroes)

        result = simulate_battle(blue_team, red_team, max_rounds=25)

        # 1. Kiểm tra đội thắng hợp lệ
        self.assertIn(result["winner_team"], ["BLUE", "RED", "DRAW"])
        self.assertGreaterEqual(result["total_rounds"], 1)
        self.assertLessEqual(result["total_rounds"], 25)

        # 2. Kiểm tra số lượng người tham gia
        self.assertEqual(len(result["blue_participants"]), 3)
        self.assertEqual(len(result["red_participants"]), 3)

        # 3. Kiểm tra HP không bao giờ bị âm
        for p in result["blue_participants"] + result["red_participants"]:
            self.assertGreaterEqual(p["hp_end"], 0)
            self.assertGreaterEqual(p["damage_dealt"], 0)
            self.assertIn(p["is_winner"], [0, 1])

        # 4. Kiểm tra sự kiện
        self.assertGreater(len(result["events"]), 0)
        last_event = result["events"][-1]
        self.assertEqual(last_event["event_type"], "MATCH_END")

    def test_no_defeated_hero_acts(self):
        """Kiểm tra không có tướng đã bị hạ gục tiếp tục hành động ở các lượt sau."""
        blue_team = roll_team(self.sample_heroes)
        red_team = roll_team(self.sample_heroes)

        result = simulate_battle(blue_team, red_team)
        defeated_participants = set()

        for ev in result["events"]:
            actor_idx = ev.get("actor_idx")
            if ev["event_type"] == "DEFEAT":
                defeated_participants.add(ev.get("target_idx"))
            elif ev["event_type"] in ["ATTACK", "CRITICAL", "SKILL", "HEAL"]:
                # Tướng hành động không được nằm trong danh sách đã bị hạ gục
                self.assertNotIn(actor_idx, defeated_participants, f"Tướng {actor_idx} đã chết nhưng vẫn hành động!")


if __name__ == "__main__":
    unittest.main()
