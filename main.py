import sqlite3
import requests
import os
import threading
import urllib.parse
from flask import Flask
import telebot
from telebot import types

# ==================== RENDER FREE WEB SERVER ====================
app = Flask('')

@app.route('/')
def home():
    return "TG SHOP Core Engine Online!"

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
    
    # Table for Countries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS countries (
            country_id INTEGER PRIMARY KEY,
            country_name TEXT,
            flag TEXT
        )
    ''')
    
    # Table for Price Tiers belonging to Countries
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS country_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_id INTEGER,
            tier_name TEXT,
            base_price REAL,
            qty INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_user', 'admin_username')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('upi_id', 'rohit0853@ptaxis')")
    cursor.execute("UPDATE settings SET value = 'rohit0853@ptaxis' WHERE key = 'upi_id' AND (value = 'example@upi' OR value = '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('profit_margin', '10.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_deposit', '50.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('max_deposit', '10000.0')")
    
    # Initial Sample Data Setup
    cursor.execute("SELECT COUNT(*) FROM countries")
    if cursor.fetchone()[0] == 0:
        countries_data = [
            (22, "India", "🇮🇳"),
            (187, "USA", "🇺🇸"),
            (6, "Indonesia", "🇮🇩"),
            (5, "Myanmar", "🇲🇲"),
            (60, "Bangladesh", "🇧🇩"),
            (10, "Vietnam", "🇻🇳"),
            (0, "Global / Any", "🌐")
        ]
        cursor.executemany("INSERT INTO countries (country_id, country_name, flag) VALUES (?, ?, ?)", countries_data)
        
        tiers_data = [
            (22, "India (High Quality)", 55.0, 100),
            (22, "India (Standard)", 45.0, 7665),
            (22, "India (Economy)", 30.0, 7769),
            (187, "USA (Premium)", 40.0, 500),
            (187, "USA (Standard)", 25.0, 2000),
            (0, "Global Server", 15.0, 5000)
        ]
        cursor.executemany("INSERT INTO country_tiers (country_id, tier_name, base_price, qty) VALUES (?, ?, ?, ?)", tiers_data)
            
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

def get_user_orders(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT order_id, service, cost, status, timestamp FROM sales WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_countries():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT country_id, country_name, flag FROM countries")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_tiers_by_country(country_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, tier_name, base_price, qty FROM country_tiers WHERE country_id = ?", (country_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_country_tier(c_id, name, price, qty):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # Check if country exists
    cursor.execute("SELECT country_name FROM countries WHERE country_id = ?", (c_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO countries (country_id, country_name, flag) VALUES (?, ?, '🌐')", (c_id, f"Country {c_id}"))
    cursor.execute("INSERT INTO country_tiers (country_id, tier_name, base_price, qty) VALUES (?, ?, ?, ?)", (c_id, name, price, qty))
    conn.commit()
    conn.close()

def delete_country_tier(tier_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM country_tiers WHERE id = ?", (tier_id,))
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

# ==================== DYNAMIC UPI QR GENERATOR ====================
def generate_upi_qr(upi_id, amount, name="TG SHOP"):
    upi_uri = f"upi://pay?pa={upi_id}&pn={urllib.parse.quote(name)}&am={amount}&cu=INR"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_uri)}"
    return qr_url

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

# ==================== UI MARKUPS ====================
def main_categories_markup():
    support_username = get_setting("support_user")
    markup = types.InlineKeyboardMarkup()
    
    markup.add(types.InlineKeyboardButton("📱 Telegram Accounts", callback_data="tg_accounts"))
    markup.row(
        types.InlineKeyboardButton("💰 My Wallet", callback_data="check_wallet"),
        types.InlineKeyboardButton("➕ Deposit", callback_data="add_money")
    )
    markup.add(types.InlineKeyboardButton("📦 My Orders", callback_data="my_orders"))
    markup.add(types.InlineKeyboardButton("📢 Sales", callback_data="sales_info"))
    markup.add(types.InlineKeyboardButton("🆘 Support", url=f"https://t.me/{support_username}"))
    
    return markup

def countries_grid_markup():
    countries = get_countries()
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = []
    global_btn = None
    
    for c_id, c_name, flag in countries:
        btn_text = f"{flag} {c_name}"
        if c_id == 0 or "Global" in c_name:
            global_btn = types.InlineKeyboardButton(btn_text, callback_data=f"show_country_tiers:{c_id}")
        else:
            buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"show_country_tiers:{c_id}"))
            
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.row(buttons[i], buttons[i+1])
        else:
            markup.row(buttons[i])
            
    if global_btn:
        markup.add(global_btn)
        
    markup.add(types.InlineKeyboardButton("🔍 Search Country", callback_data="search_country"))
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="home"))
    return markup

def country_tiers_markup(country_id):
    tiers = get_tiers_by_country(country_id)
    profit = float(get_setting("profit_margin") or "5.0")
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    if not tiers:
        # Fallback if no specific tier added for this country yet
        final_price = 30.0 + profit
        markup.add(types.InlineKeyboardButton(f"Standard Quality — ₹{final_price:.2f}", callback_data=f"buy_tier:{country_id}:{final_price}"))
    else:
        for tier_id, tier_name, base_price, qty in tiers:
            final_price = base_price + profit
            btn_text = f"{tier_name} — Qty: {qty} — ₹{final_price:.2f}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_tier:{country_id}:{final_price}"))
            
    markup.add(types.InlineKeyboardButton("⬅️ Back to Countries", callback_data="tg_accounts"))
    return markup

# ==================== HANDLERS ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    first_name = message.from_user.first_name or "Client"
    styled_name = " ".join(first_name.upper())
    
    text = (
        f"👋 Hi **{styled_name}**,\n\n"
        "💎 Welcome to STORE\n"
        "Live Telegram accounts with instant delivery.\n\n"
        "__________________________________\n\n"
        f"💰 Your Wallet: ₹{int(balance) if balance.is_integer() else balance}\n"
        "__________________________________\n\n"
        "⚡ Instant Delivery | Secure Payments\n\n"
        "👇 Select an option:"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_categories_markup())

@bot.callback_query_handler(func=lambda call: not call.data.startswith("admin_"))
def user_callbacks(call):
    user_id = call.from_user.id
    first_name = call.from_user.first_name or "Client"
    styled_name = " ".join(first_name.upper())
    
    if call.data == "home":
        balance = get_user_balance(user_id)
        text = (
            f"👋 Hi **{styled_name}**,\n\n"
            "💎 Welcome to STORE\n"
            "Live Telegram accounts with instant delivery.\n\n"
            "__________________________________\n\n"
            f"💰 Your Wallet: ₹{int(balance) if balance.is_integer() else balance}\n"
            "__________________________________\n\n"
            "👇 Select an option:"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_categories_markup())

    elif call.data == "tg_accounts":
        text = (
            "✉️ **Mail Accounts**\n\n"
            "Mail-included accounts from all available qualities.\n\n"
            "👇 **Select a region to browse:**"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=countries_grid_markup())

    elif call.data.startswith("show_country_tiers:"):
        country_id = int(call.data.split(":")[1])
        text = (
            "📶 **Select Available Quality & Price Tier:**\n\n"
            "Choose your preferred package below:"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=country_tiers_markup(country_id))

    elif call.data == "check_wallet":
        balance = get_user_balance(user_id)
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("➕ Deposit Funds", callback_data="add_money"),
            types.InlineKeyboardButton("⬅️ Back", callback_data="home")
        )
        
        text = (
            "💳 **YOUR WALLET**\n\n"
            f"👤 User: `{first_name}`\n"
            f"🆔 ID: `{user_id}`\n\n"
            f"💰 Current Balance: `₹{balance:.2f}`\n\n"
            "👇 Click below to add funds:"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "add_money":
        user_states[user_id] = {"step": "WAITING_DEPOSIT_AMOUNT"}
        min_dep = get_setting("min_deposit")
        max_dep = get_setting("max_deposit")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="home"))
        
        bot.edit_message_text(
            f"💳 **AUTOMATED DEPOSIT**\n\n"
            f"⚠️ Min: `₹{min_dep}` | Max: `₹{max_dep}`\n\n"
            f"💵 **Enter the amount you want to add (e.g. 100):**",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup
        )

    elif call.data == "my_orders":
        orders = get_user_orders(user_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="home"))
        
        if not orders:
            bot.edit_message_text("📦 **MY ORDERS**\n\nYou have no previous orders.", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        else:
            msg = "📦 **YOUR RECENT ORDERS:**\n\n"
            for o_id, service, cost, status, ts in orders:
                msg += f"🆔 `{o_id}` | {service}\n💰 Amount: ₹{cost:.2f} | Status: `{status}`\n📅 {ts}\n\n"
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "sales_info":
        orders, revenue, _ = get_sales_stats()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="home"))
        
        text = (
            "📢 **STORE SALES STATISTICS**\n\n"
            f"📦 Total Accounts Sold: `{orders}`\n"
            f"⚡ Active Quality Ratio: `99.8%`"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("buy_tier:"):
        _, c_id, cost = call.data.split(":")
        cost = float(cost)
        user_bal = get_user_balance(user_id)
        
        if user_bal < cost:
            bot.answer_callback_query(call.id, f"❌ Low Balance! Required: ₹{cost:.2f}", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⚡ Allocating Number...")
        res = grizzly_get_number(country_id=int(c_id))
        
        if res["status"]:
            tx_id = res["id"]
            phone_num = res["number"]
            
            update_user_balance(user_id, -cost)
            log_sale(tx_id, user_id, "Telegram", cost, "PENDING")
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📥 Get OTP Code", callback_data=f"get_otp:{tx_id}:{cost}"))
            markup.add(types.InlineKeyboardButton("🚫 Cancel & Refund", callback_data=f"cancel:{tx_id}:{cost}"))
            
            msg = (
                "📱 **NUMBER ALLOCATED**\n\n"
                f"📞 Phone Number: `{phone_num}`\n"
                f"🆔 Order ID: `{tx_id}`\n"
                f"💰 Price: `₹{cost:.2f}`\n\n"
                "👉 Enter this number in Telegram and press 'Get OTP Code'."
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, f"❌ Stock unavailable: `{res['message']}`", parse_mode="Markdown")

    elif call.data.startswith("get_otp:"):
        _, tx_id, cost = call.data.split(":")
        status = grizzly_get_status(tx_id)
        
        if "STATUS_OK" in status:
            otp_code = status.split(":")[1]
            grizzly_set_status(tx_id, 6)
            log_sale(tx_id, user_id, "Telegram", float(cost), "COMPLETED")
            bot.send_message(call.message.chat.id, f"🎉 **YOUR OTP CODE:** `{otp_code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in status:
            bot.answer_callback_query(call.id, "⌛ Waiting for SMS...", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"Status: {status}", show_alert=True)

    elif call.data.startswith("cancel:"):
        _, tx_id, refund_amt = call.data.split(":")
        refund_amt = float(refund_amt)
        
        cancel_res = grizzly_set_status(tx_id, 8)
        if any(keyword in cancel_res for keyword in ["ACCESS_CANCEL", "ACCESS_OK", "STATUS_CANCEL"]):
            update_user_balance(user_id, refund_amt)
            log_sale(tx_id, user_id, "Telegram", refund_amt, "CANCELLED")
            bot.edit_message_text("❌ Order cancelled and balance refunded!", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "❌ Cannot cancel right now.", show_alert=True)

@bot.message_handler(func=lambda msg: msg.from_user.id in user_states and user_states[msg.from_user.id].get("step") == "WAITING_DEPOSIT_AMOUNT")
def handle_deposit_amount(message):
    user_id = message.from_user.id
    try:
        amt = float(message.text.strip())
        min_dep = float(get_setting("min_deposit") or "50.0")
        max_dep = float(get_setting("max_deposit") or "10000.0")
        
        if amt < min_dep or amt > max_dep:
            bot.reply_to(message, f"❌ Amount must be between `₹{min_dep}` and `₹{max_dep}`.", parse_mode="Markdown")
            return
            
        upi_id = get_setting("upi_id")
        qr_image_url = generate_upi_qr(upi_id, amt)
        
        user_states[user_id] = {"step": "WAITING_DEPOSIT_SCREENSHOT", "amount": amt}
        
        caption = (
            f"📲 **DYNAMIC PAYMENT QR**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 **Amount To Pay:** `₹{amt:.2f}`\n"
            f"🏦 **UPI ID:** `{upi_id}`\n\n"
            f"1️⃣ Scan via any UPI App.\n"
            f"2️⃣ Send payment screenshot here."
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="home"))
        
        bot.send_photo(message.chat.id, qr_image_url, caption=caption, parse_mode="Markdown", reply_markup=markup)
        
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number.")

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
        bot.reply_to(message, f"✅ Screenshot received! Ticket ID: `#{req_id}`", parse_mode="Markdown")
        
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton(f"✅ Approve (₹{amt:.2f})", callback_data=f"admin_approve:{req_id}:{user_id}:{amt}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{req_id}:{user_id}")
        )
        bot.send_photo(ADMIN_ID, photo_id, caption=f"🚨 **NEW PAYMENT PROOF**\nTicket ID: `#{req_id}`\nUser: `{user_id}`\nAmount: `₹{amt:.2f}`", parse_mode="Markdown", reply_markup=admin_markup)

# ==================== ADMIN CONTROL PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    orders, revenue, users = get_sales_stats()
    g_bal = grizzly_get_balance()
    g_bal_str = f"${g_bal:.2f}" if g_bal is not None else "Error"

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🏷️ Set UPI ID", callback_data="admin_set_upi"),
        types.InlineKeyboardButton("💬 Support Handle", callback_data="admin_set_support"),
        types.InlineKeyboardButton("💵 Profit Margin", callback_data="admin_set_margin"),
        types.InlineKeyboardButton("🌍 Add Price Tier", callback_data="admin_add_tier"),
        types.InlineKeyboardButton("🗑️ Del Price Tier", callback_data="admin_del_tier"),
        types.InlineKeyboardButton("➕ Add Balance", callback_data="admin_manual_add")
    )

    text = (
        "👑 **ADMIN DASHBOARD**\n\n"
        f"👥 Users: `{users}` | 📦 Orders: `{orders}`\n"
        f"💰 Revenue: `₹{revenue:.2f}` | 💳 Grizzly Bal: `{g_bal_str}`\n"
        f"💵 Margin: `₹{get_setting('profit_margin')}`\n"
        f"📌 UPI ID: `{get_setting('upi_id')}`"
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
        
        bot.edit_message_caption(f"✅ Deposit `#{req_id}` APPROVED! Added `₹{amt:.2f}` to User `{u_id}`.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, f"🎉 Deposit approved! `₹{amt:.2f}` added to your wallet.", parse_mode="Markdown")

    elif call.data.startswith("admin_reject:"):
        _, req_id, u_id = call.data.split(":")
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_caption(f"❌ Deposit `#{req_id}` REJECTED.", call.message.chat.id, call.message.message_id)
        bot.send_message(int(u_id), "❌ Deposit payment rejected.", parse_mode="Markdown")

    elif call.data == "admin_set_margin":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MARGIN"}
        bot.send_message(ADMIN_ID, "💵 Enter profit margin amount to add (e.g. 15.0):")

    elif call.data == "admin_add_tier":
        user_states[ADMIN_ID] = {"step": "ADMIN_ADD_TIER"}
        bot.send_message(ADMIN_ID, "🌍 Format: `COUNTRY_ID TIER_NAME BASE_PRICE QTY`\nExample: `22 India (Economy) 30.0 7769`", parse_mode="Markdown")

    elif call.data == "admin_del_tier":
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, tier_name, base_price FROM country_tiers")
        tiers = cursor.fetchall()
        conn.close()
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for t_id, t_name, price in tiers:
            markup.add(types.InlineKeyboardButton(f"❌ Delete: {t_name} (₹{price})", callback_data=f"admin_confirm_del:{t_id}"))
        bot.send_message(ADMIN_ID, "🗑️ Select tier to delete:", reply_markup=markup)

    elif call.data.startswith("admin_confirm_del:"):
        t_id = int(call.data.split(":")[1])
        delete_country_tier(t_id)
        bot.edit_message_text("✅ Price tier deleted!", call.message.chat.id, call.message.message_id)

    elif call.data == "admin_set_upi":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_UPI"}
        bot.send_message(ADMIN_ID, "🏷️ Send new UPI ID:")

    elif call.data == "admin_manual_add":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_DIRECT_ADD"}
        bot.send_message(ADMIN_ID, "➕ Format: `USER_ID AMOUNT`", parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_admin_text_inputs(message):
    if message.from_user.id != ADMIN_ID:
        return

    state = user_states.get(ADMIN_ID, {}).get("step")
    
    if state == "ADMIN_WAITING_MARGIN":
        try:
            m = float(message.text.strip())
            set_setting("profit_margin", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Profit Margin Updated: `₹{m:.2f}`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid number.")

    elif state == "ADMIN_ADD_TIER":
        try:
            parts = message.text.strip().split()
            c_id = int(parts[0])
            qty = int(parts[-1])
            base_price = float(parts[-2])
            c_name = " ".join(parts[1:-2])
            add_country_tier(c_id, c_name, base_price, qty)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Price Tier Added: `{c_name}` (Base: ₹{base_price})", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `COUNTRY_ID TIER_NAME BASE_PRICE QTY`")

    elif state == "ADMIN_WAITING_UPI":
        set_setting("upi_id", message.text.strip())
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ UPI ID Updated: `{message.text.strip()}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_DIRECT_ADD":
        try:
            parts = message.text.strip().split()
            target_user = int(parts[0])
            amt = float(parts[1])
            update_user_balance(target_user, amt)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Added `₹{amt:.2f}` to User `{target_user}`.", parse_mode="Markdown")
            bot.send_message(target_user, f"🎉 `₹{amt:.2f}` added to your balance.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `USER_ID AMOUNT`")

# ==================== START BOT ====================
if __name__ == "__main__":
    print("TG SHOP Bot Running with Clean 2-Step Country -> Tier System...")
    bot.infinity_polling()
