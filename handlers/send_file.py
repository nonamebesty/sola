# (c) @JAsuran

import asyncio
from configs import Config
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from handlers.helpers import str_to_b64


async def reply_forward(message: Message, file_id: int):
    try:
        #Asuran
        # get media type
        media = message.document or message.video or message.audio or message.photo
        # get file name
        file_name = media.file_name if media.file_name else ""
        # get caption (if any)
        caption = message.caption if media.file_name else ""
        await message.reply_text(
            f"**Files will be Deleted After 1 min**\n\n"
            f"**__To Retrive the Stored File, just again open the link!__**\n\n"
            f"**{caption}\n\nLink:** https://telegram.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(str(file_id))}",
            disable_web_page_preview=True, quote=True)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await reply_forward(message, file_id)


async def media_forward(bot: Client, user_id: int, file_id: int):
    try:
        if Config.FORWARD_AS_COPY is True:
            return await bot.copy_message(chat_id=user_id, from_chat_id=Config.DB_CHANNEL,
                                          message_id=file_id)
        elif Config.FORWARD_AS_COPY is False:
            return await bot.forward_messages(chat_id=user_id, from_chat_id=Config.DB_CHANNEL,
                                              message_ids=file_id)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return media_forward(bot, user_id, file_id)
        await message.delete()
    
async def send_media_and_reply(bot: Client, user_id: int, file_id: int):
    sent_message = await media_forward(bot, user_id, file_id)
    await reply_forward(message=sent_message, file_id=file_id)
    asyncio.create_task(delete_after_delay(sent_message, 60))

async def delete_after_delay(message, delay):
    await asyncio.sleep(delay)
    try:
        await sent_message.delete()
