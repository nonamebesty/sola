import asyncio
import traceback
import os
import base64 # Import base64 directly here as it's used in helper functions

try:
    from configs import Config
except ImportError:
    print("Error: 'configs.py' not found or 'Config' class not defined inside it.")
    print("Please make sure you have a 'configs.py' file with a 'Config' class.")
    exit(1) # Exit if configuration is missing

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.errors import FloodWait, MessageNotModified

# --- Helper Functions ---
def TimeFormatter(milliseconds: int) -> str:
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
    return base64.urlsafe_b64encode(str(text).encode("ascii")).decode("ascii").strip("=")

def b64_to_str(text: str) -> str:
    try:
        # Pad with '==' to ensure correct base64 decoding if padding was removed.
        # This is generally what urlsafe_b64decode expects if no padding is present.
        padding_needed = len(text) % 4
        if padding_needed != 0:
            text += '=' * (4 - padding_needed)
        return base64.urlsafe_b64decode(text.encode("ascii")).decode("ascii")
    except (base64.binascii.Error, UnicodeDecodeError) as e:
        print(f"Base64 decoding error for text '{text}': {e}")
        # Return original text or raise a specific error if you want to handle it differently
        raise ValueError(f"Invalid base64 string: {text}") from e
    except Exception as e:
        print(f"Unexpected error in b64_to_str for text '{text}': {e}")
        raise

# --- Global Variables for Batch Handling ---
BATCH_FILES = {}
BATCH_EDITABLE_MESSAGES = {}
BATCH_TIMEOUT_TASKS = {}
BATCH_TIMEOUT = 10 # Seconds to wait for more files in a batch

# --- Core Functions ---
async def forward_to_channel(bot: Client, message: Message, editable: Message):
    """
    Forwards a message to the DB_CHANNEL.
    Handles FloodWait errors by waiting and retrying, and logs other errors.
    """
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
        print(f"FloodWait: Got {sl.value}s from {editable.chat.id}")
        if sl.value > 45: # If the wait is long, notify the log channel
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
        return await forward_to_channel(bot, message, editable) # Retry forwarding
    except Exception as e:
        print(f"Error forwarding message: {e}")
        traceback.print_exc()
        # Log the error if a log channel is configured
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FORWARD_ERROR:\nError forwarding message for user `{editable.chat.id}`: `{e}`\n\nTraceback:\n`{traceback.format_exc()}`",
                disable_web_page_preview=True
            )
        return None

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    """
    Saves a batch of media messages to the DB_CHANNEL and generates a shareable link.
    """
    try:
        message_ids_in_db = []
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            return

        original_messages = []
        # Fetch messages in chunks to avoid hitting Telegram API limits
        for i in range(0, len(message_ids), 100):
            chunk_ids = message_ids[i:i+100]
            try:
                fetched_chunk = await bot.get_messages(chat_id=editable.chat.id, message_ids=chunk_ids)
                original_messages.extend(fetched_chunk)
            except Exception as e:
                print(f"Error fetching messages chunk for user {editable.chat.id}: {e}")
                if Config.LOG_CHANNEL:
                    await bot.send_message(
                        chat_id=int(Config.LOG_CHANNEL),
                        text=f"#BatchFetchError:\nError fetching message chunk for user `{editable.chat.id}`: `{e}`"
                    )
                continue # Try to process remaining chunks even if one fails

        if not original_messages:
            await editable.edit("Could not fetch any messages to save in the batch. Please try again.")
            return

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
                print(f"Failed to save message {msg.id} for user {editable.chat.id}. Skipping...")
                
        if not message_ids_in_db:
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel or no media was found.")
            return

        message_ids_str = " ".join(message_ids_in_db)

        # Save the list of forwarded message IDs as a manifest in the DB_CHANNEL
        saved_batch_manifest_message = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
            text=message_ids_str,
            disable_web_page_preview=True
        )

        # Create the shareable link using the manifest message ID
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
        except Exception: # Avoid crashing if editing editable message fails
            pass
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
    Saves a single media message to the DB_CHANNEL and generates a shareable link.
    """
    try:
        forwarded_msg = await forward_to_channel(bot, message, editable)
        if not forwarded_msg:
            await editable.edit("Failed to save the file to the database channel. Please try again later.")
            return
            
        file_er_id = str(forwarded_msg.id)
        
        # Add a private note to the forwarded message in DB_CHANNEL
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
                    [[InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]])
            )

# --- Batch Processing Handlers ---
async def handle_batch_timeout(bot: Client, user_id: int):
    """
    Called when a batch timeout occurs. Shows the 'Get Batch Link' button or saves single file.
    """
    try:
        await asyncio.sleep(BATCH_TIMEOUT)
        print(f"Batch timeout triggered for user: {user_id}")

        if user_id in BATCH_FILES and BATCH_FILES[user_id]:
            editable_message = BATCH_EDITABLE_MESSAGES.get(user_id)
            if editable_message and editable_message.chat.id == user_id:
                num_files = len(BATCH_FILES[user_id])
                # Only show the button if there's more than one file, otherwise save as single
                if num_files > 1:
                    new_text = f"**{num_files} files received!**\n\nClick the button below to get the batch link."
                    print(f"Attempting to show button for {user_id}. Files: {num_files}")
                    try:
                        await editable_message.edit(
                            new_text,
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("⚡️ Get Batch Link ⚡️", callback_data=f"get_batch_{user_id}")]]
                            )
                        )
                    except MessageNotModified:
                        print(f"MessageNotModified: Batch button text already set for {user_id}.")
                    except Exception as e:
                        print(f"Error editing message for batch button for {user_id}: {e}")
                        traceback.print_exc()
                else: # Only 1 file, save it directly
                    print(f"Only 1 file in batch for {user_id} after timeout. Saving as single.")
                    # Get the message object for the single file
                    message_id_to_save = BATCH_FILES[user_id][0]
                    try:
                        single_message = await bot.get_messages(chat_id=user_id, message_ids=message_id_to_save)
                        if single_message and single_message.media:
                            await editable_message.edit("Saving your single file...")
                            await save_media_in_channel(bot, editable_message, single_message)
                        else:
                            await editable_message.edit("No media found to save for single file.")
                    except Exception as e:
                        print(f"Error saving single file for {user_id}: {e}")
                        await editable_message.edit(f"Error saving your file: `{e}`")
                    finally:
                        # Ensure cleanup after single file save
                        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
                        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]

            else:
                print(f"No valid editable message found for user {user_id} during batch timeout. Cleaning up.")
                if user_id in BATCH_FILES: del BATCH_FILES[user_id]
                if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        else:
            print(f"No files in batch for user {user_id} after timeout. Cleaning up.")
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]

    except asyncio.CancelledError:
        print(f"Batch timeout for user {user_id} was cancelled.")
    except Exception as e:
        print(f"Error in handle_batch_timeout for user {user_id}: {e}")
        traceback.print_exc()
    finally:
        # Ensure the timeout task is removed from the dictionary
        if user_id in BATCH_TIMEOUT_TASKS:
            del BATCH_TIMEOUT_TASKS[user_id]


@Client.on_message(filters.private & filters.media & filters.incoming)
async def process_media_messages(bot: Client, message: Message):
    """
    Handles incoming media messages from private chats.
    Initiates or adds to a batch processing flow.
    """
    # Only process if it's actually a media message with file_id
    if not (message.document or message.video or message.photo or message.audio):
        print(f"Skipping non-media message from {message.from_user.id}: {message.id}")
        return

    user_id = message.from_user.id
    print(f"Received media message from user: {user_id}, Message ID: {message.id}")

    if user_id in BATCH_FILES:
        # User is already in a batch process
        BATCH_FILES[user_id].append(message.id)
        current_file_count = len(BATCH_FILES[user_id])
        print(f"Adding to existing batch for {user_id}. Current files: {current_file_count}")

        # Cancel the old timeout task and start a new one
        if user_id in BATCH_TIMEOUT_TASKS and not BATCH_TIMEOUT_TASKS[user_id].done():
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            print(f"Cancelled old timeout for {user_id}")
            
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        print(f"Started new timeout task for {user_id}")

        try:
            editable_msg = BATCH_EDITABLE_MESSAGES.get(user_id)
            if editable_msg:
                new_text = (
                    f"Adding file to batch... Total files: {current_file_count}. "
                    "Send more files or click 'Done' to finalize the batch."
                )
                
                reply_markup = InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✅ Done with Batch", callback_data=f"finalize_batch_{user_id}")]
                    ]
                )
                # Only show 'Save This File Now' if it's the only file in the current batch state
                # or if the first file of a new batch was just added (to address the initial problem)
                if current_file_count == 1:
                    reply_markup.inline_keyboard.append(
                        [InlineKeyboardButton("💾 Save This File Now", callback_data=f"save_single_{message.id}")]
                    )
                await editable_msg.edit(new_text, reply_markup=reply_markup)
            else:
                print(f"Warning: No editable message found for user {user_id} while adding to batch. Attempting to create one.")
                # Fallback: if editable message somehow got lost, try to create a new one
                editable = await message.reply_text("Processing your files...")
                BATCH_EDITABLE_MESSAGES[user_id] = editable

        except MessageNotModified:
            print(f"MessageNotModified: Edit attempt for {user_id} had same content. Current count: {current_file_count}.")
            # This is expected if the message text isn't changing.
        except Exception as e:
            print(f"Error editing message for user {user_id}: {e}")
            traceback.print_exc()

    else:
        # Start a new batch or process as a single file
        print(f"Starting new batch/single file process for {user_id}. Message ID: {message.id}")
        
        initial_text = "Received your first file! Send more files to create a batch, or choose an option below."
        initial_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Done with Batch", callback_data=f"finalize_batch_{user_id}")],
                [InlineKeyboardButton("💾 Save This File Now", callback_data=f"save_single_{message.id}")]
            ]
        )
        
        editable = await message.reply_text(initial_text, reply_markup=initial_markup)
        
        BATCH_EDITABLE_MESSAGES[user_id] = editable
        BATCH_FILES[user_id] = [message.id]
        
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        print(f"Started initial timeout task for {user_id}")


@Client.on_callback_query(filters.regex(r"^get_batch_"))
async def get_batch_callback(bot: Client, query: CallbackQuery):
    """
    Handles the callback query when the user clicks 'Get Batch Link'.
    """
    user_id = query.from_user.id
    print(f"Get Batch Callback received from user: {user_id}")

    await query.answer("Generating batch link...", show_alert=False)

    if user_id in BATCH_FILES and BATCH_FILES[user_id]:
        message_ids = BATCH_FILES[user_id]
        editable = BATCH_EDITABLE_MESSAGES.get(user_id)

        if not editable:
            print(f"Error: No editable message found for {user_id} in callback. Cleaning up.")
            await query.message.edit("An error occurred: Could not find the editable message for your batch.")
            # Clear data if editable message is missing
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
            if user_id in BATCH_TIMEOUT_TASKS:
                BATCH_TIMEOUT_TASKS[user_id].cancel()
                del BATCH_TIMEOUT_TASKS[user_id]
            return

        try:
            # Update the message to indicate processing has started
            await editable.edit("Preparing to save your batch files. This may take a moment...")
        except MessageNotModified:
            print(f"MessageNotModified: Preparing text already set for {user_id}.")
        except Exception as e:
            print(f"Error editing 'preparing' message for {user_id}: {e}")
            traceback.print_exc()

        await save_batch_media_in_channel(bot, editable, message_ids)
    else:
        print(f"No batch files found for user {user_id} during callback. Stale button or cleanup already done.")
        await query.message.edit("No batch files found for you. Please send files to start a new batch.")
        # Ensure cleanup in case of stale button
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]

@Client.on_callback_query(filters.regex(r"^finalize_batch_"))
async def finalize_batch_callback(bot: Client, query: CallbackQuery):
    """
    Handles the 'Done with Batch' callback query.
    """
    user_id = query.from_user.id
    print(f"Finalize Batch Callback received from user: {user_id}")

    await query.answer("Finalizing batch...", show_alert=False)

    if user_id in BATCH_FILES and BATCH_FILES[user_id]:
        message_ids = BATCH_FILES[user_id]
        editable = BATCH_EDITABLE_MESSAGES.get(user_id)

        if not editable:
            print(f"Error: No editable message found for {user_id} in finalize callback. Cleaning up.")
            await query.message.edit("An error occurred: Could not find the editable message for your batch.")
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
            if user_id in BATCH_TIMEOUT_TASKS:
                BATCH_TIMEOUT_TASKS[user_id].cancel()
                del BATCH_TIMEOUT_TASKS[user_id]
            return
        
        # Cancel any pending timeout for this user immediately
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]
            print(f"Cancelled timeout for {user_id} due to explicit finalize.")

        num_files = len(message_ids)
        if num_files > 1:
            await editable.edit(f"Finalizing batch with {num_files} files. Saving to database channel...")
            await save_batch_media_in_channel(bot, editable, message_ids)
        elif num_files == 1:
            await editable.edit("Only one file in batch. Saving it as a single file...")
            # Fetch the single message object
            message_id_to_save = message_ids[0]
            try:
                single_message = await bot.get_messages(chat_id=user_id, message_ids=message_id_to_save)
                if single_message and single_message.media:
                    await save_media_in_channel(bot, editable, single_message)
                else:
                    await editable.edit("No media found to save for single file.")
            except Exception as e:
                print(f"Error saving single file from finalize_batch for {user_id}: {e}")
                await editable.edit(f"Error saving your file: `{e}`")
            finally:
                # Ensure cleanup after single file save
                if user_id in BATCH_FILES: del BATCH_FILES[user_id]
                if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        else:
            await editable.edit("No files were added to the batch. Please send files first.")
            # Clear any residual batch data
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
            
    else:
        print(f"No batch files found for user {user_id} during finalize callback. Stale button?")
        await query.message.edit("No batch files found for you. Please send files to start a new batch.")
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]


@Client.on_callback_query(filters.regex(r"^save_single_"))
async def save_single_callback(bot: Client, query: CallbackQuery):
    """
    Handles the 'Save This File Now' callback query for a single file.
    """
    user_id = query.from_user.id
    message_id_to_save = int(query.data.split("_")[2]) # Extract original message_id
    print(f"Save Single Callback received from user: {user_id} for message {message_id_to_save}")

    await query.answer("Saving single file...", show_alert=False)

    editable = BATCH_EDITABLE_MESSAGES.get(user_id)
    if not editable:
        print(f"Error: No editable message found for {user_id} for single save.")
        await query.message.edit("An error occurred: Could not find the editable message.")
        # Ensure cleanup if editable message is missing
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]
        return

    # Cancel any pending timeout for this user immediately
    if user_id in BATCH_TIMEOUT_TASKS:
        BATCH_TIMEOUT_TASKS[user_id].cancel()
        del BATCH_TIMEOUT_TASKS[user_id]
        print(f"Cancelled timeout for {user_id} due to explicit single save.")

    try:
        # Fetch the original message object for saving
        original_message = await bot.get_messages(chat_id=user_id, message_ids=message_id_to_save)
        if original_message and original_message.media:
            await editable.edit("Saving your file...")
            await save_media_in_channel(bot, editable, original_message)
        else:
            await editable.edit("No media found to save for single file. It might have been deleted.")
    except Exception as e:
        print(f"Error fetching or saving single file for {user_id}: {e}")
        await editable.edit(f"Error saving your file: `{e}`")
    finally:
        # Clear batch data after single file save
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]

# --- Other Handlers ---
@Client.on_message(filters.command("start"))
async def start_command(bot: Client, message: Message):
    """
    Handles the /start command.
    If a JAsuran_ encoded ID is provided, it retrieves and forwards the file(s).
    Otherwise, it sends a welcome message.
    """
    if len(message.command) > 1 and message.command[1].startswith("JAsuran_"):
        encoded_id = message.command[1].split("_", 1)[1]
        print(f"DEBUG: Received encoded_id: '{encoded_id}' from user {message.from_user.id}")

        manifest_message_id = None
        try:
            decoded_str = b64_to_str(encoded_id)
            print(f"DEBUG: Decoded string: '{decoded_str}' for user {message.from_user.id}")
            manifest_message_id = int(decoded_str)
            print(f"DEBUG: Converted manifest_message_id: {manifest_message_id} for user {message.from_user.id}")
            
        except ValueError as ve: # Catch specific ValueError from b64_to_str or int()
            error_msg = f"Invalid link format. The file ID in the link seems corrupted or incorrect. Error: `{ve}`"
            print(f"Error for user {message.from_user.id}: {error_msg}. Decoded string was: '{decoded_str}'")
            await message.reply_text(error_msg + "\n\nPlease ensure you are using the correct share link.")
            return
        except Exception as e: # Catch any other unexpected errors during decoding/conversion
            error_msg = f"An unexpected error occurred while processing the link: `{e}`."
            print(f"Error for user {message.from_user.id}: {error_msg}. Traceback:\n{traceback.format_exc()}")
            await message.reply_text(error_msg + "\n\nPlease try again or contact support.")
            return

        # Now proceed with fetching the manifest message using the valid integer ID
        manifest_message = None
        try:
            manifest_message = await bot.get_messages(
                chat_id=Config.DB_CHANNEL,
                message_ids=manifest_message_id
            )
        except Exception as e:
            print(f"Error fetching manifest message {manifest_message_id} for user {message.from_user.id}: {e}")
            traceback.print_exc()
            await message.reply_text("The files associated with this link could not be found. They might have been deleted from the database.")
            return

        if manifest_message and manifest_message.text:
            # Check if it's a batch link (space-separated IDs) or a single file link
            if " " in manifest_message.text: # Assuming space means multiple IDs
                message_ids_str = manifest_message.text
                message_ids = []
                try:
                    message_ids = [int(mid) for mid in message_ids_str.split()]
                except ValueError:
                    await message.reply_text("Error: Batch data in the link's manifest is corrupted. Please try a different link.")
                    return

                if not message_ids:
                    await message.reply_text("Invalid batch link or no files found in this batch.")
                    return

                await message.reply_text(f"Fetching {len(message_ids)} files from the batch. This may take a moment...")
                
                for msg_id in message_ids:
                    try:
                        await bot.copy_message(
                            chat_id=message.chat.id,
                            from_chat_id=Config.DB_CHANNEL,
                            message_id=msg_id
                        )
                        await asyncio.sleep(0.5) # Small delay to prevent hitting flood limits
                    except FloodWait as e:
                        await message.reply_text(f"Got FloodWait of {e.value}s. Please wait...")
                        await asyncio.sleep(e.value + 1)
                        # Retry after flood wait
                        await bot.copy_message(
                            chat_id=message.chat.id,
                            from_chat_id=Config.DB_CHANNEL,
                            message_id=msg_id
                        )
                    except Exception as e:
                        print(f"Error forwarding file {msg_id}: {e}")
                        await message.reply_text(f"Could not forward one of the files from the batch (ID: {msg_id}). It might have been deleted or there was an error: `{e}`")
            else: # Single file link
                try:
                    file_id = int(manifest_message.text)
                    await bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=Config.DB_CHANNEL,
                        message_id=file_id
                    )
                except ValueError:
                    await message.reply_text("Error: Single file ID in the link's manifest is corrupted. Please try a different link.")
                    return
                except Exception as e:
                    await message.reply_text(f"Could not retrieve the single file. It might have been deleted or there was an error: `{e}`")
        else:
            await message.reply_text("Invalid share link. The manifest message might be empty or corrupted in the database.")

    else:
        # Standard welcome message
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
    Handles the 'ban user' callback. (Requires manual backend implementation for actual banning).
    """
    user_to_ban_id = int(query.data.split("_")[2])
    admin_id = query.from_user.id
    print(f"Admin {admin_id} requested to ban user {user_to_ban_id}")
    
    # You would typically add this user_to_ban_id to a database or a ban list
    # and then implement logic in message handlers to block messages from banned users.
    
    await query.answer(f"User {user_to_ban_id} has been marked for banning. (Requires backend implementation)", show_alert=True)
    try:
        # Remove the inline button after action
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.reply_text(f"User `{user_to_ban_id}` has been noted for banning by admin `{admin_id}`. Action required by bot owner.", quote=True)
    except Exception as e:
        print(f"Error editing ban message or replying: {e}")

# --- Initialize and Run the Bot ---
# Create the Pyrogram client instance
app = Client(
    "my_file_store_bot", # A unique name for your session file
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

if __name__ == "__main__":
    print("Starting bot...")
    # This runs the bot until it's manually stopped (e.g., Ctrl+C)
    app.run()
    print("Bot stopped.")
