import sqlite3
import requests
import time
import os
import telebot
from telebot import types

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
GRIZZLY_API_KEY = os.getenv("GRIZZLY_API_KEY", "YOUR_GRIZZLY_API_KEY_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))  # Aapka Telegram Numeric ID

# Telegram ke liye Grizzly SMS Service Code (tg = telegram)
SERVICE_CODE = "tg"

# Price setup: Kitne extra paise/profit add karna hai (USD/RUB equivalent ya INR/Points mein)
PROFIT_MARGIN = 5.0  # Misaal ke taur par base price mein +5 add hoga

bot = telebot.TeleBot(BOT_TOKEN)

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
    conn.commit()
    conn.close()

init_db()

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
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# ==================== GRIZZLY SMS API HELPER ====================
GRIZZLY_BASE_URL = "https://api.grizzlysms.com/stubs/handler_api.php"

def grizzly_get_balance():
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getBalance"
        res = requests.get(url, timeout=10).text
        if "ACCESS_BALANCE" in res:
            return float(res.split(":")[1])
        return None
    except Exception as e:
        print(f"Error fetching Grizzly balance: {e}")
        return None

def grizzly_get_number(country_id=0):
    # Country ID 0 = Any/Default
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getNumber&service={SERVICE_CODE}&country={country_id}"
        res = requests.get(url, timeout=10).text
        if "ACCESS_NUMBER" in res:
            parts = res.split(":")
            tx_id = parts[1]
            number = parts[2]
            return {"status": True, "id": tx_id, "number": number}
        else:
            return {"status": False, "message": res}
    except Exception as e:
        return {"status": False, "message": str(e)}

def grizzly_get_status(tx_id):
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=getStatus&id={tx_id}"
        res = requests.get(url, timeout=10).text
        return res
    except Exception as e:
        return f"ERROR: {e}"

def grizzly_set_status(tx_id, status_code):
    # status_code: 8 = Cancel, 6 = Finish
    try:
        url = f"{GRIZZLY_BASE_URL}?api_key={GRIZZLY_API_KEY}&action=setStatus&id={tx_id}&status={status_code}"
        res = requests.get(url, timeout=10).text
        return res
    except Exception as e:
        return f"ERROR: {e}"

# ==================== BOT HANDLERS ====================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_buy = types.InlineKeyboardButton("📱 Buy Telegram Account", callback_data="buy_tg")
    btn_wallet = types.InlineKeyboardButton("💰 Wallet / Balance", callback_data="wallet")
    btn_help = types.InlineKeyboardButton("ℹ️ Help / Support", callback_data="help")
    markup.add(btn_buy, btn_wallet, btn_help)
    
    welcome_text = (
        f"👋 Welcome! **{message.from_user.first_name}**\n\n"
        f"💳 **Your Current Balance:** `{balance}`\n\n"
        f"Is bot se aap Telegram Virtual Accounts ke numbers aur OTP buy kar sakte hain."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    user_id = call.from_user.id
    
    if call.data == "wallet":
        balance = get_user_balance(user_id)
        msg = (
            f"💰 **Wallet Overview**\n\n"
            f"• User ID: `{user_id}`\n"
            f"• Balance: `{balance}`\n\n"
            f"Balance add karne ke liye Admin ko contact karein."
        )
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="home")
        markup.add(btn_back)
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "home":
        balance = get_user_balance(user_id)
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_buy = types.InlineKeyboardButton("📱 Buy Telegram Account", callback_data="buy_tg")
        btn_wallet = types.InlineKeyboardButton("💰 Wallet / Balance", callback_data="wallet")
        btn_help = types.InlineKeyboardButton("ℹ️ Help / Support", callback_data="help")
        markup.add(btn_buy, btn_wallet, btn_help)
        
        bot.edit_message_text(
            f"👋 Main Menu\n\n💳 **Your Balance:** `{balance}`",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    elif call.data == "buy_tg":
        user_bal = get_user_balance(user_id)
        # Base Cost assumption (Aap ise hardcode ya dynamic calculate kar sakte hain)
        cost = 15.0 + PROFIT_MARGIN  
        
        if user_bal < cost:
            bot.answer_callback_query(call.id, f"❌ Insufficient Balance! Minimum `{cost}` required.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⌛ Fetching number from server...")
        
        res = grizzly_get_number()
        if res["status"]:
            tx_id = res["id"]
            phone_num = res["number"]
            
            # Deduct balance from user
            update_user_balance(user_id, -cost)
            
            markup = types.InlineKeyboardMarkup()
            btn_check = types.InlineKeyboardButton("🔄 Get OTP / Status", callback_data=f"get_otp:{tx_id}")
            btn_cancel = types.InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel:{tx_id}:{cost}")
            markup.add(btn_check)
            markup.add(btn_cancel)
            
            msg = (
                f"✅ **Number Purchased Successfully!**\n\n"
                f"📞 **Phone Number:** `{phone_num}`\n"
                f"🆔 **Order ID:** `{tx_id}`\n\n"
                f"1️⃣ Is number ko Telegram par enter karein.\n"
                f"2️⃣ Click **'Get OTP'** button below when SMS is sent."
            )
            bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, f"❌ Error ordering number: `{res['message']}`", parse_mode="Markdown")

    elif call.data.startswith("get_otp:"):
        tx_id = call.data.split(":")[1]
        status = grizzly_get_status(tx_id)
        
        if "STATUS_OK" in status:
            otp_code = status.split(":")[1]
            # Complete the transaction on Grizzly
            grizzly_set_status(tx_id, 6)
            bot.send_message(call.message.chat.id, f"🎉 **Your Telegram OTP Code is:** `{otp_code}`", parse_mode="Markdown")
        elif "STATUS_WAIT_CODE" in status:
            bot.answer_callback_query(call.id, "⌛ Waiting for SMS... Send OTP from Telegram app first then check again.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"Status: {status}", show_alert=True)

    elif call.data.startswith("cancel:"):
        _, tx_id, refund_amt = call.data.split(":")
        refund_amt = float(refund_amt)
        
        cancel_res = grizzly_set_status(tx_id, 8)
        if "ACCESS_CANCEL" in cancel_res or "ACCESS_OK" in cancel_res or "STATUS_CANCEL" in cancel_res:
            update_user_balance(user_id, refund_amt)
            bot.edit_message_text("❌ **Order Cancelled!** Balance has been refunded to your wallet.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, f"Cannot cancel yet: {cancel_res}", show_alert=True)

    elif call.data == "help":
        bot.answer_callback_query(call.id, "Support: Contact Admin for balance add / queries.", show_alert=True)

# ==================== ADMIN COMMANDS ====================
@bot.message_handler(commands=['addbalance'])
def add_balance_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        # Command format: /addbalance USER_ID AMOUNT
        args = message.text.split()
        target_user = int(args[1])
        amount = float(args[2])
        
        update_user_balance(target_user, amount)
        bot.reply_to(message, f"✅ Successfully added `{amount}` balance to User `{target_user}`.", parse_mode="Markdown")
        
        # Notify User
        try:
            bot.send_message(target_user, f"🎉 **Balance Added!** `{amount}` credited to your wallet by Admin.", parse_mode="Markdown")
        except:
            pass
    except Exception as e:
        bot.reply_to(message, "❌ **Invalid Format!**\nUse: `/addbalance <USER_ID> <AMOUNT>`", parse_mode="Markdown")

@bot.message_handler(commands=['checkgrizzly'])
def check_grizzly_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    bal = grizzly_get_balance()
    if bal is not None:
        bot.reply_to(message, f"💳 **Grizzly SMS Main Account Balance:** `{bal}` USD/RUB", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Failed to fetch Grizzly balance. Check API Key.")

# ==================== START BOT ====================
if __name__ == "__main__":
    print("Bot is starting...")
    bot.infinity_polling()