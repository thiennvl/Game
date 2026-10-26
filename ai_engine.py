"""
AI Engine: Tactical AI decision-making for RED opponent team (and BLUE in Auto Mode).
Evaluates abilities, targets, element advantages, lethal strikes, and defensive plays.
"""

from typing import Dict, Any, List, Optional, Tuple


def get_element_multiplier(atk_elem: str, def_elem: str) -> float:
    """Xác định hệ số khắc hệ giữa 2 nguyên tố (Pokémon-like)."""
    if atk_elem == "FIRE" and def_elem == "NATURE":
        return 1.5
    if atk_elem == "NATURE" and def_elem == "WATER":
        return 1.5
    if atk_elem == "WATER" and def_elem == "FIRE":
        return 1.5

    if atk_elem == "FIRE" and def_elem == "WATER":
        return 0.75
    if atk_elem == "WATER" and def_elem == "NATURE":
        return 0.75
    if atk_elem == "NATURE" and def_elem == "FIRE":
        return 0.75

    return 1.0


def choose_best_action(actor: Any, all_combatants: List[Any]) -> Tuple[Dict[str, Any], Any]:
    """
    AI đánh giá toàn bộ chiêu thức khả dụng (cooldown == 0) và mục tiêu hợp lệ để chọn hành động tối ưu.
    Trả về: (selected_ability, selected_target_or_targets)
    """
    allies = [c for c in all_combatants if c.team_side == actor.team_side and c.hp > 0]
    enemies = [c for c in all_combatants if c.team_side != actor.team_side and c.hp > 0]

    # Lấy các chiêu không trong thời gian hồi
    available_abilities = [ab for ab in actor.abilities if ab.get("current_cd", 0) == 0]
    if not available_abilities:
        if actor.abilities:
            available_abilities = [actor.abilities[0]]
        else:
            available_abilities = [{
                "id": 0,
                "name": "Basic Strike",
                "description": "Tấn công cơ bản",
                "element": getattr(actor, "element", "NEUTRAL"),
                "skill_power": 100,
                "target_type": "SINGLE_ENEMY",
                "accuracy": 100,
                "cooldown": 0,
                "current_cd": 0,
                "icon": "⚔️"
            }]

    best_score = -999999
    best_choice = (available_abilities[0], enemies[0] if enemies else actor)


    for ab in available_abilities:
        target_type = ab.get("target_type", "SINGLE_ENEMY")

        if target_type == "SELF":
            # Chiêu tự dựng khiên hoặc buff
            score = 50
            if actor.hp < actor.max_hp * 0.5:
                score += 80  # Càng yếu máu càng cần dựng khiên
            if score > best_score:
                best_score = score
                best_choice = (ab, actor)

        elif target_type in ["SINGLE_ALLY"]:
            # Chiêu hỗ trợ/hồi máu đồng đội
            for ally in allies:
                hp_ratio = ally.hp / ally.max_hp
                score = 0
                if hp_ratio < 0.4:
                    score += 250  # Cứu nguy đồng đội sắp chết
                elif hp_ratio < 0.7:
                    score += 120
                else:
                    score += 20  # Không quá cần hồi máu

                if ab.get("status_effect") == "SHIELD" and hp_ratio < 0.6:
                    score += 60

                if score > best_score:
                    best_score = score
                    best_choice = (ab, ally)

        elif target_type == "ALL_ENEMIES":
            # Chiêu diện rộng
            total_est_dmg = 0
            for en in enemies:
                elem_mult = get_element_multiplier(ab.get("element", actor.element), en.element)
                est_dmg = (actor.atk * ab.get("skill_power", 100) / 100.0) * elem_mult
                total_est_dmg += est_dmg
                if en.hp <= est_dmg:
                    total_est_dmg += 150  # Thưởng lớn nếu có thể kết liễu kẻ địch

            score = total_est_dmg * 1.3
            if score > best_score:
                best_score = score
                best_choice = (ab, enemies)  # Danh sách tất cả kẻ địch

        else:
            # SINGLE_ENEMY: Đánh đơn
            for en in enemies:
                elem_mult = get_element_multiplier(ab.get("element", actor.element), en.element)
                raw_dmg = (actor.atk * ab.get("skill_power", 100) / 100.0)
                eff_def = max(0, en.defense - actor.armor_penetration)
                est_dmg = max(1, (raw_dmg - eff_def * 0.5) * elem_mult)

                score = est_dmg

                # 1. Ưu tiên tuyệt đối hạ gục mục tiêu thấp máu (Lethal Strike)
                if en.hp <= est_dmg:
                    score += 300

                # 2. Khắc hệ
                if elem_mult > 1.0:
                    score += 45
                elif elem_mult < 1.0:
                    score -= 30

                # 3. Ưu tiên tướng sát thương chủ lực của địch (Mage, Assassin)
                if en.role in ["Pháp sư", "Sát thủ", "Hỏa pháp sư"]:
                    score += 35

                # 4. Hiệu ứng trạng thái có giá trị
                if ab.get("status_effect") == "STUN":
                    score += 60
                elif ab.get("status_effect") == "BURN":
                    score += 30
                elif ab.get("status_effect") == "MARKED":
                    score += 40

                if score > best_score:
                    best_score = score
                    best_choice = (ab, en)

    return best_choice
