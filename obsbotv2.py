import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import time
from datetime import datetime, timedelta

print("please do not close this windows")

# Track last access time per user_id
user_cooldowns = {}
COOLDOWN_SECONDS = 300  # 10 minutes

# === LOAD CONFIG ===
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
VIDEO_FOLDER = config["VIDEO_FOLDER"]
NOTEPAD_FILE = config["NOTEPAD_FILE"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = time.time()

    last_time = user_cooldowns.get(user_id, 0)
    if now - last_time < COOLDOWN_SECONDS:
        wait = int(COOLDOWN_SECONDS - (now - last_time))
        minutes = wait // 60
        seconds = wait % 60
        await update.message.reply_text(
            f"⏳ Please wait {minutes}m {seconds}s before making another request."
        )
        return

    # Update user cooldown time
    user_cooldowns[user_id] = now

    # Proceed with file listing
    video_files = [f for f in os.listdir(VIDEO_FOLDER) if f.endswith(('.mp4', '.mkv'))]

    if not video_files:
        await update.message.reply_text("No MP4 or MKV files found in the folder.")
        return

    keyboard = [[InlineKeyboardButton(f, callback_data=f)] for f in video_files]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select a file to append to notepad:", reply_markup=reply_markup)



async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_file = query.data
    full_path = os.path.join(VIDEO_FOLDER, selected_file)

    with open(NOTEPAD_FILE, 'a', encoding='utf-8') as f:
        f.write(full_path + '\n')

    await query.edit_message_text(text=f"✅ File added:\n`{full_path}`", parse_mode='Markdown')

    with open(NOTEPAD_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    await query.message.reply_text(f"📝 Items In Queue:\n```\n{content}```", parse_mode='Markdown')


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.run_polling()


if __name__ == '__main__':
    main()
