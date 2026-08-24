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
        res.raise_for_status()
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
                    "id": str(member["id"]),
                    "name": member["name"].strip(),
                    "group": int(member["group"]),
                    "group_name": member["group_name"].strip(),
                    "server_id": str(member["server"]),
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

    removed_keys = old_keys - new_keys
    added_keys = new_keys - old_keys
    same_keys = old_keys & new_keys

    # Группируем выбывших и прибывших по id игрока для определения переводов
    removed_by_id = {old_state[k]["id"]: k for k in removed_keys}
    added_by_id = {new_state[k]["id"]: k for k in added_keys}

    transferred_ids = set(removed_by_id.keys()) & set(added_by_id.keys())

    # 1. Переводы между серверами
    for p_id in transferred_ids:
        old_k = removed_by_id[p_id]
        new_k = added_by_id[p_id]
        
        old_m = old_state[old_k]
        new_m = new_state[new_k]

        details = f"Переведен: {old_m['server_name']} → {new_m['server_name']}"
        if old_m["group"] != new_m["group"]:
            details += f" ({old_m['group_name']} → {new_m['group_name']})"
        else:
            details += f" ({new_m['group_name']})"

        events.append({
            "timestamp": timestamp,
            "player": new_m["name"],
            "server": new_m["server_name"],
            "details": details,
            "badge_type": "transfer",
            "badge_text": "ПЕРЕВОД"
        })

        # Исключаем из обычной обработки удалений и добавлений
        removed_keys.remove(old_k)
        added_keys.remove(new_k)

    # 2. Приняты в состав (чистое добавление)
    for k in added_keys:
        m = new_state[k]
        events.append({
            "timestamp": timestamp,
            "player": m["name"],
            "server": m["server_name"],
            "details": f"Принят на должность ({m['group_name']})",
            "badge_type": "added",
            "badge_text": "ПРИНЯТ"
        })

    # 3. Уволены из состава (чистое удаление)
    for k in removed_keys:
        m = old_state[k]
        events.append({
            "timestamp": timestamp,
            "player": m["name"],
            "server": m["server_name"],
            "details": f"Снят с должности (Был: {m['group_name']})",
            "badge_type": "removed",
            "badge_text": "СНЯТ"
        })

    # 4. Повышения и понижения в рамках одного сервера
    for k in same_keys:
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
