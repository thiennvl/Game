"""
Analytics module for Tactical Battle Arena & Meta Tracker.
Provides SQL-based data analytics for heroes, abilities, elements,
team compositions, equipment meta, economy ledgers, and match history.
"""

from typing import Dict, Any, List, Optional
from database import get_db_connection


def get_overview_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Tính toán các chỉ số tổng quan của toàn bộ đấu trường bằng SQL.
    Bao gồm tổng số trận, số trận thắng/thua/hòa của người chơi (BLUE),
    tỉ lệ thắng, tướng được pick nhiều nhất, tướng có tỉ lệ thắng cao nhất,
    và tổng quan kinh tế (Gold kiếm được / đã tiêu).
    """
    conn = get_db_connection(db_path)
    try:
        summary_query = """
            SELECT 
                COUNT(*) AS total_matches,
                COALESCE(SUM(CASE WHEN winner_team = 'BLUE' THEN 1 ELSE 0 END), 0) AS player_wins,
                COALESCE(SUM(CASE WHEN winner_team = 'RED' THEN 1 ELSE 0 END), 0) AS player_losses,
                COALESCE(SUM(CASE WHEN winner_team = 'DRAW' THEN 1 ELSE 0 END), 0) AS player_draws,
                CASE 
                    WHEN COUNT(*) > 0 THEN ROUND(100.0 * SUM(CASE WHEN winner_team = 'BLUE' THEN 1 ELSE 0 END) / COUNT(*), 1)
                    ELSE 0.0 
                END AS player_win_rate,
                COALESCE(SUM(CASE WHEN battle_mode = 'TACTICAL' THEN 1 ELSE 0 END), 0) AS tactical_matches,
                COALESCE(SUM(CASE WHEN battle_mode = 'AUTO' THEN 1 ELSE 0 END), 0) AS auto_matches
            FROM matches;
        """
        summary_row = conn.execute(summary_query).fetchone()
        stats = dict(summary_row) if summary_row else {
            "total_matches": 0,
            "player_wins": 0,
            "player_losses": 0,
            "player_draws": 0,
            "player_win_rate": 0.0,
            "tactical_matches": 0,
            "auto_matches": 0
        }

        # Tướng được pick nhiều nhất
        most_picked_query = """
            SELECT h.name, h.emoji, h.element, COUNT(mp.id) AS pick_count
            FROM match_participants mp
            JOIN heroes h ON mp.hero_id = h.id
            GROUP BY h.id, h.name, h.emoji, h.element
            ORDER BY pick_count DESC, h.name ASC
            LIMIT 1;
        """
        most_picked_row = conn.execute(most_picked_query).fetchone()
        stats["most_picked_hero"] = dict(most_picked_row) if most_picked_row else None

        # Tướng có tỉ lệ thắng cao nhất (xét các tướng có xuất hiện ít nhất 1 lần)
        highest_winrate_query = """
            SELECT 
                h.name, 
                h.emoji, 
                h.element,
                COUNT(mp.id) AS total_picks,
                SUM(mp.is_winner) AS total_wins,
                ROUND(100.0 * SUM(mp.is_winner) / COUNT(mp.id), 1) AS win_rate
            FROM match_participants mp
            JOIN heroes h ON mp.hero_id = h.id
            GROUP BY h.id, h.name, h.emoji, h.element
            HAVING COUNT(mp.id) > 0
            ORDER BY win_rate DESC, total_picks DESC
            LIMIT 1;
        """
        highest_winrate_row = conn.execute(highest_winrate_query).fetchone()
        stats["highest_winrate_hero"] = dict(highest_winrate_row) if highest_winrate_row else None

        # Tổng quan kinh tế
        econ_query = """
            SELECT 
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_gold_earned,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_gold_spent
            FROM currency_transactions;
        """
        econ_row = conn.execute(econ_query).fetchone()
        if econ_row:
            stats["total_gold_earned"] = econ_row["total_gold_earned"]
            stats["total_gold_spent"] = econ_row["total_gold_spent"]
        else:
            stats["total_gold_earned"] = 0
            stats["total_gold_spent"] = 0

        # Số lượt quay Lucky Wheel
        spins_count = conn.execute("SELECT COUNT(*) FROM wheel_spin_history;").fetchone()[0]
        stats["total_wheel_spins"] = spins_count

        return stats
    finally:
        conn.close()


def get_hero_analytics(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Phân tích hiệu năng từng tướng bằng SQL:
    - Số lần xuất hiện (picks), số trận thắng, Win rate
    - Tổng sát thương, sát thương trung bình mỗi trận
    - Tổng số mạng hạ gục (kills), hệ nguyên tố và cấp độ hiện tại
    """
    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT 
                h.id AS hero_id,
                h.name,
                h.role,
                h.element,
                h.emoji,
                h.base_hp,
                h.base_atk,
                h.base_def,
                h.base_speed,
                COALESCE(hp.level, 1) as current_level,
                COUNT(mp.id) AS total_picks,
                COALESCE(SUM(mp.is_winner), 0) AS total_wins,
                CASE 
                    WHEN COUNT(mp.id) > 0 THEN ROUND(100.0 * SUM(mp.is_winner) / COUNT(mp.id), 1)
                    ELSE 0.0 
                END AS win_rate,
                COALESCE(SUM(mp.damage_dealt), 0) AS total_damage,
                CASE 
                    WHEN COUNT(mp.id) > 0 THEN ROUND(1.0 * SUM(mp.damage_dealt) / COUNT(mp.id), 1)
                    ELSE 0.0 
                END AS avg_damage,
                COALESCE(SUM(mp.kills), 0) AS total_kills,
                CASE 
                    WHEN COUNT(mp.id) > 0 THEN ROUND(1.0 * SUM(mp.kills) / COUNT(mp.id), 1)
                    ELSE 0.0 
                END AS avg_kills
            FROM heroes h
            LEFT JOIN match_participants mp ON h.id = mp.hero_id
            LEFT JOIN hero_progress hp ON h.id = hp.hero_id AND hp.player_id = 1
            WHERE h.is_active = 1
            GROUP BY h.id, h.name, h.role, h.element, h.emoji, h.base_hp, h.base_atk, h.base_def, h.base_speed, hp.level
            ORDER BY total_picks DESC, win_rate DESC, h.name ASC;
        """
        cur = conn.execute(query)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_element_analytics(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Phân tích tỉ lệ thắng và hiệu năng theo từng hệ nguyên tố (FIRE, WATER, NATURE)."""
    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT 
                h.element,
                COUNT(mp.id) AS total_picks,
                COALESCE(SUM(mp.is_winner), 0) AS total_wins,
                CASE 
                    WHEN COUNT(mp.id) > 0 THEN ROUND(100.0 * SUM(mp.is_winner) / COUNT(mp.id), 1)
                    ELSE 0.0 
                END AS win_rate,
                COALESCE(SUM(mp.damage_dealt), 0) AS total_damage,
                CASE 
                    WHEN COUNT(mp.id) > 0 THEN ROUND(1.0 * SUM(mp.damage_dealt) / COUNT(mp.id), 1)
                    ELSE 0.0 
                END AS avg_damage
            FROM heroes h
            JOIN match_participants mp ON h.id = mp.hero_id
            GROUP BY h.element
            ORDER BY total_picks DESC;
        """
        cur = conn.execute(query)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_composition_analytics(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Phân tích đội hình (3 tướng) bằng SQL:
    Chuẩn hóa đội hình bằng cách sắp xếp tên tướng theo alphabet qua CTE,
    đảm bảo cùng một bộ 3 tướng luôn được gom thành 1 đội hình duy nhất.
    """
    conn = get_db_connection(db_path)
    try:
        query = """
            WITH team_heroes AS (
                SELECT 
                    mp.match_id, 
                    mp.team_side, 
                    mp.is_winner, 
                    h.name,
                    h.emoji
                FROM match_participants mp
                JOIN heroes h ON mp.hero_id = h.id
                ORDER BY mp.match_id, mp.team_side, h.name ASC
            ),
            team_compositions AS (
                SELECT 
                    match_id, 
                    team_side, 
                    is_winner,
                    GROUP_CONCAT(name, ' + ') AS comp_name,
                    GROUP_CONCAT(emoji, ' ') AS comp_emojis
                FROM team_heroes
                GROUP BY match_id, team_side
                HAVING COUNT(name) = 3
            )
            SELECT 
                comp_name,
                comp_emojis,
                COUNT(*) AS total_matches,
                SUM(is_winner) AS wins,
                ROUND(100.0 * SUM(is_winner) / COUNT(*), 1) AS win_rate
            FROM team_compositions
            GROUP BY comp_name, comp_emojis
            ORDER BY total_matches DESC, win_rate DESC
            LIMIT ?;
        """
        cur = conn.execute(query, (limit,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_equipment_meta_analytics(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Thống kê tần suất sở hữu và nâng cấp các món trang bị trong kho đồ người chơi."""
    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT 
                ec.id as catalog_id,
                ec.name,
                ec.slot_type,
                ec.rarity,
                ec.icon,
                COUNT(ii.id) as total_owned,
                COALESCE(SUM(CASE WHEN ii.is_equipped = 1 THEN 1 ELSE 0 END), 0) as currently_equipped,
                ROUND(AVG(ii.upgrade_level), 1) as avg_upgrade_level
            FROM equipment_catalog ec
            LEFT JOIN inventory_items ii ON ec.id = ii.equipment_id AND ii.player_id = 1
            WHERE ec.is_active = 1
            GROUP BY ec.id, ec.name, ec.slot_type, ec.rarity, ec.icon
            HAVING total_owned > 0
            ORDER BY currently_equipped DESC, total_owned DESC;
        """
        cur = conn.execute(query)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_wheel_distribution_analytics(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Thống kê phân phối phần thưởng thực tế nhận được từ Vòng Quay May Mắn."""
    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT 
                rarity,
                reward_type,
                COUNT(*) as count,
                ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM wheel_spin_history WHERE player_id = 1), 1) as actual_percentage
            FROM wheel_spin_history
            WHERE player_id = 1
            GROUP BY rarity, reward_type
            ORDER BY count DESC;
        """
        cur = conn.execute(query)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_recent_matches(limit: int = 25, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách các trận đấu gần nhất kèm chế độ chơi (Tactical / Auto) và phần thưởng."""
    conn = get_db_connection(db_path)
    try:
        query = """
            SELECT 
                m.id,
                m.created_at,
                m.winner_team,
                m.total_rounds,
                m.status,
                COALESCE(m.battle_mode, 'AUTO') as battle_mode,
                COALESCE(m.gold_reward, 0) as gold_reward,
                COALESCE(m.xp_reward, 0) as xp_reward,
                (
                    SELECT GROUP_CONCAT(h.emoji || ' ' || h.name, ' | ')
                    FROM match_participants mp
                    JOIN heroes h ON mp.hero_id = h.id
                    WHERE mp.match_id = m.id AND mp.team_side = 'BLUE'
                    ORDER BY mp.slot_no ASC
                ) AS blue_lineup,
                (
                    SELECT GROUP_CONCAT(h.emoji || ' ' || h.name, ' | ')
                    FROM match_participants mp
                    JOIN heroes h ON mp.hero_id = h.id
                    WHERE mp.match_id = m.id AND mp.team_side = 'RED'
                    ORDER BY mp.slot_no ASC
                ) AS red_lineup
            FROM matches m
            ORDER BY m.id DESC
            LIMIT ?;
        """
        cur = conn.execute(query, (limit,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_match_detail(match_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Lấy chi tiết toàn bộ một trận đấu: đội hình, cấp độ, trang bị và toàn bộ Battle Events."""
    conn = get_db_connection(db_path)
    try:
        match_cur = conn.execute("SELECT * FROM matches WHERE id = ?;", (match_id,))
        match_row = match_cur.fetchone()
        if not match_row:
            return None
        match_data = dict(match_row)

        # Các tướng tham gia
        part_query = """
            SELECT 
                mp.id AS participant_id,
                mp.match_id,
                mp.hero_id,
                mp.team_side,
                mp.slot_no,
                mp.hp_start,
                mp.hp_end,
                mp.damage_dealt,
                mp.kills,
                mp.is_winner,
                COALESCE(mp.hero_level, 1) as hero_level,
                COALESCE(mp.element, h.element) as element,
                mp.equipment_snapshot,
                h.name,
                h.role,
                h.emoji
            FROM match_participants mp
            JOIN heroes h ON mp.hero_id = h.id
            WHERE mp.match_id = ?
            ORDER BY mp.team_side DESC, mp.slot_no ASC;
        """
        part_cur = conn.execute(part_query, (match_id,))
        participants = [dict(r) for r in part_cur.fetchall()]

        match_data["blue_participants"] = [p for p in participants if p["team_side"] == "BLUE"]
        match_data["red_participants"] = [p for p in participants if p["team_side"] == "RED"]

        # Toàn bộ sự kiện
        events_query = """
            SELECT 
                be.id,
                be.match_id,
                be.round_no,
                be.event_order,
                be.actor_participant_id,
                be.target_participant_id,
                be.event_type,
                be.damage,
                be.message,
                be.created_at,
                be.ability_name,
                be.is_crit,
                be.is_miss,
                be.element_mult,
                be.shield_absorbed,
                be.status_applied,
                h_actor.name AS actor_name,
                h_actor.emoji AS actor_emoji,
                mp_actor.team_side AS actor_side,
                mp_actor.slot_no AS actor_slot,
                h_target.name AS target_name,
                h_target.emoji AS target_emoji,
                mp_target.team_side AS target_side,
                mp_target.slot_no AS target_slot
            FROM battle_events be
            LEFT JOIN match_participants mp_actor ON be.actor_participant_id = mp_actor.id
            LEFT JOIN heroes h_actor ON mp_actor.hero_id = h_actor.id
            LEFT JOIN match_participants mp_target ON be.target_participant_id = mp_target.id
            LEFT JOIN heroes h_target ON mp_target.hero_id = h_target.id
            WHERE be.match_id = ?
            ORDER BY be.event_order ASC;
        """
        events_cur = conn.execute(events_query, (match_id,))
        match_data["events"] = [dict(r) for r in events_cur.fetchall()]

        return match_data
    finally:
        conn.close()
