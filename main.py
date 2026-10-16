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
    return "Telegram Virtual Account Bot is Running!"

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

# State tracking for Inputs
user_states = {}

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0
        )
    ''')
    
    # Sales Table
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
    
    # Deposit Requests Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            photo_id TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    
    # Countries Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS countries (
            country_id INTEGER PRIMARY KEY,
            country_name TEXT,
            price REAL
        )
    ''')
    
    # Admin Settings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Default Settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_user', 'admin_username')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('upi_id', 'example@upi')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('profit_margin', '5.0')")
    
    # Default Countries (Example: 0 = Any/Russia, 22 = India, 187 = USA)
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (0, 'Russia / Any', 15.0)")
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (22, 'India', 25.0)")
    cursor.execute("INSERT OR IGNORE INTO countries (country_id, country_name, price) VALUES (187, 'USA', 20.0)")
    
    conn.commit()
    conn.close()

init_db()

# DB Helpers
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

# ==================== USER MAIN MENU ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    support_username = get_setting("support_user")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_buy = types.InlineKeyboardButton("📱 Buy Telegram Number", callback_data="select_country")
    btn_wallet = types.InlineKeyboardButton("💳 Wallet & Add Cash", callback_data="wallet")
    btn_support = types.InlineKeyboardButton("💬 Live Support", url=f"https://t.me/{support_username}")
    btn_refresh = types.InlineKeyboardButton("🔄 Refresh", callback_data="home")
    
    markup.add(btn_buy, btn_wallet)
    markup.add(btn_support, btn_refresh)
    
    text = (
        f"⚡ **Welcome to Premium OTP Store** ⚡\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"💰 **Your Balance:** `{balance:.2f} ₹`\n\n"
        f"🚀 *Instant Telegram Virtual Accounts & OTP Service.*"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# ==================== USER CALLBACK HANDLERS ====================
@bot.callback_query_handler(func=lambda call: not call.data.startswith("admin_"))
def user_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "home":
        balance = get_user_balance(user_id)
        support_username = get_setting("support_user")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📱 Buy Telegram Number", callback_data="select_country"),
            types.InlineKeyboardButton("💳 Wallet & Add Cash", callback_data="wallet"),
            types.InlineKeyboardButton("💬 Live Support", url=f"https://t.me/{support_username}"),
            types.InlineKeyboardButton("🔄 Refresh", callback_data="home")
        )
        text = (
            f"⚡ **Main Menu**\n\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💰 **Your Balance:** `{balance:.2f} ₹`"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "wallet":
        balance = get_user_balance(user_id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_add = types.InlineKeyboardButton("➕ Add Money (UPI / QR)", callback_data="add_money")
        btn_back = types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="home")
        markup.add(btn_add, btn_back)
        
        text = (
            f"💰 **Wallet Balance Overview**\n\n"
            f"• **Current Balance:** `{balance:.2f} ₹`\n"
            f"• **User ID:** `{user_id}`\n\n"
            f"Niche button par click karke paise add karein."
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "add_money":
        qr_file_id = get_setting("qr_file_id")
        upi_id = get_setting("upi_id")
        
        caption = (
            f"💳 **Add Money to Wallet**\n\n"
            f"1️⃣ QR Code / UPI ID par payment karein:\n"
            f"📌 **UPI ID:** `{upi_id}`\n\n"
            f"2️⃣ Payment karne ke baad niche **'📸 Upload Screenshot'** button par click karke screenshot bhejein."
        )
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_submit = types.InlineKeyboardButton("📸 Upload Screenshot", callback_data="submit_proof")
        btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="wallet")
        markup.add(btn_submit, btn_back)
        
        if qr_file_id:
            bot.send_photo(call.message.chat.id, qr_file_id, caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "submit_proof":
        user_states[user_id] = {"step": "WAITING_SCREENSHOT"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="home"))
        bot.send_message(call.message.chat.id, "📸 **Kripya Payment Screenshot photo bhejein:**", parse_mode="Markdown", reply_markup=markup)

    elif call.data == "select_country":
        countries = get_countries()
        profit = float(get_setting("profit_margin") or "5.0")
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        for c_id, c_name, c_price in countries:
            final_price = c_price + profit
            markup.add(types.InlineKeyboardButton(f"🌐 {c_name} - {final_price:.2f} ₹", callback_data=f"buy_num:{c_id}:{final_price}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="home"))
        bot.edit_message_text("🌍 **Select Country for Telegram Virtual Account:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("buy_num:"):
        _, c_id, cost = call.data.split(":")
        cost = float(cost)
        user_bal = get_user_balance(user_id)
        
        if user_bal < cost:
            bot.answer_callback_query(call.id, f"❌ Insufficient Balance! Minimum {cost:.2f} ₹ required.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⌛ Fetching Virtual Number...")
        res = grizzly_get_number(country_id=c_id)
        
        if res["status"]:
            tx_id = res["id"]
            phone_num = res["number"]
            
            update_user_balance(user_id, -cost)
            log_sale(tx_id, user_id, "Telegram", cost, "PENDING")
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("🔄 Get OTP Code", callback_data=f"get_otp:{tx_id}:{cost}"),
                types.InlineKeyboardButton("❌ Cancel Order & Refund", callback_data=f"cancel:{tx_id}:{cost}")
            )
            
            msg = (
                f"✅ **Number Successfully Generated!**\n\n"
                f"📞 **Phone:** `{phone_num}`\n"
                f"🆔 **Order ID:** `{tx_id}`\n"
                f"💵 **Price:** `{cost:.2f} ₹`\n\n"
                f"👉 Number ko Telegram me daalein aur OTP aane par **'Get OTP Code'** dabayein."
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, f"❌ Server Response: `{res['message']}`\n\nNumber available nahi hai ya API error hai.", parse_mode="Markdown")

    elif call.data.startswith("get_otp:"):
        _, tx_id, cost = call.data.split(":")
        status = grizzly_get_status(tx_id)
        
        if "STATUS_OK" in status:
            otp_code = status.split(":")[1]
            grizzly_set_status(tx_id, 6)
            log_sale(tx_id, user_id, "Telegram", float(cost), "COMPLETED")
            bot.send_message(call.message.chat.id, f"🎉 **Your Telegram OTP Code:** `{otp_code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in status:
            bot.answer_callback_query(call.id, "⌛ OTP nahi aaya abhi tak. Pehle App se OTP bhejein!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"Status: {status}", show_alert=True)

    elif call.data.startswith("cancel:"):
        _, tx_id, refund_amt = call.data.split(":")
        refund_amt = float(refund_amt)
        
        cancel_res = grizzly_set_status(tx_id, 8)
        if any(keyword in cancel_res for keyword in ["ACCESS_CANCEL", "ACCESS_OK", "STATUS_CANCEL"]):
            update_user_balance(user_id, refund_amt)
            log_sale(tx_id, user_id, "Telegram", refund_amt, "CANCELLED")
            bot.edit_message_text("❌ **Order Cancelled!** Balance refunded to your wallet.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ Cancel nahi ho saka.", show_alert=True)

# ==================== USER SCREENSHOT SUBMISSION ====================
@bot.message_handler(content_types=['photo'])
def handle_user_screenshot(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {}).get("step")
    
    if state == "WAITING_SCREENSHOT":
        photo_id = message.photo[-1].file_id
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO deposits (user_id, photo_id) VALUES (?, ?)", (user_id, photo_id))
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        del user_states[user_id]
        bot.reply_to(message, f"✅ **Screenshot Received!** Request ID: `#{req_id}`\nAdmin verification ke baad balance add ho jayega.", parse_mode="Markdown")
        
        # Send Notification to Admin
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Approve & Add Balance", callback_data=f"admin_approve_start:{req_id}:{user_id}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{req_id}:{user_id}")
        )
        
        caption = f"🔔 **New Deposit Request!**\n\n🆔 Request ID: `#{req_id}`\n👤 User ID: `{user_id}`"
        bot.send_photo(ADMIN_ID, photo_id, caption=caption, parse_mode="Markdown", reply_markup=admin_markup)

# ==================== ADMIN PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    orders, revenue, users = get_sales_stats()
    g_bal = grizzly_get_balance()
    g_bal_str = f"{g_bal:.2f}" if g_bal is not None else "Error"

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🖼️ Set Payment QR", callback_data="admin_set_qr"),
        types.InlineKeyboardButton("🏷️ Set UPI ID", callback_data="admin_set_upi"),
        types.InlineKeyboardButton("💬 Support Username", callback_data="admin_set_support"),
        types.InlineKeyboardButton("💵 Set Profit Margin", callback_data="admin_set_margin"),
        types.InlineKeyboardButton("🌍 Add Country", callback_data="admin_add_country"),
        types.InlineKeyboardButton("🗑️ Delete Country", callback_data="admin_del_country"),
        types.InlineKeyboardButton("➕ Manual Add Balance", callback_data="admin_manual_add")
    )

    text = (
        f"⚙️ **Admin Control Panel** ⚙️\n\n"
        f"📊 **Sales Analytics:**\n"
        f"• Total Users: `{users}`\n"
        f"• Completed Sales: `{orders}`\n"
        f"• Total Revenue: `{revenue:.2f} ₹`\n\n"
        f"💳 **Grizzly API Balance:** `{g_bal_str}` USD/RUB\n"
        f"💵 **Profit Margin:** `{get_setting('profit_margin')} ₹`\n"
        f"📌 **Current Support:** `@{get_setting('support_user')}`\n"
        f"🏦 **Current UPI ID:** `{get_setting('upi_id')}`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# ==================== ADMIN CALLBACK HANDLERS ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data.startswith("admin_approve_start:"):
        _, req_id, u_id = call.data.split(":")
        user_states[ADMIN_ID] = {"step": "ADMIN_INPUT_APPROVE_AMOUNT", "req_id": req_id, "target_user": u_id}
        bot.send_message(ADMIN_ID, f"💵 **Kitna amount add karna hai User `{u_id}` ke liye?** (Numbers only):", parse_mode="Markdown")

    elif call.data.startswith("admin_reject:"):
        _, req_id, u_id = call.data.split(":")
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_caption(f"❌ Request `#{req_id}` REJECTED.", call.message.chat.id, call.message.message_id)
        bot.send_message(int(u_id), f"❌ **Payment Request Rejected.** Screenshot clear nahi tha ya payment receive nahi hua.", parse_mode="Markdown")

    elif call.data == "admin_set_margin":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_MARGIN"}
        bot.send_message(ADMIN_ID, "💵 **Naya Profit Margin type karein (e.g. 5.0 ya 10.0):**")

    elif call.data == "admin_add_country":
        user_states[ADMIN_ID] = {"step": "ADMIN_ADD_COUNTRY"}
        bot.send_message(ADMIN_ID, "🌍 Format me bhejein: `COUNTRY_ID NAME BASE_PRICE`\n\n*Example:* `22 India 20.0`", parse_mode="Markdown")

    elif call.data == "admin_del_country":
        countries = get_countries()
        markup = types.InlineKeyboardMarkup(row_width=2)
        for c_id, c_name, _ in countries:
            markup.add(types.InlineKeyboardButton(f"❌ {c_name}", callback_data=f"admin_confirm_del:{c_id}"))
        bot.send_message(ADMIN_ID, "🗑️ Select Country to Delete:", reply_markup=markup)

    elif call.data.startswith("admin_confirm_del:"):
        c_id = call.data.split(":")[1]
        delete_country(c_id)
        bot.edit_message_text("✅ Country deleted successfully!", call.message.chat.id, call.message.message_id)

    elif call.data == "admin_set_qr":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_QR"}
        bot.send_message(ADMIN_ID, "📸 Naya Payment QR Code photo chat me bhejein:")

    elif call.data == "admin_set_upi":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_UPI"}
        bot.send_message(ADMIN_ID, "🏷️ Naya UPI ID type karke bhejein:")

    elif call.data == "admin_set_support":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_SUPPORT"}
        bot.send_message(ADMIN_ID, "💬 Support Username type karke bhejein (bina `@` ke):")

    elif call.data == "admin_manual_add":
        user_states[ADMIN_ID] = {"step": "ADMIN_WAITING_DIRECT_ADD"}
        bot.send_message(ADMIN_ID, "➕ Format me bhejein:\n`USER_ID AMOUNT`", parse_mode="Markdown")

# ==================== ADMIN INPUT HANDLER ====================
@bot.message_handler(content_types=['photo', 'text'])
def handle_admin_inputs(message):
    if message.from_user.id != ADMIN_ID:
        return

    state = user_states.get(ADMIN_ID, {}).get("step")
    
    if state == "ADMIN_INPUT_APPROVE_AMOUNT" and message.text:
        try:
            amt = float(message.text.strip())
            req_id = user_states[ADMIN_ID]["req_id"]
            u_id = int(user_states[ADMIN_ID]["target_user"])
            
            update_user_balance(u_id, amt)
            
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE deposits SET status = 'APPROVED' WHERE id = ?", (req_id,))
            conn.commit()
            conn.close()
            
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Approved Request `#{req_id}`! `{amt} ₹` added to User `{u_id}`.", parse_mode="Markdown")
            bot.send_message(u_id, f"🎉 **Payment Approved!** `{amt} ₹` credited to your wallet.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid amount number.")

    elif state == "ADMIN_WAITING_MARGIN" and message.text:
        try:
            m = float(message.text.strip())
            set_setting("profit_margin", str(m))
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ **Profit Margin Updated to:** `{m} ₹`", parse_mode="Markdown")
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
            bot.reply_to(message, f"✅ **Added Country:** `{c_name}` (ID: {c_id}) - Base Price: `{c_price} ₹`", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Format error. Use: `COUNTRY_ID NAME BASE_PRICE`")

    elif state == "ADMIN_WAITING_QR" and message.photo:
        file_id = message.photo[-1].file_id
        set_setting("qr_file_id", file_id)
        del user_states[ADMIN_ID]
        bot.reply_to(message, "✅ **Payment QR Code Updated!**", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_UPI" and message.text:
        set_setting("upi_id", message.text.strip())
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **UPI ID Updated to:** `{message.text.strip()}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_SUPPORT" and message.text:
        username = message.text.strip().replace("@", "")
        set_setting("support_user", username)
        del user_states[ADMIN_ID]
        bot.reply_to(message, f"✅ **Support Username Updated to:** `@{username}`", parse_mode="Markdown")

    elif state == "ADMIN_WAITING_DIRECT_ADD" and message.text:
        try:
            parts = message.text.strip().split()
            target_user = int(parts[0])
            amt = float(parts[1])
            update_user_balance(target_user, amt)
            del user_states[ADMIN_ID]
            bot.reply_to(message, f"✅ Added `{amt} ₹` to User `{target_user}`.", parse_mode="Markdown")
            bot.send_message(target_user, f"🎉 **Balance Added!** `{amt} ₹` credited by Admin.", parse_mode="Markdown")
        except Exception:
            bot.reply_to(message, "❌ Invalid format. Use: `USER_ID AMOUNT`")

# ==================== START BOT ====================
if __name__ == "__main__":
    print("Bot with Country System & Admin Panel Started...")
    bot.infinity_polling()
