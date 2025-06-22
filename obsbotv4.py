import os
import json
import time
import logging
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)

# === CONFIG ===
with open("config.json", "r") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
VIDEO_FOLDER = config["VIDEO_FOLDER"]
NOTEPAD_FILE = config["NOTEPAD_FILE"]
FILES_PER_PAGE = 75

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_actions.log"),
        logging.StreamHandler()
    ]
)







# === /start command ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logging.info(f"User {user.id} ({user.full_name}) used /start")

    context.user_data.clear()
    context.user_data["video_files"] = [f for f in os.listdir(VIDEO_FOLDER) if f.endswith(('.mp4', '.mkv'))]
    context.user_data["sort"] = "az"
    context.user_data["page"] = 0
    await send_file_page(update, context, 0)

# === send a file page ===
async def send_file_page(update_or_query, context, page):
    video_files = context.user_data.get("video_files", [])
    search_active = "search" in context.user_data
    sort = context.user_data.get("sort", "az")

    if sort == "az":
        video_files.sort()
    elif sort == "za":
        video_files.sort(reverse=True)
    elif sort == "new":
        video_files.sort(key=lambda x: os.path.getmtime(os.path.join(VIDEO_FOLDER, x)), reverse=True)
    elif sort == "old":
        video_files.sort(key=lambda x: os.path.getmtime(os.path.join(VIDEO_FOLDER, x)))

    total_files = len(video_files)
    total_pages = (total_files - 1) // FILES_PER_PAGE + 1
    start_idx = page * FILES_PER_PAGE
    end_idx = min(start_idx + FILES_PER_PAGE, total_files)
    current_files = video_files[start_idx:end_idx]

    keyboard = []
    for i in range(start_idx, end_idx):
        keyboard.append([InlineKeyboardButton(video_files[i], callback_data=f"file_{i}")])

    sort_buttons = [
        InlineKeyboardButton("🔼 A-Z", callback_data="sort_az"),
        InlineKeyboardButton("🔽 Z-A", callback_data="sort_za"),
        InlineKeyboardButton("🆕 Newest", callback_data="sort_new"),
        InlineKeyboardButton("📁 Oldest", callback_data="sort_old")
    ]
    keyboard.append(sort_buttons)
    if search_active:
        keyboard.append([InlineKeyboardButton("❌ Clear Search", callback_data="clear_search")])

    page_buttons = [
        InlineKeyboardButton(str(p+1), callback_data=f"page_{p}")
        for p in range(max(0, page-2), min(total_pages, page+3))
    ]
    keyboard.append(page_buttons)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ⏭️", callback_data=f"page_{page + 1}"))
    nav_buttons.append(InlineKeyboardButton("🔁 Refresh", callback_data=f"refresh_{page}"))
    keyboard.append(nav_buttons)

    title = f"Select a file (Page {page + 1} / {total_pages}):"
    if search_active:
        title += f"\n🔍 Matching: '{context.user_data['search']}'"

    reply_markup = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(title, reply_markup=reply_markup)
    else:
        await update_or_query.edit_message_text(title, reply_markup=reply_markup)

    context.user_data["page"] = page

# === Callback handler ===

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    if data.startswith("file_"):
        index = int(data.split("_")[1])
        file_name = context.user_data["video_files"][index]
        full_path = os.path.join(VIDEO_FOLDER, file_name)

        with open(NOTEPAD_FILE, "a") as f:
            f.write(full_path + "\n")

        logging.info(f"User {user.id} ({user.full_name}) appended file: {file_name}")
        await query.edit_message_text(f"✅ Appended:\n{file_name}")

    elif data.startswith("page_"):
        await send_file_page(query, context, int(data.split("_")[1]))

    elif data.startswith("refresh_"):
        await send_file_page(query, context, int(data.split("_")[1]))

    elif data.startswith("sort_"):
        context.user_data["sort"] = data.split("_")[1]
        await send_file_page(query, context, context.user_data.get("page", 0))

    elif data == "clear_search":
        context.user_data.pop("search", None)
        context.user_data["video_files"] = [f for f in os.listdir(VIDEO_FOLDER) if f.endswith(('.mp4', '.mkv'))]
        context.user_data["sort"] = "az"
        context.user_data["page"] = 0
        logging.info(f"User {user.id} ({user.full_name}) cleared search filter")
        await send_file_page(query, context, 0)

# === /search command ===

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Usage: `/search keyword`", parse_mode='Markdown')
        return

    keyword = " ".join(context.args).lower()
    all_files = [f for f in os.listdir(VIDEO_FOLDER) if f.endswith(('.mp4', '.mkv'))]
    filtered = [f for f in all_files if keyword in f.lower()]

    logging.info(f"User {user.id} ({user.full_name}) searched for: {keyword}")

    if not filtered:
        await update.message.reply_text("🔍 No matching files found.")
        return

    context.user_data["video_files"] = filtered
    context.user_data["search"] = keyword
    context.user_data["sort"] = "az"
    context.user_data["page"] = 0
    await send_file_page(update, context, 0)

# === /list command ===

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logging.info(f"User {user.id} ({user.full_name}) used /list")

    if os.path.exists(NOTEPAD_FILE):
        with open(NOTEPAD_FILE, "r") as f:
            content = f.read()
        if content:
            await update.message.reply_text(f"📄 Songs IN QUEUE\n```{content}```", parse_mode='Markdown')
        else:
            await update.message.reply_text("📄queue is empty.")
    else:
        await update.message.reply_text("📄 Notepad file not found.")

# === MAIN ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()
