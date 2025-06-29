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
# Assuming handlers.helpers.str_to_b64 is correctly defined and imported
# For a full self-contained solution, you might want to move b64_to_str here too.
# For now, we assume str_to_b64 is correctly imported and b64_to_str is somewhere else needed for /start.
# If str_to_b64 is your own helper, make sure its dependency 'base64' is imported.

# Your helper functions (TimeFormatter, humanbytes, human_size)
# I'm keeping your original TimeFormatter and humanbytes as they are, but note the humanbytes implementation:
# humanbytes(size): it expects an int and returns a string with 'B' suffix.
# human_size(bytes, units): This is a recursive function, you're not using it.
# Let's streamline to just use humanbytes.

def TimeFormatter(milliseconds: int) -> str:
    # Ensure milliseconds is not None or invalid
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
    return tmp[:-2] if tmp else "0 sec" # Added check for empty string

def humanbytes(size):
    if not size:
        return "0 B" # Return "0 B" for consistency
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

# human_size is not used in the provided snippet, so keeping it as is or removing it
def human_size(bytes, units=[' bytes','KB','MB','GB','TB', 'PB', 'EB']):
    """ Returns a human readable string representation of bytes """
    return str(bytes) + units[0] if int(bytes) < 1024 else human_size(int(bytes)>>10, units[1:])
    
async def forward_to_channel(bot: Client, message: Message, editable: Message):
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
        # Adjusted FloodWait handling as per previous discussions
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
        # Only log if Config.LOG_CHANNEL is set, avoid error if not
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FORWARD_ERROR:\nError forwarding message for user `{editable.chat.id}`: `{e}`\n\nTraceback:\n`{traceback.format_exc()}`",
                disable_web_page_preview=True
            )
        return None # Return None if forwarding failed

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            return

        message_ids_str = ""
        # Fetch messages first to handle potential issues before forwarding loop
        messages_to_process = []
        for msg_id in message_ids:
            try:
                msg = await bot.get_messages(chat_id=editable.chat.id, message_ids=msg_id)
                if msg and msg.media: # Only add if it's a valid media message
                    messages_to_process.append(msg)
                else:
                    print(f"Skipping invalid or non-media message ID {msg_id} in batch.")
            except Exception as e:
                print(f"Error fetching message {msg_id} for batch: {e}")
                # Optionally, notify user or log specific message fetch failures

        if not messages_to_process:
            await editable.edit("No valid media files found in the batch to save.")
            return
            
        await editable.edit(f"Saving {len(messages_to_process)} files to the database channel... This may take a moment.")

        for message in messages_to_process:
            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                # If forwarding failed, log it and continue to next message
                print(f"Failed to forward message {message.id} for user {editable.chat.id}. Skipping...")
                continue
            message_ids_str += f"{str(sent_message.id)} "
            await asyncio.sleep(2) # Small delay to avoid flood waits

        if not message_ids_str.strip(): # Check if any messages were successfully forwarded
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel or no media was found.")
            return

        SaveMessage = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
            text=message_ids_str.strip(), # Remove trailing space
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Delete Batch", callback_data="closeMessage") # Make sure "closeMessage" handler exists
            ]])
        )
        share_link = f"https://nammatvserial.jasurun.workers.dev?start=JAsuran_{str_to_b64(str(SaveMessage.id))}"

        await editable.edit(
            f"**{share_link}**", # More descriptive text
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )
        if Config.LOG_CHANNEL: # Only send to log channel if it's configured
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#BATCH_SAVE:\n\n[{editable.reply_to_message.from_user.first_name if editable.reply_to_message else 'Unknown User'}](tg://user?id={editable.reply_to_message.from_user.id if editable.reply_to_message else 'unknown_id'}) Got Batch Link!",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Link", url=share_link)]])
            )
    except Exception as err:
        import traceback # Ensure traceback is imported
        error_details = traceback.format_exc() # Get full traceback
        await editable.edit(f"Something Went Wrong during batch save!\n\n**Error:** `{err}`")
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(editable.chat.id)}` !!\n\n**Traceback:**\n`{error_details}`", # Use full traceback
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]
                    ]
                )
            )


async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    try:
        # Forward the message and get its ID in the DB channel
        forwarded_msg = await message.forward(Config.DB_CHANNEL)
        file_er_id = str(forwarded_msg.id)
        
        await forwarded_msg.reply_text(
            f"#PRIVATE_FILE:\n\n[{message.from_user.first_name}](tg://user?id={message.from_user.id}) Got File Link!",
            disable_web_page_preview=True
        )
        
        # --- Initialize variables before use ---
        file_size = "N/A"
        duration_str = ""
        caption = message.caption if message.caption else "" # Get caption early

        # Get the media object (document, video, audio, photo)
        media = message.document or message.video or message.audio or message.photo

        # Get file size if media exists
        if media and hasattr(media, 'file_size') and media.file_size is not None:
            file_size = humanbytes(media.file_size)
        
        # Get duration string if it's a video or audio
        if message.video or message.audio:
            media_with_duration = message.video or message.audio
            if media_with_duration and hasattr(media_with_duration, 'duration') and media_with_duration.duration is not None:
                duration_in_ms = media_with_duration.duration * 1000
                duration_str = f"[⏰ {TimeFormatter(duration_in_ms)}]"
        # --- End of initialization and variable assignment ---

        share_link = f"https://nammatvserial.jasurun.workers.dev/?start=JAsuran_{str_to_b64(file_er_id)}"

        # Construct reply_text using the now-defined variables
        reply_text = f"**{caption}**\n\n**Size:** {file_size} {duration_str}\n\n**Link:**{share_link}"

        await editable.edit(
            text=reply_text, # Use the constructed reply_text
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )
    except FloodWait as sl:
        # The FloodWait block here is for issues during 'await editable.edit' or final steps
        # The 'await save_media_in_channel(bot, editable, message)' might cause infinite loop
        # if the same error re-occurs. Better to just wait and log.
        print(f"FloodWait on final edit: {sl.value}s from {editable.chat.id}")
        if sl.value > 45:
            await asyncio.sleep(sl.value)
            if Config.LOG_CHANNEL:
                await bot.send_message(
                    chat_id=int(Config.LOG_CHANNEL),
                    text=f"#FloodWait:\nGot FloodWait of `{str(sl.value)}s` from `{str(editable.chat.id)}` !! (During save_media_in_channel final edit)",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]
                        ]
                    )
                )
        # Instead of recursive call, you might want to just retry the 'editable.edit' or log.
        # For simplicity, let's allow the outer exception handler to catch if it's persistent.
    except Exception as err:
        import traceback # Ensure traceback is imported here
        error_details = traceback.format_exc() # Get full traceback
        
        error_message_to_user = f"Something Went Wrong!\n\n**Error:** `{err}`"
        
        try:
            # Safely attempt to edit the message
            if editable and hasattr(editable, 'edit_text'):
                await editable.edit(error_message_to_user)
            else:
                print(f"Failed to edit editable message (possibly gone): {error_message_to_user}")
        except Exception as edit_err:
            print(f"Secondary error trying to edit message: {edit_err}")
            
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(editable.chat.id) if editable else 'unknown'}` !!\n\n**Traceback:**\n`{error_details}`", # Use full traceback
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id) if editable else 'unknown_user_id'}")]
                    ]
                )
            )

# --- Remaining parts of your original main.py (assuming they are correct) ---
# ... (process_media_messages, get_batch_callback, finalize_batch_callback, save_single_callback) ...
# ... (start_command, ban_user_callback) ...
# ... (app = Client(...), if __name__ == "__main__": app.run()) ...
