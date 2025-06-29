# (c) @JAsuran

import asyncio
import traceback
from base64 import urlsafe_b64encode
# from asyncio.exceptions import TimeoutError # No longer needed for Client.ask()

from configs import Config # Make sure your configs.py is correctly set up
from pyrogram import Client, filters # Ensure filters are imported
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery # Import CallbackQuery type
)
from pyrogram.errors import FloodWait

# --- GLOBAL STATE STORAGE FOR CONVERSATIONS ---
# IMPORTANT: For production, these should be backed by a persistent database
# (e.g., Redis, PostgreSQL) to prevent data loss on dyno restarts or multiple dynos.
user_states = {} # Stores {user_id: "state_name"}
user_data = {}   # Stores {user_id: {"batch_link": ..., "editable_message_id": ..., "chat_id": ...}}

# Define conversation states
BATCH_STATE_WAITING_FOR_CAPTION = "waiting_for_batch_caption"
IDLE_STATE = "idle" # Default state when not in a specific conversation
# --- END GLOBAL STATE STORAGE ---


# --- Helper Functions ---

def str_to_b64(text: str) -> str:
    """Encodes a string to a URL-safe Base64 string."""
    return urlsafe_b64encode(text.encode("ascii")).decode("ascii").strip("=")

def TimeFormatter(milliseconds: int) -> str:
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
    return tmp[:-2] if tmp else "0 sec"

def humanbytes(size):
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

def human_size(bytes, units=[' bytes','KB','MB','GB','TB', 'PB', 'EB']):
    return str(bytes) + units[0] if int(bytes) < 1024 else human_size(int(bytes)>>10, units[1:])

# --- Core Logic Functions ---

async def forward_to_channel(bot: Client, message: Message, editable: Message):
    try:
        __SENT = await message.forward(Config.DB_CHANNEL)
        return __SENT
    except FloodWait as sl:
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
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FORWARD_ERROR:\nError forwarding message for user `{editable.chat.id}`: `{e}`\n\nTraceback:\n`{traceback.format_exc()}`",
                disable_web_page_preview=True
            )
        return None

# --- MODIFIED FUNCTION WITHOUT Client.ask() ---
async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    """
    Saves a batch of media, generates a link, AND asks the user for a custom caption
    using a state-based approach.
    """
    user_id = editable.chat.id
    try:
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL. Please contact support.")
            # Clear state in case of an early exit
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            return

        # Ensure we always update the message content to avoid MESSAGE_NOT_MODIFIED
        await editable.edit("Processing batch... Please wait.")
        
        messages_to_process = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)
        valid_messages = [msg for msg in messages_to_process if msg.media]

        if not valid_messages:
            await editable.edit("No valid media files found in the batch to save.")
            # Clear state
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            return
            
        await editable.edit(f"Saving {len(valid_messages)} files to the database channel... This may take a moment.")

        message_ids_str = ""
        for message in valid_messages:
            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                continue # Skip if forwarding failed for this message
            message_ids_str += f"{str(sent_message.id)} "
            await asyncio.sleep(2) # Added a small delay to prevent rate limits

        if not message_ids_str.strip():
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel.")
            # Clear state
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            return

        # Save the list of forwarded message IDs in the DB_CHANNEL
        SaveMessage = await bot.send_message(
            chat_id=int(Config.DB_CHANNEL), # Ensure DB_CHANNEL is an integer
            text=message_ids_str.strip(),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Delete Batch", callback_data="closeMessage")
            ]])
        )
        share_link = f"https://nammatvserial.jasurun.workers.dev?start=JAsuran_{str_to_b64(str(SaveMessage.id))}"

        # --- ALTERNATIVE TO Client.ask(): Set user state and ask ---
        user_states[user_id] = BATCH_STATE_WAITING_FOR_CAPTION
        user_data[user_id] = {
            "batch_link": share_link,
            "editable_message_id": editable.id,
            "chat_id": editable.chat.id
        }
        print(f"DEBUG: User {user_id} state set to: {user_states.get(user_id)}") # Debug print

        # Edit the message to ask for caption
        await editable.edit(
            "✅ Batch link generated!\n\nPlease send the caption for this batch.\n\nType `/cancel` to skip.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel Caption", callback_data="cancel_caption_batch")
            ]])
        )
        # The rest of the process (receiving caption) will be handled by handle_caption_input

    except Exception as err:
        error_details = traceback.format_exc()
        try:
            await editable.edit(f"Something Went Wrong during batch save!\n\n**Error:** `{err}`")
        except Exception as edit_err:
            print(f"Failed to edit message with error: {edit_err}: {edit_err}")
            await bot.send_message(editable.chat.id, f"Something Went Wrong during batch save!\n\n**Error:** `{err}`")

        # Clean up state in case of error
        user_states.pop(user_id, None)
        user_data.pop(user_id, None)

        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(editable.chat.id)}` !!\n\n**Traceback:**\n`{error_details}`",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]]
                )
            )

async def save_media_in_channel(bot: Client, editable: Message, message: Message):
    # This function remains largely unchanged as the request was for batch files.
    # Added robust error handling for editable.edit
    try:
        forwarded_msg = await message.forward(int(Config.DB_CHANNEL)) # Ensure DB_CHANNEL is an integer
        file_er_id = str(forwarded_msg.id)
        
        await forwarded_msg.reply_text(
            f"#PRIVATE_FILE:\n\n[{message.from_user.first_name}](tg://user?id={message.from_user.id}) Got File Link!",
            disable_web_page_preview=True
        )
        
        file_size = "N/A"
        duration_str = ""
        caption = message.caption if message.caption else ""

        media = message.document or message.video or message.audio or message.photo

        if media and hasattr(media, 'file_size') and media.file_size is not None:
            file_size = humanbytes(media.file_size)
        
        if message.video or message.audio:
            media_with_duration = message.video or message.audio
            if media_with_duration and hasattr(media_with_duration, 'duration') and media_with_duration.duration is not None:
                duration_in_ms = media_with_duration.duration * 1000
                duration_str = f"[⏰ {TimeFormatter(duration_in_ms)}]"

        share_link = f"https://nammatvserial.jasurun.workers.dev/?start=JAsuran_{str_to_b64(file_er_id)}"

        reply_text = f"**{caption}**\n\n**Size:** {file_size} {duration_str}\n\n**Link:** {share_link}"

        await editable.edit(
            text=reply_text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )
    except Exception as err:
        error_details = traceback.format_exc()
        try:
            await editable.edit(f"Something Went Wrong!\n\n**Error:** `{err}`")
        except Exception as edit_err:
            print(f"Failed to edit message with error: {edit_err}: {edit_err}")
            await bot.send_message(editable.chat.id, f"Something Went Wrong!\n\n**Error:** `{err}`")

        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(editable.chat.id)}` !!\n\n**Traceback:**\n`{error_details}`",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Ban User", callback_data=f"ban_user_{str(editable.chat.id)}")]]
                )
            )

# --- NEW MESSAGE HANDLER FOR CAPTION INPUT ---
# This handler must be registered with your Pyrogram Client instance.
# Example: app.add_handler(MessageHandler(handle_caption_input, filters.text & filters.private))
# Or using the decorator syntax:
# @app.on_message(filters.text & filters.private) if `app` is globally defined
# For this example, assuming 'bot' is the client instance passed around or accessible.
# YOU NEED TO ENSURE THIS HANDLER IS REGISTERED IN YOUR MAIN BOT FILE!
async def handle_caption_input(client: Client, message: Message):
    user_id = message.from_user.id
    
    print(f"DEBUG: handle_caption_input received message from {user_id}. Current state: {user_states.get(user_id)}")

    # Check if the user is in the state of waiting for a batch caption
    if user_states.get(user_id) == BATCH_STATE_WAITING_FOR_CAPTION:
        if user_id not in user_data:
            # This should ideally not happen if the flow is correct, but for safety
            await message.reply_text("Error: No pending batch operation found. Please restart the process.")
            user_states.pop(user_id, None) # Clear potentially stale state
            return

        batch_info = user_data[user_id]
        share_link = batch_info["batch_link"]
        editable_message_id = batch_info["editable_message_id"]
        chat_id = batch_info["chat_id"] # Use the chat_id where the editable message is

        editable_message = None
        try:
            # Try to get the editable message. It might have been deleted or inaccessible.
            editable_message = await client.get_messages(chat_id, editable_message_id)
        except Exception as e:
            print(f"WARNING: Could not retrieve editable message {editable_message_id} for user {user_id}: {e}")

        custom_caption = "Batch Files" # Default caption
        
        if message.text:
            if message.text.lower() == "/cancel":
                if editable_message:
                    await editable_message.edit("Caption skipped. Using default caption.")
                else:
                    await client.send_message(chat_id, "Caption skipped. Using default caption.")
            else:
                custom_caption = message.text
        else:
            # If user sent non-text (photo, sticker etc.) while waiting for text
            if editable_message:
                await editable_message.edit("No text provided for caption. Using default caption.")
            else:
                await client.send_message(chat_id, "No text provided for caption. Using default caption.")

        # Construct final post with the custom caption
        final_text = f"**{custom_caption}**\n\n{share_link}"
        
        # Now, update the editable message with the batch link and custom caption
        if editable_message:
            try:
                await editable_message.edit(
                    text=final_text,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Open Link", url=share_link)],
                         [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                          InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
                    ),
                    disable_web_page_preview=True
                )
            except Exception as edit_err:
                print(f"Failed to edit final message {editable_message_id}: {edit_err}")
                # Fallback to sending a new message if editing the original failed
                await client.send_message(
                    chat_id,
                    text=final_text,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("Open Link", url=share_link)],
                         [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                          InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
                    ),
                    disable_web_page_preview=True
                )
        else:
            # If original message was inaccessible from the start, send a new one
            await client.send_message(
                chat_id,
                text=final_text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Open Link", url=share_link)],
                     [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                      InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
                ),
                disable_web_page_preview=True
            )

        if Config.LOG_CHANNEL:
            user = message.from_user
            log_text = (f"#BATCH_SAVE:\n\n"
                        f"**User:** [{user.first_name or user.title}](tg://user?id={user.id})\n"
                        f"**Caption:** `{custom_caption}`\n"
                        f"Got Batch Link!")
            await client.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=log_text,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Open Link", url=share_link)]])
            )
        
        # Reset user state after successful completion
        user_states.pop(user_id, None) # Remove user_id from states
        user_data.pop(user_id, None)   # Remove user_id from data
        print(f"DEBUG: User {user_id} state reset to IDLE.")

    # IMPORTANT: If you have other message handlers, ensure their filters are specific
    # so they don't accidentally intercept messages intended for conversation flow.
    # For example, if you have a general @app.on_message for all text,
    # put the state-based handler *before* it, or use more specific filters.
    else:
        # This is a regular message, not part of the batch caption conversation flow.
        # Your existing command handlers (e.g., /start, /batch, etc.) would be defined here
        # or in other modules/plugins.
        # print(f"DEBUG: Message from {user_id} not part of caption conversation. State: {user_states.get(user_id)}")
        pass

# --- NEW CALLBACK QUERY HANDLER for "Cancel Caption" ---
# This handler must also be registered with your Pyrogram Client instance.
async def cancel_batch_caption_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    print(f"DEBUG: Cancel callback received from {user_id}. Current state: {user_states.get(user_id)}")

    if user_states.get(user_id) == BATCH_STATE_WAITING_FOR_CAPTION:
        if user_id in user_data:
            batch_info = user_data[user_id]
            share_link = batch_info["batch_link"]
            editable_message_id = batch_info["editable_message_id"]
            chat_id = batch_info["chat_id"]

            editable_message = None
            try:
                editable_message = await client.get_messages(chat_id, editable_message_id)
            except Exception as e:
                print(f"WARNING: Could not retrieve editable message {editable_message_id} on cancel for user {user_id}: {e}")

            custom_caption = "Batch Files (Caption Skipped)"
            final_text = f"**{custom_caption}**\n\n{share_link}"

            if editable_message:
                try:
                    await editable_message.edit(
                        text=final_text,
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("Open Link", url=share_link)],
                             [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                              InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
                        ),
                        disable_web_page_preview=True
                    )
                except Exception as edit_err:
                    print(f"Failed to edit message on cancel {editable_message_id}: {edit_err}")
                    await client.send_message(chat_id, f"Caption skipped. Here's your link: {share_link}")
            else:
                await client.send_message(chat_id, f"Caption skipped. Here's your link: {share_link}")

            await callback_query.answer("Caption request cancelled.")
            user_states.pop(user_id, None)
            user_data.pop(user_id, None)
            print(f"DEBUG: User {user_id} state reset after cancel.")
        else:
            await callback_query.answer("No active batch operation to cancel.", show_alert=True)
            user_states.pop(user_id, None) # Clear state if data is missing/corrupted
    else:
        await callback_query.answer("You are not in a caption input state.", show_alert=True)


# --- YOU NEED TO ADD YOUR PYROGRAM CLIENT INITIALIZATION AND HANDLER REGISTRATION ---
# This part is crucial for your bot to function.
# Here's a common example of how your main bot file might look:

# import os
# from pyrogram import Client, filters
# from pyrogram.handlers import MessageHandler, CallbackQueryHandler
#
# # Assuming the code above (functions, global vars) is in a file like 'bot_logic.py'
# # If this is all in one file, just uncomment and set up the Client instance.
#
# # class Config:
# #     API_ID = os.environ.get("API_ID")
# #     API_HASH = os.environ.get("API_HASH")
# #     BOT_TOKEN = os.environ.get("BOT_TOKEN")
# #     DB_CHANNEL = int(os.environ.get("DB_CHANNEL")) # Ensure it's an int
# #     LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL")) # Ensure it's an int
#
# app = Client(
#     "my_bot_session", # Session name
#     api_id=Config.API_ID,
#     api_hash=Config.API_HASH,
#     bot_token=Config.BOT_TOKEN,
#     # In Pyrogram v1, if you use plugins, this is how you'd load them:
#     # plugins=dict(root="plugins_folder_name")
# )
#
# @app.on_message(filters.command("start") & filters.private)
# async def start_command(client, message):
#     user_id = message.from_user.id
#     user_states[user_id] = IDLE_STATE # Ensure user state is clean on start
#     user_data.pop(user_id, None)
#     await message.reply_text("Hello! I'm your batch link bot. Send me /batch to create a link.")
#
# # Example handler to trigger save_batch_media_in_channel
# @app.on_message(filters.command("batch") & filters.private)
# async def trigger_batch_save(client, message):
#     # In a real scenario, you'd get these message_ids from a user selecting files,
#     # or a range of messages. This is just a dummy example.
#     # For demonstration, let's assume the user replies to the first message of a batch
#     # or sends /batch then selects messages.
#     # You need to implement how you collect message_ids.
#     # For a simple test, you could ask the user to reply to the first message of the batch
#     # and then get messages from that point.
#
#     # For a quick test, let's assume you're getting message IDs from somewhere.
#     # For example, if you want to save the last 3 messages before the /batch command
#     # This is a very rough example, adjust based on how users select messages.
#     # You would need to fetch the messages and get their IDs.
#     # For a robust solution, consider a "select messages" phase.
#     # Example for testing:
#     # reply_to_id = message.reply_to_message.id if message.reply_to_message else message.id
#     # messages_to_save = []
#     # async for msg in client.iter_history(chat_id=message.chat.id, offset_id=reply_to_id, limit=5):
#     #     if msg.media:
#     #         messages_to_save.append(msg.id)
#     # message_ids = messages_to_save
#
#     # DUMMY message_ids FOR TESTING - REPLACE WITH REAL LOGIC
#     # This will attempt to save message.id and message.id - 1
#     message_ids = [message.id, message.id - 1] # ADJUST THIS LOGIC TO GET ACTUAL MESSAGE IDs
#     if len(message_ids) < 1:
#         await message.reply_text("Please specify messages to batch, or use this command by replying to the first message of your batch.")
#         return
#
#     editable_msg = await message.reply_text("Initiating batch processing...")
#     await save_batch_media_in_channel(client, editable_msg, message_ids)
#
# # Register the new handlers
# app.add_handler(MessageHandler(handle_caption_input, filters.text & filters.private))
# app.add_handler(CallbackQueryHandler(cancel_batch_caption_callback, filters.regex("^cancel_caption_batch$")))
#
# # You might also want to register save_media_in_channel for single file saves.
# # @app.on_message(filters.media & filters.private & ~filters.group & ~filters.channel)
# # async def save_single_file(client, message):
# #     editable_msg = await message.reply_text("Saving file...")
# #     await save_media_in_channel(client, editable_msg, message)
#
# print("Bot starting...")
# app.run() # Start the bot
