"""
Flask Application for Tactical Battle Arena RPG & Meta Tracker.
Provides RESTful APIs for Tactical/Auto Combat, Character Progression,
Equipment Inventory, Shop, Lucky Wheel, and SQL Analytics.
"""

import os
import sys
from flask import Flask, jsonify, request, render_template

from database import init_db, get_all_heroes, get_hero_by_id, get_player_profile, save_battle_result
from hero_service import get_all_heroes_overview, get_hero_full_data, train_hero_level
from equipment_service import get_player_inventory, equip_item, unequip_item, upgrade_equipment
from shop_service import get_shop_items, buy_item
from lucky_wheel_service import get_wheel_info, spin_wheel
from battle_engine import roll_team, simulate_battle, TacticalBattleManager
from analytics import (
    get_overview_stats,
    get_hero_analytics,
    get_element_analytics,
    get_composition_analytics,
    get_equipment_meta_analytics,
    get_wheel_distribution_analytics,
    get_recent_matches,
    get_match_detail,
)

app = Flask(__name__)

# Khởi tạo cơ sở dữ liệu và migrations ngay khi ứng dụng khởi động
init_db()


# ==========================================================================
# PAGE ROUTE
# ==========================================================================
@app.route("/")
def index():
    """Trang chủ hiển thị toàn bộ giao diện game Tactical Battle Arena RPG."""
    return render_template("index.html")


# ==========================================================================
# HEROES & PROGRESSION APIs
# ==========================================================================
@app.route("/api/heroes", methods=["GET"])
def api_heroes():
    """Lấy danh sách tất cả các vị tướng kèm level, trang bị và chỉ số thực tế."""
    try:
        heroes = get_all_heroes_overview()
        return jsonify({"success": True, "data": heroes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/heroes/<int:hero_id>", methods=["GET"])
def api_hero_detail(hero_id: int):
    """Lấy thông tin chi tiết một vị tướng (chiêu thức, trang bị, chỉ số)."""
    try:
        hero = get_hero_full_data(hero_id)
        if not hero:
            return jsonify({"success": False, "error": f"Không tìm thấy tướng với ID {hero_id}"}), 404
        return jsonify({"success": True, "data": hero})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/heroes/<int:hero_id>/train", methods=["POST"])
def api_train_hero(hero_id: int):
    """Huấn luyện tướng tăng 1 cấp bằng Gold."""
    try:
        res = train_hero_level(player_id=1, hero_id=hero_id)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================================================
# COMBAT APIs (TACTICAL & AUTO MODES)
# ==========================================================================
@app.route("/api/team/roll", methods=["POST"])
def api_roll_team():
    """Roll ngẫu nhiên 3 tướng không trùng lặp cho người chơi (kèm cấp độ và trang bị thực tế)."""
    try:
        heroes = get_all_heroes_overview()
        if len(heroes) < 3:
            return jsonify({"success": False, "error": "Không đủ tướng trong cơ sở dữ liệu"}), 400

        team = roll_team(heroes, variance=0.08)
        return jsonify({"success": True, "data": team})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/battle/fight", methods=["POST"])
def api_battle_fight():
    """Chế độ Auto Mode: Mô phỏng trận đấu 3v3 toàn bộ bằng Battle Engine backend."""
    try:
        payload = request.get_json(silent=True) or {}
        player_team = payload.get("player_team")

        all_heroes = get_all_heroes_overview()
        if len(all_heroes) < 3:
            return jsonify({"success": False, "error": "Không đủ tướng trong cơ sở dữ liệu"}), 400

        if not player_team or len(player_team) != 3:
            player_team = roll_team(all_heroes)

        opponent_team = roll_team(all_heroes)
        battle_result = simulate_battle(player_team, opponent_team, max_rounds=25, battle_mode="AUTO")

        match_id = save_battle_result(battle_result)
        battle_result["match_id"] = match_id

        return jsonify({"success": True, "data": battle_result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/battle/tactical/start", methods=["POST"])
def api_tactical_start():
    """Bắt đầu một phiên đấu Tactical Mode tương tác theo lượt."""
    try:
        payload = request.get_json(silent=True) or {}
        player_team = payload.get("player_team")

        all_heroes = get_all_heroes_overview()
        if len(all_heroes) < 3:
            return jsonify({"success": False, "error": "Không đủ tướng trong cơ sở dữ liệu"}), 400

        if not player_team or len(player_team) != 3:
            player_team = roll_team(all_heroes)

        opponent_team = roll_team(all_heroes)
        init_state = TacticalBattleManager.create_battle(player_team, opponent_team)
        return jsonify(init_state)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/battle/tactical/action", methods=["POST"])
def api_tactical_action():
    """Người chơi ra lệnh chọn chiêu và mục tiêu cho tướng đang đến lượt trong Tactical Mode."""
    try:
        payload = request.get_json(silent=True) or {}
        battle_id = payload.get("battle_id")
        ability_id = payload.get("ability_id")
        target_idx = payload.get("target_idx")

        if not battle_id or ability_id is None:
            return jsonify({"success": False, "error": "Thiếu thông tin battle_id hoặc ability_id"}), 400

        res = TacticalBattleManager.execute_player_action(battle_id, ability_id, target_idx)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================================================
# PLAYER PROFILE & ECONOMY APIs
# ==========================================================================
@app.route("/api/player/profile", methods=["GET"])
def api_player_profile():
    """Lấy thông tin hồ sơ người chơi: Gold, Level, XP, Materials."""
    try:
        profile = get_player_profile(player_id=1)
        return jsonify({"success": True, "data": profile})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/player/transactions", methods=["GET"])
def api_player_transactions():
    """Lấy sổ cái lịch sử giao dịch Gold."""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cur = conn.execute("""
            SELECT * FROM currency_transactions
            WHERE player_id = 1
            ORDER BY id DESC
            LIMIT 30;
        """)
        txs = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"success": True, "data": txs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================================================
# EQUIPMENT & INVENTORY APIs
# ==========================================================================
@app.route("/api/inventory", methods=["GET"])
def api_inventory():
    """Lấy danh sách trang bị trong kho của người chơi."""
    try:
        slot_type = request.args.get("slot_type")
        rarity = request.args.get("rarity")
        items = get_player_inventory(player_id=1, slot_type=slot_type, rarity=rarity)
        return jsonify({"success": True, "data": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/inventory/equip", methods=["POST"])
def api_equip_item():
    """Trang bị một món đồ cho tướng."""
    try:
        payload = request.get_json(silent=True) or {}
        inventory_id = payload.get("inventory_id")
        hero_id = payload.get("hero_id")

        if not inventory_id or not hero_id:
            return jsonify({"success": False, "error": "Thiếu inventory_id hoặc hero_id"}), 400

        res = equip_item(player_id=1, inventory_id=inventory_id, hero_id=hero_id)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/inventory/unequip", methods=["POST"])
def api_unequip_item():
    """Tháo một món trang bị về kho đồ."""
    try:
        payload = request.get_json(silent=True) or {}
        inventory_id = payload.get("inventory_id")

        if not inventory_id:
            return jsonify({"success": False, "error": "Thiếu inventory_id"}), 400

        res = unequip_item(player_id=1, inventory_id=inventory_id)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/inventory/upgrade", methods=["POST"])
def api_upgrade_item():
    """Cường hóa trang bị lên +1 đến +5 bằng Gold và Nguyên liệu."""
    try:
        payload = request.get_json(silent=True) or {}
        inventory_id = payload.get("inventory_id")

        if not inventory_id:
            return jsonify({"success": False, "error": "Thiếu inventory_id"}), 400

        res = upgrade_equipment(player_id=1, inventory_id=inventory_id)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================================================
# SHOP APIs
# ==========================================================================
@app.route("/api/shop", methods=["GET"])
def api_shop():
    """Lấy danh mục các mặt hàng trong Shop theo phân loại."""
    try:
        catalog = get_shop_items()
        return jsonify({"success": True, "data": catalog})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/shop/buy", methods=["POST"])
def api_shop_buy():
    """Mua trang bị hoặc nguyên liệu bằng Gold."""
    try:
        payload = request.get_json(silent=True) or {}
        item_id = payload.get("item_id")
        is_material = payload.get("is_material", False)

        if not item_id:
            return jsonify({"success": False, "error": "Thiếu item_id"}), 400

        res = buy_item(player_id=1, item_id=item_id, is_material=is_material)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================================================
# LUCKY WHEEL APIs
# ==========================================================================
@app.route("/api/wheel", methods=["GET"])
def api_wheel():
    """Lấy cấu hình tỷ lệ phần thưởng và tiến trình Pity của Vòng Quay May Mắn."""
    try:
        info = get_wheel_info(player_id=1)
        return jsonify({"success": True, "data": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/wheel/spin", methods=["POST"])
def api_wheel_spin():
    """Quay Vòng Quay May Mắn bằng Gold hoặc Vé Quay."""
    try:
        payload = request.get_json(silent=True) or {}
        cost_type = payload.get("cost_type", "GOLD")
        res = spin_wheel(player_id=1, cost_type=cost_type)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================================================
# ANALYTICS & MATCH HISTORY APIs
# ==========================================================================
@app.route("/api/analytics/overview", methods=["GET"])
def api_analytics_overview():
    """Lấy chỉ số tổng quan trận đấu và kinh tế."""
    try:
        data = get_overview_stats()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/heroes", methods=["GET"])
def api_analytics_heroes():
    """Lấy thống kê hiệu năng chi tiết từng tướng."""
    try:
        data = get_hero_analytics()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/elements", methods=["GET"])
def api_analytics_elements():
    """Lấy thống kê hiệu năng theo hệ nguyên tố (FIRE, WATER, NATURE)."""
    try:
        data = get_element_analytics()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/compositions", methods=["GET"])
def api_analytics_compositions():
    """Lấy bảng xếp hạng đội hình 3 tướng chuẩn hóa."""
    try:
        limit = request.args.get("limit", default=10, type=int)
        data = get_composition_analytics(limit=limit)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/equipment", methods=["GET"])
def api_analytics_equipment():
    """Lấy thống kê trang bị được sở hữu và cường hóa trong kho đồ."""
    try:
        data = get_equipment_meta_analytics()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/wheel", methods=["GET"])
def api_analytics_wheel():
    """Lấy phân phối phần thưởng thực tế nhận được từ Vòng Quay May Mắn."""
    try:
        data = get_wheel_distribution_analytics()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/matches", methods=["GET"])
def api_matches():
    """Lấy danh sách các trận đấu gần nhất."""
    try:
        limit = request.args.get("limit", default=30, type=int)
        data = get_recent_matches(limit=limit)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/matches/<int:match_id>", methods=["GET"])
def api_match_detail(match_id: int):
    """Lấy chi tiết một trận đấu cùng snapshot chỉ số, trang bị và toàn bộ Battle Events."""
    try:
        detail = get_match_detail(match_id)
        if not detail:
            return jsonify({"success": False, "error": f"Không tìm thấy trận đấu với ID {match_id}"}), 404
        return jsonify({"success": True, "data": detail})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    port = int(os.environ.get("PORT", 5000))
    print(f"[SERVER] Tactical Battle Arena RPG dang chay tai: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
