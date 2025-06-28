import asyncio
import traceback
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
# Import the specific error for graceful handling
from pyrogram.errors import FloodWait, MessageNotModified 

# --- Configuration Class (unchanged, just showing context) ---
class Config:
    BOT_USERNAME = "your_bot_username"
    DB_CHANNEL = -1001234567890
    LOG_CHANNEL = -1009876543210
    API_ID = 1234567
    API_HASH = "your_api_hash"
    BOT_TOKEN = "your_bot_token"

# --- Helper Functions (unchanged) ---
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
    import base64
    return base64.urlsafe_b64encode(str(text).encode("ascii")).decode("ascii").strip("=")

def b64_to_str(text: str) -> str:
    import base64
    return base64.urlsafe_b64decode(text.encode("ascii") + b"==").decode("ascii")

# --- Global Variables for Batch Handling (unchanged) ---
BATCH_FILES = {}
BATCH_EDITABLE_MESSAGES = {}
BATCH_TIMEOUT_TASKS = {}
BATCH_TIMEOUT = 10

# --- Core Functions (relevant modifications) ---

async def forward_to_channel(bot: Client, message: Message, editable: Message):
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
        print(f"FloodWait: Got {sl.value}s from {editable.chat.id}")
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
    except Exception as e:
        print(f"Error forwarding message: {e}")
        traceback.print_exc()
        return None

async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        message_ids_in_db = []
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            return

        original_messages = []
        for i in range(0, len(message_ids), 100):
            chunk_ids = message_ids[i:i+100]
            try:
                fetched_chunk = await bot.get_messages(chat_id=editable.chat.id, message_ids=chunk_ids)
                original_messages.extend(fetched_chunk)
            except Exception as e:
                print(f"Error fetching messages chunk: {e}")
                if Config.LOG_CHANNEL:
                    await bot.send_message(
                        chat_id=Config.LOG_CHANNEL,
                        text=f"#BatchFetchError:\nError fetching message chunk for user `{editable.chat.id}`: `{e}`"
                    )
                continue
        
        if not original_messages:
            await editable.edit("Could not fetch any messages to save in the batch. Please try again.")
            return

        media_messages = [msg for msg in original_messages if msg.media]
        if not media_messages:
            await editable.edit("No media files found in the selected messages to save.")
            return
            
        # This edit will happen once, so less likely to cause MESSAGE_NOT_MODIFIED here
        await editable.edit(f"Saving {len(media_messages)} files to the database channel... This may take a moment.")

        for msg in media_messages:
            sent_message = await forward_to_channel(bot, msg, editable)
            if sent_message:
                message_ids_in_db.append(str(sent_message.id))
            else:
                print(f"Failed to save message {msg.id}. Skipping...")
                
        if not message_ids_in_db:
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel or no media was found.")
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
            await editable.edit(error_message + "\n\nPlease contact support or try again later.")
            if Config.LOG_CHANNEL:
                await bot.send_message(
                    chat_id=int(Config.LOG_CHANNEL),
                    text=f"#BATCH_SAVE_ERROR:\n`{error_message}`\n\nUser: `{editable.chat.id}`\nTraceback:\n`{traceback.format_exc()}`",
                    disable_web_page_preview=True
                )
        except Exception:
            pass
    finally:
        user_id = editable.chat.id
        if user_id in BATCH_FILES:
            del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES:
            del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]

async def save_media_in_channel(bot: Client, editable: Message, message: Message):
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

        # This edit will happen once, so less likely to cause MESSAGE_NOT_MODIFIED here
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

# --- Batch Processing Handlers (relevant modifications) ---

async def handle_batch_timeout(bot: Client, user_id: int):
    try:
        await asyncio.sleep(BATCH_TIMEOUT)
        print(f"Batch timeout triggered for user: {user_id}")

        if user_id in BATCH_FILES and BATCH_FILES[user_id]:
            editable_message = BATCH_EDITABLE_MESSAGES.get(user_id)
            if editable_message and editable_message.chat.id == user_id:
                num_files = len(BATCH_FILES[user_id])
                new_text = f"**{num_files} files received!**\n\nClick the button below to get the batch link."
                print(f"Attempting to show button for {user_id}. Files: {num_files}")
                try:
                    # Catch MessageNotModified here specifically
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
        if user_id in BATCH_TIMEOUT_TASKS:
            del BATCH_TIMEOUT_TASKS[user_id]


@Client.on_message(filters.private & filters.media & filters.incoming)
async def process_media_messages(bot: Client, message: Message):
    if not (message.document or message.video or message.photo or message.audio):
        print(f"Skipping non-media message from {message.from_user.id}: {message.id}")
        return

    user_id = message.from_user.id
    print(f"Received media message from user: {user_id}, Message ID: {message.id}")

    if user_id in BATCH_FILES:
        BATCH_FILES[user_id].append(message.id)
        current_file_count = len(BATCH_FILES[user_id])
        print(f"Adding to existing batch for {user_id}. Current files: {current_file_count}")

        if user_id in BATCH_TIMEOUT_TASKS and not BATCH_TIMEOUT_TASKS[user_id].done():
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            print(f"Cancelled old timeout for {user_id}")
        
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        print(f"Started new timeout task for {user_id}")

        try:
            editable_msg = BATCH_EDITABLE_MESSAGES.get(user_id)
            if editable_msg:
                new_text = f"Adding file to batch... Total files: {current_file_count}. Waiting for more files or timeout to get batch link."
                # Catch MessageNotModified here specifically
                await editable_msg.edit(new_text)
            else:
                print(f"Warning: No editable message found for user {user_id} while adding to batch. Attempting to create one.")
                # Fallback: if editable message somehow got lost, try to create a new one
                editable = await message.reply_text("Processing your files...")
                BATCH_EDITABLE_MESSAGES[user_id] = editable

        except MessageNotModified:
            print(f"MessageNotModified: Edit attempt for {user_id} had same content. Current count: {current_file_count}.")
            # This is expected and can be ignored.
        except Exception as e:
            print(f"Error editing message for user {user_id}: {e}")
            traceback.print_exc()

    else:
        print(f"Starting new batch/single file process for {user_id}. Message ID: {message.id}")
        editable = await message.reply_text("Processing your file...")
        BATCH_EDITABLE_MESSAGES[user_id] = editable
        BATCH_FILES[user_id] = [message.id]
        
        BATCH_TIMEOUT_TASKS[user_id] = asyncio.create_task(handle_batch_timeout(bot, user_id))
        print(f"Started initial timeout task for {user_id}")

@Client.on_callback_query(filters.regex(r"^get_batch_"))
async def get_batch_callback(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    print(f"Get Batch Callback received from user: {user_id}")

    await query.answer("Generating batch link...", show_alert=False)

    if user_id in BATCH_FILES and BATCH_FILES[user_id]:
        message_ids = BATCH_FILES[user_id]
        editable = BATCH_EDITABLE_MESSAGES.get(user_id)

        if not editable:
            print(f"Error: No editable message found for {user_id} in callback.")
            await query.message.edit("An error occurred: Could not find the editable message for your batch.")
            if user_id in BATCH_FILES: del BATCH_FILES[user_id]
            if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
            if user_id in BATCH_TIMEOUT_TASKS:
                BATCH_TIMEOUT_TASKS[user_id].cancel()
                del BATCH_TIMEOUT_TASKS[user_id]
            return

        try:
            # This edit should change the message, so MessageNotModified is less likely here.
            await editable.edit("Preparing to save your batch files. This may take a moment...")
        except MessageNotModified:
            print(f"MessageNotModified: Preparing text already set for {user_id}.")
        except Exception as e:
            print(f"Error editing 'preparing' message for {user_id}: {e}")
            traceback.print_exc()

        await save_batch_media_in_channel(bot, editable, message_ids)
    else:
        print(f"No batch files found for user {user_id} during callback. Stale button?")
        await query.message.edit("No batch files found for you. Please send files to start a new batch.")
        if user_id in BATCH_FILES: del BATCH_FILES[user_id]
        if user_id in BATCH_EDITABLE_MESSAGES: del BATCH_EDITABLE_MESSAGES[user_id]
        if user_id in BATCH_TIMEOUT_TASKS:
            BATCH_TIMEOUT_TASKS[user_id].cancel()
            del BATCH_TIMEOUT_TASKS[user_id]

# --- Other Handlers (unchanged) ---

@Client.on_message(filters.command("start"))
async def start_command(bot: Client, message: Message):
    if len(message.command) > 1 and message.command[1].startswith("JAsuran_"):
        encoded_id = message.command[1].split("_", 1)[1]
        
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

        if manifest_message and manifest_message.text and " " in manifest_message.text:
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
            
            for msg_id in message_ids:
                try:
                    await bot.copy_message(
                        chat_id=message.chat.id,
                        from_chat_id=Config.DB_CHANNEL,
                        message_id=msg_id
                    )
                    await asyncio.sleep(0.5)
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
                    await message.reply_text(f"Could not forward one of the files from the batch (ID: {msg_id}). It might have been deleted or there was an error: `{e}`")
        elif manifest_message and manifest_message.text:
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
    user_to_ban_id = int(query.data.split("_")[2])
    print(f"Admin {query.from_user.id} requested to ban user {user_to_ban_id}")
    
    await query.answer(f"User {user_to_ban_id} has been marked for banning. (Requires backend implementation)", show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.reply_text(f"User `{user_to_ban_id}` has been noted for banning. Action required by bot owner.", quote=True)
    except Exception as e:
        print(f"Error editing ban message or replying: {e}")

# --- Initialize and Run the Bot ---
# This part assumes you're running this directly or importing 'app' from another file.
# Make sure your API_ID, API_HASH, and BOT_TOKEN are set in the Config class.

# app = Client(
#     "my_file_store_bot", # A name for your session
#     api_id=Config.API_ID,
#     api_hash=Config.API_HASH,
#     bot_token=Config.BOT_TOKEN
# )

# if __name__ == "__main__":
#     print("Starting bot...")
#     app.run()
#     print("Bot stopped.")
