# (c) @JAsuran

import asyncio
import traceback
from base64 import urlsafe_b64encode
# from asyncio.exceptions import TimeoutError # No longer needed for bot.ask()

from configs import Config
from pyrogram import Client, filters # Import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.errors import FloodWait

# --- GLOBAL STATE STORAGE (Alternative to Client.ask()) ---
user_states = {} # To store the current conversation state for each user
user_data = {}   # To temporarily store data needed for the conversation (e.g., the editable message)

# Define conversation states
BATCH_STATE_WAITING_FOR_CAPTION = "waiting_for_batch_caption"
IDLE_STATE = "idle"
# --- END GLOBAL STATE STORAGE ---


# --- Helper Functions (unchanged) ---
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
            return

        await editable.edit("Processing batch... Please wait.")
        
        messages_to_process = await bot.get_messages(chat_id=editable.chat.id, message_ids=message_ids)
        valid_messages = [msg for msg in messages_to_process if msg.media]

        if not valid_messages:
            await editable.edit("No valid media files found in the batch to save.")
            return
            
        await editable.edit(f"Saving {len(valid_messages)} files to the database channel... This may take a moment.")

        message_ids_str = ""
        for message in valid_messages:
            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                continue
            message_ids_str += f"{str(sent_message.id)} "
            await asyncio.sleep(2)

        if not message_ids_str.strip():
            await editable.edit("Could not save any files from the batch. This might be a permission issue in the database channel.")
            return

        SaveMessage = await bot.send_message(
            chat_id=Config.DB_CHANNEL,
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
            "editable_message_id": editable.id, # Store editable message ID
            "chat_id": editable.chat.id # Store chat ID
        }

        # Edit the message to ask for caption
        await editable.edit(
            "✅ Batch link generated!\n\nPlease send the caption for this batch.\n\nType `/cancel` to skip.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel Caption", callback_data="cancel_caption_batch")
            ]])
        )
        # The rest of the process will be handled by the new message handler below

    except Exception as err:
        error_details = traceback.format_exc()
        try:
            await editable.edit(f"Something Went Wrong during batch save!\n\n**Error:** `{err}`")
        except Exception as edit_err:
            print(f"Failed to edit message with error: {edit_err}")
            await bot.send_message(editable.chat.id, f"Something Went Wrong during batch save!\n\n**Error:** `{err}`")

        # Clean up state in case of error
        if user_id in user_states:
            del user_states[user_id]
        if user_id in user_data:
            del user_data[user_id]

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
    # This function remains unchanged as the request was for batch files.
    try:
        forwarded_msg = await message.forward(Config.DB_CHANNEL)
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
            print(f"Failed to edit message with error: {edit_err}")
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
@Client.on_message(filters.text & filters.private) # Adjust filters as needed (e.g., only from private chats)
async def handle_caption_input(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if the user is in the state of waiting for a batch caption
    if user_states.get(user_id) == BATCH_STATE_WAITING_FOR_CAPTION:
        if user_id not in user_data:
            # Should not happen if flow is correct, but for safety
            await message.reply_text("Error: No pending batch operation found. Please restart the process.")
            user_states.pop(user_id, None)
            return

        batch_info = user_data[user_id]
        share_link = batch_info["batch_link"]
        editable_message_id = batch_info["editable_message_id"]
        chat_id = batch_info["chat_id"]

        try:
            # Try to get the editable message. It might have been deleted or inaccessible.
            editable_message = await client.get_messages(chat_id, editable_message_id)
        except Exception:
            # If we can't get the original editable message, send a new one
            editable_message = None

        custom_caption = "Batch Files" # Default caption
        if message.text and message.text.lower() == "/cancel":
            if editable_message:
                await editable_message.edit("Caption skipped. Using default caption.")
            else:
                await client.send_message(chat_id, "Caption skipped. Using default caption.")
        elif message.text:
            custom_caption = message.text
        else:
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
                print(f"Failed to edit final message: {edit_err}")
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
            # If original message was inaccessible, send a new one
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
            user = message.from_user # Use message.from_user for logging the caption provider
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
        
        # Reset user state after completion
        user_states[user_id] = IDLE_STATE
        user_data.pop(user_id, None)

    # You might have other message handlers here for other commands/interactions
    elif user_states.get(user_id) == IDLE_STATE or user_states.get(user_id) is None:
        # This is a regular message, not part of a conversation flow
        # Your existing command handlers (e.g., /start, /batch) would go here
        pass

# --- NEW CALLBACK QUERY HANDLER for "Cancel Caption" ---
@Client.on_callback_query(filters.regex("^cancel_caption_batch$"))
async def cancel_batch_caption_callback(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_states.get(user_id) == BATCH_STATE_WAITING_FOR_CAPTION:
        if user_id in user_data:
            batch_info = user_data[user_id]
            share_link = batch_info["batch_link"]
            editable_message_id = batch_info["editable_message_id"]
            chat_id = batch_info["chat_id"]

            try:
                editable_message = await client.get_messages(chat_id, editable_message_id)
            except Exception:
                editable_message = None

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
                    print(f"Failed to edit message on cancel: {edit_err}")
                    await client.send_message(chat_id, f"Caption skipped. Here's your link: {share_link}")
            else:
                await client.send_message(chat_id, f"Caption skipped. Here's your link: {share_link}")

            await callback_query.answer("Caption request cancelled.")
            user_states[user_id] = IDLE_STATE
            user_data.pop(user_id, None)
        else:
            await callback_query.answer("No active batch operation to cancel.", show_alert=True)
            user_states.pop(user_id, None) # Clear state if data is missing
    else:
        await callback_query.answer("You are not in a caption input state.", show_alert=True)
        
# ---
# You need to ensure your main Pyrogram client setup is correct and registers these handlers.
# Example (assuming `app` is your Client instance):
#
# from pyrogram import Client
#
# app = Client(
#     "my_bot",
#     api_id=Config.API_ID,
#     api_hash=Config.API_HASH,
#     bot_token=Config.BOT_TOKEN,
#     plugins={"root": "plugins"} # If you organize handlers in plugins
# )
#
# # It's good practice to add a default handler to reset states if needed,
# # or to inform users if they type something unexpected.
# @app.on_message(filters.command("start"))
# async def start_command(client, message):
#     user_states[message.from_user.id] = IDLE_STATE
#     user_data.pop(message.from_user.id, None) # Clear any leftover data
#     await message.reply_text("Hello! I'm your bot.")
#
# # Make sure your /batch command or whatever triggers save_batch_media_in_channel
# # is also defined and correctly calls it.
# # For example:
# @app.on_message(filters.command("batch") & filters.private)
# async def process_batch_command(client, message):
#     # Dummy message_ids for testing
#     # In your actual implementation, you'd get these from user selection or other logic
#     message_ids = [message.id - 1, message.id - 2] # Example: last two messages
#     editable_msg = await message.reply_text("Starting batch process...")
#     await save_batch_media_in_channel(client, editable_msg, message_ids)
#
#
# app.run()
# ---
