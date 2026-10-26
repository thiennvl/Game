"""
Hero Service: Handles hero stat calculation, progression, XP, and leveling.
"""

from typing import Dict, Any, List, Optional
from database import get_db_connection, get_hero_by_id


ROLE_GROWTH = {
    "Hiệp sĩ": {"hp": 16, "def": 3, "atk": 2, "speed": 1, "crit": 0.2, "acc": 0.1},
    "Pháp sư": {"hp": 8, "def": 1, "atk": 5, "speed": 2, "crit": 0.3, "acc": 0.2},
    "Sát thủ": {"hp": 10, "def": 1, "atk": 4, "speed": 3, "crit": 0.6, "acc": 0.3},
    "Cung thủ": {"hp": 11, "def": 2, "atk": 4, "speed": 2, "crit": 0.4, "acc": 0.4},
    "Hộ vệ": {"hp": 22, "def": 4, "atk": 1, "speed": 1, "crit": 0.1, "acc": 0.1},
    "Trị liệu": {"hp": 12, "def": 2, "atk": 3, "speed": 2, "crit": 0.1, "acc": 0.2},
    "Cuồng chiến": {"hp": 15, "def": 2, "atk": 4, "speed": 2, "crit": 0.4, "acc": 0.2},
    "Hỏa pháp sư": {"hp": 8, "def": 1, "atk": 5, "speed": 2, "crit": 0.3, "acc": 0.2}
}


def calculate_hero_effective_stats(base_hero: Dict[str, Any], level: int = 1, equipped_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Tính toán chỉ số chiến đấu cuối cùng của tướng:
    Chỉ số cuối = Chỉ số gốc + (Level - 1) * Tăng trưởng theo vai trò + Tổng chỉ số từ trang bị (+15%/cấp cường hóa)
    """
    role = base_hero.get("role", "Hiệp sĩ")
    growth = ROLE_GROWTH.get(role, {"hp": 12, "def": 2, "atk": 3, "speed": 2, "crit": 0.2, "acc": 0.2})
    lvl_factor = max(0, level - 1)

    # 1. Chỉ số từ Level
    hp = base_hero["base_hp"] + lvl_factor * growth["hp"]
    atk = base_hero["base_atk"] + lvl_factor * growth["atk"]
    defense = base_hero.get("base_def", 15) + lvl_factor * growth["def"]
    speed = base_hero.get("base_speed", 20) + lvl_factor * growth["speed"]
    accuracy = base_hero.get("base_accuracy", 95) + lvl_factor * growth["acc"]
    crit_rate = base_hero.get("base_crit_rate", 5.0) + lvl_factor * growth["crit"]
    crit_damage = base_hero.get("base_crit_damage", 150.0)
    armor_pen = 0
    element_bonus = 0.0

    # 2. Cộng dồn từ các trang bị đang mặc
    items = equipped_items or []
    for it in items:
        up_lvl = it.get("upgrade_level", 0)
        mult = 1.0 + (0.15 * up_lvl)

        hp += int(round(it.get("bonus_hp", 0) * mult))
        atk += int(round(it.get("bonus_atk", 0) * mult))
        defense += int(round(it.get("bonus_def", 0) * mult))
        speed += int(round(it.get("bonus_speed", 0) * mult))
        accuracy += round(it.get("bonus_accuracy", 0) * mult, 1)
        crit_rate += round(it.get("bonus_crit_rate", 0) * mult, 1)
        crit_damage += round(it.get("bonus_crit_damage", 0) * mult, 1)
        armor_pen += int(round(it.get("armor_penetration", 0) * mult))
        element_bonus += round(it.get("element_bonus", 0) * mult, 1)

    return {
        "hero_id": base_hero["id"],
        "name": base_hero["name"],
        "role": base_hero["role"],
        "element": base_hero.get("element", "NATURE"),
        "emoji": base_hero["emoji"],
        "level": level,
        "hp": max(50, int(hp)),
        "max_hp": max(50, int(hp)),
        "atk": max(5, int(atk)),
        "def": max(0, int(defense)),
        "speed": max(5, int(speed)),
        "accuracy": min(100.0, max(30.0, round(accuracy, 1))),
        "crit_rate": min(100.0, max(0.0, round(crit_rate, 1))),
        "crit_damage": max(100.0, round(crit_damage, 1)),
        "armor_penetration": max(0, int(armor_pen)),
        "element_bonus": max(0.0, round(element_bonus, 1))
    }


def get_hero_full_data(hero_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Lấy toàn bộ thông tin tướng, chỉ số gốc, chỉ số sau trang bị và danh sách chiêu thức."""
    hero_info = get_hero_by_id(hero_id, db_path)
    if not hero_info:
        return None

    level = hero_info.get("level", 1)
    equipped = hero_info.get("equipped_items", [])
    effective_stats = calculate_hero_effective_stats(hero_info, level, equipped)

    # Ghép thông tin
    hero_info["effective_stats"] = effective_stats
    hero_info["next_level_xp"] = level * 100
    return hero_info


def get_all_heroes_overview(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả 8 tướng với thông tin đầy đủ về level, trang bị và chỉ số."""
    conn = get_db_connection(db_path)
    try:
        heroes_cur = conn.execute("SELECT id FROM heroes WHERE is_active = 1 ORDER BY id ASC;")
        hero_ids = [r["id"] for r in heroes_cur.fetchall()]
        return [get_hero_full_data(h_id, db_path) for h_id in hero_ids]
    finally:
        conn.close()


def train_hero_level(player_id: int, hero_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Huấn luyện tướng tăng 1 cấp trực tiếp bằng Gold."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            # Lấy thông tin level hiện tại
            cur_prog = conn.execute("SELECT level, xp FROM hero_progress WHERE player_id = ? AND hero_id = ?;", (player_id, hero_id)).fetchone()
            if not cur_prog:
                return {"success": False, "error": "Không tìm thấy tiến trình tướng"}
            
            curr_level = cur_prog["level"]
            if curr_level >= 20:
                return {"success": False, "error": "Tướng đã đạt cấp tối đa (Level 20)"}

            gold_cost = curr_level * 150
            # Kiểm tra Gold
            prof = conn.execute("SELECT gold FROM player_profile WHERE id = ?;", (player_id,)).fetchone()
            if not prof or prof["gold"] < gold_cost:
                return {"success": False, "error": f"Không đủ Gold! Cần {gold_cost} Gold để nâng cấp."}

            new_gold = prof["gold"] - gold_cost
            new_level = curr_level + 1

            conn.execute("UPDATE player_profile SET gold = ? WHERE id = ?;", (new_gold, player_id))
            conn.execute("UPDATE hero_progress SET level = ? WHERE player_id = ? AND hero_id = ?;", (new_level, player_id, hero_id))
            conn.execute("""
                INSERT INTO currency_transactions (player_id, amount, balance_after, reason, reference_id)
                VALUES (?, ?, ?, 'HERO_LEVEL_TRAIN', ?);
            """, (player_id, -gold_cost, new_gold, hero_id))

            return {
                "success": True,
                "hero_id": hero_id,
                "new_level": new_level,
                "remaining_gold": new_gold,
                "message": f"Tướng đã lên Level {new_level} thành công!"
            }
    finally:
        conn.close()
