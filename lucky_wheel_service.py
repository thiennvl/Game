"""
Lucky Wheel Service: Handles the lucky wheel spin mechanics, published probabilities,
pity counter, reward distribution, and spin history audit ledger.
"""

import random
from typing import Dict, Any, List, Optional
from database import get_db_connection


SPIN_COST_GOLD = 150
PITY_THRESHOLD = 10  # Sau 10 lượt quay không trúng Epic/Legendary, lượt tiếp theo đảm bảo Epic+

# Danh sách tỷ lệ công khai (Tổng = 100%)
PUBLISHED_ODDS = [
    {"type": "GOLD", "label": "Vàng (120 - 350 Gold)", "chance": 45, "color": "#f59e0b"},
    {"type": "MATERIAL", "label": "Nguyên Liệu Nâng Cấp", "chance": 25, "color": "#06b6d4"},
    {"type": "EQUIP_COMMON", "label": "Trang Bị COMMON", "chance": 15, "color": "#9ca3af"},
    {"type": "EQUIP_RARE", "label": "Trang Bị RARE", "chance": 8, "color": "#3b82f6"},
    {"type": "EQUIP_EPIC", "label": "Trang Bị EPIC", "chance": 5, "color": "#a855f7"},
    {"type": "EQUIP_LEGENDARY", "label": "Trang Bị LEGENDARY", "chance": 2, "color": "#eab308"}
]


def get_wheel_info(player_id: int = 1, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Lấy thông tin cấu hình vòng quay, tỷ lệ thưởng, tiến trình pity và lịch sử quay gần nhất."""
    conn = get_db_connection(db_path)
    try:
        prof = conn.execute("SELECT pity_counter, gold FROM player_profile WHERE id = ?;", (player_id,)).fetchone()
        pity = prof["pity_counter"] if prof else 0
        gold = prof["gold"] if prof else 0

        # Lấy số vé quay
        ticket_row = conn.execute("SELECT quantity FROM player_materials WHERE player_id = ? AND material_type = 'LUCKY_TICKET';", (player_id,)).fetchone()
        tickets = ticket_row["quantity"] if ticket_row else 0

        # Lấy 15 lượt quay gần nhất
        history_cur = conn.execute("""
            SELECT * FROM wheel_spin_history
            WHERE player_id = ?
            ORDER BY id DESC
            LIMIT 15;
        """, (player_id,))
        history = [dict(r) for r in history_cur.fetchall()]

        return {
            "spin_cost_gold": SPIN_COST_GOLD,
            "pity_threshold": PITY_THRESHOLD,
            "current_pity": pity,
            "spins_until_pity": max(0, PITY_THRESHOLD - pity),
            "player_gold": gold,
            "player_tickets": tickets,
            "published_odds": PUBLISHED_ODDS,
            "recent_history": history
        }
    finally:
        conn.close()


def spin_wheel(player_id: int = 1, cost_type: str = "GOLD", random_seed: Optional[int] = None, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Thực hiện 1 lượt quay Vòng Quay May Mắn:
    - Kiểm tra tài nguyên hợp lệ (150 Gold hoặc 1 Lucky Ticket)
    - Kiểm tra bảo hiểm Pity (>= 10 lượt -> chắc chắn ra EPIC hoặc LEGENDARY)
    - Sinh phần thưởng ngẫu nhiên theo tỷ lệ backend
    - Cập nhật số dư/kho đồ và lưu lịch sử trong một transaction duy nhất
    """
    if random_seed is not None:
        random.seed(random_seed)

    conn = get_db_connection(db_path)
    try:
        with conn:
            # 1. Kiểm tra tài nguyên
            prof = conn.execute("SELECT gold, pity_counter FROM player_profile WHERE id = ?;", (player_id,)).fetchone()
            if not prof:
                return {"success": False, "error": "Hồ sơ người chơi không tồn tại"}

            pity_before = prof["pity_counter"]
            gold = prof["gold"]

            ticket_row = conn.execute("SELECT quantity FROM player_materials WHERE player_id = ? AND material_type = 'LUCKY_TICKET';", (player_id,)).fetchone()
            tickets = ticket_row["quantity"] if ticket_row else 0

            if cost_type == "TICKET":
                if tickets < 1:
                    return {"success": False, "error": "Bạn không có Vé Quay May Mắn! Hãy mua trong Shop hoặc dùng Gold."}
                conn.execute("UPDATE player_materials SET quantity = quantity - 1 WHERE player_id = ? AND material_type = 'LUCKY_TICKET';", (player_id,))
            else:
                if gold < SPIN_COST_GOLD:
                    return {"success": False, "error": f"Không đủ Gold! Cần {SPIN_COST_GOLD} Gold (Hiện có: {gold})."}
                gold -= SPIN_COST_GOLD
                conn.execute("UPDATE player_profile SET gold = ? WHERE id = ?;", (gold, player_id))
                conn.execute("""
                    INSERT INTO currency_transactions (player_id, amount, balance_after, reason)
                    VALUES (?, ?, ?, 'WHEEL_SPIN_COST');
                """, (player_id, -SPIN_COST_GOLD, gold))

            # 2. Quyết định phần thưởng
            # Kiểm tra cơ chế Pity bảo hiểm
            if pity_before >= PITY_THRESHOLD:
                # Bảo hiểm kích hoạt: 75% ra EPIC, 25% ra LEGENDARY
                is_pity_triggered = True
                roll_pity = random.random()
                reward_category = "EQUIP_LEGENDARY" if roll_pity < 0.25 else "EQUIP_EPIC"
            else:
                is_pity_triggered = False
                # Random theo tỷ lệ chuẩn
                roll = random.uniform(0, 100)
                if roll < 45:
                    reward_category = "GOLD"
                elif roll < 70:
                    reward_category = "MATERIAL"
                elif roll < 85:
                    reward_category = "EQUIP_COMMON"
                elif roll < 93:
                    reward_category = "EQUIP_RARE"
                elif roll < 98:
                    reward_category = "EQUIP_EPIC"
                else:
                    reward_category = "EQUIP_LEGENDARY"

            # 3. Phân bổ phần thưởng cụ thể
            reward_type = ""
            reward_name = ""
            reward_rarity = "COMMON"
            slice_index = 0  # 0..5 vị trí trên vòng quay đồ họa

            if reward_category == "GOLD":
                slice_index = 0
                amount = random.randint(120, 350)
                reward_type = "GOLD"
                reward_name = f"{amount} Gold"
                reward_rarity = "COMMON"
                gold += amount
                conn.execute("UPDATE player_profile SET gold = ? WHERE id = ?;", (gold, player_id))
                conn.execute("""
                    INSERT INTO currency_transactions (player_id, amount, balance_after, reason)
                    VALUES (?, ?, ?, 'WHEEL_REWARD_GOLD');
                """, (player_id, amount, gold))

            elif reward_category == "MATERIAL":
                slice_index = 1
                mat_roll = random.random()
                if mat_roll < 0.65:
                    qty = random.randint(1, 3)
                    reward_type = "MATERIAL"
                    reward_name = f"{qty}x Đá Cường Hóa"
                    reward_rarity = "RARE"
                    conn.execute("""
                        INSERT INTO player_materials (player_id, material_type, quantity)
                        VALUES (?, 'UPGRADE_STONE', ?)
                        ON CONFLICT(player_id, material_type) DO UPDATE SET quantity = quantity + excluded.quantity;
                    """, (player_id, qty))
                elif mat_roll < 0.85:
                    reward_type = "MATERIAL"
                    reward_name = "1x Tinh Thể Nguyên Tố"
                    reward_rarity = "EPIC"
                    conn.execute("""
                        INSERT INTO player_materials (player_id, material_type, quantity)
                        VALUES (?, 'ELEMENT_CRYSTAL', 1)
                        ON CONFLICT(player_id, material_type) DO UPDATE SET quantity = quantity + 1;
                    """, (player_id,))
                else:
                    reward_type = "MATERIAL"
                    reward_name = "1x Vé Quay Bổ Sung"
                    reward_rarity = "RARE"
                    conn.execute("""
                        INSERT INTO player_materials (player_id, material_type, quantity)
                        VALUES (?, 'LUCKY_TICKET', 1)
                        ON CONFLICT(player_id, material_type) DO UPDATE SET quantity = quantity + 1;
                    """, (player_id,))

            else:
                # Trang bị
                target_rarity = reward_category.replace("EQUIP_", "")
                reward_rarity = target_rarity
                slice_index = 2 if target_rarity == "COMMON" else (3 if target_rarity == "RARE" else (4 if target_rarity == "EPIC" else 5))

                eq_cur = conn.execute("SELECT id, name, icon FROM equipment_catalog WHERE rarity = ? AND slot_type != 'MATERIAL';", (target_rarity,))
                candidates = eq_cur.fetchall()
                if candidates:
                    chosen = random.choice(candidates)
                    reward_type = "EQUIPMENT"
                    reward_name = f"{chosen['icon']} {chosen['name']}"
                    conn.execute("""
                        INSERT INTO inventory_items (player_id, equipment_id, upgrade_level, is_equipped)
                        VALUES (?, ?, 0, 0);
                    """, (player_id, chosen["id"]))
                else:
                    # Fallback nếu không tìm thấy
                    reward_type = "GOLD"
                    reward_name = "500 Gold"
                    gold += 500
                    conn.execute("UPDATE player_profile SET gold = ? WHERE id = ?;", (gold, player_id))

            # 4. Cập nhật Pity Counter
            if reward_rarity in ["EPIC", "LEGENDARY"]:
                pity_after = 0
            else:
                pity_after = pity_before + 1

            conn.execute("UPDATE player_profile SET pity_counter = ? WHERE id = ?;", (pity_after, player_id))

            # 5. Ghi nhật ký vòng quay
            conn.execute("""
                INSERT INTO wheel_spin_history (player_id, cost_type, reward_type, reward_name, rarity, pity_before, pity_after)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (player_id, cost_type, reward_type, reward_name, reward_rarity, pity_before, pity_after))

            return {
                "success": True,
                "reward_type": reward_type,
                "reward_name": reward_name,
                "rarity": reward_rarity,
                "slice_index": slice_index,
                "is_pity_triggered": is_pity_triggered,
                "pity_before": pity_before,
                "pity_after": pity_after,
                "remaining_gold": gold,
                "message": f"🎉 Bạn nhận được: {reward_name}!"
            }
    finally:
        conn.close()
