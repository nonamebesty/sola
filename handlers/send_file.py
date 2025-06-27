# (c) @JAsuran

import asyncio
from configs import Config
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from handlers.helpers import str_to_b64
from handlers.save_media import TimeFormatter

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


async def reply_forward(message: Message, file_id: int):
    try:
        #Asuran
        # get media type
        media = message.document or message.video or message.audio or message.photo
        media1 = message.video or message.audio
        # get file name
        file_name = media.file_name if media.file_name else ""
        file_size = humanbytes(media.file_size) if media.file_size else "N/A"
        # get file duration
        duration = TimeFormatter(media1.duration * 1000)
        # get caption (if any)

        #caption = message.caption if media.file_name else ""
        
        caption = (message.text.split(" ", 1)[1] if len(message.text.split(" ", 1)) > 1 else None)
        
        await message.reply_text(
            f"**Files will be Deleted After 15 min**\n\n"
            f"**__To Retrive the Stored File, just again open the link!__**\n\n"
            f"**{caption} ~ [⏰ {duration}]\n\n📤 Size: {file_size}\n\n🎫 Quality: All\n\n🎧 Audio : Tamil\n\nLink:** https://nammatvserial.jasurun.workers.dev/?start=JAsuran_{str_to_b64(str(file_id))}",
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
    #await reply_forward(message=sent_message, file_id=file_id)
    asyncio.create_task(delete_after_delay(sent_message, 900))

async def delete_after_delay(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception as e:
        print(f"Error deleting message {sent_message.message_id}: {e}")

