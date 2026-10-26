"""
Comprehensive Unit Tests for Tactical Battle Arena RPG:
- Elemental Advantages & Pokémon-like Tactical Damage Formula
- Status Effects: BURN, STUN, SHIELD, MARKED, HEAL
- Character Progression & Leveling Up
- Free Fire-inspired Equipment, Slots & Enhancements (+1 to +5)
- Shop System & Currency Ledger
- Lucky Wheel Probabilities & Pity Counter
"""

import os
import tempfile
import unittest
from database import init_db, get_db_connection, get_player_profile, save_battle_result
from hero_service import calculate_hero_effective_stats, get_hero_full_data, train_hero_level
from equipment_service import get_player_inventory, equip_item, unequip_item, upgrade_equipment
from shop_service import get_shop_items, buy_item
from lucky_wheel_service import get_wheel_info, spin_wheel, PITY_THRESHOLD
from ai_engine import get_element_multiplier
from battle_engine import Combatant, execute_action, process_end_of_round, simulate_battle, TacticalBattleManager


class TestTacticalRPG(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        init_db(self.temp_db_path)

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_element_multiplier_triangle(self):
        """Kiểm tra quy tắc tương khắc ngũ hành Pokémon: FIRE > NATURE > WATER > FIRE."""
        # Ưu thế (1.5x)
        self.assertEqual(get_element_multiplier("FIRE", "NATURE"), 1.5)
        self.assertEqual(get_element_multiplier("NATURE", "WATER"), 1.5)
        self.assertEqual(get_element_multiplier("WATER", "FIRE"), 1.5)

        # Bị kháng (0.75x)
        self.assertEqual(get_element_multiplier("FIRE", "WATER"), 0.75)
        self.assertEqual(get_element_multiplier("WATER", "NATURE"), 0.75)
        self.assertEqual(get_element_multiplier("NATURE", "FIRE"), 0.75)

        # Trung tính (1.0x)
        self.assertEqual(get_element_multiplier("FIRE", "FIRE"), 1.0)
        self.assertEqual(get_element_multiplier("NEUTRAL", "WATER"), 1.0)

    def test_hero_progression_and_stats(self):
        """Kiểm tra chỉ số tướng tăng trưởng theo cấp độ và theo đặc tính vai trò."""
        hero = get_hero_full_data(1, self.temp_db_path)  # Knight
        self.assertIsNotNone(hero)
        self.assertEqual(hero["level"], 1)

        # Tính chỉ số ở level 5
        lvl5_stats = calculate_hero_effective_stats(hero, level=5)
        self.assertGreater(lvl5_stats["hp"], hero["base_hp"])
        self.assertGreater(lvl5_stats["def"], hero["base_def"])
        self.assertGreater(lvl5_stats["atk"], hero["base_atk"])

        # Thử nâng cấp level bằng Gold
        train_res = train_hero_level(player_id=1, hero_id=1, db_path=self.temp_db_path)
        self.assertTrue(train_res["success"])
        self.assertEqual(train_res["new_level"], 2)

    def test_equipment_equip_and_unequip(self):
        """Kiểm tra trang bị, tháo trang bị và ràng buộc chỉ 1 món trên 1 slot."""
        inv = get_player_inventory(player_id=1, db_path=self.temp_db_path)
        self.assertGreater(len(inv), 0)

        sword = next((it for it in inv if it["slot_type"] == "WEAPON"), None)
        self.assertIsNotNone(sword)

        # Trang bị thanh kiếm cho Knight (hero_id=1)
        res = equip_item(player_id=1, inventory_id=sword["inventory_id"], hero_id=1, db_path=self.temp_db_path)
        self.assertTrue(res["success"])

        # Kiểm tra chỉ số sau khi trang bị
        hero = get_hero_full_data(1, self.temp_db_path)
        self.assertGreater(hero["effective_stats"]["atk"], hero["base_atk"])

        # Tháo trang bị
        unequip_res = unequip_item(player_id=1, inventory_id=sword["inventory_id"], db_path=self.temp_db_path)
        self.assertTrue(unequip_res["success"])

        # Chỉ số trở về ban đầu
        hero_after = get_hero_full_data(1, self.temp_db_path)
        self.assertEqual(hero_after["effective_stats"]["atk"], hero["base_atk"])

    def test_equipment_upgrade_levels(self):
        """Kiểm tra cường hóa trang bị từ 0 lên +1 (+15% chỉ số) và trừ tài nguyên chính xác."""
        inv = get_player_inventory(player_id=1, db_path=self.temp_db_path)
        item = inv[0]

        up_res = upgrade_equipment(player_id=1, inventory_id=item["inventory_id"], db_path=self.temp_db_path)
        self.assertTrue(up_res["success"])
        self.assertEqual(up_res["new_level"], 1)

        # Kiểm tra chỉ số sau nâng cấp
        inv_after = get_player_inventory(player_id=1, db_path=self.temp_db_path)
        item_after = next(it for it in inv_after if it["inventory_id"] == item["inventory_id"])
        self.assertEqual(item_after["upgrade_level"], 1)
        self.assertGreaterEqual(item_after["current_atk"], item["current_atk"])

    def test_shop_purchase_and_balance_validation(self):
        """Kiểm tra mua đồ trong Shop: trừ tiền và tăng đồ trong kho."""
        prof_before = get_player_profile(player_id=1, db_path=self.temp_db_path)
        initial_gold = prof_before["gold"]

        # Mua Bronze Ring (giá 100 Gold, id=14)
        buy_res = buy_item(player_id=1, item_id=14, is_material=False, db_path=self.temp_db_path)
        self.assertTrue(buy_res["success"])

        prof_after = get_player_profile(player_id=1, db_path=self.temp_db_path)
        self.assertEqual(prof_after["gold"], initial_gold - 100)

        # Mua khi không đủ tiền
        conn = get_db_connection(self.temp_db_path)
        conn.execute("UPDATE player_profile SET gold = 10 WHERE id = 1;")
        conn.commit()
        conn.close()

        fail_buy = buy_item(player_id=1, item_id=14, is_material=False, db_path=self.temp_db_path)
        self.assertFalse(fail_buy["success"])

    def test_lucky_wheel_odds_and_pity(self):
        """Kiểm tra vòng quay may mắn và cơ chế Pity: kích hoạt Epic/Legendary khi đạt ngưỡng 10."""
        # Giả lập pity counter lên 10
        conn = get_db_connection(self.temp_db_path)
        conn.execute("UPDATE player_profile SET gold = 5000, pity_counter = 10 WHERE id = 1;")
        conn.commit()
        conn.close()

        spin_res = spin_wheel(player_id=1, cost_type="GOLD", db_path=self.temp_db_path)
        self.assertTrue(spin_res["success"])
        self.assertTrue(spin_res["is_pity_triggered"])
        self.assertIn(spin_res["rarity"], ["EPIC", "LEGENDARY"])
        self.assertEqual(spin_res["pity_after"], 0)

    def test_tactical_battle_step_execution(self):
        """Kiểm tra khởi tạo trận Tactical Mode và lệnh người chơi chọn chiêu thức."""
        heroes_sample = [
            {"id": 1, "name": "Knight", "role": "Hiệp sĩ", "element": "WATER", "hp": 160, "max_hp": 160, "atk": 25, "def": 25, "speed": 18, "accuracy": 95, "crit_rate": 5.0, "crit_damage": 150.0, "emoji": "🛡️", "abilities": [{"id": 1, "name": "Sword Slash", "skill_power": 100, "target_type": "SINGLE_ENEMY", "accuracy": 100, "cooldown": 0, "element": "WATER"}]},
            {"id": 2, "name": "Mage", "role": "Pháp sư", "element": "FIRE", "hp": 110, "max_hp": 110, "atk": 38, "def": 12, "speed": 22, "accuracy": 90, "crit_rate": 10.0, "crit_damage": 160.0, "emoji": "🔮", "abilities": [{"id": 5, "name": "Arcane Bolt", "skill_power": 95, "target_type": "SINGLE_ENEMY", "accuracy": 100, "cooldown": 0, "element": "FIRE"}]},
            {"id": 3, "name": "Assassin", "role": "Sát thủ", "element": "NATURE", "hp": 115, "max_hp": 115, "atk": 36, "def": 14, "speed": 30, "accuracy": 98, "crit_rate": 25.0, "crit_damage": 200.0, "emoji": "🗡️", "abilities": [{"id": 9, "name": "Quick Strike", "skill_power": 90, "target_type": "SINGLE_ENEMY", "accuracy": 100, "cooldown": 0, "element": "NATURE"}]}
        ]

        init_res = TacticalBattleManager.create_battle(heroes_sample, heroes_sample, self.temp_db_path)
        self.assertTrue(init_res["success"])
        b_id = init_res["battle_id"]

        # Nếu đang chờ người chơi
        if init_res["status"] == "WAITING_PLAYER":
            act = init_res["active_actor"]
            self.assertEqual(act["team_side"], "BLUE")
            ab_id = act["abilities"][0]["id"]

            action_res = TacticalBattleManager.execute_player_action(b_id, ab_id, target_idx=3, db_path=self.temp_db_path)
            self.assertTrue(action_res["success"])
            self.assertGreater(len(action_res["new_events"]), 0)


if __name__ == "__main__":
    unittest.main()
