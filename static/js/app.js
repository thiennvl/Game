/**
 * Tactical Battle Arena RPG & Meta Tracker
 * Main Frontend Application Script
 */

// Application Global State
const state = {
    currentTab: "tab-arena",
    battleMode: "TACTICAL", // "TACTICAL" or "AUTO"
    playerTeam: null,
    opponentTeam: null,

    // Tactical Battle Session State
    tacticalBattleId: null,
    selectedAbilityId: null,
    selectedTargetIdx: null,
    isTacticalBusy: false,

    // Auto Battle State
    autoBattle: null,
    autoPlaybackIndex: 0,
    isAutoPlaying: false,
    autoTimer: null,
    autoSpeed: 600,

    // Inventory & Equipment State
    selectedHeroIdForEquip: 1,
    selectedInventoryItem: null,

    // Lucky Wheel State
    isSpinning: false,
    wheelAngle: 0,

    // Chart.js instances
    charts: {
        winrate: null,
        damage: null,
        elements: null
    }
};

// ==========================================================================
// INITIALIZATION
// ==========================================================================
document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    setupArenaEvents();
    setupEquipmentEvents();
    setupShopEvents();
    setupWheelEvents();
    setupHistoryEvents();
    setupModalEvents();

    // Initial Data Load
    refreshPlayerProfile();
    rollPlayerTeam();
    drawLuckyWheelCanvas();
});

// ==========================================================================
// NAVIGATION & HEADER CURRENCY
// ==========================================================================
function setupNavigation() {
    const tabs = document.querySelectorAll(".nav-tab");
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.getAttribute("data-target");
            switchTab(target);
        });
    });
}

function switchTab(tabId) {
    state.currentTab = tabId;

    document.querySelectorAll(".nav-tab").forEach(t => {
        const isActive = t.getAttribute("data-target") === tabId;
        t.classList.toggle("active", isActive);
    });

    document.querySelectorAll(".tab-content").forEach(content => {
        const isMatch = content.id === tabId;
        content.style.display = isMatch ? "block" : "none";
        content.classList.toggle("active", isMatch);
    });

    refreshPlayerProfile();

    // Load data for specific tabs
    if (tabId === "tab-heroes") loadHeroManagement();
    else if (tabId === "tab-equipment") loadEquipmentScreen();
    else if (tabId === "tab-shop") loadShopCatalog();
    else if (tabId === "tab-wheel") loadWheelScreen();
    else if (tabId === "tab-meta") loadMetaTrackerData();
    else if (tabId === "tab-history") loadMatchHistory();
    else if (tabId === "tab-profile") loadProfileScreen();
}

async function refreshPlayerProfile() {
    try {
        const res = await fetch("/api/player/profile");
        const json = await res.json();
        if (json.success) {
            const p = json.data;
            document.getElementById("header-gold-val").textContent = p.gold.toLocaleString();
            document.getElementById("header-ticket-val").textContent = p.materials.LUCKY_TICKET || 0;
            const shopGold = document.getElementById("shop-gold-display");
            if (shopGold) shopGold.textContent = `${p.gold.toLocaleString()} Gold`;
        }
    } catch (e) {
        console.error("Lỗi cập nhật hồ sơ người chơi:", e);
    }
}

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "success" ? "✅" : (type === "error" ? "❌" : "ℹ️");
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(12px)";
        setTimeout(() => toast.remove(), 250);
    }, 3200);
}

// ==========================================================================
// TAB 1: ARENA (2D TACTICAL & AUTO BATTLE)
// ==========================================================================
function setupArenaEvents() {
    // Mode toggle
    const btnTactical = document.getElementById("btn-mode-tactical");
    const btnAuto = document.getElementById("btn-mode-auto");

    btnTactical.addEventListener("click", () => {
        state.battleMode = "TACTICAL";
        btnTactical.classList.add("active");
        btnAuto.classList.remove("active");
        document.getElementById("auto-playback-controls").style.display = "none";
        resetArenaState();
    });

    btnAuto.addEventListener("click", () => {
        state.battleMode = "AUTO";
        btnAuto.classList.add("active");
        btnTactical.classList.remove("active");
        document.getElementById("tactical-command-panel").style.display = "none";
        resetArenaState();
    });

    // Roll team
    document.getElementById("btn-roll-team").addEventListener("click", rollPlayerTeam);

    // Start battle
    document.getElementById("btn-start-battle").addEventListener("click", startArenaBattle);

    // Tactical Command events
    document.getElementById("btn-cancel-target").addEventListener("click", clearTacticalTargeting);
    document.getElementById("btn-confirm-action").addEventListener("click", submitTacticalPlayerAction);

    // Auto Mode playback controls
    document.getElementById("btn-step-battle").addEventListener("click", () => {
        pauseAutoPlayback();
        playNextAutoStep();
    });
    document.getElementById("btn-auto-play").addEventListener("click", toggleAutoPlayback);
    document.getElementById("btn-speed-toggle").addEventListener("click", toggleAutoSpeed);
    document.getElementById("btn-skip-battle").addEventListener("click", skipAutoToEnd);
}

async function rollPlayerTeam() {
    try {
        const btn = document.getElementById("btn-roll-team");
        btn.disabled = true;
        btn.innerHTML = `<span class="btn-icon">⏳</span> Đang roll...`;

        const res = await fetch("/api/team/roll", { method: "POST" });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Không thể roll đội hình");

        state.playerTeam = json.data;
        renderBattleRoster(state.playerTeam, "BLUE", document.getElementById("blue-roster-container"));
        updateTeamHpDisplay("BLUE", state.playerTeam);

        resetArenaState();
        showToast("Đã roll đội hình 3 vị tướng mới!", "success");
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        const btn = document.getElementById("btn-roll-team");
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-icon">🎲</span> Roll Đội Hình`;
    }
}

function resetArenaState() {
    pauseAutoPlayback();
    state.tacticalBattleId = null;
    state.autoBattle = null;
    state.autoPlaybackIndex = 0;
    clearTacticalTargeting();

    document.getElementById("tactical-command-panel").style.display = "none";
    document.getElementById("auto-playback-controls").style.display = "none";
    document.getElementById("turn-order-queue").style.display = "none";
    document.getElementById("arena-round-counter").textContent = "Chờ trận";
    document.getElementById("log-round-info").textContent = "Hiệp: 0 | Sự kiện: 0";
    document.getElementById("red-team-hp").textContent = "Tổng HP: ---";
    document.getElementById("red-roster-container").innerHTML = `
        <div class="empty-roster-placeholder">
            <div class="placeholder-icon">🤖</div>
            <p>Đối thủ sẽ xuất hiện khi bạn bấm <strong>"Bắt Đầu Chiến Đấu"</strong>!</p>
        </div>
    `;
    document.getElementById("battle-log-feed").innerHTML = `
        <div class="log-empty-msg">
            Sẵn sàng! Chế độ ${state.battleMode === "TACTICAL" ? "Tactical (Thủ công)" : "Auto (Tự động)"} đang kích hoạt. Bấm Bắt Đầu Chiến Đấu!
        </div>
    `;
}

function renderBattleRoster(combatants, teamSide, container) {
    container.innerHTML = "";
    combatants.forEach((c, slot) => {
        const pIdx = c.participant_idx !== undefined ? c.participant_idx : (teamSide === "BLUE" ? slot : slot + 3);
        const card = document.createElement("div");
        card.className = "combatant-card";
        card.id = `combatant-card-${pIdx}`;
        card.setAttribute("data-idx", pIdx);
        card.setAttribute("data-side", teamSide);

        const currentHp = Math.max(0, c.hp !== undefined ? c.hp : c.max_hp);
        const maxHp = c.max_hp || 100;
        const hpPct = Math.round((currentHp / maxHp) * 100);
        const shieldVal = c.shield || 0;
        const shieldPct = Math.min(100, Math.round((shieldVal / maxHp) * 100));

        const elemIcon = c.element === "FIRE" ? "🔥" : (c.element === "WATER" ? "💧" : "🌿");
        const elemClass = `elem-${(c.element || 'nature').toLowerCase()}`;

        // Status effects pills
        const statuses = c.status_effects ? Object.keys(c.status_effects) : [];
        const statusHtml = statuses.map(s => {
            const cls = `status-${s.toLowerCase()}`;
            return `<span class="status-pill ${cls}">${s}</span>`;
        }).join("");

        card.innerHTML = `
            <div class="avatar-2d-box">
                <span class="avatar-emoji">${c.emoji || '⚔️'}</span>
                <span class="badge-elem-mini ${elemClass}" title="Hệ ${c.element}">${elemIcon}</span>
                <span class="badge-lvl-mini">Lv.${c.level || 1}</span>
            </div>
            <div class="combatant-main-info">
                <div class="name-element-row">
                    <span class="combatant-name">${c.name}</span>
                    <span class="combatant-role-text">• ${c.role}</span>
                </div>
                <div class="hp-shield-bar-track">
                    <div class="hp-fill" id="hp-fill-${pIdx}" style="width: ${hpPct}%;"></div>
                    ${shieldVal > 0 ? `<div class="shield-overlay-fill" id="shield-fill-${pIdx}" style="width: ${shieldPct}%;"></div>` : ''}
                </div>
                <div class="hp-text-row">
                    <span>HP: <strong id="hp-val-${pIdx}">${currentHp}</strong>/${maxHp} ${shieldVal > 0 ? `(+${shieldVal}🛡️)` : ''}</span>
                    <span>${hpPct}%</span>
                </div>
                <div class="status-badges-row" id="status-row-${pIdx}">${statusHtml}</div>
            </div>
            <div class="combatant-stats-right">
                <span class="stat-tag tag-atk" title="Sát thương">⚔️ ${c.atk}</span>
                <span class="stat-tag tag-def" title="Phòng thủ">🛡️ ${c.defense || c.def || 15}</span>
                <span class="stat-tag tag-spd" title="Tốc độ lượt">⚡ ${c.speed || 20}</span>
            </div>
        `;

        // Direct Click Targeting Listener
        card.addEventListener("click", () => handleCombatantDirectClick(pIdx, teamSide, c));

        container.appendChild(card);
    });
}

function updateTeamHpDisplay(side, heroes) {
    const total = heroes.reduce((sum, h) => sum + (h.hp !== undefined ? h.hp : h.max_hp || 0), 0);
    const elem = side === "BLUE" ? document.getElementById("blue-team-hp") : document.getElementById("red-team-hp");
    elem.textContent = `Tổng HP: ${total}`;
}

async function startArenaBattle() {
    if (!state.playerTeam || state.playerTeam.length !== 3) {
        await rollPlayerTeam();
    }

    const btnFight = document.getElementById("btn-start-battle");
    const btnRoll = document.getElementById("btn-roll-team");
    btnFight.disabled = true;
    btnRoll.disabled = true;

    if (state.battleMode === "TACTICAL") {
        // TACTICAL MODE: Start interactive session
        try {
            btnFight.innerHTML = `<span class="btn-icon">⏳</span> Đang khởi tạo...`;
            const res = await fetch("/api/battle/tactical/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ player_team: state.playerTeam })
            });
            const json = await res.json();
            if (!json.success) throw new Error(json.error || "Không thể bắt đầu Tactical Battle");

            state.tacticalBattleId = json.battle_id;
            document.getElementById("battle-log-feed").innerHTML = "";

            processTacticalStepResult(json);
        } catch (err) {
            showToast(err.message, "error");
            btnFight.disabled = false;
            btnRoll.disabled = false;
            btnFight.innerHTML = `<span class="btn-icon">⚔️</span> BẮT ĐẦU CHIẾN ĐẤU`;
        }
    } else {
        // AUTO MODE: Full backend simulation
        try {
            btnFight.innerHTML = `<span class="btn-icon">⏳</span> Đang mô phỏng...`;
            const res = await fetch("/api/battle/fight", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ player_team: state.playerTeam })
            });
            const json = await res.json();
            if (!json.success) throw new Error(json.error || "Lỗi mô phỏng Auto Battle");

            state.autoBattle = json.data;
            state.opponentTeam = json.data.red_participants;
            state.autoPlaybackIndex = 0;

            renderBattleRoster(state.opponentTeam, "RED", document.getElementById("red-roster-container"));
            updateTeamHpDisplay("RED", state.opponentTeam);

            document.getElementById("battle-log-feed").innerHTML = "";
            document.getElementById("auto-playback-controls").style.display = "flex";
            document.getElementById("arena-round-counter").textContent = "Hiệp 1";

            startAutoPlayback();
        } catch (err) {
            showToast(err.message, "error");
            btnFight.disabled = false;
            btnRoll.disabled = false;
            btnFight.innerHTML = `<span class="btn-icon">⚔️</span> BẮT ĐẦU CHIẾN ĐẤU`;
        }
    }
}

// ==========================================================================
// TACTICAL MODE INTERACTION (CHỌN CHIÊU & MỤC TIÊU)
// ==========================================================================
function processTacticalStepResult(data) {
    document.getElementById("arena-round-counter").textContent = `Hiệp ${data.round_no}`;

    // Cập nhật Combatants trên cả 2 phe
    const blueCombatants = data.combatants.filter(c => c.team_side === "BLUE");
    const redCombatants = data.combatants.filter(c => c.team_side === "RED");

    renderBattleRoster(blueCombatants, "BLUE", document.getElementById("blue-roster-container"));
    renderBattleRoster(redCombatants, "RED", document.getElementById("red-roster-container"));
    updateTeamHpDisplay("BLUE", blueCombatants);
    updateTeamHpDisplay("RED", redCombatants);

    // Ghi nhận các sự kiện mới vào Battle Log
    if (data.new_events && data.new_events.length > 0) {
        data.new_events.forEach(ev => appendLogItem(ev));
    }

    // Hiển thị Turn Order Queue
    renderTurnQueue(data.combatants);

    // Kiểm tra trạng thái
    if (data.status === "WAITING_PLAYER" && data.active_actor) {
        // Đến lượt tướng của người chơi
        setupTacticalCommandCenter(data.active_actor, data.combatants);
    } else if (data.status === "COMPLETED") {
        // Trận đấu kết thúc
        document.getElementById("tactical-command-panel").style.display = "none";
        document.getElementById("btn-start-battle").disabled = false;
        document.getElementById("btn-roll-team").disabled = false;
        document.getElementById("btn-start-battle").innerHTML = `<span class="btn-icon">⚔️</span> CHIẾN ĐẤU TIẾP`;

        refreshPlayerProfile();

        if (data.winner_team === "BLUE") {
            showToast("🎉 CHIẾN THẮNG! Bạn nhận được +120 Gold và +120 XP!", "success");
        } else if (data.winner_team === "RED") {
            showToast("💀 THẤT BẠI! Đội Red đã chiến thắng. Nhận +50 Gold an ủi.", "error");
        } else {
            showToast("⚖️ HÒA! Trận đấu kết thúc bất phân thắng bại.", "info");
        }
    }
}

function renderTurnQueue(combatants) {
    const queueBar = document.getElementById("turn-order-queue");
    const container = document.getElementById("queue-items-container");
    queueBar.style.display = "flex";
    container.innerHTML = "";

    const aliveSorted = combatants.filter(c => c.hp > 0).sort((a, b) => b.speed - a.speed);
    aliveSorted.forEach((c, idx) => {
        const node = document.createElement("div");
        node.className = `queue-node ${c.team_side.toLowerCase()} ${idx === 0 ? 'active-now' : ''}`;
        node.innerHTML = `<span>${c.emoji}</span> <span>${c.name}</span> <small>⚡${c.speed}</small>`;
        container.appendChild(node);
    });
}

function setupTacticalCommandCenter(activeActor, allCombatants) {
    const panel = document.getElementById("tactical-command-panel");
    panel.style.display = "block";

    document.getElementById("cmd-actor-emoji").textContent = activeActor.emoji;
    document.getElementById("cmd-actor-name").textContent = `${activeActor.name} (Lv.${activeActor.level})`;
    document.getElementById("cmd-actor-role").textContent = `${activeActor.role} • Hệ ${activeActor.element}`;

    // Highlight thẻ bài của tướng đang hành động
    document.querySelectorAll(".combatant-card").forEach(el => el.classList.remove("turn-active"));
    const activeCard = document.getElementById(`combatant-card-${activeActor.participant_idx}`);
    if (activeCard) activeCard.classList.add("turn-active");

    // Hiển thị 4 chiêu thức
    const abilitiesGrid = document.getElementById("cmd-abilities-grid");
    abilitiesGrid.innerHTML = "";

    clearTacticalTargeting();

    activeActor.abilities.forEach((ab, idx) => {
        const btn = document.createElement("div");
        const isCd = ab.current_cd > 0;
        btn.className = `ability-card-btn ${isCd ? 'disabled' : ''}`;
        btn.id = `btn-ability-${ab.id}`;

        const elemIcon = ab.element === "FIRE" ? "🔥" : (ab.element === "WATER" ? "💧" : (ab.element === "NATURE" ? "🌿" : "⚪"));
        const elemClass = `elem-${(ab.element || 'neutral').toLowerCase()}`;

        btn.innerHTML = `
            ${isCd ? `<span class="ab-cd-badge">Hồi: ${ab.current_cd} hiệp</span>` : ''}
            <div class="ab-top-row">
                <div class="ab-title-wrap">
                    <span>${ab.icon || '⚡'}</span>
                    <span>${ab.name}</span>
                </div>
                <span class="badge-elem-tag ${elemClass}">${elemIcon} ${ab.element}</span>
            </div>
            <div class="ab-stats-row">
                <span>💥 Uy lực: <strong>${ab.skill_power}</strong></span>
                <span>🎯 Cx: <strong>${ab.accuracy}%</strong></span>
                <span>🎯 Loại: <small>${formatTargetType(ab.target_type)}</small></span>
            </div>
            <p class="ab-desc">${ab.description || ''}</p>
        `;

        if (!isCd) {
            btn.addEventListener("click", () => selectTacticalAbility(ab, activeActor, allCombatants));
        }

        abilitiesGrid.appendChild(btn);

        // Mặc định chọn chiêu đầu tiên nếu chưa chọn
        if (idx === 0 && !isCd && !state.selectedAbilityId) {
            selectTacticalAbility(ab, activeActor, allCombatants);
        }
    });
}

function formatTargetType(tType) {
    if (tType === "SINGLE_ENEMY") return "1 Địch";
    if (tType === "ALL_ENEMIES") return "Toàn Địch";
    if (tType === "SINGLE_ALLY") return "1 Đồng minh";
    if (tType === "SELF") return "Bản thân";
    return tType;
}

function selectTacticalAbility(ability, actor, allCombatants) {
    state.selectedAbilityId = ability.id;
    state.selectedTargetIdx = null;

    // Highlight nút chiêu thức
    document.querySelectorAll(".ability-card-btn").forEach(el => el.classList.remove("selected"));
    const activeBtn = document.getElementById(`btn-ability-${ability.id}`);
    if (activeBtn) activeBtn.classList.add("selected");

    // Xóa targeting cũ
    clearTargetHighlights();

    const targetType = ability.target_type;
    const instruction = document.getElementById("cmd-instruction");

    if (targetType === "ALL_ENEMIES") {
        instruction.textContent = "⚡ Chiêu thức diện rộng sẽ đánh trúng TOÀN BỘ quân địch! Hãy bấm Xác Nhận.";
        document.getElementById("cmd-target-name").textContent = "💥 Toàn bộ đội hình RED";
        document.getElementById("btn-confirm-action").disabled = false;
        // Highlight tất cả kẻ địch
        document.querySelectorAll("[data-side='RED']").forEach(el => el.classList.add("targetable"));
    } else if (targetType === "SELF") {
        instruction.textContent = "🛡️ Chiêu thức tự áp dụng lên bản thân. Hãy bấm Xác Nhận.";
        document.getElementById("cmd-target-name").textContent = `Bản thân (${actor.name})`;
        document.getElementById("btn-confirm-action").disabled = false;
        state.selectedTargetIdx = actor.participant_idx;
        const selfCard = document.getElementById(`combatant-card-${actor.participant_idx}`);
        if (selfCard) selfCard.classList.add("target-selected");
    } else if (targetType === "SINGLE_ALLY") {
        instruction.textContent = "💚 Nhấp vào một đồng minh ĐỘI BLUE trên chiến trường để hỗ trợ/hồi máu!";
        document.getElementById("cmd-target-name").textContent = "Chưa chọn đồng minh";
        document.getElementById("btn-confirm-action").disabled = true;
        // Highlight đồng đội còn sống
        document.querySelectorAll("[data-side='BLUE']").forEach(el => {
            if (!el.classList.contains("dead")) el.classList.add("targetable");
        });
    } else {
        // SINGLE_ENEMY
        instruction.textContent = "🎯 Nhấp trực tiếp vào một kẻ địch ĐỘI RED trên chiến trường để tấn công!";
        document.getElementById("cmd-target-name").textContent = "Chưa chọn mục tiêu";
        document.getElementById("btn-confirm-action").disabled = true;
        // Highlight kẻ địch còn sống
        document.querySelectorAll("[data-side='RED']").forEach(el => {
            if (!el.classList.contains("dead")) el.classList.add("targetable");
        });
    }
}

function handleCombatantDirectClick(pIdx, teamSide, combatant) {
    if (state.battleMode !== "TACTICAL" || !state.selectedAbilityId) return;

    const card = document.getElementById(`combatant-card-${pIdx}`);
    if (!card || !card.classList.contains("targetable")) return;

    // Đánh dấu mục tiêu được chọn
    document.querySelectorAll(".combatant-card").forEach(el => el.classList.remove("target-selected"));
    card.classList.add("target-selected");

    state.selectedTargetIdx = pIdx;
    document.getElementById("cmd-target-name").textContent = `${combatant.emoji} [${teamSide}] ${combatant.name} (Slot ${combatant.slot_no + 1})`;
    document.getElementById("btn-confirm-action").disabled = false;
}

function clearTargetHighlights() {
    document.querySelectorAll(".combatant-card").forEach(el => {
        el.classList.remove("targetable", "target-selected");
    });
}

function clearTacticalTargeting() {
    state.selectedAbilityId = null;
    state.selectedTargetIdx = null;
    clearTargetHighlights();
    document.querySelectorAll(".ability-card-btn").forEach(el => el.classList.remove("selected"));
    document.getElementById("cmd-target-name").textContent = "Chưa chọn mục tiêu";
    document.getElementById("btn-confirm-action").disabled = true;
}

async function submitTacticalPlayerAction() {
    if (!state.tacticalBattleId || !state.selectedAbilityId || state.isTacticalBusy) return;

    try {
        state.isTacticalBusy = true;
        const btnConfirm = document.getElementById("btn-confirm-action");
        btnConfirm.disabled = true;
        btnConfirm.textContent = "⏳ Đang thi triển...";

        const res = await fetch("/api/battle/tactical/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                battle_id: state.tacticalBattleId,
                ability_id: state.selectedAbilityId,
                target_idx: state.selectedTargetIdx
            })
        });

        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Hành động thất bại");

        clearTacticalTargeting();
        processTacticalStepResult(json);
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        state.isTacticalBusy = false;
        const btnConfirm = document.getElementById("btn-confirm-action");
        btnConfirm.textContent = "⚔️ XÁC NHẬN TẤN CÔNG";
    }
}

// ==========================================================================
// AUTO MODE PLAYBACK (TỰ ĐỘNG PHÁT VÀ ĐIỀU KHIỂN TỐC ĐỘ)
// ==========================================================================
function startAutoPlayback() {
    state.isAutoPlaying = true;
    document.getElementById("btn-auto-play").textContent = "⏸️ Tạm dừng";
    clearInterval(state.autoTimer);
    state.autoTimer = setInterval(playNextAutoStep, state.autoSpeed);
}

function pauseAutoPlayback() {
    state.isAutoPlaying = false;
    document.getElementById("btn-auto-play").textContent = "▶️ Tự động";
    clearInterval(state.autoTimer);
}

function toggleAutoPlayback() {
    if (state.isAutoPlaying) pauseAutoPlayback();
    else {
        if (!state.autoBattle) return;
        startAutoPlayback();
    }
}

function toggleAutoSpeed() {
    const btn = document.getElementById("btn-speed-toggle");
    if (state.autoSpeed === 600) {
        state.autoSpeed = 250;
        btn.textContent = "⚡ 2x";
    } else if (state.autoSpeed === 250) {
        state.autoSpeed = 100;
        btn.textContent = "⚡ 3x";
    } else {
        state.autoSpeed = 600;
        btn.textContent = "⚡ 1x";
    }

    if (state.isAutoPlaying) startAutoPlayback();
}

function playNextAutoStep() {
    if (!state.autoBattle || !state.autoBattle.events) return;
    const events = state.autoBattle.events;
    if (state.autoPlaybackIndex >= events.length) {
        finishAutoBattlePlayback();
        return;
    }

    const ev = events[state.autoPlaybackIndex];
    appendLogItem(ev);
    document.getElementById("arena-round-counter").textContent = `Hiệp ${ev.round_no}`;
    document.getElementById("log-round-info").textContent = `Hiệp: ${ev.round_no} | Sự kiện: ${ev.event_order}/${events.length}`;

    // Hiệu ứng trên thẻ bài
    const actorCard = document.getElementById(`combatant-card-${ev.actor_idx}`);
    const targetCard = document.getElementById(`combatant-card-${ev.target_idx}`);

    document.querySelectorAll(".combatant-card").forEach(el => el.classList.remove("turn-active"));
    if (actorCard) actorCard.classList.add("turn-active");

    if (targetCard) {
        if (ev.event_type === "HEAL") {
            targetCard.classList.add("heal-glow");
            setTimeout(() => targetCard.classList.remove("heal-glow"), 500);
        } else if (ev.damage > 0) {
            targetCard.classList.add("hit-shake");
            setTimeout(() => targetCard.classList.remove("hit-shake"), 400);
        }
        if (ev.event_type === "DEFEAT") {
            targetCard.classList.add("dead");
        }
    }

    state.autoPlaybackIndex++;
    if (state.autoPlaybackIndex >= events.length) {
        finishAutoBattlePlayback();
    }
}

function skipAutoToEnd() {
    if (!state.autoBattle) return;
    pauseAutoPlayback();

    const events = state.autoBattle.events;
    while (state.autoPlaybackIndex < events.length) {
        appendLogItem(events[state.autoPlaybackIndex]);
        state.autoPlaybackIndex++;
    }

    finishAutoBattlePlayback();
}

function finishAutoBattlePlayback() {
    pauseAutoPlayback();
    document.querySelectorAll(".combatant-card").forEach(el => el.classList.remove("turn-active"));

    const btnFight = document.getElementById("btn-start-battle");
    const btnRoll = document.getElementById("btn-roll-team");
    btnFight.disabled = false;
    btnRoll.disabled = false;
    btnFight.innerHTML = `<span class="btn-icon">⚔️</span> CHIẾN ĐẤU TIẾP`;

    refreshPlayerProfile();

    const winner = state.autoBattle.winner_team;
    if (winner === "BLUE") showToast("🎉 CHIẾN THẮNG! Đội Blue đã thắng trận!", "success");
    else if (winner === "RED") showToast("💀 THẤT BẠI! Đội Red đã chiến thắng.", "error");
    else showToast("⚖️ HÒA! Trận đấu kết thúc bất phân thắng bại.", "info");
}

function appendLogItem(ev) {
    const feed = document.getElementById("battle-log-feed");
    const item = document.createElement("div");
    const type = (ev.event_type || 'attack').toLowerCase();
    item.className = `log-item ${type}`;

    let badge = "";
    if (ev.actor_side === "BLUE") badge = `<span class="log-badge badge-blue">BLUE</span>`;
    else if (ev.actor_side === "RED") badge = `<span class="log-badge badge-red">RED</span>`;

    item.innerHTML = `${badge} <span>${ev.message}</span>`;
    feed.appendChild(item);
    feed.scrollTop = feed.scrollHeight;
}

// ==========================================================================
// TAB 2: HERO MANAGEMENT SCREEN
// ==========================================================================
async function loadHeroManagement() {
    try {
        const res = await fetch("/api/heroes");
        const json = await res.json();
        if (!json.success) throw new Error("Không thể tải danh sách tướng");

        const container = document.getElementById("heroes-management-container");
        container.innerHTML = json.data.map(h => {
            const stats = h.effective_stats || {};
            const xpReq = h.next_level_xp || (h.level * 100);
            const xpPct = Math.min(100, Math.round(((h.xp || 0) / xpReq) * 100));

            const elemIcon = h.element === "FIRE" ? "🔥" : (h.element === "WATER" ? "💧" : "🌿");
            const elemClass = `elem-${(h.element || 'nature').toLowerCase()}`;

            const skillsHtml = (h.abilities || []).map(ab => `
                <div class="mgr-ab-item">
                    <span>${ab.icon || '⚡'} <strong>${ab.name}</strong></span>
                    <small>💥${ab.skill_power} | 🎯${ab.accuracy}%</small>
                </div>
            `).join("");

            return `
                <div class="hero-mgr-card">
                    <div class="hero-mgr-header">
                        <div class="hero-mgr-avatar">
                            <span>${h.emoji}</span>
                        </div>
                        <div class="mgr-name-box">
                            <h3>${h.name}</h3>
                            <span class="badge-elem-tag ${elemClass}">${elemIcon} Hệ ${h.element}</span>
                            <span class="text-muted">• ${h.role}</span>
                        </div>
                    </div>

                    <div class="hero-xp-track-box">
                        <div class="xp-label-row">
                            <strong>Level ${h.level}</strong>
                            <span>${h.xp || 0} / ${xpReq} XP</span>
                        </div>
                        <div class="xp-bar-track">
                            <div class="xp-bar-fill" style="width: ${xpPct}%;"></div>
                        </div>
                    </div>

                    <div class="mgr-stats-grid">
                        <div>❤️ HP: <strong>${stats.max_hp || h.base_hp}</strong></div>
                        <div>⚔️ ATK: <strong>${stats.atk || h.base_atk}</strong></div>
                        <div>🛡️ DEF: <strong>${stats.def || h.base_def}</strong></div>
                        <div>⚡ SPD: <strong>${stats.speed || h.base_speed}</strong></div>
                        <div>🎯 Accuracy: <strong>${stats.accuracy || h.base_accuracy}%</strong></div>
                        <div>💥 Crit: <strong>${stats.crit_rate || h.base_crit_rate}%</strong></div>
                    </div>

                    <div class="mgr-abilities-preview">
                        <strong>Kỹ Năng Kích Hoạt:</strong>
                        ${skillsHtml}
                    </div>

                    <button class="btn btn-primary btn-sm" onclick="trainHero(${h.id}, ${h.level})">
                        💎 Huấn Luyện Lên Cấp (${h.level * 150} Gold)
                    </button>
                </div>
            `;
        }).join("");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function trainHero(heroId, currLevel) {
    try {
        const res = await fetch(`/api/heroes/${heroId}/train`, { method: "POST" });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Huấn luyện thất bại");

        showToast(json.message, "success");
        refreshPlayerProfile();
        loadHeroManagement();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==========================================================================
// TAB 3: EQUIPMENT / INVENTORY SCREEN
// ==========================================================================
function setupEquipmentEvents() {
    document.getElementById("equip-hero-select").addEventListener("change", (e) => {
        state.selectedHeroIdForEquip = parseInt(e.target.value);
        loadHeroEquipPreview();
    });

    document.getElementById("filter-slot-type").addEventListener("change", loadInventoryGrid);
    document.getElementById("filter-rarity").addEventListener("change", loadInventoryGrid);

    // Equip / Upgrade buttons
    document.getElementById("btn-equip-selected").addEventListener("click", equipSelectedItem);
    document.getElementById("btn-upgrade-selected").addEventListener("click", upgradeSelectedItem);

    // Unequip buttons for slots
    document.getElementById("btn-unequip-weapon").addEventListener("click", () => unequipSlot("WEAPON"));
    document.getElementById("btn-unequip-armor").addEventListener("click", () => unequipSlot("ARMOR"));
    document.getElementById("btn-unequip-boots").addEventListener("click", () => unequipSlot("BOOTS"));
    document.getElementById("btn-unequip-accessory").addEventListener("click", () => unequipSlot("ACCESSORY"));
}

async function loadEquipmentScreen() {
    // Populate hero select dropdown
    const res = await fetch("/api/heroes");
    const json = await res.json();
    if (json.success) {
        const sel = document.getElementById("equip-hero-select");
        sel.innerHTML = json.data.map(h => `
            <option value="${h.id}" ${h.id === state.selectedHeroIdForEquip ? 'selected' : ''}>
                ${h.emoji} ${h.name} (Lv.${h.level} - ${h.role})
            </option>
        `).join("");
    }

    loadHeroEquipPreview();
    loadInventoryGrid();
}

async function loadHeroEquipPreview() {
    try {
        const res = await fetch(`/api/heroes/${state.selectedHeroIdForEquip}`);
        const json = await res.json();
        if (!json.success) return;

        const h = json.data;
        document.getElementById("preview-hero-emoji").textContent = h.emoji;
        document.getElementById("preview-hero-name").textContent = h.name;
        document.getElementById("preview-hero-level").textContent = `Lv. ${h.level}`;

        // Reset 4 slots
        ["weapon", "armor", "boots", "accessory"].forEach(s => {
            document.getElementById(`slot-${s}-title`).textContent = "Chưa trang bị";
            document.getElementById(`slot-${s}`).classList.remove("occupied");
            document.getElementById(`btn-unequip-${s}`).style.display = "none";
        });

        // Fill equipped slots
        (h.equipped_items || []).forEach(it => {
            const slotKey = it.slot_type.toLowerCase();
            const titleElem = document.getElementById(`slot-${slotKey}-title`);
            const slotCard = document.getElementById(`slot-${slotKey}`);
            const btnUnequip = document.getElementById(`btn-unequip-${slotKey}`);

            if (titleElem) {
                titleElem.innerHTML = `<strong>${it.icon || '🗡️'} ${it.name} (+${it.upgrade_level})</strong>`;
                slotCard.classList.add("occupied");
                btnUnequip.style.display = "inline-flex";
                btnUnequip.setAttribute("data-inv-id", it.inventory_id);
            }
        });

        // Render effective stats
        const stats = h.effective_stats || {};
        document.getElementById("preview-stats-list").innerHTML = `
            <div>❤️ HP: <strong>${stats.max_hp}</strong></div>
            <div>⚔️ ATK: <strong>${stats.atk}</strong></div>
            <div>🛡️ DEF: <strong>${stats.def}</strong></div>
            <div>⚡ SPD: <strong>${stats.speed}</strong></div>
            <div>🎯 ACC: <strong>${stats.accuracy}%</strong></div>
            <div>💥 CRIT: <strong>${stats.crit_rate}%</strong></div>
        `;
    } catch (e) {
        console.error(e);
    }
}

async function loadInventoryGrid() {
    try {
        const slot = document.getElementById("filter-slot-type").value;
        const rarity = document.getElementById("filter-rarity").value;

        let url = "/api/inventory?";
        if (slot) url += `slot_type=${slot}&`;
        if (rarity) url += `rarity=${rarity}&`;

        const res = await fetch(url);
        const json = await res.json();
        if (!json.success) return;

        const grid = document.getElementById("inventory-items-grid");
        if (json.data.length === 0) {
            grid.innerHTML = `<div class="text-center text-muted p-4">Kho đồ trống. Hãy ghé Cửa hàng hoặc quay Vòng quay may mắn nhé!</div>`;
            return;
        }

        grid.innerHTML = json.data.map(it => `
            <div class="inv-item-card rarity-${it.rarity} ${state.selectedInventoryItem && state.selectedInventoryItem.inventory_id === it.inventory_id ? 'selected' : ''}"
                 onclick="selectInventoryItem(${it.inventory_id})">
                <span class="inv-item-lvl">+${it.upgrade_level}</span>
                <div class="inv-item-icon">${it.icon || '🗡️'}</div>
                <span class="inv-item-name">${it.name}</span>
                <span class="inv-item-slot">${it.slot_type}</span>
                ${it.is_equipped ? `<span class="inv-equipped-tag">Đang mặc (${it.equipped_hero_name || 'Hero'})</span>` : ''}
            </div>
        `).join("");
    } catch (e) {
        console.error(e);
    }
}

async function selectInventoryItem(inventoryId) {
    const res = await fetch("/api/inventory");
    const json = await res.json();
    if (!json.success) return;

    const item = json.data.find(it => it.inventory_id === inventoryId);
    if (!item) return;

    state.selectedInventoryItem = item;
    loadInventoryGrid();

    // Show Detail Action Card
    const card = document.getElementById("item-detail-card");
    card.style.display = "flex";

    document.getElementById("detail-icon").textContent = item.icon || '🗡️';
    document.getElementById("detail-name").textContent = item.name;
    document.getElementById("detail-rarity").textContent = item.rarity;
    document.getElementById("detail-rarity").className = `badge-rarity badge-rarity-${item.rarity.toLowerCase()}`;
    document.getElementById("detail-slot").textContent = item.slot_type;
    document.getElementById("detail-upgrade-badge").textContent = `+${item.upgrade_level}`;

    // Stats breakdown
    const statsArr = [];
    if (item.current_atk > 0) statsArr.push(`⚔️ +${item.current_atk} ATK`);
    if (item.current_def > 0) statsArr.push(`🛡️ +${item.current_def} DEF`);
    if (item.current_hp > 0) statsArr.push(`❤️ +${item.current_hp} HP`);
    if (item.current_speed > 0) statsArr.push(`⚡ +${item.current_speed} SPD`);
    if (item.current_crit_rate > 0) statsArr.push(`💥 +${item.current_crit_rate}% CRIT`);
    if (item.current_armor_penetration > 0) statsArr.push(`💨 +${item.current_armor_penetration} Xuyên giáp`);

    document.getElementById("detail-stats-body").innerHTML = statsArr.map(s => `<div>${s}</div>`).join("") || `<div>Chỉ số cơ bản</div>`;

    // Upgrade cost
    const costNote = document.getElementById("detail-upgrade-cost-note");
    if (item.upgrade_cost) {
        costNote.innerHTML = `Chi phí cường hóa lên <strong>+${item.upgrade_level + 1}</strong>: 🪙 ${item.upgrade_cost.gold} Gold + 💎 ${item.upgrade_cost.stones} Đá cường hóa ${item.upgrade_cost.crystals > 0 ? `+ 🔮 ${item.upgrade_cost.crystals} Tinh thể` : ''}`;
        document.getElementById("btn-upgrade-selected").disabled = false;
    } else {
        costNote.innerHTML = `Trang bị đã đạt cấp tối đa (+${item.max_upgrade_level})!`;
        document.getElementById("btn-upgrade-selected").disabled = true;
    }
}

async function equipSelectedItem() {
    if (!state.selectedInventoryItem) return;

    try {
        const res = await fetch("/api/inventory/equip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                inventory_id: state.selectedInventoryItem.inventory_id,
                hero_id: state.selectedHeroIdForEquip
            })
        });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Không thể trang bị");

        showToast(json.message, "success");
        loadHeroEquipPreview();
        loadInventoryGrid();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function unequipSlot(slotType) {
    const btn = document.getElementById(`btn-unequip-${slotType.toLowerCase()}`);
    const invId = btn.getAttribute("data-inv-id");
    if (!invId) return;

    try {
        const res = await fetch("/api/inventory/unequip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ inventory_id: parseInt(invId) })
        });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Không thể tháo đồ");

        showToast(json.message, "success");
        loadHeroEquipPreview();
        loadInventoryGrid();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function upgradeSelectedItem() {
    if (!state.selectedInventoryItem) return;

    try {
        const res = await fetch("/api/inventory/upgrade", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ inventory_id: state.selectedInventoryItem.inventory_id })
        });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Cường hóa thất bại");

        showToast(json.message, "success");
        refreshPlayerProfile();
        selectInventoryItem(state.selectedInventoryItem.inventory_id);
        loadHeroEquipPreview();
        loadInventoryGrid();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==========================================================================
// TAB 4: SHOP SCREEN
// ==========================================================================
function setupShopEvents() {
    document.querySelectorAll(".btn-shop-cat").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".btn-shop-cat").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            renderShopCategory(btn.getAttribute("data-cat"));
        });
    });
}

let shopCache = null;

async function loadShopCatalog() {
    try {
        const res = await fetch("/api/shop");
        const json = await res.json();
        if (json.success) {
            shopCache = json.data;
            renderShopCategory("WEAPON");
        }
    } catch (e) {
        console.error(e);
    }
}

function renderShopCategory(category) {
    if (!shopCache) return;
    const items = shopCache[category] || [];
    const container = document.getElementById("shop-items-grid");

    if (items.length === 0) {
        container.innerHTML = `<div class="text-center p-4">Danh mục này hiện chưa có mặt hàng.</div>`;
        return;
    }

    container.innerHTML = items.map(it => {
        const isMat = category === "MATERIAL";
        return `
            <div class="shop-item-card rarity-${it.rarity}">
                <div class="shop-item-top">
                    <span class="shop-item-icon">${it.icon || '🗡️'}</span>
                    <div class="shop-item-title-box">
                        <h4>${it.name}</h4>
                        <span class="badge-rarity">${it.rarity}</span>
                    </div>
                </div>
                <div class="shop-item-stats">
                    ${it.description || ''}
                </div>
                <div class="shop-item-bottom">
                    <span class="shop-price-tag">🪙 ${it.price} Gold</span>
                    <button class="btn btn-primary btn-sm" onclick="buyShopItem(${it.id}, ${isMat})">
                        Mua Ngay
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

async function buyShopItem(itemId, isMaterial) {
    try {
        const res = await fetch("/api/shop/buy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ item_id: itemId, is_material: isMaterial })
        });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Giao dịch thất bại");

        showToast(json.message, "success");
        refreshPlayerProfile();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==========================================================================
// TAB 5: LUCKY WHEEL SCREEN (CANVAS ANIMATION & PITY)
// ==========================================================================
function setupWheelEvents() {
    document.getElementById("btn-spin-gold").addEventListener("click", () => triggerWheelSpin("GOLD"));
    document.getElementById("btn-spin-ticket").addEventListener("click", () => triggerWheelSpin("TICKET"));
}

async function loadWheelScreen() {
    try {
        const res = await fetch("/api/wheel");
        const json = await res.json();
        if (json.success) {
            const d = json.data;
            document.getElementById("pity-text").textContent = `${d.current_pity} / ${d.pity_threshold} (Chắc chắn Epic+ sau ${d.spins_until_pity} lượt)`;
            const pct = Math.min(100, Math.round((d.current_pity / d.pity_threshold) * 100));
            document.getElementById("pity-fill").style.width = `${pct}%`;
            document.getElementById("wheel-tickets-count").textContent = d.player_tickets;

            // Render Odds Table
            document.getElementById("wheel-odds-tbody").innerHTML = d.published_odds.map(o => `
                <tr>
                    <td><strong style="color: ${o.color};">${o.label}</strong></td>
                    <td><strong>${o.chance}%</strong></td>
                    <td>Xác suất mở thưởng ngẫu nhiên</td>
                </tr>
            `).join("");

            // Render History
            renderWheelHistory(d.recent_history);
        }
    } catch (e) {
        console.error(e);
    }
}

function renderWheelHistory(history) {
    const feed = document.getElementById("wheel-history-feed");
    if (!history || history.length === 0) {
        feed.innerHTML = `<div class="text-center text-muted p-2">Chưa có lượt quay nào</div>`;
        return;
    }

    feed.innerHTML = history.map(h => `
        <div class="log-item" style="border-left-color: ${h.rarity === 'LEGENDARY' ? '#f59e0b' : (h.rarity === 'EPIC' ? '#a855f7' : '#3b82f6')};">
            <span>[${h.cost_type}]</span>
            <strong>${h.reward_name}</strong>
            <span class="badge-rarity" style="margin-left: auto;">${h.rarity}</span>
        </div>
    `).join("");
}

function drawLuckyWheelCanvas() {
    const canvas = document.getElementById("wheel-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const numSlices = 6;
    const sliceAngle = (2 * Math.PI) / numSlices;
    const colors = ["#f59e0b", "#06b6d4", "#9ca3af", "#3b82f6", "#a855f7", "#eab308"];
    const labels = ["Gold 🪙", "Nguyên liệu 💎", "Common 🗡️", "Rare 🛡️", "Epic 🔮", "Legendary ⚔️"];

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const r = cx - 10;

    for (let i = 0; i < numSlices; i++) {
        const startAngle = i * sliceAngle - Math.PI / 2;
        const endAngle = startAngle + sliceAngle;

        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, startAngle, endAngle);
        ctx.fillStyle = colors[i];
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#0e131f";
        ctx.stroke();

        // Label
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(startAngle + sliceAngle / 2);
        ctx.textAlign = "right";
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 13px Outfit, sans-serif";
        ctx.fillText(labels[i], r - 18, 5);
        ctx.restore();
    }

    // Center pin
    ctx.beginPath();
    ctx.arc(cx, cy, 22, 0, 2 * Math.PI);
    ctx.fillStyle = "#0e131f";
    ctx.fill();
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 3;
    ctx.stroke();
}

async function triggerWheelSpin(costType) {
    if (state.isSpinning) return;

    try {
        state.isSpinning = true;
        const res = await fetch("/api/wheel/spin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cost_type: costType })
        });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || "Không thể quay thưởng");

        // Animate Wheel
        const sliceIdx = json.slice_index || 0;
        const sliceAngleDeg = 360 / 6;
        // Target angle points to top pointer
        const targetDeg = (360 - (sliceIdx * sliceAngleDeg + sliceAngleDeg / 2));
        const totalRotations = 5 * 360;
        state.wheelAngle += totalRotations + targetDeg - (state.wheelAngle % 360);

        const canvas = document.getElementById("wheel-canvas");
        canvas.style.transform = `rotate(${state.wheelAngle}deg)`;

        setTimeout(() => {
            state.isSpinning = false;
            showToast(json.message, "success");
            refreshPlayerProfile();
            loadWheelScreen();
        }, 4100);
    } catch (e) {
        state.isSpinning = false;
        showToast(e.message, "error");
    }
}

// ==========================================================================
// TAB 6: META TRACKER & CHARTS
// ==========================================================================
async function loadMetaTrackerData() {
    try {
        const [overviewRes, heroesRes, elemsRes, compsRes] = await Promise.all([
            fetch("/api/analytics/overview"),
            fetch("/api/analytics/heroes"),
            fetch("/api/analytics/elements"),
            fetch("/api/analytics/compositions?limit=10")
        ]);

        const ovJson = await overviewRes.json();
        const hJson = await heroesRes.json();
        const elJson = await elemsRes.json();
        const cJson = await compsRes.json();

        if (ovJson.success) renderOverviewCards(ovJson.data);
        if (hJson.success) {
            renderCharts(hJson.data, elJson.data);
            renderHeroesTable(hJson.data);
        }
        if (cJson.success) renderCompositionsTable(cJson.data);
    } catch (e) {
        console.error(e);
    }
}

function renderOverviewCards(data) {
    document.getElementById("stat-total-matches").textContent = data.total_matches;
    document.getElementById("stat-breakdown").textContent = `Thắng: ${data.player_wins} | Thua: ${data.player_losses} | Hòa: ${data.player_draws}`;
    document.getElementById("stat-win-rate").textContent = `${data.player_win_rate}%`;
    document.getElementById("stat-mode-breakdown").textContent = `Tactical: ${data.tactical_matches} | Auto: ${data.auto_matches}`;

    if (data.most_picked_hero) {
        document.getElementById("stat-most-picked").textContent = `${data.most_picked_hero.emoji} ${data.most_picked_hero.name}`;
        document.getElementById("stat-most-picked-count").textContent = `${data.most_picked_hero.pick_count} lượt xuất hiện`;
    }

    if (data.highest_winrate_hero) {
        document.getElementById("stat-highest-winrate").textContent = `${data.highest_winrate_hero.emoji} ${data.highest_winrate_hero.name}`;
        document.getElementById("stat-highest-winrate-info").textContent = `${data.highest_winrate_hero.win_rate}% (${data.highest_winrate_hero.total_wins}/${data.highest_winrate_hero.total_picks} trận)`;
    }

    document.getElementById("stat-gold-economy").textContent = `🪙 +${data.total_gold_earned} / -${data.total_gold_spent}`;
    document.getElementById("stat-spins-count").textContent = `${data.total_wheel_spins} lượt quay Lucky Wheel`;
}

function renderCharts(heroesData, elementData) {
    const labels = heroesData.map(h => `${h.emoji} ${h.name}`);
    const winRates = heroesData.map(h => h.win_rate);
    const avgDamages = heroesData.map(h => h.avg_damage);

    // 1. Win Rate Chart
    if (state.charts.winrate) state.charts.winrate.destroy();
    const ctxWin = document.getElementById("chart-winrate").getContext("2d");
    state.charts.winrate = new Chart(ctxWin, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: "Win Rate (%)",
                data: winRates,
                backgroundColor: "rgba(59, 130, 246, 0.75)",
                borderColor: "#3b82f6",
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, max: 100, ticks: { color: "#9ca3af" }, grid: { color: "rgba(255,255,255,0.05)" } },
                x: { ticks: { color: "#9ca3af" }, grid: { display: false } }
            },
            plugins: { legend: { display: false } }
        }
    });

    // 2. Avg Damage Chart
    if (state.charts.damage) state.charts.damage.destroy();
    const ctxDmg = document.getElementById("chart-avg-damage").getContext("2d");
    state.charts.damage = new Chart(ctxDmg, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: "Avg Damage",
                data: avgDamages,
                backgroundColor: "rgba(239, 68, 68, 0.75)",
                borderColor: "#ef4444",
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, ticks: { color: "#9ca3af" }, grid: { color: "rgba(255,255,255,0.05)" } },
                x: { ticks: { color: "#9ca3af" }, grid: { display: false } }
            },
            plugins: { legend: { display: false } }
        }
    });

    // 3. Elements Doughnut Chart
    if (state.charts.elements) state.charts.elements.destroy();
    const ctxElem = document.getElementById("chart-elements").getContext("2d");
    const elLabels = (elementData || []).map(e => `${e.element === 'FIRE' ? '🔥' : (e.element === 'WATER' ? '💧' : '🌿')} ${e.element} (${e.win_rate}%)`);
    const elPicks = (elementData || []).map(e => e.total_picks);
    state.charts.elements = new Chart(ctxElem, {
        type: "doughnut",
        data: {
            labels: elLabels,
            datasets: [{
                data: elPicks,
                backgroundColor: ["#ef4444", "#06b6d4", "#10b981"],
                borderWidth: 2,
                borderColor: "#0e131f"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: "right", labels: { color: "#9ca3af", boxWidth: 12 } } }
        }
    });
}

function renderHeroesTable(heroes) {
    document.getElementById("heroes-analytics-tbody").innerHTML = heroes.map(h => `
        <tr>
            <td><strong>${h.emoji} ${h.name}</strong></td>
            <td><span class="badge-elem-tag elem-${h.element.toLowerCase()}">${h.element}</span></td>
            <td>${h.role}</td>
            <td><strong style="color: #93c5fd;">Lv. ${h.current_level}</strong></td>
            <td><strong>${h.total_picks}</strong></td>
            <td>${h.total_wins}</td>
            <td><strong style="color: ${h.win_rate >= 50 ? 'var(--green-accent)' : 'var(--text-muted)'};">${h.win_rate}%</strong></td>
            <td>${h.total_damage}</td>
            <td>${h.avg_damage}</td>
            <td>${h.total_kills}</td>
        </tr>
    `).join("");
}

function renderCompositionsTable(comps) {
    const tbody = document.getElementById("compositions-tbody");
    if (!comps || comps.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Chưa có dữ liệu đội hình</td></tr>`;
        return;
    }

    tbody.innerHTML = comps.map((c, idx) => `
        <tr>
            <td>
                <span class="comp-rank-badge rank-${idx + 1}">#${idx + 1}</span>
                <strong>${c.comp_emojis || ''} ${c.comp_name}</strong>
            </td>
            <td>${c.total_matches}</td>
            <td><span style="color: var(--green-accent);">${c.wins}</span></td>
            <td><strong>${c.win_rate}%</strong></td>
        </tr>
    `).join("");
}

// ==========================================================================
// TAB 7: MATCH HISTORY & DETAIL MODAL
// ==========================================================================
function setupHistoryEvents() {
    document.getElementById("btn-refresh-history").addEventListener("click", loadMatchHistory);
}

async function loadMatchHistory() {
    try {
        const res = await fetch("/api/matches?limit=30");
        const json = await res.json();
        if (!json.success) return;

        const list = document.getElementById("history-matches-list");
        if (json.data.length === 0) {
            list.innerHTML = `<div class="history-empty">Chưa có trận đấu nào được lưu lại.</div>`;
            return;
        }

        list.innerHTML = json.data.map(m => {
            const isWin = m.winner_team === "BLUE";
            const isLoss = m.winner_team === "RED";
            const badgeClass = isWin ? "badge-win" : (isLoss ? "badge-loss" : "badge-draw");
            const badgeText = isWin ? "VICTORY" : (isLoss ? "DEFEAT" : "DRAW");

            return `
                <div class="history-match-item" onclick="openMatchModal(${m.id})">
                    <div class="match-result-badge ${badgeClass}">${badgeText}</div>
                    <span class="modal-mode-badge">${m.battle_mode || 'AUTO'}</span>
                    <div class="match-item-teams">
                        <div class="match-team-row"><span class="match-side-label side-blue">BLUE</span> <span>${m.blue_lineup || '---'}</span></div>
                        <div class="match-team-row"><span class="match-side-label side-red">RED</span> <span>${m.red_lineup || '---'}</span></div>
                    </div>
                    <div class="match-item-meta">
                        <div><strong>${m.total_rounds} Hiệp</strong></div>
                        <div>+${m.gold_reward} 🪙 | +${m.xp_reward} XP</div>
                    </div>
                    <button class="btn btn-outline btn-sm">Chi tiết 🔍</button>
                </div>
            `;
        }).join("");
    } catch (e) {
        console.error(e);
    }
}

function setupModalEvents() {
    document.getElementById("btn-close-modal").addEventListener("click", () => {
        document.getElementById("match-modal").style.display = "none";
    });
    document.getElementById("match-modal").addEventListener("click", (e) => {
        if (e.target.id === "match-modal") document.getElementById("match-modal").style.display = "none";
    });
}

async function openMatchModal(matchId) {
    try {
        const res = await fetch(`/api/matches/${matchId}`);
        const json = await res.json();
        if (!json.success) return;

        const m = json.data;
        document.getElementById("modal-match-title").textContent = `Chi Tiết Trận Đấu #${m.id} (${m.total_rounds} Hiệp)`;
        document.getElementById("modal-mode-badge").textContent = m.battle_mode || 'AUTO';

        const isWin = m.winner_team === "BLUE";
        const isLoss = m.winner_team === "RED";
        const badge = document.getElementById("modal-match-badge");
        badge.className = `modal-badge match-result-badge ${isWin ? 'badge-win' : (isLoss ? 'badge-loss' : 'badge-draw')}`;
        badge.textContent = isWin ? "BLUE THẮNG" : (isLoss ? "RED THẮNG" : "HÒA");

        // Roster snapshots
        const renderRoster = (participants) => participants.map(p => `
            <div class="modal-hero-item">
                <div>
                    <span>${p.emoji}</span>
                    <strong>${p.name}</strong>
                    <small>(Lv.${p.hero_level || 1} • ${p.element})</small>
                </div>
                <div>
                    <span>HP: ${p.hp_end}/${p.hp_start} | Dmg: <strong>${p.damage_dealt}</strong> | Kills: <strong>${p.kills}</strong></span>
                </div>
            </div>
        `).join("");

        document.getElementById("modal-blue-heroes").innerHTML = renderRoster(m.blue_participants);
        document.getElementById("modal-red-heroes").innerHTML = renderRoster(m.red_participants);

        // Full battle events
        document.getElementById("modal-log-feed").innerHTML = (m.events || []).map(ev => {
            const type = (ev.event_type || 'attack').toLowerCase();
            let b = "";
            if (ev.actor_side === "BLUE") b = `<span class="log-badge badge-blue">BLUE</span>`;
            else if (ev.actor_side === "RED") b = `<span class="log-badge badge-red">RED</span>`;
            return `<div class="log-item ${type}">${b} <span>${ev.message}</span></div>`;
        }).join("");

        document.getElementById("match-modal").style.display = "flex";
    } catch (e) {
        console.error(e);
    }
}

// ==========================================================================
// TAB 8: PLAYER PROFILE & FINANCIAL TRANSACTIONS LEDGER
// ==========================================================================
async function loadProfileScreen() {
    try {
        const [profRes, txRes] = await Promise.all([
            fetch("/api/player/profile"),
            fetch("/api/player/transactions")
        ]);

        const pJson = await profRes.json();
        const txJson = await txRes.json();

        if (pJson.success) {
            const p = pJson.data;
            document.getElementById("profile-level-badge").textContent = `Level ${p.player_level}`;
            const reqXp = p.player_level * 150;
            document.getElementById("profile-xp-text").textContent = `${p.player_xp} / ${reqXp} XP`;
            const xpPct = Math.min(100, Math.round((p.player_xp / reqXp) * 100));
            document.getElementById("profile-xp-fill").style.width = `${xpPct}%`;

            document.getElementById("prof-gold").textContent = p.gold.toLocaleString();
            document.getElementById("prof-stones").textContent = p.materials.UPGRADE_STONE || 0;
            document.getElementById("prof-crystals").textContent = p.materials.ELEMENT_CRYSTAL || 0;
            document.getElementById("prof-tickets").textContent = p.materials.LUCKY_TICKET || 0;
        }

        if (txJson.success) {
            const tbody = document.getElementById("transactions-tbody");
            if (txJson.data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Chưa có giao dịch nào</td></tr>`;
                return;
            }

            tbody.innerHTML = txJson.data.map(tx => {
                const isPos = tx.amount > 0;
                const sign = isPos ? `+${tx.amount}` : `${tx.amount}`;
                const color = isPos ? "var(--green-accent)" : "#f87171";

                return `
                    <tr>
                        <td><small>${tx.created_at}</small></td>
                        <td><strong>${tx.reason}</strong></td>
                        <td><strong style="color: ${color};">${sign} Gold</strong></td>
                        <td>${tx.balance_after.toLocaleString()} Gold</td>
                    </tr>
                `;
            }).join("");
        }
    } catch (e) {
        console.error(e);
    }
}
