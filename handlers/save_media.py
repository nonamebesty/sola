# (c) @JAsuran

import asyncio
import traceback
from configs import Config
from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.errors import FloodWait
from handlers.helpers import str_to_b64

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + " days, ") if days else "") + \
        ((str(hours) + " hrs, ") if hours else "") + \
        ((str(minutes) + " min, ") if minutes else "") + \
        ((str(seconds) + " sec, ") if seconds else "") + \
        ((str(milliseconds) + " millisec, ") if milliseconds else "")
    return tmp[:-2]

def humanbytes(size):
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

async def forward_to_channel(bot: Client, message: Message, editable: Message):
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
        if sl.value > 45:
            await asyncio.sleep(sl.value)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FloodWait:\nGot FloodWait of `{str(sl.value)}s` from `{str(editable.chat.id)}` !!",
                disable_web_page_preview=True
            )
        return await forward_to_channel(bot, message, editable)
    except Exception as e:
        print(f"Error forwarding message: {e}")
        return None

async def save_media_in_channel(bot: Client, editable: Message, message: Message):
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
        await editable.edit(f"Error: {err}")

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL.")
            return

        message_ids_str = ""
        file_names_list = []
        
        messages_to_process = []
        for msg_id in message_ids:
            try:
                msg = await bot.get_messages(chat_id=editable.chat.id, message_ids=msg_id)
                if msg and msg.media:
                    messages_to_process.append(msg)
            except Exception as e:
                print(f"Error fetching message {msg_id}: {e}")

        if not messages_to_process:
            await editable.edit("No valid media files found in the batch.")
            return
            
        await editable.edit(f"Processing {len(messages_to_process)} files... ⏳")

        for message in messages_to_process:
            # --- NAME EXTRACTION LOGIC ---
            media_name = "Unknown File"
            if message.caption:
                media_name = message.caption.splitlines()[0]
            elif message.document and message.document.file_name:
                media_name = message.document.file_name
            elif message.video and message.video.file_name:
                media_name = message.video.file_name
            elif message.audio and message.audio.file_name:
                media_name = message.audio.file_name
            
            # TRUNCATE NAME IF TOO LONG
            if len(media_name) > 30:
                media_name = media_name[:30] + "..."
            # -----------------------------

            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                continue
            
            # Add to list ONLY if forward was successful
            # WE USE BACKTICKS (`) TO PREVENT MARKDOWN ERRORS
            file_names_list.append(f"**{len(file_names_list) + 1}.** `{media_name}`")
            
            message_ids_str += f"{str(sent_message.id)} "
            await asyncio.sleep(2) 

        if not message_ids_str.strip():
            await editable.edit("Failed to save files.")
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

        # --- FINAL TEXT GENERATION ---
        files_summary = "\n".join(file_names_list)
        
        final_text = (
            f"**Batch Link Created!** ✅\n\n"
            f"{files_summary}\n\n"
            f"**Link:** {share_link}"
        )
        
        # Safety Check for Telegram Message Limit (4096 chars)
        if len(final_text) > 4000:
             final_text = (
                f"**Batch Link Created!** ✅\n\n"
                f"__List contains {len(file_names_list)} files.__\n\n"
                f"**Link:** {share_link}"
            )
        # -----------------------------

        await editable.edit(
            final_text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )
        
    except Exception as err:
        traceback.print_exc()
        await editable.edit(f"Error: {err}")
