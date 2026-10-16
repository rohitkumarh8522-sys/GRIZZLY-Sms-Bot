import sqlite3
import requests
import os
import threading
from flask import Flask
import telebot
from telebot import types

# ==================== RENDER FREE WEB SERVER (PORT BINDING) ====================
app = Flask('')

@app.route('/')
def home():
    return "Telegram Virtual Account Bot is Running Successfully!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Flask server ko background thread me chalana taaki Render port error na de
threading.Thread(target=run_flask).start()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
GRIZZLY_API_KEY = os.getenv("GRIZZLY_API_KEY", "YOUR_GRIZZLY_API_KEY_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # Aapka Numeric Telegram ID

SERVICE_CODE = "tg"
PROFIT_MARGIN = 5.0  # Base Price + Profit Margin

bot = telebot.TeleBot(BOT_TOKEN)

# State tracking for Admin Inputs (QR code update / Support Username update)
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
    
    # Sales/Orders Table
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
            amount REAL,
            utr_id TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    
    # Admin Settings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Default Values
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_user', 'admin_username')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('upi_id', 'example@upi')")
    
    conn.commit()
    conn.close()

init_db()

# DB Helper Functions
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
        res = requests.get(url, timeout=10).text
        if "ACCESS_NUMBER" in res:
            parts = res.split(":")
            return {"status": True, "id": parts[1], "number": parts[2]}
        return {"status": False, "message": res}
    except Exception as e:
        return {"status": False, "message": str(e)}

def grizzly_get_status(tx_id):
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getStatus&id={tx_id}"
        return requests.get(url, timeout=10).text
    except Exception as e:
        return f"ERROR: {e}"

def grizzly_set_status(tx_id, status_code):
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=setStatus&id={tx_id}&status={status_code}"
        return requests.get(url, timeout=10).text
    except Exception as e:
        return f"ERROR: {e}"

# ==================== USER MAIN MENU ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    support_username = get_setting("support_user")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_buy = types.InlineKeyboardButton("📱 Buy Telegram Number", callback_data="buy_tg")
    btn_wallet = types.InlineKeyboardButton("💳 Wallet & Add Cash", callback_data="wallet")
    btn_support = types.InlineKeyboardButton("💬 Live Support", url=f"https://t.me/{support_username}")
    btn_refresh = types.InlineKeyboardButton("🔄 Refresh", callback_data="home")
    
    markup.add(btn_buy, btn_wallet)
    markup.add(btn_support, btn_refresh)
    
    text = (
        f"⚡ **Welcome to Premium OTP Store** ⚡\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"💰 **Your Balance:** `{balance:.2f} ₹/Pts`\n\n"
        f"🚀 *Instant Telegram Virtual Accounts & OTP Delivery Service.*"
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
            types.InlineKeyboardButton("📱 Buy Telegram Number", callback_data="buy_tg"),
            types.InlineKeyboardButton("💳 Wallet & Add Cash", callback_data="wallet"),
            types.InlineKeyboardButton("💬 Live Support", url=f"https://t.me/{support_username}"),
            types.InlineKeyboardButton("🔄 Refresh", callback_data="home")
        )
        text = (
            f"⚡ **Main Menu**\n\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💰 **Your Balance:** `{balance:.2f} ₹/Pts`"
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
            f"• **Current Balance:** `{balance:.2f}`\n"
            f"• **User ID:** `{user_id}`\n\n"
            f"Niche button par click karke QR Code se paise add karein."
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "add_money":
        qr_file_id = get_setting("qr_file_id")
        upi_id = get_setting("upi_id")
        
        caption = (
            f"💳 **Add Money to Wallet**\n\n"
            f"1️⃣ Niche diye gaye QR Code / UPI par payment karein.\n"
            f"📌 **UPI ID:** `{upi_id}`\n\n"
            f"2️⃣ Payment hone ke baad, command bhejein:\n"
            f"`/deposit <Amount> <UTR/Transaction_ID>`\n\n"
            f"*(Example: `/deposit 100 409281920192`)*"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="wallet"))
        
        if qr_file_id:
            bot.send_photo(call.message.chat.id, qr_file_id, caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "buy_tg":
        user_bal = get_user_balance(user_id)
        cost = 15.0 + PROFIT_MARGIN
        
        if user_bal < cost:
            bot.answer_callback_query(call.id, f"❌ Insufficient Balance! Minimum `{cost}` required.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⌛ Fetching Virtual Number...")
        res = grizzly_get_number()
        
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
                f"💵 **Charged:** `{cost}`\n\n"
                f"👉 Number ko Telegram me daalein aur OTP aane par **'Get OTP Code'** dabayein."
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, f"❌ Server Error: `{res['message']}`", parse_mode="Markdown")

    elif call.data.startswith("get_otp:"):
        _, tx_id, cost = call.data.split(":")
        status = grizzly_get_status(tx_id)
        
        if "STATUS_OK" in status:
            otp_code = status.split(":")[1]
            grizzly_set_status(tx_id, 6) # Complete order
            log_sale(tx_id, user_id, "Telegram", float(cost), "COMPLETED")
            bot.send_message(call.message.chat.id, f"🎉 **Your Telegram OTP Code:** `{otp_code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in status:
            bot.answer_callback_query(call.id, "⌛ SMS nahi aaya abhi tak. Pehle App se OTP bhejein!", show_alert=True)
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
            bot.answer_callback_query(call.id, "❌ Cancel nahi ho saka (Ho sakta hai OTP aa gaya ho).", show_alert=True)

# ==================== DEPOSIT REQUEST SYSTEM ====================
@bot.message_handler(commands=['deposit'])
def handle_deposit_req(message):
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "⚠️ **Wrong Format!**\nUse: `/deposit <Amount> <UTR_ID>`", parse_mode="Markdown")
            return
            
        amount = float(args[1])
        utr_id = args[2]
        user_id = message.from_user.id
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO deposits (user_id, amount, utr_id) VALUES (?, ?, ?)", (user_id, amount, utr_id))
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Deposit Request Sent! ID: `#{req_id}`\nAdmin verification ka intezar karein.", parse_mode="Markdown")
        
        # Send Notification to Admin
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve:{req_id}:{user_id}:{amount}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{req_id}:{user_id}:{amount}")
        )
        
        admin_msg = (
            f"🔔 **New Payment Deposit Request!**\n\n"
            f"🆔 **Request ID:** `#{req_id}`\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"💵 **Amount:** `{amount}`\n"
            f"🔢 **UTR / Tx ID:** `{utr_id}`"
        )
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=admin_markup)

    except Exception as e:
        bot.reply_to(message, f"❌ Error processing request: {e}")

# ==================== ADMIN PANEL (`/admin`) ====================
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
        types.InlineKeyboardButton("➕ Direct Add Balance", callback_data="admin_manual_add")
    )

    text = (
        f"⚙️ **Admin Control Panel** ⚙️\n\n"
        f"📊 **Sales Analytics:**\n"
        f"• Total Users: `{users}`\n"
        f"• Completed Sales: `{orders}`\n"
        f"• Total Revenue: `{revenue:.2f}`\n\n"
        f"💳 **Grizzly API Balance:** `{g_bal_str}` USD/RUB\n"
        f"📌 **Current Support:** `@{get_setting('support_user')}`\n"
        f"🏦 **Current UPI ID:** `{get_setting('upi_id')}`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# ==================== ADMIN CALLBACK HANDLERS ====================
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
        
        bot.edit_message_text(f"✅ Deposit Request `#{req_id}` APPROVED! `{amt}` added to User `{u_id}`.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, f"🎉 **Deposit Approved!** `{amt}` balance credited to your account.", parse_mode="Markdown")

    elif call.data.startswith("admin_reject:"):
        _, req_id, u_id, amt = call.data.split(":")
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        
        bot.edit_message_text(f"❌ Deposit Request `#{req_id}` REJECTED.", call.message.chat.id, call.message.message_id)
        bot.send_message(int(u_id), f"❌ **Deposit Request Rejected.** Contact Support for help.", parse_mode="Markdown")

    elif call.data == "admin_set_qr":
        user_states[ADMIN_ID] = "WAITING_FOR_QR"
        bot.send_message(ADMIN_ID, "📸 Send Payment QR Code Photo in chat now:")

    elif call.data == "admin_set_upi":
        user_states[ADMIN_ID] = "WAITING_FOR_UPI"
        bot.send_message(ADMIN_ID, "🏷️ Send new UPI ID text (e.g. `paytm@upi`):")

    elif call.data == "admin_set_support":
        user_states[ADMIN_ID] = "WAITING_FOR_SUPPORT"
        bot.send_message(ADMIN_ID, "💬 Send Support Telegram Username (without `@`):")

    elif call.data == "admin_manual_add":
        bot.send_message(ADMIN_ID, "➕ Send command in format:\n`/addbalance <USER_ID> <AMOUNT>`", parse_mode="Markdown")

# ==================== ADMIN STATE/INPUT HANDLER ====================
@bot.message_handler(content_types=['photo', 'text'])
def handle_admin_inputs(message):
    if message.from_user.id != ADMIN_ID:
        return

    state = user_states.get(ADMIN_ID)
    
    if state == "WAITING_FOR_QR" and message.photo:
        file_id = message.photo[-1].file_id
        set_setting("qr_file_id", file_id)
        user_states[ADMIN_ID] = None
        bot.reply_to(message, "✅ **Payment QR Code Updated Successfully!**", parse_mode="Markdown")

    elif state == "WAITING_FOR_UPI" and message.text:
        set_setting("upi_id", message.text.strip())
        user_states[ADMIN_ID] = None
        bot.reply_to(message, f"✅ **UPI ID Updated to:** `{message.text.strip()}`", parse_mode="Markdown")

    elif state == "WAITING_FOR_SUPPORT" and message.text:
        username = message.text.strip().replace("@", "")
        set_setting("support_user", username)
        user_states[ADMIN_ID] = None
        bot.reply_to(message, f"✅ **Support Username Updated to:** `@{username}`", parse_mode="Markdown")

@bot.message_handler(commands=['addbalance'])
def manual_add_balance(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        target = int(args[1])
        amt = float(args[2])
        update_user_balance(target, amt)
        bot.reply_to(message, f"✅ Added `{amt}` to `{target}`.", parse_mode="Markdown")
        bot.send_message(target, f"🎉 **Balance Added!** `{amt}` credited by Admin.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Format: `/addbalance USER_ID AMOUNT`")

# ==================== START BOT ====================
if __name__ == "__main__":
    print("Bot with Flask Web Server & Admin Panel Started...")
    bot.infinity_polling()
