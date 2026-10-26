"""
Shop Service: Handles item catalog display and Gold-based purchases.
Ensures atomic transactions and updates inventory and currency ledgers.
"""

from typing import Dict, Any, List, Optional
from database import get_db_connection


# Danh mục các gói nguyên liệu có thể mua trong Shop
MATERIAL_SHOP_OFFERS = [
    {
        "id": 901,
        "name": "Upgrade Stone Pack (x2)",
        "slot_type": "MATERIAL",
        "material_type": "UPGRADE_STONE",
        "quantity": 2,
        "price": 180,
        "rarity": "RARE",
        "icon": "💎",
        "description": "Gói 2 viên Đá Cường Hóa dùng để nâng cấp vũ khí và trang bị."
    },
    {
        "id": 902,
        "name": "Element Crystal (x1)",
        "slot_type": "MATERIAL",
        "material_type": "ELEMENT_CRYSTAL",
        "quantity": 1,
        "price": 320,
        "rarity": "EPIC",
        "icon": "🔮",
        "description": "Tinh thể nguyên tố quý hiếm cần thiết khi nâng trang bị lên +4 và +5."
    },
    {
        "id": 903,
        "name": "Lucky Spin Ticket (x1)",
        "slot_type": "MATERIAL",
        "material_type": "LUCKY_TICKET",
        "quantity": 1,
        "price": 150,
        "rarity": "RARE",
        "icon": "🎟️",
        "description": "Vé quay Vòng Quay May Mắn để nhận Gold, nguyên liệu và trang bị hiếm."
    }
]


def get_shop_items(db_path: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Lấy danh sách tất cả mặt hàng trong Cửa hàng phân theo danh mục."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("""
            SELECT * FROM equipment_catalog
            WHERE is_active = 1
            ORDER BY slot_type ASC, price ASC;
        """)
        catalog_items = [dict(r) for r in cur.fetchall()]

        categories = {
            "WEAPON": [],
            "ARMOR": [],
            "BOOTS": [],
            "ACCESSORY": [],
            "MATERIAL": list(MATERIAL_SHOP_OFFERS)
        }

        for item in catalog_items:
            stype = item["slot_type"]
            if stype in categories:
                categories[stype].append(item)

        return categories
    finally:
        conn.close()


def buy_item(player_id: int, item_id: int, is_material: bool = False, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Mua trang bị hoặc nguyên liệu bằng Gold:
    - Kiểm tra số dư Gold của người chơi
    - Khấu trừ Gold và thêm vật phẩm vào kho đồ (hoặc kho nguyên liệu)
    - Ghi nhận lịch sử giao dịch vào currency_transactions
    - Trả về số dư mới và vật phẩm nhận được
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            # 1. Kiểm tra mặt hàng
            if is_material:
                offer = next((m for m in MATERIAL_SHOP_OFFERS if m["id"] == item_id), None)
                if not offer:
                    return {"success": False, "error": "Gói nguyên liệu không tồn tại"}
                price = offer["price"]
                item_name = offer["name"]
                mat_type = offer["material_type"]
                qty = offer["quantity"]
            else:
                cur = conn.execute("SELECT * FROM equipment_catalog WHERE id = ? AND is_active = 1;", (item_id,))
                eq = cur.fetchone()
                if not eq:
                    return {"success": False, "error": "Trang bị không tồn tại trong cửa hàng"}
                price = eq["price"]
                item_name = eq["name"]

            # 2. Kiểm tra số dư Gold
            prof = conn.execute("SELECT gold FROM player_profile WHERE id = ?;", (player_id,)).fetchone()
            if not prof or prof["gold"] < price:
                return {"success": False, "error": f"Không đủ Gold! Cần {price} Gold (Hiện có: {prof['gold'] if prof else 0})."}

            new_gold = prof["gold"] - price

            # 3. Trừ Gold
            conn.execute("UPDATE player_profile SET gold = ? WHERE id = ?;", (new_gold, player_id))

            # 4. Trao vật phẩm
            if is_material:
                conn.execute("""
                    INSERT INTO player_materials (player_id, material_type, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(player_id, material_type) DO UPDATE SET quantity = quantity + excluded.quantity;
                """, (player_id, mat_type, qty))
            else:
                conn.execute("""
                    INSERT INTO inventory_items (player_id, equipment_id, upgrade_level, is_equipped)
                    VALUES (?, ?, 0, 0);
                """, (player_id, item_id))

            # 5. Ghi sổ cái tài chính
            conn.execute("""
                INSERT INTO currency_transactions (player_id, amount, balance_after, reason, reference_id)
                VALUES (?, ?, ?, 'SHOP_PURCHASE', ?);
            """, (player_id, -price, new_gold, item_id))

            return {
                "success": True,
                "message": f"🎉 Mua thành công {item_name}!",
                "item_name": item_name,
                "spent_gold": price,
                "remaining_gold": new_gold
            }
    finally:
        conn.close()
