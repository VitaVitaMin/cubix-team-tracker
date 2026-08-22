import requests
import json
import time
from datetime import datetime

API_URL = "https://cubixworld.net/api/team"
STATE_FILE = "state.json"
LOG_FILE = "changes_log.json"
CHECK_INTERVAL = 300  # Интервал проверки в секундах (например, 5 минут)

def fetch_current_team():
    try:
        response = requests.get(API_URL, timeout=10)
        data = response.json()
        if data.get("type") != "success":
            return None
        
        flat_team = {}
        servers = data.get("team", {})
        for server_key, server_data in servers.items():
            server_name = server_data.get("server_name", "").strip()
            members = server_data.get("team", {})
            for m_key, member in members.items():
                member_id = member["id"]
                # Ключ включает ID и сервер, так как один человек может быть в составе разных серверов
                unique_key = f"{member_id}_{member['server']}"
                flat_team[unique_key] = {
                    "id": member_id,
                    "name": member["name"],
                    "group": member["group"],
                    "group_name": member["group_name"].strip(),
                    "server_id": member["server"],
                    "server_name": server_name
                }
        return flat_team
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        return None

def load_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def compare_states(old_state, new_state):
    events = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    old_keys = set(old_state.keys())
    new_keys = set(new_state.keys())

    # 1. Новые в составе
    added_keys = new_keys - old_keys
    for k in added_keys:
        m = new_state[k]
        events.append({
            "time": timestamp,
            "type": "ADDED",
            "player": m["name"],
            "server": m["server_name"],
            "group": m["group_name"],
            "details": f"Добавлен в состав на {m['server_name']} (Должность: {m['group_name']})"
        })

    # 2. Убранные из состава
    removed_keys = old_keys - new_keys
    for k in removed_keys:
        m = old_state[k]
        events.append({
            "time": timestamp,
            "type": "REMOVED",
            "player": m["name"],
            "server": m["server_name"],
            "group": m["group_name"],
            "details": f"Удален из состава {m['server_name']} (Был: {m['group_name']})"
        })

    # 3. Изменения у оставшихся
    common_keys = old_keys & new_keys
    for k in common_keys:
        old_m = old_state[k]
        new_m = new_state[k]

        # Изменение должности (повышение / понижение)
        if old_m["group"] != new_m["group"]:
            action = "PROMOTED" if new_m["group"] > old_m["group"] else "DEMOTED"
            action_text = "Повышен" if action == "PROMOTED" else "Понижен"
            events.append({
                "time": timestamp,
                "type": action,
                "player": new_m["name"],
                "server": new_m["server_name"],
                "old_group": old_m["group_name"],
                "new_group": new_m["group_name"],
                "details": f"{action_text} на {new_m['server_name']}: {old_m['group_name']} -> {new_m['group_name']}"
            })

    return events

def run_worker():
    print("Воркер запущен...")
    while True:
        current_state = fetch_current_team()
        if current_state is not None:
            old_state = load_json(STATE_FILE)
            
            if old_state:
                changes = compare_states(old_state, current_state)
                if changes:
                    logs = load_json(LOG_FILE)
                    if not isinstance(logs, list):
                        logs = []
                    logs.extend(changes)
                    save_json(LOG_FILE, logs)
                    print(f"Зафиксировано изменений: {len(changes)}")
            
            save_json(STATE_FILE, current_state)
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run_worker()
