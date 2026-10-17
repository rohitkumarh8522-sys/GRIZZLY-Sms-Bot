import sqlite3
import requests
import os
import threading
from flask import Flask
import telebot
from telebot import types

# ==================== RENDER FREE WEB SERVER ====================
app = Flask('')

@app.route('/')
def home():
    return "Telegram OTP Bot is Online & Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
GRIZZLY_API_KEY = os.getenv("GRIZZLY_API_KEY", "YOUR_GRIZZLY_API_KEY_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # Aapka Telegram ID

SERVICE_CODE = "tg"

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER,
            service TEXT,
            cost REAL,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            photo_id TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS countries (
            country_id INTEGER PRIMARY KEY,
            country_name TEXT,
            price REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_user', 'admin_username')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('upi_id', 'example@upi')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('profit_margin', '5.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_deposit', '50.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('max_deposit', '10000.0')")
    
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (0, '🇷🇺 Russia / Any', 15.0)")
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (22, '🇮🇳 India', 25.0)")
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (187, '🇺🇸 USA', 20.0)")
    
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

def set_setting(key, value):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0.0))
        conn.commit()
        conn.close()
        return 0.0
    conn.close()
    return row[0]

def update_user_balance(user_id, amount):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def log_sale(order_id, user_id, service, cost, status):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO sales (order_id, user_id, service, cost, status) VALUES (?, ?, ?, ?, ?)",
                   (order_id, user_id, service, cost, status))
    conn.commit()
    conn.close()

def get_countries():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT country_id, country_name, price FROM countries")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_country(country_id, name, price):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO countries (country_id, country_name, price) VALUES (?, ?, ?)", (country_id, name, price))
    conn.commit()
    conn.close()

def delete_country(country_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM countries WHERE country_id = ?", (country_id,))
    conn.commit()
    conn.close()

def get_sales_stats():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(cost) FROM sales WHERE status = 'COMPLETED'")
    res = cursor.fetchone()
    total_orders = res[0] or 0
    total_revenue = res[1] or 0.0
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0] or 0
    conn.close()
    return total_orders, total_revenue, total_users

# ==================== GRIZZLY SMS API ====================
GRIZZLY_BASE_URL = "https://api.grizzlysms.com/stubs/handler_api.php"

def grizzly_get_balance():
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getBalance"
        res = requests.get(url, timeout=10).text
        if "ACCESS_BALANCE" in res:
            return float(res.split(":")[1])
        return None
    except Exception:
        return None

def grizzly_get_number(country_id=0):
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getNumber&service={SERVICE_CODE}&country={country_id}"
        res = requests.get(url, timeout=12).text.strip()
        if res.startswith("ACCESS_NUMBER"):
            parts = res.split(":")
            return {"status": True, "id": parts[1], "number": parts[2]}
        return {"status": False, "message": res}
    except Exception as e:
        return {"status": False, "message": str(e)}

def grizzly_get_status(tx_id):
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getStatus&id={tx_id}"
        return requests.get(url, timeout=10).text.strip()
    except Exception as e:
        return f"ERROR: {e}"

def grizzly_set_status(tx_id, status_code):
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=setStatus&id={tx_id}&status={status_code}"
        return requests.get(url, timeout=10).text.strip()
    except Exception as e:
        return f"ERROR: {e}"

# ==================== USER INTERFACE DESIGN ====================
def main_menu_markup():
    support_username = get_setting("support_user")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 Buy Telegram Number", callback_data="select_country"),
        types.InlineKeyboardButton("💰 Check Wallet Balance", callback_data="check_wallet"),
        types.InlineKeyboardButton("➕ Add Money (Deposit)", callback_data="add_money"),
        types.InlineKeyboardButton("💬 Live Support", url=f"https://t.me/{support_username}"),
        types.InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="home")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    text = (
        "┌─────────────────────────┐\n"
        "✨   **TELEGRAM OTP STORE**   ✨\n"
        "└─────────────────────────┘\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"💳 **Balance:** `₹{balance:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ Instant Virtual Numbers\n"
        "🔒 Secure & Non-Drop Accounts\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Niche diye gaye option ko select karein:*"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu_markup())

@bot.callback_query_handler(func=lambda call: not call.data.startswith("admin_"))
def user_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "home":
        balance = get_user_balance(user_id)
        text = (
            "┌─────────────────────────┐\n"
            "✨   **TELEGRAM OTP STORE**   ✨\n"
            "└─────────────────────────┘\n\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💳 **Balance:** `₹{balance:.2f}`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 *Select an option below:*"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu_markup())

    elif call.data == "check_wallet":
        balance = get_user_balance(user_id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("➕ Add Money Now", callback_data="add_money"),
            types.InlineKeyboardButton("🔙 Back to Menu", callback_data="home")
        )
        
        text = (
            "┌─────────────────────────┐\n"
            "💎    **WALLET OVERVIEW**    💎\n"
            "└─────────────────────────┘\n\n"
            f"👤 **Your ID:** `{user_id}`\n"
            f"💰 **Current Balance:** `₹{balance:.2f}`\n\n"
            "📌 *Account me balance add karne ke liye 'Add Money Now' par click karein.*"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "add_money":
        qr_file_id = get_setting("qr_file_id")
        upi_id = get_setting("upi_id")
        min_dep = get_setting("min_deposit")
        max_dep = get_setting("max_deposit")
        
        caption = (
            "┌─────────────────────────┐\n"
            "📲    **ADD FUNDS TO WALLET**    📲\n"
            "└─────────────────────────┘\n\n"
            f"⚠️ **Limits:** Min `₹{min_dep}` — Max `₹{max_dep}`\n\n"
            "1️⃣ **QR Code scan karein ya UPI ID par pay karein:**\n"
            f"📌 ` {upi_id} `\n\n"
            "2️⃣ **Payment ke baad niche button dabakar amount enter karein:**"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💵 Enter Amount & Upload Proof", callback_data="start_deposit"),
            types.InlineKeyboardButton("🔙 Back to Menu", callback_data="home")
        )
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        if qr_file_id:
            bot.send_photo(call.message.chat.id, qr_file_id, caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "start_deposit":
        user_states[user_id] = {"step": "WAITING_DEPOSIT_AMOUNT"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="home"))
        bot.send_message(call.message.chat.id, "💵 **Aapne kitne rupay ka payment kiya hai? (Amount type karein):**", parse_mode="Markdown", reply_markup=markup)

    elif call.data == "select_country":
        countries = get_countries()
        profit = float(get_setting("profit_margin") or "5.0")
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c_id, c_name, c_price in countries:
            final_price = c_price + profit
            markup.add(types.InlineKeyboardButton(f"🌐 {c_name} ➔ ₹{final_price:.2f}", callback_data=f"buy_num:{c_id}:{final_price}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="home"))
        bot.edit_message_text("🌍 **SELECT COUNTRY FOR TELEGRAM NUMBER:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("buy_num:"):
        _, c_id, cost = call.data.split(":")
        cost = float(cost)
        user_bal = get_user_balance(user_id)
        
        if user_bal < cost:
            bot.answer_callback_query(call.id, f"❌ Low Balance! Required: ₹{cost:.2f}", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⌛ Generating Number...")
        res = grizzly_get_number(country_id=c_id)
        
        if res["status"]:
            tx_id = res["id"]
            phone_num = res["number"]
            
            update_user_balance(user_id, -cost)
            log_sale(tx_id, user_id, "Telegram", cost, "PENDING")
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("🔄 Check & Get OTP", callback_data=f"get_otp:{tx_id}:{cost}"),
                types.InlineKeyboardButton("❌ Cancel & Refund", callback_data=f"cancel:{tx_id}:{cost}")
            )
            
            msg = (
                "┌─────────────────────────┐\n"
                "📱   **NUMBER GENERATED**   📱\n"
                "└─────────────────────────┘\n\n"
                f"📞 **Phone Number:** `{phone_num}`\n"
                f"🆔 **Order ID:** `{tx_id}`\n"
                f"💰 **Charged:** `₹{cost:.2f}`\n\n"
                "👉 *Is number ko Telegram me dalein, aur OTP aane par button dabayein.*"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, f"❌ **Notice:** `{res['message']}`\n\nStock temporarily unavailable. Please try again later.", parse_mode="Markdown")

    elif call.data.startswith("get_otp:"):
        _, tx_id, cost = call.data.split(":")
        status = grizzly_get_status(tx_id)
        
        if "STATUS_OK" in status:
            otp_code = status.split(":")[1]
            grizzly_set_status(tx_id, 6)
            log_sale(tx_id, user_id, "Telegram", float(cost), "COMPLETED")
            bot.send_message(call.message.chat.id, f"🎉 **YOUR TELEGRAM OTP CODE:**\n\n`{otp_code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in status:
            bot.answer_callback_query(call.id, "⌛ Waiting for SMS... Send OTP from Telegram first!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"Status: {status}", show_alert=True)

    elif call.data.startswith("cancel:"):
        _, tx_id, refund_amt = call.data.split(":")
        refund_amt = float(refund_amt)
        
        cancel_res = grizzly_set_status(tx_id, 8)
        if any(keyword in cancel_res for keyword in ["ACCESS_CANCEL", "ACCESS_OK", "STATUS_CANCEL"]):
            update_user_balance(user_id, refund_amt)
            log_sale(tx_id, user_id, "Telegram", refund_amt, "CANCELLED")
            bot.edit_message_text("❌ **Order Cancelled!** Balance successfully refunded to wallet.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ Cancel nahi ho sakta (OTP process active hai).", show_alert=True)

@bot.message_handler(func=lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "WAITING_DEPOSIT_AMOUNT")
def handle_deposit_amount(message):
    user_id = message.from_user.id
    try:
        amt = float(message.text.strip())
        min_dep = float(get_setting("min_deposit") or "50.0")
        max_dep = float(get_setting("max_deposit") or "10000.0")
        
        if amt < min_dep or amt > max_dep:
            bot.reply_to(message, f"❌ **Invalid Amount!**\nLimit: Min `₹{min_dep}` aur Max `₹{max_dep}` ke beech amount daalein.", parse_mode="Markdown")
            return
            
        user_states[user_id] = {"step": "WAITING_DEPOSIT_SCREENSHOT", "amount": amt}
        bot.reply_to(message, f"✅ Amount accepted: `₹{amt}`\n\n📸 **Ab apne payment ka clear screenshot yahan bhej dein:**", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Kripya sirf valid number type karein (e.g. 100)")

@bot.message_handler(content_types=['photo'])
def handle_user_screenshot(message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        return

    state_data = user_states.get(user_id, {})
    if state_data.get("step") == "WAITING_DEPOSIT_SCREENSHOT":
        photo_id = message.photo[-1].file_id
        amt = state_data["amount"]
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO deposits (user_id, amount, photo_id) VALUES (?, ?, ?)", (user_id, amt, photo_id))
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        del user_states[user_id]
        bot.reply_to(message, f"✅ **Screenshot Received!** (Request ID: `#{req_id}`)\nAdmin dwara verify hote hi `₹{amt}` credit kar diya jayega.", parse_mode="Markdown")
        
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton(f"✅ Approve (₹{amt})", callback_data=f"admin_approve:{req_id}:{user_id}:{amt}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{req_id}:{user_id}")
        )
        
        caption = f"🚨 **NEW PAYMENT PROOF** 🚨\n\n🆔 Request ID: `#{req_id}`\n👤 User ID: `{user_id}`\n💵 Claimed Amount: `₹{amt}`"
        bot.send_photo(ADMIN_ID, photo_id, caption=caption, parse_mode="Markdown", reply_markup=admin_markup)

# ==================== PREMIUM ADMIN PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    orders, revenue, users = get_sales_stats()
    g_bal = grizzly_get_balance()
    g_bal_str = f"${g_bal:.2f}" if g_bal is not None else "Error"

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🖼️ Set Payment QR", callback_data="admin_set_qr"),
        types.InlineKeyboardButton("🏷️ Set UPI ID", callback_data="admin_set_upi"),
        types.InlineKeyboardButton("💬 Support Handle", callback_data="admin_set_support"),
        types.InlineKeyboardButton("💵 Set Margin", callback_data="admin_set_margin"),
        types.InlineKeyboardButton("📉 Min Deposit", callback_data="admin_set_min"),
        types.InlineKeyboardButton("📈 Max Deposit", callback_data="admin_set_max"),
        types.InlineKeyboardButton("🌍 Add Country", callback_data="admin_add_country"),
        types.InlineKeyboardButton("🗑️ Del Country", callback_data="admin_del_country"),
        types.InlineKeyboardButton("➕ Add Balance", callback_data="admin_manual_add")
    )

    text = (
        "┌─────────────────────────┐\n"
        "⚡   **ADMIN CONTROL HUB**   ⚡\n"
        "└─────────────────────────┘\n\n"
        "📊 **ANALYTICS:**\n"
        f"• Total Users: `{users}`\n"
        f"• Completed Orders: `{orders}`\n"
        f"• Total Revenue: `₹{revenue:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **Grizzly Wallet:** `{g_bal_str}`\n"
        f"💵 **Profit Margin:** `₹{get_setting('profit_margin')}`\n"
        f"📉 **Min Deposit:** `₹{get_setting('min_deposit')}`\n"
        f"📈 **Max Deposit:** `₹{get_setting('max_deposit')}`\n"
        f"📌 **Support:** `@{get_setting('support_user')}`\n"
        f"🏦 **UPI ID:** `{get_setting('upi_id')}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data.startswith("admin_approve:"):
        _, req_id, u_id, amt = call.data.split(":")
        u_id, amt = int(u_id), float(amt)
        
        update_user_balance(u_id, amt)
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'APPROVED' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_caption(f"✅ Deposit Request `#{req_id}` APPROVED! Added `₹{amt}` to User `{u_id}`.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, f"🎉 **Payment Approved!** `₹{amt}` wallet me credit kar diya gaya hai.", parse_mode="Markdown")

    elif call.data.startswith("admin_reject:"):
        _, req_id, u_id = call.data.split(":")
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_caption(f"❌ Deposit Request `#{req_id}` REJECTED.", call.message.chat.id, call.message.message_id)
        bot.send_message(int(u_id), f"❌ **Payment Rejected!** Aapka screenshot verify nahi ho saka.", parse_mode="Markdown")

    elif call.data == "admin_set_margin":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MARGIN"}
        bot.send_message(ADMIN_ID, "💵 **Naya Profit Margin enter karein (e.g. 5.0):**")

    elif call.data == "admin_set_min":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MIN_DEP"}
        bot.send_message(ADMIN_ID, "📉 **Naya Minimum Deposit Limit enter karein (e.g. 50.0):**")

    elif call.data == "admin_set_max":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MAX_DEP"}
        bot.send_message(ADMIN_ID, "📈 **Naya Maximum Deposit Limit enter karein (e.g. 10000.0):**")

    elif call.data == "admin_add_country":
        user_states[ADMIN_ID] = {"step": "ADMIN_ADD_COUNTRY"}
        bot.send_message(ADMIN_ID, "🌍 **Format:** `COUNTRY_ID COUNTRY_NAME BASE_PRICE`\n\n*Example:* `22 India 25.0`", parse_mode="Markdown")

    elif call.data == "admin_del_country":
        countries = get_countries()
        markup = types.InlineKeyboardMarkup(row_width=2)
        for c_id, c_name, _ in countries:
            markup.add(types.InlineKeyboardButton(f"❌ {c_name}", callback_data=f"admin_confirm_del:{c_id}"))
        bot.send_message(ADMIN_ID, "🗑️ **Delete karne ke liye Country select karein:**", reply_markup=markup)

    elif call.data.startswith("admin_confirm_del:"):
        c_id = call.data.split(":")[1]
        delete_country(c_id)
        bot.edit_message_text("✅ Country successfully deleted!", call.message.chat.id, call.message.message_id)

    elif call.data == "admin_set_qr":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_QR"}
        bot.send_message(ADMIN_ID, "📸 **[QR UPLOAD MODE ACTIVE]**\n\nAb apna QR Code photo ya document yahan bhej dein:")

    elif call.data == "admin_set_upi":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_UPI"}
        bot.send_message(ADMIN_ID, "🏷️ Naya UPI ID text yahan bhejein:")

    elif call.data == "admin_set_support":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_SUPPORT"}
        bot.send_message(ADMIN_ID, "💬 Naya Support Username bhejein (bina `@` ke):")

    elif call.data == "admin_manual_add":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_DIRECT_ADD"}
        bot.send_message(ADMIN_ID, "➕ **Format:** `USER_ID AMOUNT`\n\n*Example:* `8926941404 100`", parse_mode="Markdown")

@bot.message_handler(content_types=['photo', 'document', 'text'])
def handle_admin_inputs(message):
    if message.from_user.id != ADMIN_ID:
        return

    state = user_states.get(ADMIN_ID, {}).get("step")
    
    if state == "ADMIN_WAITING_QR" and (message.photo or message.document):
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id
            
        set_setting("qr_file_id", file_id)
        del user_states[ADMIN_ID]
        bot.reply_to(message, "✅ **Payment QR Code Updated Successfully!**", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_MARGIN" and message.text:
        try:
            m = float(message.text.strip())
            set_setting("profit_margin", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Profit Margin Updated:** `₹{m}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_WAITING_MIN_DEP" and message.text:
        try:
            m = float(message.text.strip())
            set_setting("min_deposit", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Minimum Deposit Updated:** `₹{m}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_WAITING_MAX_DEP" and message.text:
        try:
            m = float(message.text.strip())
            set_setting("max_deposit", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Maximum Deposit Updated:** `₹{m}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_ADD_COUNTRY" and message.text:
        try:
            parts = message.text.strip().split()
            c_id = int(parts[0])
            c_name = parts[1]
            c_price = float(parts[2])
            add_country(c_id, c_name, c_price)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Country Added:** `{c_name}` (ID: {c_id}) - Base Price: `₹{c_price}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `COUNTRY_ID NAME PRICE`")

    elif state == "ADMIN_WAITING_UPI" and message.text:
        set_setting("upi_id", message.text.strip())
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **UPI ID Updated:** `{message.text.strip()}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_SUPPORT" and message.text:
        username = message.text.strip().replace("@", "")
        set_setting("support_user", username)
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **Support Username Updated:** `@{username}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_DIRECT_ADD" and message.text:
        try:
            parts = message.text.strip().split()
            target_user = int(parts[0])
            amt = float(parts[1])
            update_user_balance(target_user, amt)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Added `₹{amt}` to User `{target_user}`.", parse_mode="Markdown")
            bot.send_message(target_user, f"🎉 **Balance Credited!** `₹{amt}` add kar diya gaya hai.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `USER_ID AMOUNT`")

# ==================== START BOT ====================
if __name__ == "__main__":
    print("Premium Telegram Bot Started...")
    bot.infinity_polling()
