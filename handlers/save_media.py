# (c) @JAsuran

import asyncio
import traceback
from configs import Config
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.errors import FloodWait
from handlers.helpers import str_to_b64

# --- Helper Functions (unchanged) ---

def TimeFormatter(milliseconds: int) -> str:
    """Formats milliseconds into a human-readable string (days, hrs, min, sec)."""
    if not milliseconds:
        return "N/A"
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s") if seconds else "")
    return tmp.strip(', ') if tmp else "0s"

def humanbytes(size: int) -> str:
    """Converts bytes to a human-readable format (KB, MB, GB)."""
    if not size:
        return "0B"
    power = 2**10
    n = 0
    Dic_powerN = {0: 'B', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n]

# --- Global Variables for Batch Handling ---
# Stores message IDs for a user's current batch
# Format: {user_id: [message_id1, message_id2, ...]}
BATCH_FILES = {}
# Stores the editable message for a batch, to update it later
# Format: {user_id: editable_message_object}
BATCH_EDITABLE_MESSAGES = {}
# Stores the asyncio task for batch timeout, to cancel it if new files arrive
# Format: {user_id: asyncio_task_object}
BATCH_TIMEOUT_TASKS = {}
# Defines the time (in seconds) to wait for new files before considering a batch complete
BATCH_TIMEOUT = 5

# --- Core Functions (modified and new) ---

async def forward_to_channel(bot: Client, message: Message, editable: Message):
    """
    Forwards a message to the DB_CHANNEL with robust FloodWait handling.
    """
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

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    """
    Saves a batch of media to the DB_CHANNEL, handling potential flood waits for each file.
    """
    try:
        message_ids_in_db = []

        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            return

        # Fetch messages in batches to avoid hitting API limits for large lists
        original_messages = []
        for i in range(0, len(message_ids), 100): # Fetch 100 messages at a time
            chunk_ids = message_ids[i:i+100]
            try:
                fetched_chunk = await bot.get_messages(chat_id=editable.chat.id, message_ids=chunk_ids)
                original_messages.extend(fetched_chunk)
            except Exception as e:
                print(f"Error fetching messages chunk: {e}")
                await editable.edit(f"Could not fetch some messages from the batch. Skipping these files. Error: `{e}`")
                continue
        
        if not original_messages:
            await editable.edit("Could not fetch any messages to save in the batch. Please try again.")
            return

        await editable.edit(f"Saving {len(original_messages)} files to the database channel...")

        for msg in original_messages:
            # Ensure only media messages are processed for saving
            if msg.media:
                sent_message = await forward_to_channel(bot, msg, editable)
                if sent_message:
                    message_ids_in_db.append(str(sent_message.id))
                else:
                    print(f"Failed to save message {msg.id}. Skipping...") # For debugging
            else:
                print(f"Message {msg.id} is not media. Skipping...") # For debugging
                
        if not message_ids_in_db:
            await editable.edit("Could not save any media files from the batch. This might be a permission issue in the database channel or no media was found.")
            return

        message_ids_str = " ".join(message_ids_in_db)

        saved_batch_manifest_message = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
            text=message_ids_str,
            disable_web_page_preview=True
        )

        share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(str(saved_batch_manifest_message.id))}"

        await editable.edit(
            f"**Successfully saved {len(message_ids_in_db)} files!**\n\nHere is your shareable link:\n`{share_link}`",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Open Link", url=share_link)],
                    [InlineKeyboardButton("Bots Channel", url="https://telegram.me/As_botzz"),
                     InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu")]
                ]
            )
        )
    except Exception as err:
        error_message = f"An unexpected error occurred during batch saving: `{err}`"
        traceback.print_exc()
        try:
            await editable.edit(error_message + "\n\nPlease contact support.")
        except Exception:
            pass # Avoid another error if editing fails
    finally:
        # Clean up batch data for the user
        user_id = editable.chat.id
        if user_id in BATCH_FILES:
            del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES:
            del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]


async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    """
    Saves a single media file to the DB_CHANNEL, handling different media types and captions correctly.
    This function will now be called for single file saves OR if a batch isn't detected.
    """
    try:
        forwarded_msg = await forward_to_channel(bot, message, editable)
        if not forwarded_msg:
            await editable.edit("Failed to save the file to the database channel. Please try again later.")
            return
            
        file_er_id = str(forwarded_msg.id)
        
        await forwarded_msg.reply_text(
            f"#PRIVATE_FILE:\n\nSaved by: [{message.from_user.first_name}](tg://user?id={message.from_user.id})",
            disable_web_page_preview=True
        )

        media = message.document or message.video or message.audio or message.photo
        file_size = humanbytes(getattr(media, 'file_size', 0))

        duration_str = ""
        if message.video or message.audio:
            media_with_duration = message.video or message.audio
            duration_in_ms = media_with_duration.duration * 1000
            duration_str = f"[⏰ {TimeFormatter(duration_in_ms)}]"

        caption = message.caption if message.caption else ""
        
        share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(file_er_id)}"

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

# --- New Handlers for Batch Processing ---

async def handle_batch_timeout(bot: Client, user_id: int):
    """
    Called when the batch timeout expires. Presents the "Get Batch Link" button.
    """
    await asyncio.sleep(BATCH_TIMEOUT)
    if user_id in BATCH_FILES and BATCH_FILES[user_id]:
        editable_message = BATCH_EDITABLE_MESSAGES.get(user_id)
        if editable_message:
            num_files = len(BATCH_FILES[user_id])
            await editable_message.edit(
                f"**{num_files} files received!**\n\nClick the button below to get the batch link.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⚡️ Get Batch Link ⚡️", callback_data=f"get_batch_{user_id}")]]
                )
            )
        else:
            print(f"No editable message found for user {user_id} during batch timeout.")
    
    # Clean up the timeout task as it's done
    if user_id in BATCH_TIMEOUT_TASKS:
        del BATCH_TIMEOUT_TASKS[user_id]


@Client.on_message(filters.private & filters.media & filters.incoming)
async def process_media_messages(bot: Client, message: Message):
    """
    Handles incoming media messages for both single file and batch saving.
    """
    user_id = message.from_user.id
    
    # If a batch is already in progress, add the message to it
    if user_id in BATCH_FILES:
        BATCH_FILES[user_id].append(message.id)
        # Reset the timeout task
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        await BATCH_EDITABLE_MESSAGES[user_id].edit(
            f"Adding file to batch... Total files: {len(BATCH_FILES[user_id])}. Waiting for more files or timeout to get batch link."
        )
    else:
        # Start a new batch or prepare for a single file save
        # Send an initial message that we can edit later
        editable = await message.reply_text("Processing your file...")
        BATCH_EDITABLE_MESSAGES[user_id] = editable
        BATCH_FILES[user_id] = [message.id]
        
        # Start a timeout task to check if it's a batch
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))

        # If it's likely a single file (e.g., first file in a long time), save it immediately.
        # This logic needs refinement based on desired user experience.
        # For simplicity, here we always initiate a potential batch, and only if no more
        # files arrive within BATCH_TIMEOUT will the batch button appear.
        # If you want to process single files immediately:
        # await save_media_in_channel(bot, editable, message)
        # and then remove the batch logic for this path.
        # The current implementation will always try to form a batch first.

@Client.on_callback_query(filters.regex(r"^get_batch_"))
async def get_batch_callback(bot: Client, query: CallbackQuery):
    """
    Handles the callback when the "Get Batch Link" button is clicked.
    """
    user_id = query.from_user.id
    await query.answer("Generating batch link...", show_alert=False)

    if user_id in BATCH_FILES and BATCH_FILES[user_id]:
        message_ids = BATCH_FILES[user_id]
        editable = BATCH_EDITABLE_MESSAGES.get(user_id)

        if not editable:
            await query.message.edit("An error occurred: Could not find the editable message for your batch.")
            # Clean up residual data
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
            if user_id in BATCH_TIMEOUT_TASKS:
                BATCH_TIMEOUT_TASKS[user_id].cancel()
                del BATCH_TIMEOUT_TASKS[user_id]
            return

        # Clear the current text and show processing
        await editable.edit("Preparing to save your batch files. This may take a moment...")
        await save_batch_media_in_channel(bot, editable, message_ids)
    else:
        await query.message.edit("No batch files found for you. Please send files to start a new batch.")
        # Clean up any potential stale data
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]

# --- Other handlers (e.g., /start, ban_user) would go here ---
# Example of a simplified start handler
@Client.on_message(filters.command("start"))
async def start_command(bot: Client, message: Message):
    if len(message.command) > 1 and message.command[1].startswith("JAsuran_"):
        # This is likely a deep link for a saved file/batch
        encoded_id = message.command[1].split("_", 1)[1]
        file_id_or_message_ids_str = await bot.get_messages(
            chat_id=Config.DB_CHANNEL,
            message_ids=int(str_to_b64(encoded_id, decode=True))
        )
        
        # Check if it's a single file or a batch manifest
        if file_id_or_message_ids_str.text and " " in file_id_or_message_ids_str.text:
            # Assume it's a batch manifest (space-separated IDs)
            message_ids = [int(mid) for mid in file_id_or_message_ids_str.text.split()]
            if not message_ids:
                await message.reply_text("Invalid batch link or no files found in this batch.")
                return

            await message.reply_text(f"Fetching {len(message_ids)} files from the batch...")
            for msg_id in message_ids:
                try:
                    # Forward each message from DB_CHANNEL to the user
                    await bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=Config.DB_CHANNEL,
                        message_id=msg_id
                    )
                    await asyncio.sleep(0.5) # Small delay to avoid FloodWait
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=Config.DB_CHANNEL,
                        message_id=msg_id
                    )
                except Exception as e:
                    print(f"Error forwarding file {msg_id}: {e}")
                    await message.reply_text(f"Could not forward one of the files from the batch (ID: {msg_id}). It might have been deleted or there was an error: `{e}`")
        else:
            # Assume it's a single file ID
            file_id = int(str_to_b64(encoded_id, decode=True))
            try:
                await bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=Config.DB_CHANNEL,
                    message_id=file_id
                )
            except Exception as e:
                await message.reply_text(f"Could not retrieve the file. It might have been deleted or there was an error: `{e}`")
    else:
        await message.reply_text("Hello! Send me any media file to save it. You can send multiple files and I'll give you a batch link!")

# Callback for banning user (simplified)
@Client.on_callback_query(filters.regex(r"^ban_user_"))
async def ban_user_callback(bot: Client, query: CallbackQuery):
    user_to_ban_id = int(query.data.split("_")[2])
    # In a real bot, you'd add logic here to add the user to a banned list
    # and prevent them from using the bot.
    await query.answer(f"User {user_to_ban_id} has been marked for banning. (Not actually banned in this demo)", show_alert=True)
    await query.message.edit_reply_markup(reply_markup=None) # Remove button
