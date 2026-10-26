"""
Database module for Tactical Battle Arena & Meta Tracker.
Handles SQLite schema creation, migrations, seed data, and atomic transactions.
"""

import os
import json
import sqlite3
from typing import Optional, List, Dict, Any

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
DB_PATH = os.path.join(DB_DIR, "arena.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Tạo kết nối tới SQLite database.
    Bật foreign keys PRAGMA để đảm bảo toàn vẹn dữ liệu quan hệ.
    Sử dụng sqlite3.Row để truy cập kết quả theo tên cột giống dict.
    """
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column_exists(conn: sqlite3.Connection, table_name: str, col_name: str, col_def: str) -> None:
    """Thêm cột mới vào bảng nếu cột chưa tồn tại (Migration an toàn không mất dữ liệu cũ)."""
    cur = conn.execute(f"PRAGMA table_info({table_name});")
    existing_cols = [row["name"] for row in cur.fetchall()]
    if col_name not in existing_cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};")


def init_db(db_path: Optional[str] = None) -> None:
    """
    Khởi tạo cấu trúc các bảng và chạy migration nâng cấp an toàn.
    Đảm bảo tính idempotent: giữ nguyên lịch sử trận đấu và dữ liệu cũ.
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            # ==============================================================
            # 1. BẢNG CỐT LÕI (CORE TABLES)
            # ==============================================================
            # Bảng heroes: Lưu thông tin các vị tướng
            conn.execute("""
                CREATE TABLE IF NOT EXISTS heroes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL,
                    base_hp INTEGER NOT NULL,
                    base_atk INTEGER NOT NULL,
                    skill_name TEXT NOT NULL,
                    skill_description TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
            """)

            # Migration cho bảng heroes (thêm element, def, speed, accuracy, crit)
            ensure_column_exists(conn, "heroes", "element", "TEXT NOT NULL DEFAULT 'NATURE'")
            ensure_column_exists(conn, "heroes", "base_def", "INTEGER NOT NULL DEFAULT 15")
            ensure_column_exists(conn, "heroes", "base_speed", "INTEGER NOT NULL DEFAULT 20")
            ensure_column_exists(conn, "heroes", "base_accuracy", "INTEGER NOT NULL DEFAULT 95")
            ensure_column_exists(conn, "heroes", "base_crit_rate", "REAL NOT NULL DEFAULT 5.0")
            ensure_column_exists(conn, "heroes", "base_crit_damage", "REAL NOT NULL DEFAULT 150.0")

            # Bảng matches: Lưu kết quả trận đấu
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    winner_team TEXT NOT NULL CHECK(winner_team IN ('BLUE', 'RED', 'DRAW')),
                    total_rounds INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'COMPLETED'
                );
            """)

            # Migration cho bảng matches
            ensure_column_exists(conn, "matches", "battle_mode", "TEXT NOT NULL DEFAULT 'AUTO'")
            ensure_column_exists(conn, "matches", "gold_reward", "INTEGER NOT NULL DEFAULT 0")
            ensure_column_exists(conn, "matches", "xp_reward", "INTEGER NOT NULL DEFAULT 0")

            # Bảng match_participants: 6 tướng tham gia mỗi trận
            conn.execute("""
                CREATE TABLE IF NOT EXISTS match_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    hero_id INTEGER NOT NULL REFERENCES heroes(id),
                    team_side TEXT NOT NULL CHECK(team_side IN ('BLUE', 'RED')),
                    slot_no INTEGER NOT NULL CHECK(slot_no IN (0, 1, 2)),
                    hp_start INTEGER NOT NULL,
                    hp_end INTEGER NOT NULL,
                    damage_dealt INTEGER NOT NULL DEFAULT 0,
                    kills INTEGER NOT NULL DEFAULT 0,
                    is_winner INTEGER NOT NULL DEFAULT 0 CHECK(is_winner IN (0, 1))
                );
            """)

            # Migration cho bảng match_participants
            ensure_column_exists(conn, "match_participants", "hero_level", "INTEGER NOT NULL DEFAULT 1")
            ensure_column_exists(conn, "match_participants", "equipment_snapshot", "TEXT NOT NULL DEFAULT '[]'")
            ensure_column_exists(conn, "match_participants", "element", "TEXT NOT NULL DEFAULT 'NATURE'")

            # Bảng battle_events: Nhật ký sự kiện chi tiết
            conn.execute("""
                CREATE TABLE IF NOT EXISTS battle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    round_no INTEGER NOT NULL,
                    event_order INTEGER NOT NULL,
                    actor_participant_id INTEGER REFERENCES match_participants(id),
                    target_participant_id INTEGER REFERENCES match_participants(id),
                    event_type TEXT NOT NULL,
                    damage INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Migration cho bảng battle_events
            ensure_column_exists(conn, "battle_events", "ability_id", "INTEGER DEFAULT NULL")
            ensure_column_exists(conn, "battle_events", "ability_name", "TEXT DEFAULT NULL")
            ensure_column_exists(conn, "battle_events", "is_crit", "INTEGER NOT NULL DEFAULT 0")
            ensure_column_exists(conn, "battle_events", "is_miss", "INTEGER NOT NULL DEFAULT 0")
            ensure_column_exists(conn, "battle_events", "element_mult", "REAL NOT NULL DEFAULT 1.0")
            ensure_column_exists(conn, "battle_events", "shield_absorbed", "INTEGER NOT NULL DEFAULT 0")
            ensure_column_exists(conn, "battle_events", "status_applied", "TEXT DEFAULT NULL")

            # ==============================================================
            # 2. BẢNG TIẾN TRÌNH & HỒ SƠ NGƯỜI CHƠI (PROFILE & PROGRESSION)
            # ==============================================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS player_profile (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gold INTEGER NOT NULL DEFAULT 800,
                    player_level INTEGER NOT NULL DEFAULT 1,
                    player_xp INTEGER NOT NULL DEFAULT 0,
                    pity_counter INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Seed player profile mặc định (800 Gold) nếu chưa có
            cur_p = conn.execute("SELECT COUNT(*) FROM player_profile;")
            if cur_p.fetchone()[0] == 0:
                conn.execute("INSERT INTO player_profile (id, gold, player_level, player_xp, pity_counter) VALUES (1, 800, 1, 0, 0);")

            # Bảng player_materials: Lưu các loại nguyên liệu nâng cấp
            conn.execute("""
                CREATE TABLE IF NOT EXISTS player_materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL REFERENCES player_profile(id) ON DELETE CASCADE,
                    material_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(player_id, material_type)
                );
            """)

            # Seed nguyên liệu ban đầu
            default_materials = [
                (1, "UPGRADE_STONE", 6),
                (1, "ELEMENT_CRYSTAL", 2),
                (1, "LUCKY_TICKET", 3)
            ]
            conn.executemany("""
                INSERT OR IGNORE INTO player_materials (player_id, material_type, quantity)
                VALUES (?, ?, ?);
            """, default_materials)

            # Bảng hero_progress: Cấp độ và XP riêng cho từng tướng
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hero_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL REFERENCES player_profile(id) ON DELETE CASCADE,
                    hero_id INTEGER NOT NULL REFERENCES heroes(id) ON DELETE CASCADE,
                    level INTEGER NOT NULL DEFAULT 1,
                    xp INTEGER NOT NULL DEFAULT 0,
                    rank INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(player_id, hero_id)
                );
            """)

            # ==============================================================
            # 3. HỆ THỐNG CHIÊU THỨC (POKÉMON-LIKE ABILITIES)
            # ==============================================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS abilities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    element TEXT NOT NULL CHECK(element IN ('FIRE', 'WATER', 'NATURE', 'NEUTRAL')),
                    skill_power INTEGER NOT NULL DEFAULT 100,
                    target_type TEXT NOT NULL CHECK(target_type IN ('SINGLE_ENEMY', 'ALL_ENEMIES', 'SINGLE_ALLY', 'SELF')),
                    accuracy INTEGER NOT NULL DEFAULT 100,
                    cooldown INTEGER NOT NULL DEFAULT 0,
                    status_effect TEXT DEFAULT NULL CHECK(status_effect IN ('BURN', 'STUN', 'SHIELD', 'MARKED', 'HEAL', NULL)),
                    status_chance INTEGER NOT NULL DEFAULT 0,
                    status_duration INTEGER NOT NULL DEFAULT 0,
                    icon TEXT NOT NULL DEFAULT '⚡'
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS hero_abilities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hero_id INTEGER NOT NULL REFERENCES heroes(id) ON DELETE CASCADE,
                    ability_id INTEGER NOT NULL REFERENCES abilities(id) ON DELETE CASCADE,
                    slot_order INTEGER NOT NULL CHECK(slot_order IN (1, 2, 3, 4)),
                    UNIQUE(hero_id, slot_order),
                    UNIQUE(hero_id, ability_id)
                );
            """)

            # ==============================================================
            # 4. HỆ THỐNG TRANG BỊ & KHO ĐỒ (FREE FIRE-INSPIRED EQUIPMENT)
            # ==============================================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS equipment_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    slot_type TEXT NOT NULL CHECK(slot_type IN ('WEAPON', 'ARMOR', 'BOOTS', 'ACCESSORY', 'MATERIAL')),
                    rarity TEXT NOT NULL CHECK(rarity IN ('COMMON', 'RARE', 'EPIC', 'LEGENDARY')),
                    bonus_atk INTEGER NOT NULL DEFAULT 0,
                    bonus_def INTEGER NOT NULL DEFAULT 0,
                    bonus_hp INTEGER NOT NULL DEFAULT 0,
                    bonus_speed INTEGER NOT NULL DEFAULT 0,
                    bonus_accuracy INTEGER NOT NULL DEFAULT 0,
                    bonus_crit_rate REAL NOT NULL DEFAULT 0.0,
                    bonus_crit_damage REAL NOT NULL DEFAULT 0.0,
                    armor_penetration INTEGER NOT NULL DEFAULT 0,
                    element_bonus REAL NOT NULL DEFAULT 0.0,
                    price INTEGER NOT NULL DEFAULT 100,
                    max_upgrade_level INTEGER NOT NULL DEFAULT 5,
                    icon TEXT NOT NULL DEFAULT '🗡️',
                    description TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL REFERENCES player_profile(id) ON DELETE CASCADE,
                    equipment_id INTEGER NOT NULL REFERENCES equipment_catalog(id) ON DELETE CASCADE,
                    upgrade_level INTEGER NOT NULL DEFAULT 0,
                    is_equipped INTEGER NOT NULL DEFAULT 0 CHECK(is_equipped IN (0, 1)),
                    equipped_hero_id INTEGER DEFAULT NULL REFERENCES heroes(id),
                    equipped_slot TEXT DEFAULT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # ==============================================================
            # 5. KINH TẾ, GIAO DỊCH & VÒNG QUAY (ECONOMY & LUCKY WHEEL)
            # ==============================================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS currency_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL REFERENCES player_profile(id) ON DELETE CASCADE,
                    amount INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    reference_id INTEGER DEFAULT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS upgrade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
                    equipment_name TEXT NOT NULL,
                    level_before INTEGER NOT NULL,
                    level_after INTEGER NOT NULL,
                    gold_cost INTEGER NOT NULL,
                    materials_cost INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS wheel_spin_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL REFERENCES player_profile(id) ON DELETE CASCADE,
                    cost_type TEXT NOT NULL,
                    reward_type TEXT NOT NULL,
                    reward_name TEXT NOT NULL,
                    rarity TEXT NOT NULL,
                    pity_before INTEGER NOT NULL,
                    pity_after INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Bảng active_tactical_battles lưu phiên đấu Tactical theo lượt giữa các request
            conn.execute("""
                CREATE TABLE IF NOT EXISTS active_tactical_battles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    battle_state_json TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Indexes để tăng tốc độ truy vấn
            conn.execute("CREATE INDEX IF NOT EXISTS idx_participants_match_id ON match_participants(match_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_participants_hero_id ON match_participants(hero_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_battle_events_match_id ON battle_events(match_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_created_at ON matches(created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_player_id ON inventory_items(player_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_hero_id ON inventory_items(equipped_hero_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_player ON currency_transactions(player_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wheel_spins_player ON wheel_spin_history(player_id);")

            # ==============================================================
            # 6. SEED DỮ LIỆU TƯỚNG & CẬP NHẬT CHỈ SỐ MỚI
            # ==============================================================
            default_heroes = [
                ("Knight", "Hiệp sĩ", 160, 24, "Iron Shield", "Giảm 35% sát thương nhận vào khi bị tấn công", "🛡️", 1, "WATER", 28, 18, 95, 5.0, 150.0),
                ("Mage", "Pháp sư", 110, 38, "Arcane Burst", "30% cơ hội phóng bão phép gây 180% sát thương", "🔮", 1, "FIRE", 12, 22, 90, 10.0, 160.0),
                ("Assassin", "Sát thủ", 115, 36, "Shadow Strike", "35% cơ hội tung đòn chí mạng gây 200% sát thương", "🗡️", 1, "NATURE", 14, 30, 98, 25.0, 200.0),
                ("Archer", "Cung thủ", 125, 32, "Double Shot", "30% cơ hội bắn 2 mũi tên liên tiếp vào đối thủ", "🏹", 1, "NATURE", 16, 26, 100, 15.0, 175.0),
                ("Guardian", "Hộ vệ", 180, 20, "Holy Barrier", "Giảm 25% sát thương nhận vào và phản 20% sát thương lại kẻ tấn công", "🏰", 1, "WATER", 35, 14, 90, 5.0, 150.0),
                ("Healer", "Trị liệu", 120, 22, "Divine Grace", "Hồi phục 30 HP cho đồng đội có lượng máu thấp nhất", "💚", 1, "WATER", 18, 24, 95, 5.0, 150.0),
                ("Berserker", "Cuồng chiến", 145, 30, "Blood Rage", "Khi máu dưới 50%, bộc phát sức mạnh tăng 50% sát thương", "🪓", 1, "FIRE", 18, 25, 92, 18.0, 180.0),
                ("Pyromancer", "Hỏa pháp sư", 105, 40, "Flame Wave", "25% cơ hội thiêu đốt lan toả gây thêm 15 sát thương chuẩn", "🔥", 1, "FIRE", 10, 23, 92, 12.0, 165.0)
            ]

            for h in default_heroes:
                conn.execute("""
                    INSERT INTO heroes (name, role, base_hp, base_atk, skill_name, skill_description, emoji, is_active, element, base_def, base_speed, base_accuracy, base_crit_rate, base_crit_damage)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        element = excluded.element,
                        base_def = excluded.base_def,
                        base_speed = excluded.base_speed,
                        base_accuracy = excluded.base_accuracy,
                        base_crit_rate = excluded.base_crit_rate,
                        base_crit_damage = excluded.base_crit_damage;
                """, h)

            # Khởi tạo hero_progress cho các tướng nếu chưa có
            heroes_rows = conn.execute("SELECT id FROM heroes;").fetchall()
            for row in heroes_rows:
                conn.execute("""
                    INSERT OR IGNORE INTO hero_progress (player_id, hero_id, level, xp, rank)
                    VALUES (1, ?, 1, 0, 1);
                """, (row["id"],))

            # ==============================================================
            # 7. SEED DANH MỤC CHIÊU THỨC (ABILITIES) & LIÊN KẾT TƯỚNG
            # ==============================================================
            abilities_seed = [
                # Knight (WATER)
                ("Sword Slash", "Chém kiếm cơ bản gây sát thương vật lý", "WATER", 100, "SINGLE_ENEMY", 100, 0, None, 0, 0, "⚔️"),
                ("Shield Bash", "Đập mạnh khiên gây choáng mục tiêu 1 hiệp", "NEUTRAL", 85, "SINGLE_ENEMY", 95, 2, "STUN", 45, 1, "🛡️"),
                ("Iron Wall", "Dựng lũy khiên kiên cố tạo lá chắn hấp thụ sát thương", "WATER", 0, "SELF", 100, 3, "SHIELD", 100, 2, "🏰"),
                ("Tidal Strike", "Chém kiếm cuộn triều dâng gây sát thương cực mạnh", "WATER", 140, "SINGLE_ENEMY", 90, 3, None, 0, 0, "🌊"),

                # Mage (FIRE)
                ("Arcane Bolt", "Bắn tia ma thuật cơ bản vào đối thủ", "NEUTRAL", 95, "SINGLE_ENEMY", 100, 0, None, 0, 0, "🔮"),
                ("Fireball", "Quả cầu lửa nổ bùng thiêu đốt mục tiêu", "FIRE", 130, "SINGLE_ENEMY", 90, 1, "BURN", 55, 2, "💥"),
                ("Meteor Burst", "Mưa sao băng rực lửa quét sạch toàn bộ đối thủ", "FIRE", 105, "ALL_ENEMIES", 85, 3, "BURN", 45, 2, "☄️"),
                ("Ignite Surge", "Bộc phát hỏa diệm khắc dấu tử thần nhận thêm 30% sát thương", "FIRE", 155, "SINGLE_ENEMY", 90, 3, "MARKED", 65, 2, "🔥"),

                # Assassin (NATURE)
                ("Quick Strike", "Đòn đánh chớp nhoáng với độ chính xác cao", "NATURE", 90, "SINGLE_ENEMY", 100, 0, None, 0, 0, "🗡️"),
                ("Shadow Blade", "Lưỡi dao bóng tối với tỉ lệ chí mạng cực cao", "NATURE", 145, "SINGLE_ENEMY", 95, 2, None, 0, 0, "🌑"),
                ("Mark for Death", "Khắc dấu tử thần khiến mục tiêu chịu thêm 30% sát thương", "NEUTRAL", 70, "SINGLE_ENEMY", 100, 2, "MARKED", 100, 2, "🎯"),
                ("Assassinate", "Nhát chém ám sát hiểm hóc gây lượng sát thương tàn bạo", "NATURE", 190, "SINGLE_ENEMY", 90, 4, None, 0, 0, "🩸"),

                # Archer (NATURE)
                ("Aimed Shot", "Ngắm bắn chuẩn xác không bao giờ trượt", "NATURE", 95, "SINGLE_ENEMY", 100, 0, None, 0, 0, "🏹"),
                ("Piercing Arrow", "Mũi tên xuyên kích bỏ qua một phần giáp đối phương", "NATURE", 130, "SINGLE_ENEMY", 95, 2, None, 0, 0, "💨"),
                ("Arrow Volley", "Bắn loạt mưa tên xé gió lên toàn bộ quân địch", "NATURE", 85, "ALL_ENEMIES", 90, 3, None, 0, 0, "🌧️"),
                ("Sniper Shot", "Phát bắn ngắm tỉa cự ly xa uy lực chết chóc", "NEUTRAL", 175, "SINGLE_ENEMY", 95, 3, None, 0, 0, "🎯"),

                # Guardian (WATER)
                ("Heavy Strike", "Cú giáng búa nặng nề làm rung chuyển đối thủ", "WATER", 90, "SINGLE_ENEMY", 95, 0, None, 0, 0, "🔨"),
                ("Protect Ally", "Tạo lá chắn thần thánh bảo vệ một đồng minh", "WATER", 0, "SINGLE_ALLY", 100, 2, "SHIELD", 100, 2, "🛡️"),
                ("Taunt Stance", "Khiêu khích kẻ thù và dựng khiên kiên cố", "NEUTRAL", 0, "SELF", 100, 3, "SHIELD", 100, 2, "🗣️"),
                ("Earthquake", "Chấn động địa chấn gây sát thương diện rộng và choáng", "NEUTRAL", 95, "ALL_ENEMIES", 90, 3, "STUN", 35, 1, "🌋"),

                # Healer (WATER)
                ("Radiant Bolt", "Tia sáng thanh tẩy kẻ địch", "NEUTRAL", 80, "SINGLE_ENEMY", 100, 0, None, 0, 0, "✨"),
                ("Divine Heal", "Phép trị liệu thần thánh hồi 50 HP cho một đồng đội", "WATER", 100, "SINGLE_ALLY", 100, 2, "HEAL", 100, 0, "💚"),
                ("Ocean Grace", "Sóng biển hồi phục ban phước lành cho một đồng đội bị thương", "WATER", 85, "SINGLE_ALLY", 100, 2, "HEAL", 100, 0, "🌊"),
                ("Purify & Barrier", "Thanh tẩy và dựng kết giới khiên bảo hộ đồng đội", "NEUTRAL", 0, "SINGLE_ALLY", 100, 2, "SHIELD", 100, 2, "🕊️"),

                # Berserker (FIRE)
                ("Axe Cleave", "Nhát bổ rìu lửa cơ bản", "FIRE", 105, "SINGLE_ENEMY", 95, 0, None, 0, 0, "🪓"),
                ("Blood Rage Hit", "Cú bổ rìu bộc phát cuồng nộ uy lực lớn", "FIRE", 140, "SINGLE_ENEMY", 90, 2, None, 0, 0, "🩸"),
                ("Whirlwind Axe", "Xoay cuồng phong rìu lửa trúng toàn bộ quân địch", "FIRE", 90, "ALL_ENEMIES", 90, 3, None, 0, 0, "🌀"),
                ("Execute", "Đòn bổ quyết định hạ gục kẻ yếu máu", "NEUTRAL", 185, "SINGLE_ENEMY", 85, 4, None, 0, 0, "💀"),

                # Pyromancer (FIRE)
                ("Flame Bolt", "Tia lửa thiêu đốt đơn mục tiêu", "FIRE", 95, "SINGLE_ENEMY", 95, 0, "BURN", 35, 2, "🔥"),
                ("Flame Wave", "Sóng lửa quét rực cháy gây sát thương và thiêu đốt", "FIRE", 125, "SINGLE_ENEMY", 90, 2, "BURN", 75, 2, "🌊"),
                ("Inferno Blast", "Bão lửa địa ngục thiêu rụi toàn bộ đối phương", "FIRE", 100, "ALL_ENEMIES", 85, 3, "BURN", 55, 2, "🌋"),
                ("Blazing Brand", "Khắc dấu ấn hỏa thần tăng sát thương nhận vào", "FIRE", 150, "SINGLE_ENEMY", 90, 3, "MARKED", 70, 2, "🏷️")
            ]

            for a in abilities_seed:
                conn.execute("""
                    INSERT INTO abilities (name, description, element, skill_power, target_type, accuracy, cooldown, status_effect, status_chance, status_duration, icon)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        description = excluded.description,
                        element = excluded.element,
                        skill_power = excluded.skill_power,
                        target_type = excluded.target_type,
                        accuracy = excluded.accuracy,
                        cooldown = excluded.cooldown,
                        status_effect = excluded.status_effect,
                        status_chance = excluded.status_chance,
                        status_duration = excluded.status_duration,
                        icon = excluded.icon;
                """, a)

            # Gán 4 chiêu thức cho từng tướng
            hero_ability_mappings = {
                "Knight": ["Sword Slash", "Shield Bash", "Iron Wall", "Tidal Strike"],
                "Mage": ["Arcane Bolt", "Fireball", "Meteor Burst", "Ignite Surge"],
                "Assassin": ["Quick Strike", "Shadow Blade", "Mark for Death", "Assassinate"],
                "Archer": ["Aimed Shot", "Piercing Arrow", "Arrow Volley", "Sniper Shot"],
                "Guardian": ["Heavy Strike", "Protect Ally", "Taunt Stance", "Earthquake"],
                "Healer": ["Radiant Bolt", "Divine Heal", "Ocean Grace", "Purify & Barrier"],
                "Berserker": ["Axe Cleave", "Blood Rage Hit", "Whirlwind Axe", "Execute"],
                "Pyromancer": ["Flame Bolt", "Flame Wave", "Inferno Blast", "Blazing Brand"]
            }

            for hero_name, skill_list in hero_ability_mappings.items():
                h_row = conn.execute("SELECT id FROM heroes WHERE name = ?;", (hero_name,)).fetchone()
                if h_row:
                    h_id = h_row["id"]
                    for slot, ab_name in enumerate(skill_list, start=1):
                        ab_row = conn.execute("SELECT id FROM abilities WHERE name = ?;", (ab_name,)).fetchone()
                        if ab_row:
                            conn.execute("""
                                INSERT OR REPLACE INTO hero_abilities (hero_id, ability_id, slot_order)
                                VALUES (?, ?, ?);
                            """, (h_id, ab_row["id"], slot))

            # ==============================================================
            # 8. SEED DANH MỤC TRANG BỊ (EQUIPMENT CATALOG) & VẬT PHẨM MẪU
            # ==============================================================
            equipment_seed = [
                # Weapons
                ("Iron Longsword", "WEAPON", "COMMON", 12, 0, 0, 0, 2, 3.0, 0.0, 0, 0.0, 150, 5, "🗡️", "Thanh trường kiếm rèn từ thép thông thường."),
                ("Flame Scythe", "WEAPON", "RARE", 24, 0, 0, 0, 0, 6.0, 10.0, 5, 10.0, 420, 5, "🪓", "Lưỡi hái rực lửa tăng sát thương hệ Hỏa."),
                ("Frost Staff", "WEAPON", "RARE", 22, 12, 30, 0, 0, 4.0, 0.0, 0, 10.0, 440, 5, "🔮", "Gậy phép băng giá tăng sát thương và phòng thủ hệ Nước."),
                ("Dragon Sniper Bow", "WEAPON", "EPIC", 40, 0, 0, 4, 10, 12.0, 20.0, 20, 0.0, 950, 5, "🏹", "Cung ngắm rồng xuyên phá lớp giáp phòng thủ."),
                ("Excalibur of Light", "WEAPON", "LEGENDARY", 68, 15, 60, 5, 8, 18.0, 35.0, 30, 15.0, 2300, 5, "⚔️", "Thánh kiếm truyền thuyết sở hữu sức mạnh vô song."),

                # Armor
                ("Leather Vest", "ARMOR", "COMMON", 0, 8, 40, 2, 0, 0.0, 0.0, 0, 0.0, 130, 5, "🥋", "Áo giáp da dẻo dai giúp tăng lượng máu khởi đầu."),
                ("Guardian Chainmail", "ARMOR", "RARE", 0, 20, 85, 0, 0, 0.0, 0.0, 0, 0.0, 400, 5, "🛡️", "Giáp xích của đội vệ binh cung cấp độ bền bỉ cao."),
                ("Dragon Scale Armor", "ARMOR", "EPIC", 5, 35, 150, 0, 0, 0.0, 0.0, 0, 10.0, 900, 5, "🦺", "Áo giáp chế tác từ vảy rồng cứng cáp."),
                ("Titan Divine Plate", "ARMOR", "LEGENDARY", 10, 55, 240, 4, 0, 0.0, 0.0, 0, 0.0, 2100, 5, "🏰", "Chiến giáp Titan bất khả xâm phạm."),

                # Boots
                ("Traveler Boots", "BOOTS", "COMMON", 0, 2, 15, 6, 0, 0.0, 0.0, 0, 0.0, 110, 5, "🥾", "Đôi ủng lữ hành giúp gia tăng tốc độ di chuyển."),
                ("Windrunner Greaves", "BOOTS", "RARE", 0, 6, 30, 12, 3, 4.0, 0.0, 0, 0.0, 340, 5, "👟", "Giày chạy trong gió tăng tốc độ và tỉ lệ chí mạng."),
                ("Shadow Stalker Boots", "BOOTS", "EPIC", 8, 10, 50, 20, 5, 8.0, 15.0, 10, 0.0, 820, 5, "👢", "Giày sát thủ bóng đêm di chuyển chớp nhoáng."),
                ("Hermes Golden Sandals", "BOOTS", "LEGENDARY", 12, 18, 90, 30, 8, 12.0, 20.0, 15, 0.0, 1950, 5, "👡", "Đôi hài vàng thần thoại mang lại tốc độ tuyệt luân."),

                # Accessories
                ("Bronze Ring", "ACCESSORY", "COMMON", 4, 4, 20, 2, 0, 2.0, 0.0, 0, 0.0, 100, 5, "💍", "Chiếc nhẫn đồng đơn giản hỗ trợ các chỉ số cơ bản."),
                ("Ruby Amulet", "ACCESSORY", "RARE", 16, 8, 40, 0, 0, 5.0, 12.0, 5, 5.0, 360, 5, "📿", "Mặt dây chuyền hồng ngọc tăng sát thương và chí mạng."),
                ("Eye of the Falcon", "ACCESSORY", "EPIC", 22, 10, 50, 4, 12, 10.0, 25.0, 18, 0.0, 880, 5, "🧿", "Bùa mắt ưng tăng tối đa độ chính xác và xuyên giáp."),
                ("Heart of the Phoenix", "ACCESSORY", "LEGENDARY", 30, 25, 120, 6, 5, 15.0, 30.0, 20, 15.0, 2200, 5, "💖", "Trái tim phượng hoàng bộc phát nguồn sinh lực bất diệt.")
            ]

            for eq in equipment_seed:
                conn.execute("""
                    INSERT INTO equipment_catalog (
                        name, slot_type, rarity, bonus_atk, bonus_def, bonus_hp, bonus_speed,
                        bonus_accuracy, bonus_crit_rate, bonus_crit_damage, armor_penetration,
                        element_bonus, price, max_upgrade_level, icon, description, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(name) DO UPDATE SET
                        slot_type = excluded.slot_type,
                        rarity = excluded.rarity,
                        bonus_atk = excluded.bonus_atk,
                        bonus_def = excluded.bonus_def,
                        bonus_hp = excluded.bonus_hp,
                        bonus_speed = excluded.bonus_speed,
                        bonus_accuracy = excluded.bonus_accuracy,
                        bonus_crit_rate = excluded.bonus_crit_rate,
                        bonus_crit_damage = excluded.bonus_crit_damage,
                        armor_penetration = excluded.armor_penetration,
                        element_bonus = excluded.element_bonus,
                        price = excluded.price,
                        icon = excluded.icon,
                        description = excluded.description;
                """, eq)

            # Cung cấp sẵn 2 món đồ khởi đầu trong kho để người chơi trang bị thử nghiệm
            starter_inv = conn.execute("SELECT COUNT(*) FROM inventory_items WHERE player_id = 1;").fetchone()[0]
            if starter_inv == 0:
                starter_items = [
                    (1, "Iron Longsword"),
                    (1, "Leather Vest")
                ]
                for p_id, item_name in starter_items:
                    eq_row = conn.execute("SELECT id FROM equipment_catalog WHERE name = ?;", (item_name,)).fetchone()
                    if eq_row:
                        conn.execute("""
                            INSERT INTO inventory_items (player_id, equipment_id, upgrade_level, is_equipped)
                            VALUES (?, ?, 0, 0);
                        """, (p_id, eq_row["id"]))

    finally:
        conn.close()


def get_all_heroes(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả tướng kèm thông tin hệ nguyên tố, chỉ số và tiến trình level."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("""
            SELECT h.*, 
                   COALESCE(hp.level, 1) as level,
                   COALESCE(hp.xp, 0) as xp
            FROM heroes h
            LEFT JOIN hero_progress hp ON h.id = hp.hero_id AND hp.player_id = 1
            WHERE h.is_active = 1
            ORDER BY h.id ASC;
        """)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_hero_by_id(hero_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Lấy thông tin chi tiết của 1 tướng kèm chiêu thức và trang bị hiện tại."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("""
            SELECT h.*, 
                   COALESCE(hp.level, 1) as level,
                   COALESCE(hp.xp, 0) as xp
            FROM heroes h
            LEFT JOIN hero_progress hp ON h.id = hp.hero_id AND hp.player_id = 1
            WHERE h.id = ?;
        """, (hero_id,))
        row = cur.fetchone()
        if not row:
            return None
        hero_data = dict(row)

        # Lấy 4 chiêu thức của tướng
        ab_cur = conn.execute("""
            SELECT a.*, ha.slot_order
            FROM abilities a
            JOIN hero_abilities ha ON a.id = ha.ability_id
            WHERE ha.hero_id = ?
            ORDER BY ha.slot_order ASC;
        """, (hero_id,))
        hero_data["abilities"] = [dict(r) for r in ab_cur.fetchall()]

        # Lấy trang bị đang mặc của tướng
        eq_cur = conn.execute("""
            SELECT ii.id as inventory_id, ii.upgrade_level, ii.equipped_slot,
                   ec.*
            FROM inventory_items ii
            JOIN equipment_catalog ec ON ii.equipment_id = ec.id
            WHERE ii.equipped_hero_id = ? AND ii.is_equipped = 1;
        """, (hero_id,))
        hero_data["equipped_items"] = [dict(r) for r in eq_cur.fetchall()]

        return hero_data
    finally:
        conn.close()


def get_player_profile(player_id: int = 1, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Lấy thông tin hồ sơ người chơi: Gold, Level, XP, Pity Counter, Materials."""
    conn = get_db_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM player_profile WHERE id = ?;", (player_id,))
        row = cur.fetchone()
        if not row:
            return {"id": 1, "gold": 800, "player_level": 1, "player_xp": 0, "pity_counter": 0, "materials": {}}
        profile = dict(row)

        # Lấy nguyên liệu
        mat_cur = conn.execute("SELECT material_type, quantity FROM player_materials WHERE player_id = ?;", (player_id,))
        materials = {r["material_type"]: r["quantity"] for r in mat_cur.fetchall()}
        profile["materials"] = materials

        return profile
    finally:
        conn.close()


def save_battle_result(battle_result: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Lưu toàn bộ kết quả trận đấu xuống SQLite trong một Database Transaction duy nhất.
    Cập nhật bảng matches, match_participants, battle_events, trao thưởng Gold & XP,
    và ghi nhật ký giao dịch tài chính currency_transactions.
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            gold_reward = battle_result.get("gold_reward", 0)
            xp_reward = battle_result.get("xp_reward", 0)
            battle_mode = battle_result.get("battle_mode", "AUTO")

            # 1. Ghi vào bảng matches
            cur = conn.execute(
                """
                INSERT INTO matches (winner_team, total_rounds, status, battle_mode, gold_reward, xp_reward)
                VALUES (?, ?, 'COMPLETED', ?, ?, ?);
                """,
                (battle_result["winner_team"], battle_result["total_rounds"], battle_mode, gold_reward, xp_reward)
            )
            match_id = cur.lastrowid

            # 2. Ghi 6 bản ghi vào bảng match_participants
            idx_to_db_id = {}
            all_participants = battle_result["blue_participants"] + battle_result["red_participants"]
            for p in all_participants:
                eq_snapshot = json.dumps(p.get("equipment", []))
                part_cur = conn.execute(
                    """
                    INSERT INTO match_participants (
                        match_id, hero_id, team_side, slot_no, hp_start, hp_end, damage_dealt, kills, is_winner,
                        hero_level, equipment_snapshot, element
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        match_id,
                        p["hero_id"],
                        p["team_side"],
                        p["slot_no"],
                        p["hp_start"],
                        p["hp_end"],
                        p["damage_dealt"],
                        p["kills"],
                        p["is_winner"],
                        p.get("level", 1),
                        eq_snapshot,
                        p.get("element", "NATURE")
                    )
                )
                idx_to_db_id[p["participant_idx"]] = part_cur.lastrowid

            # 3. Ghi toàn bộ sự kiện vào bảng battle_events
            events_data = []
            for ev in battle_result["events"]:
                actor_db_id = idx_to_db_id.get(ev.get("actor_idx"))
                target_db_id = idx_to_db_id.get(ev.get("target_idx"))

                events_data.append((
                    match_id,
                    ev["round_no"],
                    ev["event_order"],
                    actor_db_id,
                    target_db_id,
                    ev["event_type"],
                    ev.get("damage", 0),
                    ev["message"],
                    ev.get("ability_id"),
                    ev.get("ability_name"),
                    ev.get("is_crit", 0),
                    ev.get("is_miss", 0),
                    ev.get("element_mult", 1.0),
                    ev.get("shield_absorbed", 0),
                    ev.get("status_applied")
                ))

            conn.executemany(
                """
                INSERT INTO battle_events (
                    match_id, round_no, event_order, actor_participant_id, target_participant_id, event_type, damage, message,
                    ability_id, ability_name, is_crit, is_miss, element_mult, shield_absorbed, status_applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                events_data
            )

            # 4. Trao thưởng Gold & XP nếu không phải Simulation test
            if battle_mode in ["TACTICAL", "AUTO"] and gold_reward > 0:
                p_cur = conn.execute("SELECT gold, player_level, player_xp FROM player_profile WHERE id = 1;")
                p_row = p_cur.fetchone()
                if p_row:
                    new_gold = p_row["gold"] + gold_reward
                    new_player_xp = p_row["player_xp"] + xp_reward
                    new_player_level = p_row["player_level"]
                    if new_player_xp >= new_player_level * 150:
                        new_player_xp -= new_player_level * 150
                        new_player_level += 1

                    conn.execute("""
                        UPDATE player_profile 
                        SET gold = ?, player_level = ?, player_xp = ?
                        WHERE id = 1;
                    """, (new_gold, new_player_level, new_player_xp))

                    conn.execute("""
                        INSERT INTO currency_transactions (player_id, amount, balance_after, reason, reference_id)
                        VALUES (1, ?, ?, 'BATTLE_REWARD', ?);
                    """, (gold_reward, new_gold, match_id))

                # Trao XP cho các tướng Blue tham gia
                for p in battle_result["blue_participants"]:
                    h_id = p["hero_id"]
                    prog_cur = conn.execute("SELECT level, xp FROM hero_progress WHERE player_id = 1 AND hero_id = ?;", (h_id,))
                    prog_row = prog_cur.fetchone()
                    if prog_row:
                        curr_lvl = prog_row["level"]
                        curr_xp = prog_row["xp"] + xp_reward
                        req_xp = curr_lvl * 100
                        while curr_xp >= req_xp and curr_lvl < 20:
                            curr_xp -= req_xp
                            curr_lvl += 1
                            req_xp = curr_lvl * 100

                        conn.execute("""
                            UPDATE hero_progress 
                            SET level = ?, xp = ?
                            WHERE player_id = 1 AND hero_id = ?;
                        """, (curr_lvl, curr_xp, h_id))

            return match_id
    finally:
        conn.close()
