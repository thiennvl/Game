"""
Battle Engine for Tactical Battle Arena RPG.
Implements Pokémon-like tactical turn-based combat, Free Fire-inspired stats,
elemental advantages, status effects (BURN, STUN, SHIELD, MARKED, HEAL),
accuracy/miss check, and dual mode (Tactical & Auto Mode).
"""

import copy
import json
import random
from typing import List, Dict, Any, Tuple, Optional
from ai_engine import get_element_multiplier, choose_best_action
from database import get_db_connection, get_hero_by_id


class Combatant:
    """Đại diện cho một tướng tham gia trong trận chiến với đầy đủ chỉ số RPG."""

    def __init__(self, data: Dict[str, Any], team_side: str, slot_no: int, participant_idx: int):
        self.hero_id = data.get("id") or data.get("hero_id")
        self.name = data["name"]
        self.role = data["role"]
        self.element = data.get("element", "NATURE")
        self.emoji = data.get("emoji", "⚔️")
        self.level = data.get("level", 1)

        # Chỉ số chiến đấu
        self.max_hp = int(data.get("max_hp", data.get("hp", data.get("base_hp", 100))))
        self.hp = int(data.get("hp", self.max_hp))
        self.shield = int(data.get("shield", 0))
        self.atk = int(data.get("atk", data.get("base_atk", 20)))
        self.defense = int(data.get("def", data.get("base_def", 15)))
        self.speed = int(data.get("speed", data.get("base_speed", 20)))
        self.accuracy = float(data.get("accuracy", data.get("base_accuracy", 95)))
        self.crit_rate = float(data.get("crit_rate", data.get("base_crit_rate", 5.0)))
        self.crit_damage = float(data.get("crit_damage", data.get("base_crit_damage", 150.0)))
        self.armor_penetration = int(data.get("armor_penetration", 0))
        self.element_bonus = float(data.get("element_bonus", 0.0))

        self.team_side = team_side  # 'BLUE' hoặc 'RED'
        self.slot_no = slot_no      # 0, 1, 2
        self.participant_idx = participant_idx  # 0..5 duy nhất

        # Chiêu thức
        self.abilities = copy.deepcopy(data.get("abilities", []))
        if not self.abilities:
            self.abilities = [{
                "id": 0,
                "name": "Basic Strike",
                "description": "Tấn công cơ bản",
                "element": self.element,
                "skill_power": 100,
                "target_type": "SINGLE_ENEMY",
                "accuracy": 100,
                "cooldown": 0,
                "current_cd": 0,
                "icon": "⚔️"
            }]
        for ab in self.abilities:
            if "current_cd" not in ab:
                ab["current_cd"] = 0


        # Trạng thái bất lợi / có lợi
        self.status_effects = copy.deepcopy(data.get("status_effects", {}))

        # Trang bị
        self.equipment = copy.deepcopy(data.get("equipped_items", data.get("equipment", [])))

        # Thống kê sau trận
        self.damage_dealt = 0
        self.healing_done = 0
        self.kills = 0
        self.is_winner = 0

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển đổi thành dictionary cho JSON serialization."""
        return {
            "participant_idx": self.participant_idx,
            "hero_id": self.hero_id,
            "name": self.name,
            "role": self.role,
            "element": self.element,
            "emoji": self.emoji,
            "level": self.level,
            "team_side": self.team_side,
            "slot_no": self.slot_no,
            "hp": max(0, self.hp),
            "max_hp": self.max_hp,
            "shield": self.shield,
            "atk": self.atk,
            "def": self.defense,
            "speed": self.speed,
            "accuracy": self.accuracy,
            "crit_rate": self.crit_rate,
            "crit_damage": self.crit_damage,
            "armor_penetration": self.armor_penetration,
            "element_bonus": self.element_bonus,
            "status_effects": dict(self.status_effects),
            "abilities": [
                {
                    "id": ab.get("id"),
                    "name": ab.get("name"),
                    "description": ab.get("description"),
                    "element": ab.get("element"),
                    "skill_power": ab.get("skill_power"),
                    "target_type": ab.get("target_type"),
                    "accuracy": ab.get("accuracy"),
                    "cooldown": ab.get("cooldown"),
                    "current_cd": ab.get("current_cd", 0),
                    "icon": ab.get("icon", "⚡")
                }
                for ab in self.abilities
            ],
            "equipment": self.equipment,
            "damage_dealt": self.damage_dealt,
            "healing_done": self.healing_done,
            "kills": self.kills,
            "is_winner": self.is_winner
        }

    def to_participant_record(self) -> Dict[str, Any]:
        """Chuyển thành bản ghi lưu trữ vào match_participants."""
        return {
            "participant_idx": self.participant_idx,
            "hero_id": self.hero_id,
            "name": self.name,
            "role": self.role,
            "element": self.element,
            "emoji": self.emoji,
            "team_side": self.team_side,
            "slot_no": self.slot_no,
            "level": self.level,
            "hp_start": self.max_hp,
            "hp_end": max(0, self.hp),
            "damage_dealt": self.damage_dealt,
            "kills": self.kills,
            "is_winner": self.is_winner,
            "equipment": self.equipment
        }


def roll_team(available_heroes: List[Dict[str, Any]], variance: float = 0.08) -> List[Dict[str, Any]]:
    """Tạo ngẫu nhiên một đội 3 tướng không trùng lặp kèm chỉ số biến động nhẹ."""
    if len(available_heroes) < 3:
        raise ValueError("Cần ít nhất 3 tướng trong cơ sở dữ liệu để tạo đội.")

    chosen_heroes = random.sample(available_heroes, 3)
    team = []

    for slot, h in enumerate(chosen_heroes):
        # Nạp chiêu thức và trang bị đầy đủ nếu chưa có
        hero_full = get_hero_by_id(h["id"]) or h
        level = hero_full.get("level", 1)

        hp_factor = random.uniform(1.0 - variance, 1.0 + variance)
        atk_factor = random.uniform(1.0 - variance, 1.0 + variance)

        base_hp = hero_full.get("hp", hero_full.get("base_hp", 120))
        base_atk = hero_full.get("atk", hero_full.get("base_atk", 25))

        actual_hp = max(60, int(round(base_hp * hp_factor)))
        actual_atk = max(10, int(round(base_atk * atk_factor)))

        team.append({
            "id": hero_full["id"],
            "hero_id": hero_full["id"],
            "name": hero_full["name"],
            "role": hero_full["role"],
            "element": hero_full.get("element", "NATURE"),
            "emoji": hero_full["emoji"],
            "level": level,
            "base_hp": base_hp,
            "base_atk": base_atk,
            "hp": actual_hp,
            "max_hp": actual_hp,
            "atk": actual_atk,

            "def": hero_full.get("def", hero_full.get("base_def", 15)),
            "speed": hero_full.get("speed", hero_full.get("base_speed", 20)),
            "accuracy": hero_full.get("accuracy", hero_full.get("base_accuracy", 95)),
            "crit_rate": hero_full.get("crit_rate", hero_full.get("base_crit_rate", 5.0)),
            "crit_damage": hero_full.get("crit_damage", hero_full.get("base_crit_damage", 150.0)),
            "armor_penetration": hero_full.get("armor_penetration", 0),
            "element_bonus": hero_full.get("element_bonus", 0.0),
            "abilities": hero_full.get("abilities", []),
            "equipped_items": hero_full.get("equipped_items", []),
            "slot_no": slot
        })

    return team


def execute_action(actor: Combatant, ability: Dict[str, Any], targets: List[Combatant], round_no: int, event_order: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    Thực thi 1 hành động/chiêu thức từ actor nhắm vào danh sách targets:
    - Tính trúng/trượt (Accuracy & Miss)
    - Tính khắc hệ (Element Multiplier)
    - Tính chí mạng (Critical)
    - Tính xuyên giáp và giảm sát thương bởi DEF
    - Trừ lá chắn SHIELD trước khi trừ HP
    - Kích hoạt hiệu ứng trạng thái (BURN, STUN, SHIELD, MARKED, HEAL)
    - Tạo các bản ghi Battle Events chi tiết
    """
    events = []
    target_type = ability.get("target_type", "SINGLE_ENEMY")

    # Đặt hồi chiêu cho chiêu thức
    cd = ability.get("cooldown", 0)
    for ab in actor.abilities:
        if ab.get("name") == ability.get("name"):
            ab["current_cd"] = cd + 1  # +1 vì cuối hiệp sẽ giảm 1

    # 1. CHIÊU TỰ THÂN HOẶC LÁ CHẮN ĐỒNG MINH
    if target_type in ["SELF", "SINGLE_ALLY"] and ability.get("status_effect") in ["SHIELD", "HEAL"]:
        for t in targets:
            if not t.is_alive:
                continue

            if ability.get("status_effect") == "HEAL":
                heal_val = int(actor.atk * (ability.get("skill_power", 100) / 100.0) + 30)
                old_hp = t.hp
                t.hp = min(t.max_hp, t.hp + heal_val)
                actual_heal = t.hp - old_hp
                actor.healing_done += actual_heal

                events.append({
                    "round_no": round_no,
                    "event_order": event_order,
                    "actor_side": actor.team_side,
                    "actor_name": actor.name,
                    "actor_slot": actor.slot_no,
                    "actor_idx": actor.participant_idx,
                    "target_side": t.team_side,
                    "target_name": t.name,
                    "target_slot": t.slot_no,
                    "target_idx": t.participant_idx,
                    "event_type": "HEAL",
                    "damage": actual_heal,
                    "ability_id": ability.get("id"),
                    "ability_name": ability.get("name"),
                    "is_crit": 0,
                    "is_miss": 0,
                    "element_mult": 1.0,
                    "shield_absorbed": 0,
                    "status_applied": "HEAL",
                    "message": f"💚 [{actor.team_side}] {actor.emoji} {actor.name} thi triển {ability['name']}, hồi phục {actual_heal} HP cho {t.name}!"
                })
                event_order += 1

            elif ability.get("status_effect") == "SHIELD":
                shield_gain = int(actor.defense * 2.0 + 40)
                t.shield += shield_gain

                events.append({
                    "round_no": round_no,
                    "event_order": event_order,
                    "actor_side": actor.team_side,
                    "actor_name": actor.name,
                    "actor_slot": actor.slot_no,
                    "actor_idx": actor.participant_idx,
                    "target_side": t.team_side,
                    "target_name": t.name,
                    "target_slot": t.slot_no,
                    "target_idx": t.participant_idx,
                    "event_type": "SKILL",
                    "damage": 0,
                    "ability_id": ability.get("id"),
                    "ability_name": ability.get("name"),
                    "is_crit": 0,
                    "is_miss": 0,
                    "element_mult": 1.0,
                    "shield_absorbed": 0,
                    "status_applied": "SHIELD",
                    "message": f"🛡️ [{actor.team_side}] {actor.emoji} {actor.name} kích hoạt {ability['name']}, tạo lá chắn {shield_gain} HP cho {t.name}!"
                })
                event_order += 1

        return events, event_order

    # 2. CHIÊU TẤN CÔNG (SINGLE_ENEMY HOẶC ALL_ENEMIES)
    for t in targets:
        if not t.is_alive:
            continue

        # Kiểm tra đánh trúng (Accuracy vs Miss)
        hit_chance = (actor.accuracy * (ability.get("accuracy", 100) / 100.0))
        is_miss = random.random() * 100 > hit_chance

        if is_miss:
            events.append({
                "round_no": round_no,
                "event_order": event_order,
                "actor_side": actor.team_side,
                "actor_name": actor.name,
                "actor_slot": actor.slot_no,
                "actor_idx": actor.participant_idx,
                "target_side": t.team_side,
                "target_name": t.name,
                "target_slot": t.slot_no,
                "target_idx": t.participant_idx,
                "event_type": "ATTACK",
                "damage": 0,
                "ability_id": ability.get("id"),
                "ability_name": ability.get("name"),
                "is_crit": 0,
                "is_miss": 1,
                "element_mult": 1.0,
                "shield_absorbed": 0,
                "status_applied": None,
                "message": f"💨 [{actor.team_side}] {actor.emoji} {actor.name} dùng {ability['name']} nhưng {t.name} đã né đòn kịp thời! (MISS)"
            })
            event_order += 1
            continue

        # Tính sát thương
        ability_elem = ability.get("element", actor.element)
        elem_mult = get_element_multiplier(ability_elem, t.element)

        # Thưởng % sát thương hệ nếu tướng cùng hệ với chiêu thức
        if ability_elem == actor.element and actor.element_bonus > 0:
            elem_mult += (actor.element_bonus / 100.0)

        # Tính chí mạng
        is_crit = random.random() * 100 <= actor.crit_rate
        crit_mult = (actor.crit_damage / 100.0) if is_crit else 1.0

        raw_dmg = (actor.atk * ability.get("skill_power", 100) / 100.0)
        eff_def = max(0, t.defense - actor.armor_penetration)
        final_dmg = max(1, int(round((raw_dmg - eff_def * 0.5) * elem_mult * crit_mult)))

        # Nếu mục tiêu đang chịu MARKED (+30% dmg)
        if "MARKED" in t.status_effects:
            final_dmg = int(final_dmg * 1.3)

        # Hấp thụ bằng SHIELD trước
        absorbed = 0
        if t.shield > 0:
            absorbed = min(t.shield, final_dmg)
            t.shield -= absorbed
            final_dmg -= absorbed

        actual_hp_dmg = min(t.hp, final_dmg)
        t.hp = max(0, t.hp - actual_hp_dmg)
        actor.damage_dealt += (absorbed + actual_hp_dmg)

        # Ghi nhận trạng thái áp dụng nếu có
        status_applied = None
        st_eff = ability.get("status_effect")
        st_chance = ability.get("status_chance", 0)
        st_dur = ability.get("status_duration", 1)

        if st_eff and random.random() * 100 <= st_chance and t.is_alive:
            t.status_effects[st_eff] = st_dur
            status_applied = st_eff

        # Tạo thông điệp chi tiết
        crit_text = " 💥 CHÍ MẠNG!" if is_crit else ""
        elem_text = " (Khắc hệ x1.5!)" if elem_mult > 1.0 else (" (Bị kháng x0.75)" if elem_mult < 1.0 else "")
        shield_text = f" [Giáp chắn {absorbed}]" if absorbed > 0 else ""
        status_text = f" -> Gây hiệu ứng {status_applied}!" if status_applied else ""

        ev_type = "CRITICAL" if is_crit else ("SKILL" if ability.get("cooldown", 0) > 0 else "ATTACK")

        events.append({
            "round_no": round_no,
            "event_order": event_order,
            "actor_side": actor.team_side,
            "actor_name": actor.name,
            "actor_slot": actor.slot_no,
            "actor_idx": actor.participant_idx,
            "target_side": t.team_side,
            "target_name": t.name,
            "target_slot": t.slot_no,
            "target_idx": t.participant_idx,
            "event_type": ev_type,
            "damage": absorbed + actual_hp_dmg,
            "ability_id": ability.get("id"),
            "ability_name": ability.get("name"),
            "is_crit": 1 if is_crit else 0,
            "is_miss": 0,
            "element_mult": round(elem_mult, 2),
            "shield_absorbed": absorbed,
            "status_applied": status_applied,
            "message": f"⚔️ [{actor.team_side}] {actor.emoji} {actor.name} tung {ability.get('icon', '')} {ability['name']} vào {t.name}{elem_text}{crit_text}{shield_text} gây {absorbed + actual_hp_dmg} sát thương!{status_text}"
        })
        event_order += 1

        # Hạ gục
        if not t.is_alive:
            actor.kills += 1
            events.append({
                "round_no": round_no,
                "event_order": event_order,
                "actor_side": actor.team_side,
                "actor_name": actor.name,
                "actor_slot": actor.slot_no,
                "actor_idx": actor.participant_idx,
                "target_side": t.team_side,
                "target_name": t.name,
                "target_slot": t.slot_no,
                "target_idx": t.participant_idx,
                "event_type": "DEFEAT",
                "damage": 0,
                "ability_id": None,
                "ability_name": None,
                "is_crit": 0,
                "is_miss": 0,
                "element_mult": 1.0,
                "shield_absorbed": 0,
                "status_applied": None,
                "message": f"💀 [{t.team_side}] {t.emoji} {t.name} đã ngã xuống! (KO)"
            })
            event_order += 1

    return events, event_order


def process_end_of_round(combatants: List[Combatant], round_no: int, event_order: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    Xử lý cuối mỗi hiệp:
    - Giảm thời gian hồi chiêu của các kỹ năng
    - Thiêu đốt BURN trừ 10% HP tối đa
    - Giảm thời gian các hiệu ứng trạng thái (STUN, BURN, MARKED)
    """
    events = []
    for c in combatants:
        if not c.is_alive:
            continue

        # Giảm cooldown
        for ab in c.abilities:
            if ab.get("current_cd", 0) > 0:
                ab["current_cd"] -= 1

        # Xử lý BURN
        if "BURN" in c.status_effects:
            burn_dmg = max(5, int(c.max_hp * 0.08))
            actual_burn = min(c.hp, burn_dmg)
            c.hp = max(0, c.hp - actual_burn)

            events.append({
                "round_no": round_no,
                "event_order": event_order,
                "actor_side": c.team_side,
                "actor_name": c.name,
                "actor_slot": c.slot_no,
                "actor_idx": c.participant_idx,
                "target_side": c.team_side,
                "target_name": c.name,
                "target_slot": c.slot_no,
                "target_idx": c.participant_idx,
                "event_type": "SKILL",
                "damage": actual_burn,
                "ability_id": None,
                "ability_name": "Burn Tick",
                "is_crit": 0,
                "is_miss": 0,
                "element_mult": 1.0,
                "shield_absorbed": 0,
                "status_applied": None,
                "message": f"🔥 [{c.team_side}] {c.name} bị thiêu đốt mất {actual_burn} HP!"
            })
            event_order += 1

            if not c.is_alive:
                events.append({
                    "round_no": round_no,
                    "event_order": event_order,
                    "actor_side": c.team_side,
                    "actor_name": c.name,
                    "actor_slot": c.slot_no,
                    "actor_idx": c.participant_idx,
                    "target_side": c.team_side,
                    "target_name": c.name,
                    "target_slot": c.slot_no,
                    "target_idx": c.participant_idx,
                    "event_type": "DEFEAT",
                    "damage": 0,
                    "ability_id": None,
                    "ability_name": None,
                    "is_crit": 0,
                    "is_miss": 0,
                    "element_mult": 1.0,
                    "shield_absorbed": 0,
                    "status_applied": None,
                    "message": f"💀 [{c.team_side}] {c.name} đã ngã xuống do thiêu đốt!"
                })
                event_order += 1

        # Giảm thời hạn các trạng thái
        expired = []
        for eff, dur in c.status_effects.items():
            if dur <= 1:
                expired.append(eff)
            else:
                c.status_effects[eff] = dur - 1

        for eff in expired:
            del c.status_effects[eff]

    return events, event_order


def simulate_battle(blue_data: List[Dict[str, Any]], red_data: List[Dict[str, Any]], max_rounds: int = 25, battle_mode: str = "AUTO") -> Dict[str, Any]:
    """
    Mô phỏng trận đấu từ đầu đến cuối (sử dụng cho Auto Mode hoặc kiểm thử).
    Thứ tự lượt quyết định bởi SPEED (cao hơn đi trước).
    AI lựa chọn chiêu thức và mục tiêu tối ưu cho cả hai đội.
    """
    blue_combatants = [Combatant(h, "BLUE", slot, slot) for slot, h in enumerate(blue_data)]
    red_combatants = [Combatant(h, "RED", slot, slot + 3) for slot, h in enumerate(red_data)]
    all_combatants = blue_combatants + red_combatants

    events = []
    event_order = 1
    current_round = 0

    while current_round < max_rounds:
        current_round += 1

        alive_blue = [c for c in blue_combatants if c.is_alive]
        alive_red = [c for c in red_combatants if c.is_alive]
        if not alive_blue or not alive_red:
            break

        # Sắp xếp lượt đấu trong hiệp theo SPEED giảm dần
        round_turn_order = sorted([c for c in all_combatants if c.is_alive], key=lambda x: (x.speed, random.random()), reverse=True)

        for actor in round_turn_order:
            if not actor.is_alive:
                continue

            # Kiểm tra trạng thái STUN
            if "STUN" in actor.status_effects:
                events.append({
                    "round_no": current_round,
                    "event_order": event_order,
                    "actor_side": actor.team_side,
                    "actor_name": actor.name,
                    "actor_slot": actor.slot_no,
                    "actor_idx": actor.participant_idx,
                    "target_side": "",
                    "target_name": "",
                    "target_slot": -1,
                    "target_idx": -1,
                    "event_type": "SKILL",
                    "damage": 0,
                    "ability_id": None,
                    "ability_name": "Stunned",
                    "is_crit": 0,
                    "is_miss": 0,
                    "element_mult": 1.0,
                    "shield_absorbed": 0,
                    "status_applied": None,
                    "message": f"😵 [{actor.team_side}] {actor.emoji} {actor.name} bị choáng và mất lượt hành động!"
                })
                event_order += 1
                continue

            # Kiểm tra xem đối thủ còn ai sống không
            enemies = [c for c in all_combatants if c.team_side != actor.team_side and c.is_alive]
            if not enemies:
                break

            # AI chọn chiêu và mục tiêu
            ability, target_choice = choose_best_action(actor, all_combatants)
            targets = target_choice if isinstance(target_choice, list) else [target_choice]

            action_events, event_order = execute_action(actor, ability, targets, current_round, event_order)
            events.extend(action_events)

            if not any(c.is_alive for c in blue_combatants) or not any(c.is_alive for c in red_combatants):
                break

        # Xử lý cuối hiệp (Burn, CD, Status Duration)
        round_end_events, event_order = process_end_of_round(all_combatants, current_round, event_order)
        events.extend(round_end_events)

        if not any(c.is_alive for c in blue_combatants) or not any(c.is_alive for c in red_combatants):
            break

    # Phân định thắng bại
    alive_blue_count = sum(1 for c in blue_combatants if c.is_alive)
    alive_red_count = sum(1 for c in red_combatants if c.is_alive)
    total_blue_hp = sum(max(0, c.hp) for c in blue_combatants)
    total_red_hp = sum(max(0, c.hp) for c in red_combatants)

    if alive_blue_count > 0 and alive_red_count == 0:
        winner_team = "BLUE"
    elif alive_red_count > 0 and alive_blue_count == 0:
        winner_team = "RED"
    else:
        if total_blue_hp > total_red_hp:
            winner_team = "BLUE"
        elif total_red_hp > total_blue_hp:
            winner_team = "RED"
        else:
            winner_team = "DRAW"

    for c in blue_combatants:
        c.is_winner = 1 if winner_team == "BLUE" else 0
    for c in red_combatants:
        c.is_winner = 1 if winner_team == "RED" else 0

    # Tính phần thưởng kinh tế
    if winner_team == "BLUE":
        gold_reward = 120
        xp_reward = 120
    elif winner_team == "RED":
        gold_reward = 50
        xp_reward = 60
    else:
        gold_reward = 75
        xp_reward = 80

    end_message = (
        f"🏆 Trận đấu kết thúc! Đội {winner_team} giành chiến thắng thuyết phục sau {current_round} hiệp!"
        if winner_team != "DRAW"
        else f"⚖️ Trận đấu kết thúc với kết quả HÒA sau {current_round} hiệp đấu nảy lửa!"
    )

    events.append({
        "round_no": current_round,
        "event_order": event_order,
        "actor_side": winner_team,
        "actor_name": "Referee",
        "actor_slot": -1,
        "actor_idx": -1,
        "target_side": "",
        "target_name": "",
        "target_slot": -1,
        "target_idx": -1,
        "event_type": "MATCH_END",
        "damage": 0,
        "ability_id": None,
        "ability_name": None,
        "is_crit": 0,
        "is_miss": 0,
        "element_mult": 1.0,
        "shield_absorbed": 0,
        "status_applied": None,
        "message": end_message
    })

    return {
        "battle_mode": battle_mode,
        "winner_team": winner_team,
        "total_rounds": current_round,
        "gold_reward": gold_reward,
        "xp_reward": xp_reward,
        "blue_participants": [c.to_participant_record() for c in blue_combatants],
        "red_participants": [c.to_participant_record() for c in red_combatants],
        "events": events
    }


# ==========================================================================
# TACTICAL BATTLE SESSION MANAGER (ĐIỀU KHIỂN CHIẾN THUẬT THEO LƯỢT)
# ==========================================================================
class TacticalBattleManager:
    """Quản lý phiên đấu tương tác Tactical Mode giữa người chơi và backend."""

    @staticmethod
    def create_battle(blue_data: List[Dict[str, Any]], red_data: List[Dict[str, Any]], db_path: Optional[str] = None) -> Dict[str, Any]:
        """Khởi tạo một trận đấu Tactical Mode mới và lưu vào bảng active_tactical_battles."""
        blue_combatants = [Combatant(h, "BLUE", slot, slot) for slot, h in enumerate(blue_data)]
        red_combatants = [Combatant(h, "RED", slot, slot + 3) for slot, h in enumerate(red_data)]
        all_combatants = blue_combatants + red_combatants

        # Tạo hàng đợi lượt theo SPEED
        turn_queue = [c.participant_idx for c in sorted(all_combatants, key=lambda x: x.speed, reverse=True)]

        battle_state = {
            "round_no": 1,
            "event_order": 1,
            "max_rounds": 25,
            "turn_queue": turn_queue,
            "turn_index": 0,
            "combatants": [c.to_dict() for c in all_combatants],
            "accumulated_events": [],
            "status": "IN_PROGRESS",  # 'IN_PROGRESS', 'WAITING_PLAYER', 'COMPLETED'
            "winner_team": None
        }

        # Lưu vào SQLite
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO active_tactical_battles (battle_state_json) VALUES (?);",
                    (json.dumps(battle_state),)
                )
                battle_id = cur.lastrowid
        finally:
            conn.close()

        # Chạy lượt ban đầu cho đến khi đến lượt người chơi hoặc kết thúc
        return TacticalBattleManager.advance_until_player_turn(battle_id, db_path)

    @staticmethod
    def advance_until_player_turn(battle_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Tự động thực hiện các lượt của đối thủ RED cho đến khi tới lượt tướng của BLUE hoặc hết trận."""
        conn = get_db_connection(db_path)
        try:
            with conn:
                row = conn.execute("SELECT battle_state_json FROM active_tactical_battles WHERE id = ?;", (battle_id,)).fetchone()
                if not row:
                    return {"success": False, "error": "Phiên đấu không tồn tại"}

                state = json.loads(row["battle_state_json"])
                combatants = [Combatant(c, c["team_side"], c["slot_no"], c["participant_idx"]) for c in state["combatants"]]
                # Restore runtime stats
                for idx, c in enumerate(combatants):
                    c_data = state["combatants"][idx]
                    c.hp = c_data["hp"]
                    c.shield = c_data.get("shield", 0)
                    c.status_effects = c_data.get("status_effects", {})
                    c.abilities = c_data.get("abilities", [])
                    c.damage_dealt = c_data.get("damage_dealt", 0)
                    c.kills = c_data.get("kills", 0)

                events_this_step = []

                while state["status"] == "IN_PROGRESS":
                    # Kiểm tra kết thúc trận
                    alive_blue = [c for c in combatants if c.team_side == "BLUE" and c.is_alive]
                    alive_red = [c for c in combatants if c.team_side == "RED" and c.is_alive]

                    if not alive_blue or not alive_red or state["round_no"] > state["max_rounds"]:
                        # Kết thúc trận
                        TacticalBattleManager._finalize_battle(state, combatants, events_this_step, conn)
                        break

                    # Nếu hết hàng đợi lượt trong hiệp, sang hiệp mới
                    if state["turn_index"] >= len(state["turn_queue"]):
                        # Xử lý cuối hiệp
                        end_events, state["event_order"] = process_end_of_round(combatants, state["round_no"], state["event_order"])
                        events_this_step.extend(end_events)
                        state["round_no"] += 1

                        # Kiểm tra lại sau burn
                        alive_blue = [c for c in combatants if c.team_side == "BLUE" and c.is_alive]
                        alive_red = [c for c in combatants if c.team_side == "RED" and c.is_alive]
                        if not alive_blue or not alive_red or state["round_no"] > state["max_rounds"]:
                            TacticalBattleManager._finalize_battle(state, combatants, events_this_step, conn)
                            break

                        # Sắp xếp lượt mới
                        state["turn_queue"] = [c.participant_idx for c in sorted([c for c in combatants if c.is_alive], key=lambda x: x.speed, reverse=True)]
                        state["turn_index"] = 0
                        continue

                    # Lấy tướng hành động hiện tại
                    actor_idx = state["turn_queue"][state["turn_index"]]
                    actor = next((c for c in combatants if c.participant_idx == actor_idx), None)

                    if not actor or not actor.is_alive:
                        state["turn_index"] += 1
                        continue

                    # Kiểm tra STUN
                    if "STUN" in actor.status_effects:
                        events_this_step.append({
                            "round_no": state["round_no"],
                            "event_order": state["event_order"],
                            "actor_side": actor.team_side,
                            "actor_name": actor.name,
                            "actor_slot": actor.slot_no,
                            "actor_idx": actor.participant_idx,
                            "target_side": "",
                            "target_name": "",
                            "target_slot": -1,
                            "target_idx": -1,
                            "event_type": "SKILL",
                            "damage": 0,
                            "message": f"😵 [{actor.team_side}] {actor.emoji} {actor.name} bị choáng và mất lượt!"
                        })
                        state["event_order"] += 1
                        state["turn_index"] += 1
                        continue

                    # NẾU LÀ ĐỘI BLUE (NGƯỜI CHƠI) -> DỪNG LẠI CHỜ INPUT
                    if actor.team_side == "BLUE":
                        state["status"] = "WAITING_PLAYER"
                        state["active_actor_idx"] = actor.participant_idx
                        break

                    # NẾU LÀ ĐỘI RED (AI) -> TỰ ĐỘNG CHỌN VÀ THỰC HIỆN
                    ability, target_choice = choose_best_action(actor, combatants)
                    targets = target_choice if isinstance(target_choice, list) else [target_choice]

                    action_events, state["event_order"] = execute_action(actor, ability, targets, state["round_no"], state["event_order"])
                    events_this_step.extend(action_events)
                    state["turn_index"] += 1

                # Cập nhật lại state trong database
                state["combatants"] = [c.to_dict() for c in combatants]
                state["accumulated_events"].extend(events_this_step)

                conn.execute(
                    "UPDATE active_tactical_battles SET battle_state_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (json.dumps(state), battle_id)
                )

                # Tìm active actor nếu đang chờ player
                active_actor = None
                if state["status"] == "WAITING_PLAYER":
                    active_actor = next((c.to_dict() for c in combatants if c.participant_idx == state["active_actor_idx"]), None)

                return {
                    "success": True,
                    "battle_id": battle_id,
                    "status": state["status"],
                    "round_no": state["round_no"],
                    "active_actor": active_actor,
                    "combatants": [c.to_dict() for c in combatants],
                    "new_events": events_this_step,
                    "winner_team": state.get("winner_team"),
                    "match_id": state.get("saved_match_id")
                }
        finally:
            conn.close()

    @staticmethod
    def execute_player_action(battle_id: int, ability_id: int, target_idx: int, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Thực hiện lệnh điều khiển của người chơi và tiếp tục chuyển giao cho AI."""
        conn = get_db_connection(db_path)
        try:
            with conn:
                row = conn.execute("SELECT battle_state_json FROM active_tactical_battles WHERE id = ?;", (battle_id,)).fetchone()
                if not row:
                    return {"success": False, "error": "Phiên đấu không tồn tại"}

                state = json.loads(row["battle_state_json"])
                if state["status"] != "WAITING_PLAYER":
                    return {"success": False, "error": "Trận đấu chưa sẵn sàng nhận lệnh từ người chơi"}

                combatants = [Combatant(c, c["team_side"], c["slot_no"], c["participant_idx"]) for c in state["combatants"]]
                for idx, c in enumerate(combatants):
                    c_data = state["combatants"][idx]
                    c.hp = c_data["hp"]
                    c.shield = c_data.get("shield", 0)
                    c.status_effects = c_data.get("status_effects", {})
                    c.abilities = c_data.get("abilities", [])
                    c.damage_dealt = c_data.get("damage_dealt", 0)
                    c.kills = c_data.get("kills", 0)

                actor_idx = state.get("active_actor_idx")
                actor = next((c for c in combatants if c.participant_idx == actor_idx), None)
                if not actor:
                    return {"success": False, "error": "Không tìm thấy tướng đang đến lượt"}

                # Tìm chiêu thức
                ability = next((ab for ab in actor.abilities if ab.get("id") == ability_id or ab.get("name") == str(ability_id)), None)
                if not ability:
                    return {"success": False, "error": "Chiêu thức không hợp lệ"}

                if ability.get("current_cd", 0) > 0:
                    return {"success": False, "error": f"Kỹ năng đang hồi chiêu ({ability['current_cd']} hiệp)!"}

                # Xác định mục tiêu
                target_type = ability.get("target_type", "SINGLE_ENEMY")
                if target_type == "ALL_ENEMIES":
                    targets = [c for c in combatants if c.team_side != actor.team_side and c.is_alive]
                elif target_type == "SELF":
                    targets = [actor]
                else:
                    target = next((c for c in combatants if c.participant_idx == target_idx and c.is_alive), None)
                    if not target:
                        return {"success": False, "error": "Mục tiêu không hợp lệ hoặc đã bị hạ gục"}
                    targets = [target]

                # Thực hiện hành động của người chơi
                player_events, state["event_order"] = execute_action(actor, ability, targets, state["round_no"], state["event_order"])
                state["turn_index"] += 1
                state["status"] = "IN_PROGRESS"
                state["combatants"] = [c.to_dict() for c in combatants]
                state["accumulated_events"].extend(player_events)

                conn.execute(
                    "UPDATE active_tactical_battles SET battle_state_json = ? WHERE id = ?;",
                    (json.dumps(state), battle_id)
                )

            # Tiếp tục cho đến lượt người chơi tiếp theo hoặc hết trận
            result = TacticalBattleManager.advance_until_player_turn(battle_id, db_path)
            # Gộp các sự kiện vừa do người chơi gây ra vào đầu new_events
            if result.get("success"):
                result["new_events"] = player_events + result.get("new_events", [])
            return result
        finally:
            conn.close()

    @staticmethod
    def _finalize_battle(state: Dict[str, Any], combatants: List[Combatant], events: List[Dict[str, Any]], conn: sqlite3.Connection) -> None:
        """Kết thúc trận đấu Tactical, phân định thắng bại và lưu vào matches bằng database transaction."""
        state["status"] = "COMPLETED"

        blue_c = [c for c in combatants if c.team_side == "BLUE"]
        red_c = [c for c in combatants if c.team_side == "RED"]

        alive_blue = sum(1 for c in blue_c if c.is_alive)
        alive_red = sum(1 for c in red_c if c.is_alive)
        total_blue_hp = sum(max(0, c.hp) for c in blue_c)
        total_red_hp = sum(max(0, c.hp) for c in red_c)

        if alive_blue > 0 and alive_red == 0:
            winner = "BLUE"
        elif alive_red > 0 and alive_blue == 0:
            winner = "RED"
        else:
            if total_blue_hp > total_red_hp:
                winner = "BLUE"
            elif total_red_hp > total_blue_hp:
                winner = "RED"
            else:
                winner = "DRAW"

        state["winner_team"] = winner

        for c in blue_c:
            c.is_winner = 1 if winner == "BLUE" else 0
        for c in red_c:
            c.is_winner = 1 if winner == "RED" else 0

        end_msg = (
            f"🏆 Chiến thắng vang dội! Đội {winner} đã ca khúc khải hoàn sau {state['round_no']} hiệp!"
            if winner != "DRAW"
            else f"⚖️ Trận đấu kết thúc với kết quả HÒA sau {state['round_no']} hiệp kịch tính!"
        )

        match_end_ev = {
            "round_no": state["round_no"],
            "event_order": state["event_order"],
            "actor_side": winner,
            "actor_name": "Referee",
            "actor_slot": -1,
            "actor_idx": -1,
            "target_side": "",
            "target_name": "",
            "target_slot": -1,
            "target_idx": -1,
            "event_type": "MATCH_END",
            "damage": 0,
            "message": end_msg
        }
        events.append(match_end_ev)

        # Lưu vào database
        gold_rew = 120 if winner == "BLUE" else (50 if winner == "RED" else 75)
        xp_rew = 120 if winner == "BLUE" else (60 if winner == "RED" else 80)

        battle_result = {
            "battle_mode": "TACTICAL",
            "winner_team": winner,
            "total_rounds": state["round_no"],
            "gold_reward": gold_rew,
            "xp_reward": xp_rew,
            "blue_participants": [c.to_participant_record() for c in blue_c],
            "red_participants": [c.to_participant_record() for c in red_c],
            "events": state["accumulated_events"] + events
        }

        # Lưu thông qua save_battle_result
        from database import save_battle_result
        saved_id = save_battle_result(battle_result)
        state["saved_match_id"] = saved_id
