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

# ... (Keep your existing TimeFormatter, humanbytes, forward_to_channel functions here) ...

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL.")
            return

        message_ids_str = ""
        file_names_list = [] # List to store names/captions
        
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
            # --- 1. GET CAPTION OR FILENAME ---
            media_name = ""
            if message.caption:
                # Use the first line of the caption
                media_name = message.caption.splitlines()[0]
                # Truncate if too long (to avoid errors)
                if len(media_name) > 30:
                    media_name = media_name[:30] + "..."
            elif message.document and message.document.file_name:
                media_name = message.document.file_name
            elif message.video and message.video.file_name:
                media_name = message.video.file_name
            elif message.audio and message.audio.file_name:
                media_name = message.audio.file_name
            else:
                media_name = f"File {len(file_names_list) + 1}"
            
            # Add to our list with a number (e.g., "1. Movie Name")
            file_names_list.append(f"**{len(file_names_list) + 1}.** {media_name}")
            # ----------------------------------

            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                continue
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

        # --- 2. CREATE FINAL TEXT WITH NAMES ---
        # Join the list with new lines
        files_summary = "\n".join(file_names_list)
        
        final_text = (
            f"**Batch Link Created!** ✅\n\n"
            f"{files_summary}\n\n"
            f"**Link:** {share_link}"
        )
        
        # Telegram Message Limit Check (4096 chars)
        # If list is too long, we show a simplified version
        if len(final_text) > 4000:
             final_text = (
                f"**Batch Link Created!** ✅\n\n"
                f"__List contains {len(file_names_list)} files.__\n\n"
                f"**Link:** {share_link}"
            )
        # ---------------------------------------

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
        # ... (Your existing error handling) ...
        await editable.edit(f"Error: {err}")
