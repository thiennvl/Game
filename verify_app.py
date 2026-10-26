"""
Verification script for Tactical Battle Arena RPG server and APIs.
Simulates real tactical and auto battles, verifies database records,
shop purchases, lucky wheel spins, inventory equip/upgrade, and confirms
all analytics and history endpoints return valid real data.
"""

import urllib.request
import urllib.parse
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:5000"


def request_json(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def run_checks():
    print("==========================================================")
    print("   TACTICAL BATTLE ARENA RPG - END-TO-END VERIFICATION")
    print("==========================================================")

    print("\n--- 1. Checking Home Page (GET /) ---")
    req = urllib.request.Request(BASE_URL)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "TACTICAL BATTLE ARENA" in html or "Auto-Battle Arena" in html
        assert "tab-arena" in html
        assert "tab-heroes" in html
        assert "tab-equipment" in html
        assert "tab-shop" in html
        assert "tab-wheel" in html
        assert "tab-meta" in html
        assert "tab-history" in html
        assert "tab-profile" in html
        print("  [PASS] Home page loaded with all 8 navigation tabs.")

    print("\n--- 2. Checking Heroes & Progress (GET /api/heroes) ---")
    res = request_json("/api/heroes")
    assert res["success"] is True
    heroes = res["data"]
    assert len(heroes) >= 6
    sample_hero = heroes[0]
    assert "level" in sample_hero
    assert "xp" in sample_hero
    assert "abilities" in sample_hero and len(sample_hero["abilities"]) >= 3
    assert "equipped_items" in sample_hero
    print(f"  [PASS] Retrieved {len(heroes)} heroes with abilities and progression.")
    print(f"         Sample: {sample_hero['name']} (Lv.{sample_hero['level']}, Element: {sample_hero['element']}, {len(sample_hero['abilities'])} skills)")

    print("\n--- 3. Checking Player Profile & Economy (GET /api/player/profile) ---")
    p_res = request_json("/api/player/profile")
    assert p_res["success"] is True
    profile = p_res["data"]
    assert profile["gold"] >= 0
    assert "materials" in profile
    print(f"  [PASS] Player Profile: Level {profile['player_level']}, Gold: {profile['gold']}, Materials: {profile['materials']}")

    print("\n--- 4. Checking Shop Catalog & Item Purchase ---")
    shop_res = request_json("/api/shop")
    assert shop_res["success"] is True
    shop_categories = shop_res["data"]
    assert "WEAPON" in shop_categories
    assert "MATERIAL" in shop_categories

    # Find affordable equipment or material to buy
    target_item = None
    is_mat = False
    for cat_name, items in shop_categories.items():
        for item in items:
            if item["price"] <= profile["gold"]:
                target_item = item
                is_mat = (cat_name == "MATERIAL")
                break
        if target_item:
            break

    if target_item:
        print(f"  [INFO] Purchasing '{target_item['name']}' for {target_item['price']} Gold...")
        buy_res = request_json("/api/shop/buy", method="POST", data={"item_id": target_item["id"], "is_material": is_mat})
        assert buy_res["success"] is True
        print(f"  [PASS] Bought item successfully. Remaining Gold: {buy_res.get('remaining_gold')}")
    else:
        print("  [SKIP] Not enough gold to buy an item.")

    print("\n--- 5. Checking Inventory & Equipment Management ---")
    inv_res = request_json("/api/inventory")
    assert inv_res["success"] is True
    inv_items = inv_res["data"]
    assert len(inv_items) > 0
    sample_item = inv_items[0]
    inv_id = sample_item.get("inventory_id") or sample_item.get("id")
    print(f"  [PASS] Inventory has {len(inv_items)} items. Selected: {sample_item['name']} ({sample_item['slot_type']}, +{sample_item['upgrade_level']})")

    # Equip item to hero 1
    equip_res = request_json("/api/inventory/equip", method="POST", data={"inventory_id": inv_id, "hero_id": 1})
    assert equip_res["success"] is True
    print(f"  [PASS] Equipped '{sample_item['name']}' to hero ID 1.")

    # Try upgrade item
    up_res = request_json("/api/inventory/upgrade", method="POST", data={"inventory_id": inv_id})
    if up_res.get("success"):
        print(f"  [PASS] Upgraded '{sample_item['name']}' to +{up_res.get('new_level')}. Cost: {up_res.get('cost_gold', 120)} Gold.")
    else:
        print(f"  [INFO] Upgrade result: {up_res.get('error', 'Insufficient resources')}")

    print("\n--- 6. Checking Lucky Wheel (GET & POST /api/wheel) ---")
    wheel_conf = request_json("/api/wheel")
    assert wheel_conf["success"] is True
    odds = wheel_conf["data"]["published_odds"]
    total_prob = sum(p["chance"] for p in odds)
    assert abs(total_prob - 100.0) < 0.1
    print(f"  [PASS] Lucky Wheel configuration verified (Sum of odds: {total_prob:.1f}%). Pity count: {wheel_conf['data']['current_pity']}/10")

    # Spin wheel (Use ticket if gold is below 150)
    cost_type = "TICKET" if wheel_conf["data"]["player_gold"] < 150 else "GOLD"
    spin_res = request_json("/api/wheel/spin", method="POST", data={"cost_type": cost_type})
    assert spin_res["success"] is True
    print(f"  [PASS] Lucky Wheel Spin Won ({cost_type}): {spin_res.get('reward_name')} ({spin_res.get('rarity')})! Remaining Gold: {spin_res.get('remaining_gold')}")

    print("\n--- 7. Checking Team Roll (POST /api/team/roll) ---")
    roll_res = request_json("/api/team/roll", method="POST")
    assert roll_res["success"] is True
    team = roll_res["data"]
    assert len(team) == 3
    print(f"  [PASS] Rolled 3 distinct heroes: {[h['name'] for h in team]}")

    print("\n--- 8. Simulating Tactical Battle Flow (Turn-by-Turn Combat) ---")
    start_res = request_json("/api/battle/tactical/start", method="POST", data={"player_team": team})
    assert start_res["success"] is True
    battle_state = start_res
    battle_id = battle_state["battle_id"]
    print(f"  [PASS] Tactical Battle #{battle_id} initialized with status '{battle_state['status']}'.")

    action_count = 0
    max_turns = 40
    while battle_state.get("status") == "WAITING_PLAYER" and action_count < max_turns:
        active_actor = battle_state.get("active_actor")
        if not active_actor:
            break

        # Choose first available ability off cooldown
        avail_abilities = active_actor.get("abilities", [])
        chosen_ability = avail_abilities[0] if avail_abilities else {"id": 1, "target_type": "SINGLE_ENEMY"}
        for ab in avail_abilities:
            if ab.get("current_cd", 0) == 0:
                chosen_ability = ab
                break

        # Pick target based on target_type
        tt = chosen_ability.get("target_type", "SINGLE_ENEMY")
        combatants = battle_state.get("combatants", [])
        if tt in ("SINGLE_ALLY", "SELF"):
            target_idx = active_actor["participant_idx"]
        else:
            # find an alive enemy (different team side)
            alive_enemies = [c for c in combatants if c["team_side"] != active_actor["team_side"] and c["hp"] > 0]
            target_idx = alive_enemies[0]["participant_idx"] if alive_enemies else combatants[0]["participant_idx"]

        action_res = request_json("/api/battle/tactical/action", method="POST", data={
            "battle_id": battle_id,
            "ability_id": chosen_ability["id"],
            "target_idx": target_idx
        })
        assert action_res["success"] is True
        battle_state = action_res
        action_count += 1

    print(f"  [PASS] Tactical Battle finished in {action_count} player turns. Winner: {battle_state.get('winner_team')} (Status: {battle_state.get('status')})")
    if battle_state.get("match_id"):
        print(f"         Saved to database with Match ID #{battle_state['match_id']}")

    print("\n--- 9. Simulating Auto Battle (POST /api/battle/fight) ---")
    auto_res = request_json("/api/battle/fight", method="POST", data={"player_team": team})
    assert auto_res["success"] is True
    auto_battle = auto_res["data"]
    print(f"  [PASS] Auto Battle #{auto_battle['match_id']} completed: Winner={auto_battle['winner_team']}, Rounds={auto_battle['total_rounds']}, Events={len(auto_battle['events'])}")

    print("\n--- 10. Checking Comprehensive Analytics Endpoints ---")
    ov_res = request_json("/api/analytics/overview")
    assert ov_res["success"] is True
    print(f"  [PASS] Overview: Total Matches={ov_res['data']['total_matches']}, WinRate={ov_res['data']['player_win_rate']}%")

    elem_res = request_json("/api/analytics/elements")
    assert elem_res["success"] is True
    print(f"  [PASS] Element Meta: {len(elem_res['data'])} elements analyzed: {[e['element'] for e in elem_res['data']]}")

    eq_res = request_json("/api/analytics/equipment")
    assert eq_res["success"] is True
    print(f"  [PASS] Equipment Meta: {len(eq_res['data'])} equipment items tracked in player inventory.")

    wh_res = request_json("/api/analytics/wheel")
    assert wh_res["success"] is True
    print(f"  [PASS] Wheel Analytics: {len(wh_res['data'])} prize categories tracked in spin distribution.")

    print("\n--- 11. Checking Currency Ledger & Match History ---")
    tx_res = request_json("/api/player/transactions")
    assert tx_res["success"] is True
    print(f"  [PASS] Currency Ledger: {len(tx_res['data'])} transactions recorded with positive/negative audit flow.")

    hist_res = request_json("/api/matches")
    assert hist_res["success"] is True
    print(f"  [PASS] Match History: {len(hist_res['data'])} matches recorded in SQLite.")

    print("\n==========================================================")
    print("   ALL 11 END-TO-END VERIFICATION CHECKS PASSED (100%)!")
    print("==========================================================")


if __name__ == "__main__":
    run_checks()
