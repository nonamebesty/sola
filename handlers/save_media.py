# (c) @JAsuran

import asyncio
from configs import Config
from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.errors import FloodWait
from handlers.helpers import str_to_b64
#from configs import *
#from short import get_short
#import requests


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
    # https://stackoverflow.com/a/49361727/4723940
    # 2**10 = 1024
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
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]
                    ]
                )
            )
        return await forward_to_channel(bot, message, editable)

import asyncio
import traceback
from configs import Config
from pyrogram.types import Message
from pyrogram import Client # Ensure Client is imported
from handlers.helpers import str_to_b64 # Ensure str_to_b64 is imported

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    print(f"--- [DEBUG] Entering save_batch_media_in_channel for user {editable.chat.id} ---")
    print(f"--- [DEBUG] Messages IDs to process: {message_ids} ---")

    try:
        message_ids_in_db = [] # This will store the IDs of messages *after* they are forwarded to DB_CHANNEL

        # Ensure DB_CHANNEL is correctly configured
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            print("--- [ERROR] Config.DB_CHANNEL is not set! ---")
            return

        # Fetch original messages and forward them
        # Using get_messages on user chat to ensure we have the actual message objects
        original_messages = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)
        
        if not original_messages:
            await editable.edit("No original messages found to save for batch. It might be an internal error.")
            print(f"--- [ERROR] No original messages found for IDs: {message_ids} ---")
            return

        for msg in original_messages:
            try:
                # Try to forward each message
                sent_message = await msg.forward(chat_id=Config.DB_CHANNEL)
                if sent_message:
                    message_ids_in_db.append(str(sent_message.id))
                    print(f"--- [DEBUG] Forwarded message {msg.id} to DB_CHANNEL as {sent_message.id} ---")
                    await asyncio.sleep(0.5) # Small delay to avoid hitting flood limits
                else:
                    # This branch is usually not hit, as forward would raise an exception on failure
                    print(f"--- [WARNING] Forwarding failed for message {msg.id} (returned None) ---")
                    await editable.edit(f"Failed to forward message {msg.id} to the database channel. Please check bot permissions and DB_CHANNEL configuration.")
                    return # Stop processing the batch if one message fails
            except Exception as e:
                print(f"--- [ERROR] Failed to forward message {msg.id}: {e} ---")
                await editable.edit(f"Failed to forward message {msg.id} to the database channel due to an error: `{e}`. Please check bot permissions and DB_CHANNEL configuration.")
                return # Stop processing the batch if any message fails

        # If no messages were successfully forwarded
        if not message_ids_in_db:
            await editable.edit("No files were successfully saved to the database channel for the batch. This could be a permission issue.")
            print("--- [ERROR] No message IDs collected in DB_CHANNEL ---")
            return
import asyncio
import traceback
from configs import Config
from pyrogram.types import Message
from pyrogram import Client
from handlers.helpers import str_to_b64

# Assuming forward_to_channel is defined as in your original script

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    """
    Saves a batch of media to the DB_CHANNEL, handling potential flood waits for each file.
    """
    print(f"--- [DEBUG] Entering save_batch_media_in_channel for user {editable.chat.id} ---")
    print(f"--- [DEBUG] Messages IDs to process: {message_ids} ---")

    try:
        message_ids_in_db = []

        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            print("--- [ERROR] Config.DB_CHANNEL is not set! ---")
            return

        original_messages = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)
        
        if not original_messages:
            await editable.edit("Could not fetch the messages to save. Please try again.")
            print(f"--- [ERROR] No original messages found for IDs: {message_ids} ---")
            return

        for msg in original_messages:
            # FIX: Use the robust `forward_to_channel` helper to handle FloodWait automatically.
            sent_message = await forward_to_channel(bot, msg, editable)
            
            if sent_message:
                message_ids_in_db.append(str(sent_message.id))
                print(f"--- [DEBUG] Forwarded message {msg.id} to DB_CHANNEL as {sent_message.id} ---")
                # FIX: Removed the unnecessary asyncio.sleep(0.5) as `forward_to_channel` handles waits.
            else:
                # This case might occur if forward_to_channel is modified to return None on persistent failure.
                print(f"--- [WARNING] Forwarding failed for message {msg.id} and was skipped. ---")
                await editable.edit(f"Failed to save message {msg.id}. Skipping this file and continuing...")
                

        if not message_ids_in_db:
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel.")
            print("--- [ERROR] No message IDs were collected in DB_CHANNEL after processing the batch. ---")
            return

        message_ids_str = " ".join(message_ids_in_db)
        print(f"--- [DEBUG] Batch manifest string: '{message_ids_str}' ---")

        saved_batch_manifest_message = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
            text=message_ids_str,
            disable_web_page_preview=True
        )
        print(f"--- [DEBUG] Batch manifest message ID in DB_CHANNEL: {saved_batch_manifest_message.id} ---")

        # FIX: Standardized share link format.
        share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(str(saved_batch_manifest_message.id))}"
        print(f"--- [DEBUG] Generated share link: {share_link} ---")

        await editable.edit(
            f"**Successfully saved {len(message_ids_in_db)} files!**\n\nHere is your shareable link:\n{share_link}",
            disable_web_page_preview=True
        )
        print(f"--- [DEBUG] Successfully sent batch link to user {editable.chat.id} ---")

    except Exception as err:
        error_message = f"An unexpected error occurred during batch saving: `{err}`"
        print(f"--- [CRITICAL ERROR] {error_message} ---")
        traceback.print_exc()
        try:
            await editable.edit(error_message + "\n\nPlease contact support.")
        except Exception as e:
            print(f"--- [ERROR] Could not edit user message to show the final error: {e} ---")

# Assuming other necessary imports and helper functions are present

async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    """
    Saves a single media file to the DB_CHANNEL, handling different media types and captions correctly.
    """
    try:
        # FIX: Use the `forward_to_channel` helper for DRY principle and robust FloodWait handling.
        forwarded_msg = await forward_to_channel(bot, message, editable)
        if not forwarded_msg:
            # This will happen if forwarding fails permanently.
            await editable.edit("Failed to save the file to the database channel. Please try again later.")
            return
            
        file_er_id = str(forwarded_msg.id)
        
        # Also send a reply in the DB channel for tracking.
        await forwarded_msg.reply_text(
            f"#PRIVATE_FILE:\n\nSaved by: [{message.from_user.first_name}](tg://user?id={message.from_user.id})",
            disable_web_page_preview=True
        )

        # --- Safely get media properties ---
        media = message.document or message.video or message.audio or message.photo
        file_size = humanbytes(getattr(media, 'file_size', 0))

        # FIX: Correctly and safely get file duration ONLY for video/audio.
        duration_str = ""
        if message.video or message.audio:
            media_with_duration = message.video or message.audio
            duration_in_ms = media_with_duration.duration * 1000
            duration_str = f"[⏰ {TimeFormatter(duration_in_ms)}]"

        # FIX: Corrected caption logic. Prefers the file's own caption.
        # If you want to allow overriding with text, the logic can be adjusted.
        caption = message.caption if message.caption else ""
        
        # FIX: Standardize share link to use the bot's username.
        share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(file_er_id)}"

        # Build the final reply text
        reply_text = f"**{caption}**\n\n**Size:** {file_size} {duration_str}\n\n**Link:** {share_link}"

        await editable.edit(
            text=reply_text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Open Link", url=share_link)],
                    [InlineKeyboardButton("Bots Channel", url="https://telegram.me/As_botzz"),
                     InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu")]
                ]
            ),
            disable_web_page_preview=True
        )

    except Exception as err:
        # The `forward_to_channel` handles FloodWait, so this catches other errors.
        await editable.edit(f"Something Went Wrong!\n\n**Error:** `{err}`")
        await bot.send_message(
            chat_id=int(Config.LOG_CHANNEL),
            text="#ERROR_TRACEBACK:\n"
                 f"Got Error from `{str(editable.chat.id)}` !!\n\n"
                 f"**Traceback:** `{err}`",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]
                ]
            )
        )
