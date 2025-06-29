# (c) @JAsuran

import asyncio
import traceback
from base64 import urlsafe_b64encode
from asyncio.exceptions import TimeoutError  # NEW: Import for handling ask timeout

from configs import Config
from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.errors import FloodWait

# Assuming Config is set up correctly in configs.py
# Assuming you have a full Client setup elsewhere in your main file.

# --- Helper Functions ---

def str_to_b64(text: str) -> str:
    """Encodes a string to a URL-safe Base64 string."""
    # This helper was imported, so I'm defining it here for a self-contained script.
    return urlsafe_b64encode(text.encode("ascii")).decode("ascii").strip("=")

def TimeFormatter(milliseconds: int) -> str:
    if not milliseconds:
        return "N/A"
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + " days, ") if days else "") + \
        ((str(hours) + " hrs, ") if hours else "") + \
        ((str(minutes) + " min, ") if minutes else "") + \
        ((str(seconds) + " sec, ") if seconds else "") + \
        ((str(milliseconds) + " millisec, ") if milliseconds else "")
    return tmp[:-2] if tmp else "0 sec"

def humanbytes(size):
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

def human_size(bytes, units=[' bytes','KB','MB','GB','TB', 'PB', 'EB']):
    return str(bytes) + units[0] if int(bytes) < 1024 else human_size(int(bytes)>>10, units[1:])

# --- Core Logic Functions ---

async def forward_to_channel(bot: Client, message: Message, editable: Message):
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
        print(f"FloodWait: Got {sl.value}s from {editable.chat.id}")
        if sl.value > 45:
            await asyncio.sleep(sl.value)
            if Config.LOG_CHANNEL:
                await bot.send_message(
                    chat_id=int(Config.LOG_CHANNEL),
                    text=f"#FloodWait:\nGot FloodWait of `{str(sl.value)}s` from `{str(editable.chat.id)}` !!",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]]
                    )
                )
        return await forward_to_channel(bot, message, editable)
    except Exception as e:
        print(f"Error forwarding message: {e}")
        if Config.LOG_CHANNEL:
            # We need to import traceback to use format_exc()
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FORWARD_ERROR:\nError forwarding message for user `{editable.chat.id}`: `{e}`\n\nTraceback:\n`{traceback.format_exc()}`",
                disable_web_page_preview=True
            )
        return None

# --- MODIFIED FUNCTION WITH NEW FEATURE ---
async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    """
    Saves a batch of media, generates a link, AND asks the user for a custom caption.
    """
    try:
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            return

        await editable.edit("Processing batch... Please wait.")
        
        messages_to_process = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)
        valid_messages = [msg for msg in messages_to_process if msg.media]

        if not valid_messages:
            await editable.edit("No valid media files found in the batch to save.")
            return
            
        await editable.edit(f"Saving {len(valid_messages)} files to the database channel... This may take a moment.")

        message_ids_str = ""
        for message in valid_messages:
            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                continue
            message_ids_str += f"{str(sent_message.id)} "
            await asyncio.sleep(2)

        if not message_ids_str.strip():
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel.")
            return

        SaveMessage = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
            text=message_ids_str.strip(),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Delete Batch", callback_data="closeMessage")
            ]])
        )
        share_link = f"https://nammatvserial.jasurun.workers.dev?start=JAsuran_{str_to_b64(str(SaveMessage.id))}"

        # --- NEW: Ask for caption ---
        try:
            caption_message = await bot.ask(
                chat_id=editable.chat.id,
                text="✅ Batch link generated!\n\nPlease send the caption for this batch.\n\nType `/cancel` to skip.",
                timeout=300  # 5-minute timeout
            )
            if caption_message and caption_message.text and caption_message.text.lower() == "/cancel":
                custom_caption = "Batch Files" # Default caption on cancel
                await caption_message.delete()
            elif caption_message and caption_message.text:
                custom_caption = caption_message.text
            else:
                custom_caption = "Batch Files" # Default caption if something else is sent
        except TimeoutError:
            await editable.edit("⚠️ Request timed out. Using default caption.")
            custom_caption = "Batch Files"
        except Exception as e:
            print(f"Caption asking error: {e}")
            custom_caption = "Batch Files" # Fallback caption on error

        # --- NEW: Construct final post with the custom caption ---
        final_text = f"**{custom_caption}**\n\n{share_link}"
        
        await editable.edit(
            text=final_text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )

        if Config.LOG_CHANNEL:
            # Use a more reliable way to get user info if reply_to_message is not available
            user = editable.chat
            log_text = (f"#BATCH_SAVE:\n\n"
                        f"**User:** [{user.first_name or user.title}](tg://user?id={user.id})\n"
                        f"**Caption:** `{custom_caption}`\n"
                        f"Got Batch Link!")
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=log_text,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Link", url=share_link)]])
            )
    except Exception as err:
        error_details = traceback.format_exc()
        await editable.edit(f"Something Went Wrong during batch save!\n\n**Error:** `{err}`")
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(editable.chat.id)}` !!\n\n**Traceback:**\n`{error_details}`",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]]
                )
            )

async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    # This function remains unchanged as the request was for batch files.
    try:
        forwarded_msg = await message.forward(Config.DB_CHANNEL)
        file_er_id = str(forwarded_msg.id)
        
        await forwarded_msg.reply_text(
            f"#PRIVATE_FILE:\n\n[{message.from_user.first_name}](tg://user?id={message.from_user.id}) Got File Link!",
            disable_web_page_preview=True
        )
        
        file_size = "N/A"
        duration_str = ""
        caption = message.caption if message.caption else ""

        media = message.document or message.video or message.audio or message.photo

        if media and hasattr(media, 'file_size') and media.file_size is not None:
            file_size = humanbytes(media.file_size)
        
        if message.video or message.audio:
            media_with_duration = message.video or message.audio
            if media_with_duration and hasattr(media_with_duration, 'duration') and media_with_duration.duration is not None:
                duration_in_ms = media_with_duration.duration * 1000
                duration_str = f"[⏰ {TimeFormatter(duration_in_ms)}]"

        share_link = f"https://nammatvserial.jasurun.workers.dev/?start=JAsuran_{str_to_b64(file_er_id)}"

        reply_text = f"**{caption}**\n\n**Size:** {file_size} {duration_str}\n\n**Link:** {share_link}"

        await editable.edit(
            text=reply_text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )
    except Exception as err:
        error_details = traceback.format_exc()
        await editable.edit(f"Something Went Wrong!\n\n**Error:** `{err}`")
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(editable.chat.id)}` !!\n\n**Traceback:**\n`{error_details}`",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]]
                )
            )

# ---
# You would need to add your Pyrogram Client initialization and message handlers
# below this line for the bot to be fully functional.
# For example:
#
# app = Client("my_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)
#
# @app.on_message(...)
# async def my_handler(client, message):
#     ...
#
# app.run()
# ---
