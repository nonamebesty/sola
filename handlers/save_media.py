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

        # Create a single message in DB_CHANNEL with all the new message IDs
        message_ids_str = " ".join(message_ids_in_db)
        print(f"--- [DEBUG] Batch manifest string: '{message_ids_str}' ---")

        saved_batch_manifest_message = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
            text=message_ids_str,
            disable_web_page_preview=True
        )
        print(f"--- [DEBUG] Batch manifest message ID in DB_CHANNEL: {saved_batch_manifest_message.id} ---")

        # Generate the shareable link for the manifest message
        share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(str(saved_batch_manifest_message.id))}"
        print(f"--- [DEBUG] Generated share link: {share_link} ---")

        # Edit the original message to the user with the final link
        await editable.edit(
            f"**Your batch of {len(message_ids_in_db)} files has been saved!**\n\n**Shareable Link:** {share_link}",
            disable_web_page_preview=True
        )
        print(f"--- [DEBUG] Successfully sent batch link to user {editable.chat.id} ---")

    except Exception as err:
        # Catch any broad errors that might occur during the process
        error_message = f"An unexpected error occurred during batch saving: `{err}`"
        print(f"--- [CRITICAL ERROR] {error_message} ---")
        traceback.print_exc() # Print full traceback to console/logs for detailed debugging
        try:
            await editable.edit(error_message + "\n\nPlease check bot permissions and DB_CHANNEL configuration.")
        except Exception as e:
            print(f"--- [ERROR] Could not edit user message to show error: {e} ---")


async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    try:
        forwarded_msg = await message.forward(Config.DB_CHANNEL)
        file_er_id = str(forwarded_msg.id)
        await forwarded_msg.reply_text(
            f"#PRIVATE_FILE:\n\n[{message.from_user.first_name}](tg://user?id={message.from_user.id}) Got File Link!",
            disable_web_page_preview=True)
        #Asuran
        # get media type
        media = message.document or message.video or message.audio or message.photo
        media1 = message.video or message.audio
        # get file name
        file_name = media.file_name if media.file_name else ""
        # get file duration
        duration = TimeFormatter(media1.duration * 1000)
        
        # get file size
        file_size = humanbytes(media.file_size)
        # get caption (if any)
        caption = (message.text.split(" ", 1)[1] if message.text and len(message.text.split(" ", 1)) > 1 else None)
        caption = message.caption if media.file_name else ""
        share_link = f"https://nammatvserial.jasurun.workers.dev/?start=JAsuran_{str_to_b64(file_er_id)}"
        await editable.edit(
            f"**{caption} - {file_size} [⏰ {duration}]\n\nLink:** {share_link}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/As_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu")]]
            ),
            disable_web_page_preview=True
        )
    except FloodWait as sl:
        if sl.value > 45:
            print(f"Sleep of {sl.value}s caused by FloodWait ...")
            await asyncio.sleep(sl.value)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text="#FloodWait:\n"
                     f"Got FloodWait of `{str(sl.value)}s` from `{str(editable.chat.id)}` !!",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]
                    ]
                )
            )
        await save_media_in_channel(bot, editable, message)
    except Exception as err:
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
