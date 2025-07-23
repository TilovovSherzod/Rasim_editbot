import os
import math
from telegram import Update, ReplyKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
from io import BytesIO
from suzlar import texts
from dotenv import load_dotenv

load_dotenv()

user_data = {}
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

def get_lang(context):
    return context.user_data.get('lang', 'uz')

def get_text(context, key, **kwargs):
    lang = get_lang(context)
    return texts[lang][key].format(**kwargs)

def get_buttons(context):
    lang = get_lang(context)
    return texts[lang]["buttons"]

def best_division(n):
    best_r, best_c = 1, n
    min_diff = n
    for i in range(1, int(math.sqrt(n)) + 1):
        if n % i == 0:
            r, c = i, n // i
            if abs(r - c) < min_diff:
                best_r, best_c = r, c
                min_diff = abs(r - c)
    return best_r, best_c

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup(get_buttons(context), resize_keyboard=True)
    await update.message.reply_text(get_text(context, "start"), reply_markup=markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(context, "help"))

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(context, "about"))

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_text(context, "contact"))

async def suggestion_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = 'suggestion'
    await update.message.reply_text(get_text(context, "send_suggestion"))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    photo = await update.message.photo[-1].get_file()
    photo_bytes = BytesIO()
    await photo.download_to_memory(out=photo_bytes)
    photo_bytes.seek(0)
    user_data[user_id] = {'image': photo_bytes}
    await update.message.reply_text(get_text(context, "image_saved"))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    cleaned_text = text.lower().strip().replace("‑", "-").replace("–", "-").replace("—", "-")

    if context.user_data.get('mode') == 'suggestion':
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"Taklif ({user_id}):\n{text}")
        await update.message.reply_text(get_text(context, "suggestion_thanks"))
        context.user_data['mode'] = None
        return

    if cleaned_text in ["🌐 tilni o'zgartirish", "🌐 tilni o‘zgartirish", "🌐 сменить язык", "🌐 change language"]:
        langs = ['uz', 'ru', 'en']
        current = get_lang(context)
        next_lang = langs[(langs.index(current) + 1) % len(langs)]
        context.user_data['lang'] = next_lang
        await update.message.reply_text(get_text(context, "lang_set"),
                                        reply_markup=ReplyKeyboardMarkup(get_buttons(context), resize_keyboard=True))
        return

    if cleaned_text in ["📐 rasmni bo'lish", "📐 rasmni bo‘lish", "📐 split image", "📐 разделить изображение"]:
        await update.message.reply_text(get_text(context, "enter_split"))
        context.user_data['mode'] = 'split'
        return

    if cleaned_text in ["🖤 oq-qora qilish", "🖤 grayscale", "🖤 чёрно-белое"]:
        await make_grayscale(update, context)
        return

    if cleaned_text in ["✂️ rasmni kesish", "✂️ crop image", "✂️ обрезать изображение"]:
        await ask_crop_size(update, context)
        return

    if cleaned_text in ["🚀 start"]:
        await start(update, context)
        return
    if cleaned_text in ["/help", "🆘 help", "🆘 yordam", "🆘 помощь"]:
        await help_command(update, context)
        return
    if cleaned_text in ["ℹ️ about", "ℹ️ haqida", "ℹ️ о боте"]:
        await about_command(update, context)
        return
    if cleaned_text in ["📞 contact"]:
        await contact_command(update, context)
        return
    if cleaned_text in ["💡 taklif", "💡 предложение", "💡 offer"]:
        await suggestion_command(update, context)
        return

    if context.user_data.get('mode') == 'split':
        await split_image(update, context, cleaned_text)
        context.user_data['mode'] = None
        return

    if context.user_data.get('mode') == 'custom_crop':
        await crop_image_custom(update, context, cleaned_text)
        context.user_data['mode'] = None
        return

    await update.message.reply_text(get_text(context, "unknown"))

async def split_image(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text(get_text(context, "send_photo"))
        return

    if 'x' in text:
        parts = text.replace(' ', '').split('x')
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            await update.message.reply_text(get_text(context, "wrong_format"))
            return
        rows, cols = map(int, parts)
    elif text.isdigit():
        num = int(text)
        if num not in [2, 4, 6, 8, 9, 10]:
            await update.message.reply_text(get_text(context, "only_nums"))
            return
        rows, cols = best_division(num)
    else:
        await update.message.reply_text(get_text(context, "wrong_format"))
        return

    img = Image.open(user_data[user_id]['image']).convert("RGB")
    width, height = img.size
    img = img.crop((0, 0, width - width % cols, height - height % rows))
    tile_width = img.width // cols
    tile_height = img.height // rows
    tiles = []

    for r in range(rows):
        for c in range(cols):
            box = (c * tile_width, r * tile_height, (c + 1) * tile_width, (r + 1) * tile_height)
            tile = img.crop(box)
            buf = BytesIO()
            tile.save(buf, format="JPEG")
            buf.seek(0)
            tiles.append(buf)

    await update.message.reply_text(get_text(context, "split_done", rows=rows, cols=cols, total=rows * cols))
    for i in range(0, len(tiles), 10):
        group = [InputMediaPhoto(t) for t in tiles[i:i + 10]]
        await update.message.reply_media_group(media=group)

async def make_grayscale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text(get_text(context, "send_photo"))
        return
    img = Image.open(user_data[user_id]['image']).convert("L")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    await update.message.reply_photo(photo=buf, caption=get_text(context, "grayscale_done"))

async def ask_crop_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text(get_text(context, "send_photo"))
        return
    img = Image.open(user_data[user_id]['image'])
    await update.message.reply_text(get_text(context, "enter_crop_size", width=img.width, height=img.height))
    context.user_data['mode'] = 'custom_crop'

async def crop_image_custom(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.message.from_user.id
    if user_id not in user_data or 'x' not in text:
        await update.message.reply_text(get_text(context, "wrong_format"))
        return
    try:
        w_crop, h_crop = map(int, text.replace(" ", "").split("x"))
    except:
        await update.message.reply_text(get_text(context, "wrong_format"))
        return

    img = Image.open(user_data[user_id]['image']).convert("RGB")
    if w_crop > img.width or h_crop > img.height:
        await update.message.reply_text(get_text(context, "crop_too_big"))
        return

    left = (img.width - w_crop) // 2
    top = (img.height - h_crop) // 2
    cropped = img.crop((left, top, left + w_crop, top + h_crop))
    buf = BytesIO()
    cropped.save(buf, format="JPEG")
    buf.seek(0)
    await update.message.reply_photo(photo=buf, caption=get_text(context, "crop_done", w=w_crop, h=h_crop))

def main():
    token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("contact", contact_command))
    app.add_handler(CommandHandler("taklif", suggestion_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
