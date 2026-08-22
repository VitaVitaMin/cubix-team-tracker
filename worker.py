import os
import time
import json
import requests
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- КОНФИГУРАЦИЯ ---
API_URL = "https://cubixworld.net/api/team"
CHECK_INTERVAL = 300  # Проверка каждые 5 минут

STATE_FILE = "state.json"
LOG_FILE = "changes_log.json"

# Переменные окружения из Render
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # Формат: "username/repo-name"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

# --- ВЕБ-СЕРВЕР ДЛЯ PROBE RENDER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Cubix Worker is active")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# --- ВЗАИМОДЕЙСТВИЕ С GITHUB API ---
def get_github_file(filepath):
    """Получает файл из GitHub репозитория"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}?ref={GITHUB_BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            content = res.json()
            import base64
            decoded = base64.b64decode(content["content"]).decode("utf-8")
            return json.loads(decoded), content["sha"]
        return {}, None
    except Exception as e:
        print(f"Ошибка чтения {filepath} с GitHub: {e}")
        return {}, None

def update_github_file(filepath, data, sha, commit_message):
    """Обновляет или создает файл в GitHub репозитории"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filepath}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    import base64
    content_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    base64_content = base64.b64encode(content_bytes).decode("utf-8")
    
    payload = {
        "message": commit_message,
        "content": base64_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha
        
    try:
        res = requests.put(url, json=payload, headers=headers, timeout=10)
        if res.status_code in [200, 201]:
            print(f"Файл {filepath} успешно обновлен на GitHub")
        else:
            print(f"Ошибка сохранения {filepath} на GitHub: {res.status_code} {res.text}")
    except Exception as e:
        print(f"Ошибка отправки {filepath} на GitHub: {e}")

# --- СБОР ДАННЫХ И СРАВНЕНИЕ ---
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
                    "name": member["name"],
                    "group": member["group"],
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
            "time": timestamp,
            "type": "ADDED",
            "player": m["name"],
            "server": m["server_name"],
            "group": m["group_name"],
            "details": f"Добавлен на {m['server_name']} ({m['group_name']})"
        })

    # 2. Уволены из состава
    for k in (old_keys - new_keys):
        m = old_state[k]
        events.append({
            "time": timestamp,
            "type": "REMOVED",
            "player": m["name"],
            "server": m["server_name"],
            "group": m["group_name"],
            "details": f"Удален с {m['server_name']} (Был: {m['group_name']})"
        })

    # 3. Повышения и понижения
    for k in (old_keys & new_keys):
        old_m = old_state[k]
        new_m = new_state[k]

        if old_m["group"] != new_m["group"]:
            is_promoted = new_m["group"] > old_m["group"]
            action = "PROMOTED" if is_promoted else "DEMOTED"
            action_text = "Повышен" if is_promoted else "Понижен"
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

# --- ОСНОВНОЙ ЦИКЛ ---
def worker_loop():
    print("Воркер запущен...")
    while True:
        current_state = fetch_current_team()
        if current_state is not None:
            old_state, state_sha = get_github_file(STATE_FILE)
            
            if old_state:
                changes = compare_states(old_state, current_state)
                if changes:
                    logs, log_sha = get_github_file(LOG_FILE)
                    if not isinstance(logs, list):
                        logs = []
                    logs.extend(changes)
                    
                    # Фиксируем изменения в репозитории
                    update_github_file(LOG_FILE, logs, log_sha, f"Update changes log: +{len(changes)} events")
                    print(f"[{datetime.now()}] Новых изменений: {len(changes)}")
            
            # Обновляем снимок состояния
            update_github_file(STATE_FILE, current_state, state_sha, "Update team state")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    worker_loop()
