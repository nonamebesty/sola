# (c) @JAsuran

import asyncio
import traceback
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.errors import FloodWait

# --- Configuration Class ---
# IMPORTANT: Replace these with your actual bot details
# --- Helper Functions ---

class Config:
    BOT_USERNAME = "your_bot_username"  # <-- REPLACE THIS
    DB_CHANNEL = -1001234567890         # <-- REPLACE THIS with your DB Channel ID (e.g., -1001234567890)
    LOG_CHANNEL = -1009876543210        # <-- REPLACE THIS with your Log Channel ID (optional, but recommended)

    # Add your Pyrogram API ID and HASH here
    API_ID = 1234567                     # <-- REPLACE THIS with your API ID from my.telegram.org
    API_HASH = "your_api_hash"           # <-- REPLACE THIS with your API Hash from my.telegram.org
    BOT_TOKEN = "your_bot_token"     

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

def str_to_b64(text: str) -> str:
    """Converts a string to base64 (for deep linking)."""
    import base64
    return base64.urlsafe_b64encode(str(text).encode("ascii")).decode("ascii").strip("=")

def b64_to_str(text: str) -> str:
    """Converts base64 to string (for deep linking)."""
    import base64
    return base64.urlsafe_b64decode(text.encode("ascii") + b"==").decode("ascii")

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
BATCH_TIMEOUT = 10 # Increased for better testing experience

# --- Core Functions ---

async def forward_to_channel(bot: Client, message: Message, editable: Message):
    """
    Forwards a message to the DB_CHANNEL with robust FloodWait handling.
    """
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
        print(f"FloodWait: Got {sl.value}s from {editable.chat.id}") # Debug print
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
        return await forward_to_channel(bot, message, editable) # Retry after sleep
    except Exception as e:
        print(f"Error forwarding message: {e}") # Debug print
        traceback.print_exc()
        return None

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
        # Pyrogram's get_messages accepts a list of IDs, up to 200.
        # Let's chunk to be safe and handle potential errors.
        for i in range(0, len(message_ids), 100):
            chunk_ids = message_ids[i:i+100]
            try:
                # get_messages returns a list of Message objects
                fetched_chunk = await bot.get_messages(chat_id=editable.chat.id, message_ids=chunk_ids)
                original_messages.extend(fetched_chunk)
            except Exception as e:
                print(f"Error fetching messages chunk: {e}")
                # Log the error, but try to continue with other chunks
                if Config.LOG_CHANNEL:
                    await bot.send_message(
                        chat_id=Config.LOG_CHANNEL,
                        text=f"#BatchFetchError:\nError fetching message chunk for user `{editable.chat.id}`: `{e}`"
                    )
                # await editable.edit(f"Could not fetch some messages from the batch. Skipping these files. Error: `{e}`")
                continue
        
        if not original_messages:
            await editable.edit("Could not fetch any messages to save in the batch. Please try again.")
            return

        # Filter out non-media messages before processing
        media_messages = [msg for msg in original_messages if msg.media]
        if not media_messages:
            await editable.edit("No media files found in the selected messages to save.")
            return
            
        await editable.edit(f"Saving {len(media_messages)} files to the database channel... This may take a moment.")

        for msg in media_messages:
            sent_message = await forward_to_channel(bot, msg, editable)
            if sent_message:
                message_ids_in_db.append(str(sent_message.id))
            else:
                print(f"Failed to save message {msg.id}. Skipping...") # For debugging
                # Optionally, inform the user about skipped files
                # await editable.reply_text(f"Failed to save message {msg.id}. Skipping this file.", quote=True)
                
        if not message_ids_in_db:
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel or no media was found.")
            return

        message_ids_str = " ".join(message_ids_in_db)

        # Send the manifest message containing all saved file IDs
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
            await editable.edit(error_message + "\n\nPlease contact support or try again later.")
            if Config.LOG_CHANNEL:
                await bot.send_message(
                    chat_id=int(Config.LOG_CHANNEL),
                    text=f"#BATCH_SAVE_ERROR:\n`{error_message}`\n\nUser: `{editable.chat.id}`\nTraceback:\n`{traceback.format_exc()}`",
                    disable_web_page_preview=True
                )
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
    This function will be used for single file saves. In the current batch logic,
    a single file also goes through a short 'batch' detection phase first.
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
        file_size = humanbytes(getattr(media, 'file_size', 0)) if media else "N/A"

        duration_str = ""
        if message.video or message.audio:
            media_with_duration = message.video or message.audio
            duration_in_ms = media_with_duration.duration * 1000 if media_with_duration.duration else 0
            duration_str = f"[⏰ {TimeFormatter(duration_in_ms)}]"

        caption = message.caption if message.caption else ""
        
        share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(file_er_id)}"

        reply_text = f"**{caption}**\n\n**Size:** {file_size} {duration_str}\n\n**Link:** `{share_link}`"

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
        error_message = f"Something Went Wrong!\n\n**Error:** `{err}`"
        await editable.edit(error_message)
        traceback.print_exc()
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text="#ERROR_TRACEBACK:\n"
                     f"Got Error from `{str(editable.chat.id)}` !!\n\n"
                     f"**Traceback:** `{traceback.format_exc()}`",
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
    try:
        await asyncio.sleep(BATCH_TIMEOUT)
        print(f"Batch timeout triggered for user: {user_id}") # Debug print

        if user_id in BATCH_FILES and BATCH_FILES[user_id]:
            editable_message = BATCH_EDITABLE_MESSAGES.get(user_id)
            if editable_message and editable_message.chat.id == user_id: # Ensure message belongs to the user
                num_files = len(BATCH_FILES[user_id])
                print(f"Attempting to show button for {user_id}. Files: {num_files}") # Debug print
                await editable_message.edit(
                    f"**{num_files} files received!**\n\nClick the button below to get the batch link.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⚡️ Get Batch Link ⚡️", callback_data=f"get_batch_{user_id}")]]
                    )
                )
            else:
                print(f"No valid editable message found for user {user_id} during batch timeout. Cleaning up.") # Debug print
                # If no editable message or mismatch, clean up to avoid stale state
                if user_id in BATCH_FILES: del BATCH_FILES[user_id]
                if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        else:
            print(f"No files in batch for user {user_id} after timeout. Cleaning up.") # Debug print
            # If no files, just clean up
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]

    except asyncio.CancelledError:
        print(f"Batch timeout for user {user_id} was cancelled.") # Debug print
    except Exception as e:
        print(f"Error in handle_batch_timeout for user {user_id}: {e}")
        traceback.print_exc()
    finally:
        # Clean up the timeout task regardless of outcome
        if user_id in BATCH_TIMEOUT_TASKS:
            del BATCH_TIMEOUT_TASKS[user_id]


@Client.on_message(filters.private & filters.media & filters.incoming)
async def process_media_messages(bot: Client, message: Message):
    """
    Handles incoming media messages for both single file and batch saving.
    """
    user_id = message.from_user.id
    
    # Ensure it's actual media, not just text with media group ID
    if not (message.document or message.video or message.audio or message.photo):
        print(f"Skipping non-media message from {user_id}: {message.id}")
        return # Not a media message we care about for saving

    print(f"Received media message from user: {user_id}, Message ID: {message.id}") # Debug print

    # If a batch is already in progress, add the message to it
    if user_id in BATCH_FILES:
        print(f"Adding to existing batch for {user_id}. Current files: {len(BATCH_FILES[user_id])}") # Debug print
        BATCH_FILES[user_id].append(message.id)
        # Cancel the old timeout and start a new one to extend the batch window
        if user_id in BATCH_TIMEOUT_TASKS and not BATCH_TIMEOUT_TASKS[user_id].done():
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            print(f"Cancelled old timeout for {user_id}") # Debug print
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        print(f"Started new timeout task for {user_id}") # Debug print

        try:
            editable_msg = BATCH_EDITABLE_MESSAGES.get(user_id)
            if editable_msg:
                await editable_msg.edit(
                    f"Adding file to batch... Total files: {len(BATCH_FILES[user_id])}. Waiting for more files or timeout to get batch link."
                )
            else:
                print(f"Warning: No editable message found for user {user_id} while adding to batch.") # Debug print
                # This case indicates a potential inconsistency, try to re-establish
                editable = await message.reply_text("Processing your files...")
                BATCH_EDITABLE_MESSAGES[user_id] = editable

        except Exception as e:
            print(f"Error editing message for user {user_id}: {e}")
            traceback.print_exc()

    else:
        # Start a new batch or prepare for a single file save
        # Send an initial message that we can edit later
        print(f"Starting new batch/single file process for {user_id}. Message ID: {message.id}") # Debug print
        editable = await message.reply_text("Processing your file...")
        BATCH_EDITABLE_MESSAGES[user_id] = editable
        BATCH_FILES[user_id] = [message.id]
        
        # Start a timeout task to check if it's a batch
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        print(f"Started initial timeout task for {user_id}") # Debug print

@Client.on_callback_query(filters.regex(r"^get_batch_"))
async def get_batch_callback(bot: Client, query: CallbackQuery):
    """
    Handles the callback when the "Get Batch Link" button is clicked.
    """
    user_id = query.from_user.id
    print(f"Get Batch Callback received from user: {user_id}") # Debug print

    # Acknowledge the query immediately to remove the loading animation
    await query.answer("Generating batch link...", show_alert=False)

    if user_id in BATCH_FILES and BATCH_FILES[user_id]:
        message_ids = BATCH_FILES[user_id]
        editable = BATCH_EDITABLE_MESSAGES.get(user_id)

        if not editable:
            print(f"Error: No editable message found for {user_id} in callback.") # Debug print
            await query.message.edit("An error occurred: Could not find the editable message for your batch.")
            # Clean up residual data if state is inconsistent
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
        print(f"No batch files found for user {user_id} during callback. Stale button?") # Debug print
        await query.message.edit("No batch files found for you. Please send files to start a new batch.")
        # Clean up any potential stale data
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]

# --- Other Handlers ---

@Client.on_message(filters.command("start"))
async def start_command(bot: Client, message: Message):
    if len(message.command) > 1 and message.command[1].startswith("JAsuran_"):
        # This is likely a deep link for a saved file/batch
        encoded_id = message.command[1].split("_", 1)[1]
        
        # Decode the ID and fetch the manifest message from DB_CHANNEL
        try:
            manifest_message_id = int(b64_to_str(encoded_id))
            manifest_message = await bot.get_messages(
                chat_id=Config.DB_CHANNEL,
                message_ids=manifest_message_id
            )
        except Exception as e:
            print(f"Error decoding or fetching manifest message: {e}")
            await message.reply_text("Invalid or expired share link. The file(s) might have been deleted.")
            return

        # Check if it's a single file or a batch manifest
        if manifest_message and manifest_message.text and " " in manifest_message.text:
            # Assume it's a batch manifest (space-separated IDs)
            message_ids_str = manifest_message.text
            message_ids = []
            try:
                message_ids = [int(mid) for mid in message_ids_str.split()]
            except ValueError:
                await message.reply_text("Invalid batch data in the manifest. Unable to retrieve files.")
                return

            if not message_ids:
                await message.reply_text("Invalid batch link or no files found in this batch.")
                return

            await message.reply_text(f"Fetching {len(message_ids)} files from the batch. This may take a moment...")
            
            # Forward each message from DB_CHANNEL to the user
            for msg_id in message_ids:
                try:
                    await bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=Config.DB_CHANNEL,
                        message_id=msg_id
                    )
                    await asyncio.sleep(0.5) # Small delay to avoid FloodWait
                except FloodWait as e:
                    await message.reply_text(f"Got FloodWait of {e.value}s. Please wait...")
                    await asyncio.sleep(e.value + 1)
                    await bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=Config.DB_CHANNEL,
                        message_id=msg_id
                    )
                except Exception as e:
                    print(f"Error forwarding file {msg_id}: {e}")
                    # Don't halt, just report this specific file error
                    await message.reply_text(f"Could not forward one of the files from the batch (ID: {msg_id}). It might have been deleted or there was an error: `{e}`")
        elif manifest_message and manifest_message.text: # Assuming a single message ID stored as plain text
            try:
                file_id = int(manifest_message.text)
                await bot.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=Config.DB_CHANNEL,
                    message_id=file_id
                )
            except Exception as e:
                await message.reply_text(f"Could not retrieve the single file. It might have been deleted or there was an error: `{e}`")
        else:
            await message.reply_text("Invalid share link. The manifest message might be empty or corrupted.")

    else:
        await message.reply_text(
            "Hello! 👋 Send me any media file (photo, video, document) to save it. "
            "If you send multiple files, I'll offer to create a single batch link for them!",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Bots Channel", url="https://telegram.me/As_botzz"),
                     InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu")]
                ]
            )
        )

@Client.on_callback_query(filters.regex(r"^ban_user_"))
async def ban_user_callback(bot: Client, query: CallbackQuery):
    """
    Handles the callback for banning a user from the log channel.
    In a real bot, you'd integrate this with a persistent ban list.
    """
    user_to_ban_id = int(query.data.split("_")[2])
    print(f"Admin {query.from_user.id} requested to ban user {user_to_ban_id}") # Debug print
    
    # Check if the user clicking the button is an authorized admin (optional but highly recommended)
    # For now, we'll assume anyone who sees the button can click it.
    # In a real bot: if query.from_user.id not in Config.ADMINS: return await query.answer("You are not authorized!")

    # In a real scenario, you would add user_to_ban_id to a database/file
    # of banned users and implement a check in all message handlers.
    await query.answer(f"User {user_to_ban_id} has been marked for banning. (Requires backend implementation)", show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None) # Remove button after click
        await query.message.reply_text(f"User `{user_to_ban_id}` has been noted for banning. Action required by bot owner.", quote=True)
    except Exception as e:
        print(f"Error editing ban message or replying: {e}")


# --- Initialize the Bot ---
# You would typically have your main bot instance here.
# For demonstration, let's create a simple one.

# app = Client(
#     "my_file_store_bot", # A name for your session
#     api_id=Config.API_ID,
#     api_hash=Config.API_HASH,
#     bot_token=Config.BOT_TOKEN
# )

# To run this code, you'd use something like:
# if __name__ == "__main__":
#     app.run()
