from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import json, os, uuid, asyncio
import urllib

# ================= CONFIG =================
API_ID = 34700157
API_HASH = "90d74f1f4bcc23b918ed80bb89aeecb0"
BOT_TOKEN = "8567166994:AAEUQSyGbYunLGCEEAKu1qtRzIjnfsQ51s4"

OWNER_ID = 6427267302
ADMIN_IDS = {6427267302}

SESSION_NAME = "adv_msg_bot"
DB_FILE = "db.json"
# =========================================

STATE = {}

# ================= DATABASE =================
def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "messages": {},
            "fixed_message": None,
            "users": []
        }

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    db.setdefault("messages", {})
    db.setdefault("fixed_message", None)
    db.setdefault("users", [])

    return db


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
# ===========================================

def is_admin(uid):
    return uid == OWNER_ID or uid in ADMIN_IDS

# ================= BUTTON PARSER =================
def parse_buttons(text):
    rows = []
    for raw in text.splitlines():
        if not raw.strip():
            continue

        row = []
        for part in raw.split("&&"):
            part = part.strip().replace("–", "-").replace("—", "-")

            if "-" in part:
                title, value = part.split("-", 1)
            else:
                title = value = part

            title = title.strip()
            value = value.strip()

            if value.startswith("popup:"):
                row.append(("popup", title, value[6:]))

            elif value.startswith("alert:"):
                row.append(("alert", title, value[6:]))

            elif value.startswith("copy:"):
                row.append(("copy", title, value[5:]))

            elif value.startswith("share:"):
                share_text = urllib.parse.quote(value[6:])
                share_url = f"https://t.me/share/url?text={share_text}"
                row.append(("url", title, share_url))

            elif value == "rules":
                row.append(("rules", title, ""))

            else:
                if value.startswith("t.me/"):
                    value = "https://" + value
                row.append(("url", title, value))

        rows.append(row)

    return rows


def build_keyboard(rows):
    kb = []
    for row in rows:
        btns = []
        for t, txt, val in row:
            if t == "url":
                btns.append(InlineKeyboardButton(txt, url=val))
            else:
                btns.append(InlineKeyboardButton(txt, callback_data=f"{t}|{val}"))
        kb.append(btns)
    return InlineKeyboardMarkup(kb) if kb else None
# ===============================================

app = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================= START =================
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    db = load_db()
    uid = message.from_user.id

    if uid not in db["users"]:
        db["users"].append(uid)
        save_db(db)

    args = message.text.split(maxsplit=1)

    if len(args) == 2:
        code = args[1]
        entry = db["messages"].get(code)

        if not entry:
            await message.reply("❌ Invalid or expired link")
            return

        if entry["type"] == "merged":
            for c in entry["items"]:
                msg = db["messages"].get(c)
                if not msg:
                    continue
                kb = build_keyboard(msg["buttons"])
                if msg["image"]:
                    await message.reply_photo(msg["image"], caption=msg["text"], reply_markup=kb)
                else:
                    await message.reply(msg["text"], reply_markup=kb)
            return

        kb = build_keyboard(entry["buttons"])
        if entry["image"]:
            await message.reply_photo(entry["image"], caption=entry["text"], reply_markup=kb)
        else:
            await message.reply(entry["text"], reply_markup=kb)
        return

    if is_admin(uid):
        await admin_panel(message)
    else:
        fixed = db["fixed_message"]
        if fixed and fixed in db["messages"]:
            msg = db["messages"][fixed]
            kb = build_keyboard(msg["buttons"])
            if msg["image"]:
                await message.reply_photo(msg["image"], caption=msg["text"], reply_markup=kb)
            else:
                await message.reply(msg["text"], reply_markup=kb)
        else:
            await message.reply("Welcome 👋")

# ================= ADMIN PANEL =================
async def admin_panel(message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Save Message", callback_data="save")],
        [InlineKeyboardButton("➕ Add Buttons", callback_data="buttons")],
        [InlineKeyboardButton("➕ Add Message", callback_data="merge")],
        [InlineKeyboardButton("🧷 Fix Message", callback_data="fix")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])
    await message.reply("⚙️ Admin Panel", reply_markup=kb)


@app.on_callback_query()
async def callbacks(client, cb):
    uid = cb.from_user.id
    if not is_admin(uid):
        return

    STATE[uid] = {}

    if cb.data == "cancel":
        STATE.pop(uid, None)
        await cb.message.edit("❌ Cancelled")
        return

    if cb.data == "save":
        STATE[uid]["step"] = "text"
        await cb.message.edit("✏️ Send message text")
        return

    if cb.data == "buttons":
        STATE[uid]["step"] = "btn_code"
        await cb.message.edit("🔑 Send message code")
        return

    if cb.data == "merge":
        STATE[uid]["step"] = "merge_codes"
        await cb.message.edit("🔗 Send message codes (one per line)")
        return

    if cb.data == "fix":
        STATE[uid]["step"] = "fix_code"
        await cb.message.edit("🧷 Send message code to fix")
        return

    if cb.data == "broadcast":
        STATE[uid]["step"] = "bc"
        await cb.message.edit("📢 Send broadcast message")

# ================= ADMIN FLOW =================
@app.on_message(filters.private)
async def admin_flow(client, message):
    uid = message.from_user.id
    if uid not in STATE:
        return

    db = load_db()
    step = STATE[uid]["step"]

    if step == "merge_codes":
        codes = [c.strip() for c in message.text.splitlines()]
        for c in codes:
            if c not in db["messages"]:
                await message.reply(f"❌ Invalid code: {c}")
                return

        new_code = str(uuid.uuid4())[:8]
        db["messages"][new_code] = {
            "type": "merged",
            "items": codes
        }
        save_db(db)
        STATE.pop(uid)

        bot = await client.get_me()
        await message.reply(f"✅ Merged\nhttps://t.me/{bot.username}?start={new_code}")
        return

    if step == "text":
        STATE[uid]["text"] = message.text
        STATE[uid]["step"] = "image"
        await message.reply("🖼 Send image or type skip")
        return

    if step == "image":
        code = str(uuid.uuid4())[:8]
        db["messages"][code] = {
            "type": "single",
            "text": STATE[uid]["text"],
            "image": message.photo.file_id if message.photo else None,
            "buttons": []
        }
        save_db(db)
        STATE.pop(uid)

        bot = await client.get_me()
        await message.reply(f"✅ Saved\nhttps://t.me/{bot.username}?start={code}")
        return

    if step == "btn_code":
        STATE[uid]["code"] = message.text.strip()
        STATE[uid]["step"] = "btn_text"
        await message.reply("📎 Send button structure")
        return

    if step == "btn_text":
        code = STATE[uid]["code"]
        db["messages"][code]["buttons"] = parse_buttons(message.text)
        save_db(db)
        STATE.pop(uid)
        await message.reply("✅ Buttons added")
        return

    if step == "fix_code":
        code = message.text.strip()
        if code not in db["messages"]:
            await message.reply("❌ Invalid code")
            return
        db["fixed_message"] = code
        save_db(db)
        STATE.pop(uid)
        await message.reply("🧷 Fixed message set")
        return

    if step == "bc":
        sent = 0
        for u in db["users"]:
            try:
                if message.photo:
                    await client.send_photo(u, message.photo.file_id, caption=message.caption or "")
                else:
                    await client.send_message(u, message.text)
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass

        STATE.pop(uid)
        await message.reply(f"📢 Broadcast sent to {sent} users")

# ================= CALLBACKS =================
@app.on_callback_query(filters.regex("^(popup|alert|copy|rules)"))
async def button_actions(client, cb):
    _, data = cb.data.split("|", 1)
    await cb.answer(data, show_alert=True)

print("🚀 Bot is running...")
app.run()
