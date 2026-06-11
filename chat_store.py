import json
import time
import uuid
from pathlib import Path
from config import CHATS_DIR, CHAT_TITLE_MAX_LEN


def _user_dir(user_id: int) -> Path:
    p = CHATS_DIR / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _index_path(user_id: int) -> Path:
    return _user_dir(user_id) / "index.json"

def _chat_path(user_id: int, chat_id: str) -> Path:
    return _user_dir(user_id) / f"{chat_id}.json"

def load_index(user_id: int) -> list:
    p = _index_path(user_id)
    return json.loads(p.read_text()) if p.exists() else []

def _save_index(user_id: int, index: list):
    _index_path(user_id).write_text(json.dumps(index, ensure_ascii=False, indent=2))

def create_chat(user_id: int, url: str, first_message: str) -> dict:
    chat_id = uuid.uuid4().hex[:8]
    title = first_message[:CHAT_TITLE_MAX_LEN].strip()
    chat = {"id": chat_id, "title": title, "url": url, "messages": []}
    _chat_path(user_id, chat_id).write_text(json.dumps(chat, ensure_ascii=False, indent=2))
    index = load_index(user_id)
    index.append({"id": chat_id, "title": title, "msg_count": 0, "last_active": int(time.time())})
    _save_index(user_id, index)
    return chat

def load_chat(user_id: int, chat_id: str) -> dict | None:
    p = _chat_path(user_id, chat_id)
    return json.loads(p.read_text()) if p.exists() else None

def append_messages(user_id: int, chat_id: str, user_text: str, grok_text: str):
    chat = load_chat(user_id, chat_id)
    if not chat:
        return
    ts = int(time.time())
    chat["messages"].append({"role": "user", "text": user_text, "ts": ts})
    chat["messages"].append({"role": "grok", "text": grok_text, "ts": ts})
    _chat_path(user_id, chat_id).write_text(json.dumps(chat, ensure_ascii=False, indent=2))
    index = load_index(user_id)
    for item in index:
        if item["id"] == chat_id:
            item["msg_count"] = len(chat["messages"])
            item["last_active"] = ts
            break
    _save_index(user_id, index)

def update_chat_url(user_id: int, chat_id: str, url: str):
    chat = load_chat(user_id, chat_id)
    if not chat:
        return
    chat["url"] = url
    _chat_path(user_id, chat_id).write_text(json.dumps(chat, ensure_ascii=False, indent=2))

def rename_chat(user_id: int, chat_id: str, new_title: str):
    chat = load_chat(user_id, chat_id)
    if not chat:
        return
    chat["title"] = new_title[:CHAT_TITLE_MAX_LEN]
    _chat_path(user_id, chat_id).write_text(json.dumps(chat, ensure_ascii=False, indent=2))
    index = load_index(user_id)
    for item in index:
        if item["id"] == chat_id:
            item["title"] = chat["title"]
            break
    _save_index(user_id, index)

def get_chat_by_number(user_id: int, n: int) -> dict | None:
    index = load_index(user_id)
    return index[n - 1] if 1 <= n <= len(index) else None

def export_chat_text(user_id: int, chat_id: str) -> str:
    chat = load_chat(user_id, chat_id)
    if not chat:
        return ""
    lines = [f"# {chat['title']}\n"]
    for m in chat["messages"]:
        role = "You" if m["role"] == "user" else "Grok"
        lines.append(f"{role}:\n{m['text']}\n")
    return "\n".join(lines)
