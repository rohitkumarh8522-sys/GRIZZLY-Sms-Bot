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
    return "NEXUS OTP AUTOMATION - Core Engine Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
GRIZZLY_API_KEY = os.getenv("GRIZZLY_API_KEY", "YOUR_GRIZZLY_API_KEY_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # Your Telegram ID

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
    
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (0, '🇷🇺 Russia / Server 1', 15.0)")
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (22, '🇮🇳 India Premium', 25.0)")
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (187, '🇺🇸 USA High Quality', 20.0)")
    
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

def get_user_stats(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sales WHERE user_id = ? AND status = 'COMPLETED'", (user_id,))
    total_orders = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(amount) FROM deposits WHERE user_id = ? AND status = 'APPROVED'", (user_id,))
    total_deposited = cursor.fetchone()[0] or 0.0
    conn.close()
    return total_orders, total_deposited

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

# ==================== UNIQUE USER INTERFACE ====================
def main_menu_markup():
    support_username = get_setting("support_user")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚡ Buy Virtual Number", callback_data="select_country"),
        types.InlineKeyboardButton("💳 Account Wallet", callback_data="check_wallet"),
        types.InlineKeyboardButton("📥 Add Funds / Deposit", callback_data="add_money"),
        types.InlineKeyboardButton("👨‍💻 Customer Support", url=f"https://t.me/{support_username}"),
        types.InlineKeyboardButton("🔄 Synchronize Dashboard", callback_data="home")
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    first_name = message.from_user.first_name or "Valued Client"
    
    text = (
        "💎 **NEXUS OTP AUTOMATION** 💎\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome back, **{first_name}**!\n\n"
        f"🆔 **Account ID:** `{user_id}`\n"
        f"💼 **Available Balance:** `₹{balance:.2f}`\n"
        "⚡ **System Status:** `Online & Instant`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 *High-speed virtual numbers with instant OTP delivery. Select an option from the menu below:* "
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu_markup())

@bot.callback_query_handler(func=lambda call: not call.data.startswith("admin_"))
def user_callbacks(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or "Valued Client"
    
    if call.data == "home":
        balance = get_user_balance(user_id)
        text = (
            "💎 **NEXUS OTP AUTOMATION** 💎\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Welcome back, **{first_name}**!\n\n"
            f"🆔 **Account ID:** `{user_id}`\n"
            f"💼 **Available Balance:** `₹{balance:.2f}`\n"
            "⚡ **System Status:** `Online & Instant`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 *Select an option from the menu below:* "
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu_markup())

    elif call.data == "check_wallet":
        balance = get_user_balance(user_id)
        orders, total_dep = get_user_stats(user_id)
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("➕ Add Funds Now", callback_data="add_money"),
            types.InlineKeyboardButton("🔙 Main Menu", callback_data="home")
        )
        
        text = (
            "🏦 **PERSONAL WALLET DASHBOARD**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Account Holder:** `{first_name}`\n"
            f"🆔 **Client ID:** `{user_id}`\n\n"
            f"💳 **Available Balance:** `₹{balance:.2f}`\n"
            f"📈 **Total Deposited:** `₹{total_dep:.2f}`\n"
            f"📦 **Successful Orders:** `{orders}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Need to recharge? Click 'Add Funds Now' below.*"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "add_money":
        qr_url = get_setting("qr_file_id")
        upi_id = get_setting("upi_id")
        min_dep = get_setting("min_deposit")
        max_dep = get_setting("max_deposit")
        
        caption = (
            "📥 **DEPOSIT FUNDS TO WALLET**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ **Allowed Range:** Min `₹{min_dep}` — Max `₹{max_dep}`\n\n"
            "1️⃣ **Scan QR Code or copy UPI ID:**\n"
            f"📌 ` {upi_id} `\n\n"
            "2️⃣ **After payment, click the button below to submit your details:**"
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💵 Submit Payment Proof & Amount", callback_data="start_deposit"),
            types.InlineKeyboardButton("🔙 Cancel & Return", callback_data="home")
        )
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        if qr_url and qr_url.startswith("http"):
            bot.send_photo(call.message.chat.id, qr_url, caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption + "\n\n*(Payment QR link is currently updating)*", parse_mode="Markdown", reply_markup=markup)

    elif call.data == "start_deposit":
        user_states[user_id] = {"step": "WAITING_DEPOSIT_AMOUNT"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel Process", callback_data="home"))
        bot.send_message(call.message.chat.id, "💵 **Enter the exact amount paid (e.g. 100):**", parse_mode="Markdown", reply_markup=markup)

    elif call.data == "select_country":
        countries = get_countries()
        profit = float(get_setting("profit_margin") or "5.0")
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c_id, c_name, c_price in countries:
            final_price = c_price + profit
            markup.add(types.InlineKeyboardButton(f"🌍 {c_name} ➔ ₹{final_price:.2f}", callback_data=f"buy_num:{c_id}:{final_price}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Back to Dashboard", callback_data="home"))
        bot.edit_message_text("📱 **SELECT SERVER / COUNTRY FOR TELEGRAM:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("buy_num:"):
        _, c_id, cost = call.data.split(":")
        cost = float(cost)
        user_bal = get_user_balance(user_id)
        
        if user_bal < cost:
            bot.answer_callback_query(call.id, f"❌ Insufficient Funds! Required: ₹{cost:.2f}", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⚡ Allocating Virtual Line...")
        res = grizzly_get_number(country_id=c_id)
        
        if res["status"]:
            tx_id = res["id"]
            phone_num = res["number"]
            
            update_user_balance(user_id, -cost)
            log_sale(tx_id, user_id, "Telegram", cost, "PENDING")
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📥 Fetch OTP Code", callback_data=f"get_otp:{tx_id}:{cost}"),
                types.InlineKeyboardButton("🚫 Cancel & Auto-Refund", callback_data=f"cancel:{tx_id}:{cost}")
            )
            
            msg = (
                "📱 **VIRTUAL NUMBER ALLOCATED**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📞 **Phone Number:** `{phone_num}`\n"
                f"🆔 **Order Reference:** `{tx_id}`\n"
                f"💰 **Total Charged:** `₹{cost:.2f}`\n\n"
                "👉 *Enter this phone number in Telegram, then click 'Fetch OTP Code' below.*"
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, f"❌ **Allocation Error:** `{res['message']}`\n\nStock temporarily depleted for this route. Please select another country.", parse_mode="Markdown")

    elif call.data.startswith("get_otp:"):
        _, tx_id, cost = call.data.split(":")
        status = grizzly_get_status(tx_id)
        
        if "STATUS_OK" in status:
            otp_code = status.split(":")[1]
            grizzly_set_status(tx_id, 6)
            log_sale(tx_id, user_id, "Telegram", float(cost), "COMPLETED")
            bot.send_message(call.message.chat.id, f"🎉 **VERIFICATION CODE RECEIVED:**\n\n🔑 `{otp_code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in status:
            bot.answer_callback_query(call.id, "⌛ Waiting for SMS arrival... Send code from Telegram first!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"Status: {status}", show_alert=True)

    elif call.data.startswith("cancel:"):
        _, tx_id, refund_amt = call.data.split(":")
        refund_amt = float(refund_amt)
        
        cancel_res = grizzly_set_status(tx_id, 8)
        if any(keyword in cancel_res for keyword in ["ACCESS_CANCEL", "ACCESS_OK", "STATUS_CANCEL"]):
            update_user_balance(user_id, refund_amt)
            log_sale(tx_id, user_id, "Telegram", refund_amt, "CANCELLED")
            bot.edit_message_text("❌ **Order Cancelled Successfully!** Full payment has been refunded to your wallet.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ Unable to cancel (OTP verification in progress).", show_alert=True)

@bot.message_handler(func=lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "WAITING_DEPOSIT_AMOUNT")
def handle_deposit_amount(message):
    user_id = message.from_user.id
    try:
        amt = float(message.text.strip())
        min_dep = float(get_setting("min_deposit") or "50.0")
        max_dep = float(get_setting("max_deposit") or "10000.0")
        
        if amt < min_dep or amt > max_dep:
            bot.reply_to(message, f"❌ **Amount Limit Exceeded!**\nPlease enter a value between `₹{min_dep}` and `₹{max_dep}`.", parse_mode="Markdown")
            return
            
        user_states[user_id] = {"step": "WAITING_DEPOSIT_SCREENSHOT", "amount": amt}
        bot.reply_to(message, f"✅ Amount Recorded: `₹{amt:.2f}`\n\n📸 **Now send a clear screenshot of your payment receipt:**", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid input. Please enter numbers only (e.g., 100).")

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
        bot.reply_to(message, f"✅ **Proof Submitted Successfully!** (Ticket `#{req_id}`)\nYour wallet will be credited automatically upon admin approval.", parse_mode="Markdown")
        
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton(f"✅ Approve (₹{amt:.2f})", callback_data=f"admin_approve:{req_id}:{user_id}:{amt}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{req_id}:{user_id}")
        )
        
        caption = f"🚨 **NEW PAYMENT TICKET** 🚨\n\n🆔 Ticket ID: `#{req_id}`\n👤 Client ID: `{user_id}`\n💵 Claimed Amount: `₹{amt:.2f}`"
        bot.send_photo(ADMIN_ID, photo_id, caption=caption, parse_mode="Markdown", reply_markup=admin_markup)

# ==================== ADVANCED ADMIN CONTROL CENTER ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    orders, revenue, users = get_sales_stats()
    g_bal = grizzly_get_balance()
    g_bal_str = f"${g_bal:.2f}" if g_bal is not None else "Error"

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🖼️ Set Payment QR URL", callback_data="admin_set_qr"),
        types.InlineKeyboardButton("🏷️ Update UPI ID", callback_data="admin_set_upi"),
        types.InlineKeyboardButton("💬 Support Handle", callback_data="admin_set_support"),
        types.InlineKeyboardButton("💵 Profit Margin", callback_data="admin_set_margin"),
        types.InlineKeyboardButton("📉 Min Deposit", callback_data="admin_set_min"),
        types.InlineKeyboardButton("📈 Max Deposit", callback_data="admin_set_max"),
        types.InlineKeyboardButton("🌍 Add Server Route", callback_data="admin_add_country"),
        types.InlineKeyboardButton("🗑️ Remove Route", callback_data="admin_del_country"),
        types.InlineKeyboardButton("➕ Manual Balance Add", callback_data="admin_manual_add")
    )

    text = (
        "👑 **NEXUS SYSTEM ADMIN CENTER**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 **GLOBAL ANALYTICS:**\n"
        f"• Total Registered Clients: `{users}`\n"
        f"• Completed Sales: `{orders}`\n"
        f"• Net Gross Sales: `₹{revenue:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **API Supplier Balance:** `{g_bal_str}`\n"
        f"💵 **System Margin:** `₹{get_setting('profit_margin')}`\n"
        f"📉 **Min Deposit:** `₹{get_setting('min_deposit')}`\n"
        f"📈 **Max Deposit:** `₹{get_setting('max_deposit')}`\n"
        f"📌 **Support Username:** `@{get_setting('support_user')}`\n"
        f"🏦 **Target UPI ID:** `{get_setting('upi_id')}`\n"
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
        
        bot.edit_message_caption(f"✅ Ticket `#{req_id}` APPROVED! Credited `₹{amt:.2f}` to User `{u_id}`.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, f"🎉 **Deposit Confirmed!** `₹{amt:.2f}` has been added to your wallet.", parse_mode="Markdown")

    elif call.data.startswith("admin_reject:"):
        _, req_id, u_id = call.data.split(":")
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_caption(f"❌ Ticket `#{req_id}` REJECTED.", call.message.chat.id, call.message.message_id)
        bot.send_message(int(u_id), f"❌ **Deposit Rejected!** Verification failed for your submitted payment receipt.", parse_mode="Markdown")

    elif call.data == "admin_set_margin":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MARGIN"}
        bot.send_message(ADMIN_ID, "💵 **Enter new profit margin amount per number (e.g. 5.0):**")

    elif call.data == "admin_set_min":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MIN_DEP"}
        bot.send_message(ADMIN_ID, "📉 **Enter new minimum deposit limit (e.g. 50.0):**")

    elif call.data == "admin_set_max":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MAX_DEP"}
        bot.send_message(ADMIN_ID, "📈 **Enter new maximum deposit limit (e.g. 10000.0):**")

    elif call.data == "admin_add_country":
        user_states[ADMIN_ID] = {"step": "ADMIN_ADD_COUNTRY"}
        bot.send_message(ADMIN_ID, "🌍 **Format:** `COUNTRY_ID COUNTRY_NAME BASE_PRICE`\n\n*Example:* `22 India 25.0`", parse_mode="Markdown")

    elif call.data == "admin_del_country":
        countries = get_countries()
        markup = types.InlineKeyboardMarkup(row_width=2)
        for c_id, c_name, _ in countries:
            markup.add(types.InlineKeyboardButton(f"❌ Delete {c_name}", callback_data=f"admin_confirm_del:{c_id}"))
        bot.send_message(ADMIN_ID, "🗑️ **Select server route to delete:**", reply_markup=markup)

    elif call.data.startswith("admin_confirm_del:"):
        c_id = call.data.split(":")[1]
        delete_country(c_id)
        bot.edit_message_text("✅ Server route deleted successfully!", call.message.chat.id, call.message.message_id)

    elif call.data == "admin_set_qr":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_QR"}
        bot.send_message(ADMIN_ID, "🔗 **Send QR Code Image Direct Link (URL):**")

    elif call.data == "admin_set_upi":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_UPI"}
        bot.send_message(ADMIN_ID, "🏷️ **Send new target UPI ID:**")

    elif call.data == "admin_set_support":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_SUPPORT"}
        bot.send_message(ADMIN_ID, "💬 **Send support Telegram handle (without `@`):**")

    elif call.data == "admin_manual_add":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_DIRECT_ADD"}
        bot.send_message(ADMIN_ID, "➕ **Format:** `USER_ID AMOUNT`\n\n*Example:* `123456789 100`", parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_admin_text_inputs(message):
    if message.from_user.id != ADMIN_ID:
        return

    state = user_states.get(ADMIN_ID, {}).get("step")
    
    if state == "ADMIN_WAITING_QR":
        qr_url = message.text.strip()
        set_setting("qr_file_id", qr_url)
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **Payment QR URL Updated Successfully!**\nLink: `{qr_url}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_MARGIN":
        try:
            m = float(message.text.strip())
            set_setting("profit_margin", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **System Margin Updated:** `₹{m:.2f}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_WAITING_MIN_DEP":
        try:
            m = float(message.text.strip())
            set_setting("min_deposit", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Minimum Deposit Updated:** `₹{m:.2f}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_WAITING_MAX_DEP":
        try:
            m = float(message.text.strip())
            set_setting("max_deposit", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Maximum Deposit Updated:** `₹{m:.2f}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_ADD_COUNTRY":
        try:
            parts = message.text.strip().split()
            c_id = int(parts[0])
            c_name = " ".join(parts[1:-1])
            c_price = float(parts[-1])
            add_country(c_id, c_name, c_price)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Route Added:** `{c_name}` (ID: {c_id}) - Base Price: `₹{c_price:.2f}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `COUNTRY_ID NAME PRICE`")

    elif state == "ADMIN_WAITING_UPI":
        set_setting("upi_id", message.text.strip())
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **UPI ID Updated:** `{message.text.strip()}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_SUPPORT":
        username = message.text.strip().replace("@", "")
        set_setting("support_user", username)
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **Support Handle Updated:** `@{username}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_DIRECT_ADD":
        try:
            parts = message.text.strip().split()
            target_user = int(parts[0])
            amt = float(parts[1])
            update_user_balance(target_user, amt)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Credited `₹{amt:.2f}` to User `{target_user}`.", parse_mode="Markdown")
            bot.send_message(target_user, f"🎉 **Manual Deposit Received!** `₹{amt:.2f}` has been added to your wallet.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `USER_ID AMOUNT`")

# ==================== START BOT ====================
if __name__ == "__main__":
    print("Nexus OTP Automation Engine Online...")
    bot.infinity_polling()
