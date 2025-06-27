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

# In handlers/save_media.py

from configs import Config
from pyrogram.types import Message
from pyrogram import Client, enums
from handlers.helpers import str_to_b64
import asyncio

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        message_ids_str = ""
        for message in (await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)):
            # Forward each message to the DB_CHANNEL
            sent_message = await message.forward(chat_id=Config.DB_CHANNEL)
            if sent_message:
                # Append the new message ID to our string
                message_ids_str += f"{str(sent_message.id)} "
                # Small delay to avoid flood waits
                await asyncio.sleep(0.5)
            else:
                # If forwarding fails for any message, abort
                await editable.edit("Failed to save one or more files. Please try again.")
                return

        # We need to save the list of new message IDs in a new message
        # This new message will act as our "batch"
        if message_ids_str != "":
            # Create a new message containing the space-separated IDs
            saved_message = await bot.send_message(
                chat_id=Config.DB_CHANNEL,
                text=message_ids_str,
                disable_web_page_preview=True
            )

            # Generate the shareable link for the "batch" message
            share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(str(saved_message.id))}"
            
            # Edit the user's message with the final link
            await editable.edit(
                f"**Your batch of {len(message_ids)} files has been saved!**\n\n**Shareable Link:** {share_link}",
                disable_web_page_preview=True
            )
        else:
            await editable.edit("Could not save any files. Please try again.")

    except Exception as err:
        await editable.edit(f"An error occurred: {err}")
        print(f"Error in save_batch_media_in_channel: {err}") # For your logs

async def process_batch_after_delay(bot: Client, user_id: int):
    # ...
    print(f"--- Processing for user {user_id} ---") # Add this
    batch_info = user_batch_data.get(user_id)
    # ...
    messages = batch_info["messages"]
    print(f"Collected {len(messages)} messages.") # Add this
    # ...

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        print(f"--- Saving batch with {len(message_ids)} message IDs ---") # Add this
        # ...
        print(f"Forwarded messages and got new IDs: {message_ids_str}") # Add this
        # ...
        print(f"Generated share link: {share_link}") # Add this
except Exception as err:
        # ...

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
