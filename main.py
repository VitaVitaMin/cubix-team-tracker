import os
import json
import requests
from datetime import datetime

API_URL = "https://cubixworld.net/api/team"
STATE_FILE = "state.json"
LOG_FILE = "changes_log.json"

def read_json_file(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка чтения {filepath}: {e}")
    return default

def write_json_file(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка записи {filepath}: {e}")

def fetch_current_team():
    try:
        res = requests.get(API_URL, timeout=10)
        data = res.json()
        if data.get("type") != "success":
            return None
        
        flat_team = {}
        servers = data.get("team", {})
        for _, server_data in servers.items():
            server_name = server_data.get("server_name", "").strip()
            members = server_data.get("team", {})
            for _, member in members.items():
                unique_key = f"{member['id']}_{member['server']}"
                flat_team[unique_key] = {
                    "id": member["id"],
                    "name": member["name"].strip(),
                    "group": int(member["group"]),
                    "group_name": member["group_name"].strip(),
                    "server_id": member["server"],
                    "server_name": server_name
                }
        return flat_team
    except Exception as e:
        print(f"Ошибка запроса к API Cubix: {e}")
        return None

def compare_states(old_state, new_state):
    events = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    old_keys = set(old_state.keys())
    new_keys = set(new_state.keys())

    # 1. Приняты в состав
    for k in (new_keys - old_keys):
        m = new_state[k]
        events.append({
            "timestamp": timestamp,
            "player": m["name"],
            "server": m["server_name"],
            "details": f"Принят на должность ({m['group_name']})",
            "badge_type": "added",
            "badge_text": "ПРИНЯТ"
        })

    # 2. Уволены из состава
    for k in (old_keys - new_keys):
        m = old_state[k]
        events.append({
            "timestamp": timestamp,
            "player": m["name"],
            "server": m["server_name"],
            "details": f"Снят с должности (Был: {m['group_name']})",
            "badge_type": "removed",
            "badge_text": "СНЯТ"
        })

    # 3. Повышения и понижения
    for k in (old_keys & new_keys):
        old_m = old_state[k]
        new_m = new_state[k]

        if old_m["group"] != new_m["group"]:
            is_promoted = new_m["group"] > old_m["group"]
            events.append({
                "timestamp": timestamp,
                "player": new_m["name"],
                "server": new_m["server_name"],
                "details": f"{old_m['group_name']} → {new_m['group_name']}",
                "badge_type": "promoted" if is_promoted else "demoted",
                "badge_text": "ПОВЫШЕН" if is_promoted else "ПОНИЖЕН"
            })

    return events

def main():
    print("Запуск проверки...")
    current_state = fetch_current_team()
    
    if current_state is None:
        print("Не удалось получить актуальные данные от API. Пропуск.")
        return

    old_state = read_json_file(STATE_FILE, {})
    
    if old_state:
        changes = compare_states(old_state, current_state)
        if changes:
            logs = read_json_file(LOG_FILE, [])
            if not isinstance(logs, list):
                logs = []
            
            # Добавляем новые логи в начало списка для правильного отображения сверху вниз
            logs = changes + logs
            write_json_file(LOG_FILE, logs)
            print(f"Зафиксировано новых изменений: {len(changes)}")
        else:
            print("Изменений в составе не обнаружено.")
    else:
        print("Первый запуск. Создание первичного снимка состояния.")

    write_json_file(STATE_FILE, current_state)

if __name__ == "__main__":
    main()
