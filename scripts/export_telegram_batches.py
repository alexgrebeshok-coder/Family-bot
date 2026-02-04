import os
import re
import json
import csv
import asyncio
from telethon import TelegramClient

api_id = 31306805
api_hash = '891bd9c943838aaad127318756d0adc0'

BASE_DIR = '/Users/aleksandrgrebeshok/.openclaw/workspace/telegram_export'
STATE_PATH = '/Users/aleksandrgrebeshok/.openclaw/workspace/telegram_export_state.json'
CLASS_PATH = '/Users/aleksandrgrebeshok/.openclaw/workspace/telegram_dialogs_classified.csv'

os.makedirs(BASE_DIR, exist_ok=True)

# load classification
class_map = {}
with open(CLASS_PATH, newline='', encoding='utf-8') as f:
    r = csv.DictReader(f)
    for row in r:
        key = (row['name'], row['type'])
        class_map[key] = row['category']

# load state
if os.path.exists(STATE_PATH):
    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        state = json.load(f)
else:
    state = {"done_ids": []}

done_ids = set(state.get("done_ids", []))

client = TelegramClient('tg_session', api_id, api_hash)

async def export_dialog(d):
    if d.is_user:
        return
    if d.id in done_ids:
        return
    dtype = 'group' if d.is_group else 'channel' if d.is_channel else 'other'
    cat = class_map.get((d.name, dtype), 'Прочее')
    folder = os.path.join(BASE_DIR, dtype, cat)
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[^\w\-\. ]+', '_', d.name)[:80].strip() or f'chat_{d.id}'
    out_path = os.path.join(folder, f'{safe}_{d.id}.json')

    messages = []
    async for m in client.iter_messages(d.entity, reverse=True):
        messages.append({
            'id': m.id,
            'date': m.date.isoformat() if m.date else None,
            'sender_id': m.sender_id,
            'text': m.message,
            'reply_to': m.reply_to_msg_id,
            'fwd_from': bool(m.fwd_from),
            'media': bool(m.media),
        })
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    done_ids.add(d.id)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump({"done_ids": sorted(done_ids)}, f, ensure_ascii=False, indent=2)

async def main():
    await client.connect()
    dialogs = [d async for d in client.iter_dialogs()]
    # process only one chat per run (first not done, non-user)
    for d in dialogs:
        if d.is_user:
            continue
        if d.id in done_ids:
            continue
        await export_dialog(d)
        break
    await client.disconnect()

asyncio.run(main())
