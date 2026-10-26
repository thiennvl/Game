"""
Equipment Service: Handles player inventory, equipment equipping/unequipping,
and weapon enhancement (+1 to +5) inspired by Free Fire weapon stats.
"""

from typing import Dict, Any, List, Optional
from database import get_db_connection


UPGRADE_REQUIREMENTS = {
    0: {"gold": 120, "stones": 1, "crystals": 0},
    1: {"gold": 220, "stones": 1, "crystals": 0},
    2: {"gold": 360, "stones": 2, "crystals": 0},
    3: {"gold": 550, "stones": 2, "crystals": 1},
    4: {"gold": 800, "stones": 3, "crystals": 2}
}


def get_player_inventory(player_id: int = 1, slot_type: Optional[str] = None, rarity: Optional[str] = None, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả trang bị trong kho của người chơi kèm chỉ số thực tế sau cường hóa."""
    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT ii.id as inventory_id, ii.player_id, ii.upgrade_level, ii.is_equipped,
                   ii.equipped_hero_id, ii.equipped_slot, ii.created_at as acquired_at,
                   ec.id as catalog_id, ec.name, ec.slot_type, ec.rarity,
                   ec.bonus_atk, ec.bonus_def, ec.bonus_hp, ec.bonus_speed,
                   ec.bonus_accuracy, ec.bonus_crit_rate, ec.bonus_crit_damage,
                   ec.armor_penetration, ec.element_bonus, ec.price, ec.max_upgrade_level,
                   ec.icon, ec.description,
                   h.name as equipped_hero_name, h.emoji as equipped_hero_emoji
            FROM inventory_items ii
            JOIN equipment_catalog ec ON ii.equipment_id = ec.id
            LEFT JOIN heroes h ON ii.equipped_hero_id = h.id
            WHERE ii.player_id = ?
        """
        params = [player_id]

        if slot_type:
            query += " AND ec.slot_type = ?"
            params.append(slot_type)
        if rarity:
            query += " AND ec.rarity = ?"
            params.append(rarity)

        query += " ORDER BY ii.is_equipped DESC, ec.rarity DESC, ii.id DESC;"

        cur = conn.execute(query, params)
        items = []
        for row in cur.fetchall():
            it = dict(row)
            up_lvl = it["upgrade_level"]
            mult = 1.0 + (0.15 * up_lvl)

            # Tính toán chỉ số hiện tại sau cường hóa
            it["current_atk"] = int(round(it["bonus_atk"] * mult))
            it["current_def"] = int(round(it["bonus_def"] * mult))
            it["current_hp"] = int(round(it["bonus_hp"] * mult))
            it["current_speed"] = int(round(it["bonus_speed"] * mult))
            it["current_accuracy"] = round(it["bonus_accuracy"] * mult, 1)
            it["current_crit_rate"] = round(it["bonus_crit_rate"] * mult, 1)
            it["current_crit_damage"] = round(it["bonus_crit_damage"] * mult, 1)
            it["current_armor_penetration"] = int(round(it["armor_penetration"] * mult))
            it["current_element_bonus"] = round(it["element_bonus"] * mult, 1)

            # Chi phí nâng cấp tiếp theo nếu chưa max
            if up_lvl < it["max_upgrade_level"]:
                it["upgrade_cost"] = UPGRADE_REQUIREMENTS.get(up_lvl, {"gold": 1000, "stones": 3, "crystals": 3})
            else:
                it["upgrade_cost"] = None

            items.append(it)

        return items
    finally:
        conn.close()


def equip_item(player_id: int, inventory_id: int, hero_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Trang bị một món đồ cho một tướng:
    - Kiểm tra vật phẩm thuộc về người chơi
    - Khớp đúng slot (WEAPON, ARMOR, BOOTS, ACCESSORY)
    - Nếu món đồ đang được tướng khác mặc, tự động gỡ khỏi tướng đó
    - Nếu slot của tướng đích đang có đồ, tự động gỡ món cũ
    - Toàn bộ thực hiện an toàn trong một transaction
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            # 1. Kiểm tra vật phẩm
            cur = conn.execute("""
                SELECT ii.*, ec.slot_type, ec.name as item_name
                FROM inventory_items ii
                JOIN equipment_catalog ec ON ii.equipment_id = ec.id
                WHERE ii.id = ? AND ii.player_id = ?;
            """, (inventory_id, player_id))
            item = cur.fetchone()
            if not item:
                return {"success": False, "error": "Vật phẩm không tồn tại trong kho"}

            slot_type = item["slot_type"]

            # 2. Kiểm tra tướng có tồn tại không
            h_check = conn.execute("SELECT id, name FROM heroes WHERE id = ?;", (hero_id,)).fetchone()
            if not h_check:
                return {"success": False, "error": "Tướng không tồn tại"}

            # 3. Gỡ món đồ đang ở cùng slot của tướng này (nếu có)
            conn.execute("""
                UPDATE inventory_items
                SET is_equipped = 0, equipped_hero_id = NULL, equipped_slot = NULL
                WHERE player_id = ? AND equipped_hero_id = ? AND equipped_slot = ?;
            """, (player_id, hero_id, slot_type))

            # 4. Trang bị món mới vào slot
            conn.execute("""
                UPDATE inventory_items
                SET is_equipped = 1, equipped_hero_id = ?, equipped_slot = ?
                WHERE id = ?;
            """, (hero_id, slot_type, inventory_id))

            return {
                "success": True,
                "message": f"Đã trang bị {item['item_name']} cho {h_check['name']} ({slot_type})!",
                "slot_type": slot_type,
                "hero_id": hero_id
            }
    finally:
        conn.close()


def unequip_item(player_id: int, inventory_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Gỡ trang bị khỏi tướng và đưa về trạng thái tự do trong kho đồ."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            cur = conn.execute("""
                SELECT ii.*, ec.name as item_name
                FROM inventory_items ii
                JOIN equipment_catalog ec ON ii.equipment_id = ec.id
                WHERE ii.id = ? AND ii.player_id = ?;
            """, (inventory_id, player_id))
            item = cur.fetchone()
            if not item:
                return {"success": False, "error": "Vật phẩm không tồn tại trong kho"}

            conn.execute("""
                UPDATE inventory_items
                SET is_equipped = 0, equipped_hero_id = NULL, equipped_slot = NULL
                WHERE id = ?;
            """, (inventory_id,))

            return {
                "success": True,
                "message": f"Đã tháo {item['item_name']} về kho đồ!"
            }
    finally:
        conn.close()


def upgrade_equipment(player_id: int, inventory_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Cường hóa trang bị từ cấp 0 lên tối đa cấp 5.
    Mỗi cấp tăng 15% tất cả chỉ số gốc của trang bị.
    Yêu cầu Gold và Đá cường hóa (hoặc Tinh thể nguyên tố ở cấp cao).
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            # 1. Lấy thông tin trang bị
            cur = conn.execute("""
                SELECT ii.*, ec.name as item_name, ec.max_upgrade_level,
                       ec.bonus_atk, ec.bonus_def, ec.bonus_hp, ec.bonus_speed
                FROM inventory_items ii
                JOIN equipment_catalog ec ON ii.equipment_id = ec.id
                WHERE ii.id = ? AND ii.player_id = ?;
            """, (inventory_id, player_id))
            item = cur.fetchone()
            if not item:
                return {"success": False, "error": "Vật phẩm không tồn tại"}

            curr_lvl = item["upgrade_level"]
            max_lvl = item["max_upgrade_level"]
            if curr_lvl >= max_lvl:
                return {"success": False, "error": f"Trang bị đã đạt cấp cường hóa tối đa (+{max_lvl})!"}

            cost_info = UPGRADE_REQUIREMENTS.get(curr_lvl)
            if not cost_info:
                return {"success": False, "error": "Không có thông tin chi phí nâng cấp"}

            gold_req = cost_info["gold"]
            stones_req = cost_info["stones"]
            crystals_req = cost_info["crystals"]

            # 2. Kiểm tra Gold
            prof = conn.execute("SELECT gold FROM player_profile WHERE id = ?;", (player_id,)).fetchone()
            if not prof or prof["gold"] < gold_req:
                return {"success": False, "error": f"Không đủ Gold! Cần {gold_req} Gold (Hiện có: {prof['gold'] if prof else 0})."}

            # 3. Kiểm tra Nguyên liệu
            mat_cur = conn.execute("SELECT material_type, quantity FROM player_materials WHERE player_id = ?;", (player_id,))
            mats = {r["material_type"]: r["quantity"] for r in mat_cur.fetchall()}

            stones_have = mats.get("UPGRADE_STONE", 0)
            crystals_have = mats.get("ELEMENT_CRYSTAL", 0)

            if stones_have < stones_req:
                return {"success": False, "error": f"Thiếu Đá Cường Hóa! Cần {stones_req} viên (Hiện có: {stones_have})."}
            if crystals_have < crystals_req:
                return {"success": False, "error": f"Thiếu Tinh Thể Nguyên Tố! Cần {crystals_req} viên (Hiện có: {crystals_have})."}

            # 4. Khấu trừ Gold & Nguyên liệu
            new_gold = prof["gold"] - gold_req
            conn.execute("UPDATE player_profile SET gold = ? WHERE id = ?;", (new_gold, player_id))

            conn.execute("""
                UPDATE player_materials 
                SET quantity = quantity - ? 
                WHERE player_id = ? AND material_type = 'UPGRADE_STONE';
            """, (stones_req, player_id))

            if crystals_req > 0:
                conn.execute("""
                    UPDATE player_materials 
                    SET quantity = quantity - ? 
                    WHERE player_id = ? AND material_type = 'ELEMENT_CRYSTAL';
                """, (crystals_req, player_id))

            # 5. Tăng cấp trang bị
            new_lvl = curr_lvl + 1
            conn.execute("UPDATE inventory_items SET upgrade_level = ? WHERE id = ?;", (new_lvl, inventory_id))

            # 6. Ghi nhật ký tài chính và lịch sử cường hóa
            conn.execute("""
                INSERT INTO currency_transactions (player_id, amount, balance_after, reason, reference_id)
                VALUES (?, ?, ?, 'EQUIPMENT_UPGRADE', ?);
            """, (player_id, -gold_req, new_gold, inventory_id))

            conn.execute("""
                INSERT INTO upgrade_history (inventory_item_id, equipment_name, level_before, level_after, gold_cost, materials_cost)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (inventory_id, item["item_name"], curr_lvl, new_lvl, gold_req, stones_req + crystals_req))

            return {
                "success": True,
                "message": f"🎉 Cường hóa thành công {item['item_name']} lên +{new_lvl} (+{new_lvl * 15}% chỉ số)!",
                "new_level": new_lvl,
                "remaining_gold": new_gold,
                "inventory_id": inventory_id
            }
    finally:
        conn.close()
