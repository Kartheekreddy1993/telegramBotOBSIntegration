import os
import json
import time
import logging
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# === CONFIG ===
with open("config.json", "r") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
VIDEO_FOLDERS = config["VIDEO_FOLDER"]
NOTEPAD_FILE = config["NOTEPAD_FILE"]
FILES_PER_PAGE = 75
RATE_LIMIT_SECONDS = config["TIME_LIMIT"]
USER_RATE_LIMITS = {}

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_actions.log"), logging.StreamHandler()]
)

# === Rate limit ===
def rate_limit_start(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        now = time.time()
        last_time = USER_RATE_LIMITS.get(user_id, 0)
        if now - last_time < RATE_LIMIT_SECONDS:
            remaining = int(RATE_LIMIT_SECONDS - (now - last_time))
            minutes, seconds = divmod(remaining, 60)
            await update.message.reply_text(f"⏳ You can use /start again in {minutes}m {seconds}s.")
            return
        USER_RATE_LIMITS[user_id] = now
        return await func(update, context)
    return wrapper

# === /start ===
@rate_limit_start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logging.info(f"User {user.id} ({user.full_name}) used /start")
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton(f"📁 {os.path.basename(folder)}", callback_data=f"folder_{i}")]
        for i, folder in enumerate(VIDEO_FOLDERS)
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📂 Select a folder to browse:", reply_markup=markup)

# === Get video files from one folder ===
def get_videos_from_folder(folder):
    return [
        {"name": f, "path": os.path.join(folder, f), "folder": folder}
        for f in os.listdir(folder) if f.endswith(('.mp4', '.mkv'))
    ]

# === send a file page ===
async def send_file_page(update_or_query, context, page):
    video_files = context.user_data.get("video_files", [])
    search_active = "search" in context.user_data
    sort = context.user_data.get("sort", "az")

    if sort == "az":
        video_files.sort(key=lambda x: x["name"])
    elif sort == "za":
        video_files.sort(key=lambda x: x["name"], reverse=True)
    elif sort == "new":
        video_files.sort(key=lambda x: os.path.getmtime(x["path"]), reverse=True)
    elif sort == "old":
        video_files.sort(key=lambda x: os.path.getmtime(x["path"]))

    total_files = len(video_files)
    total_pages = (total_files - 1) // FILES_PER_PAGE + 1
    start_idx = page * FILES_PER_PAGE
    end_idx = min(start_idx + FILES_PER_PAGE, total_files)

    keyboard = []
    for i in range(start_idx, end_idx):
        file = video_files[i]
        label = f"{file['name']} ({os.path.basename(file['folder'])})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"file_{i}")])

    keyboard.append([
        InlineKeyboardButton("🔼 A-Z", callback_data="sort_az"),
        InlineKeyboardButton("🔽 Z-A", callback_data="sort_za"),
        InlineKeyboardButton("🆕 Newest", callback_data="sort_new"),
        InlineKeyboardButton("📁 Oldest", callback_data="sort_old")
    ])
    if search_active:
        keyboard.append([InlineKeyboardButton("❌ Clear Search", callback_data="clear_search")])

    page_buttons = [
        InlineKeyboardButton(str(p+1), callback_data=f"page_{p}")
        for p in range(max(0, page-2), min(total_pages, page+3))
    ]
    keyboard.append(page_buttons)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ⏭️", callback_data=f"page_{page+1}"))
    nav_buttons.append(InlineKeyboardButton("🔁 Refresh", callback_data=f"refresh_{page}"))
    keyboard.append(nav_buttons)

    title = f"🎮 Files (Page {page+1}/{total_pages})"
    if search_active:
        title += f"\n🔍 Searching: '{context.user_data['search']}'"

    markup = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(title, reply_markup=markup)
    else:
        await update_or_query.edit_message_text(title, reply_markup=markup)

    context.user_data["page"] = page

# === /search ===
@rate_limit_start
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/search keyword`", parse_mode='Markdown')
        return

    keyword = " ".join(context.args).lower()
    matching_files = []

    for folder in VIDEO_FOLDERS:
        try:
            for f in os.listdir(folder):
                if f.endswith(('.mp4', '.mkv')) and keyword in f.lower():
                    matching_files.append({
                        "name": f,
                        "path": os.path.join(folder, f),
                        "folder": folder
                    })
        except Exception as e:
            logging.error(f"Error accessing folder {folder}: {e}")

    if not matching_files:
        await update.message.reply_text("🔍 No matching files found.")
        return

    context.user_data["video_files"] = matching_files
    context.user_data["search"] = keyword
    context.user_data["sort"] = "az"
    context.user_data["page"] = 0
    context.user_data.pop("selected_folder", None)

    await send_file_page(update, context, 0)

# === /list ===
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(NOTEPAD_FILE):
        with open(NOTEPAD_FILE, "r") as f:
            content = f.read()
        if content:
            await update.message.reply_text(f"📄 Songs IN QUEUE\n```{content}```", parse_mode='Markdown')
        else:
            await update.message.reply_text("📄 Queue is empty.")
    else:
        await update.message.reply_text("📄 Notepad file not found.")

# === Callback ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("folder_"):
        index = int(data.split("_")[1])
        selected_folder = VIDEO_FOLDERS[index]
        context.user_data["selected_folder"] = selected_folder
        context.user_data["video_files"] = get_videos_from_folder(selected_folder)
        context.user_data["sort"] = "az"
        context.user_data["page"] = 0
        await send_file_page(query, context, 0)

    elif data.startswith("file_"):
        index = int(data.split("_")[1])
        file = context.user_data["video_files"][index]
        with open(NOTEPAD_FILE, "a") as f:
            f.write(file["path"] + "\n")
        await query.edit_message_text(f"✅ Appended:\n{file['name']}")

    elif data.startswith("page_"):
        await send_file_page(query, context, int(data.split("_")[1]))
    elif data.startswith("refresh_"):
        await send_file_page(query, context, int(data.split("_")[1]))
    elif data.startswith("sort_"):
        context.user_data["sort"] = data.split("_")[1]
        await send_file_page(query, context, context.user_data.get("page", 0))
    elif data == "clear_search":
        folder = context.user_data.get("selected_folder")
        if folder:
            context.user_data["video_files"] = get_videos_from_folder(folder)
        context.user_data.pop("search", None)
        context.user_data["sort"] = "az"
        context.user_data["page"] = 0
        await send_file_page(query, context, 0)

# === MAIN ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()