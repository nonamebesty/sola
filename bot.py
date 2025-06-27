# (c) @JAsuran

import os
import asyncio
import traceback
from binascii import (
    Error
)
from pyrogram import (
    Client,
    filters, enums
)

#from pyrogram import Enums.ChatType

from pyrogram.errors import (
    UserNotParticipant,
    FloodWait,
    QueryIdInvalid
)
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message
)
from configs import Config
from handlers.database import db
from handlers.add_user_to_db import add_user_to_database
from handlers.send_file import send_media_and_reply
from handlers.helpers import b64_to_str, str_to_b64
from handlers.check_user_status import handle_user_status
from handlers.force_sub_handler import (
    handle_force_sub,
    get_invite_link
)
from handlers.broadcast_handlers import main_broadcast_handler
from handlers.save_media import (
    save_media_in_channel,
    save_batch_media_in_channel
)

MediaList = {}

Bot = Client(
    name=Config.BOT_USERNAME,
    in_memory=True,
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH
)


@Bot.on_message(filters.private)
async def _(bot: Client, cmd: Message):
    await handle_user_status(bot, cmd)


@Bot.on_message(filters.command("start") & filters.private)
async def start(bot: Client, cmd: Message):

    if cmd.from_user.id in Config.BANNED_USERS:
        await cmd.reply_text("Sorry, You are banned.")
        return
    if Config.UPDATES_CHANNEL is not None:
        back = await handle_force_sub(bot, cmd)
        if back == 400:
            return
    
    usr_cmd = cmd.text.split("_", 1)[-1]
    if usr_cmd == "/start":
        await add_user_to_database(bot, cmd)
        await cmd.reply_text(
            Config.HOME_TEXT.format(cmd.from_user.first_name, cmd.from_user.id),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Support Group", url="https://t.me/AsuranMoviefinder"),
                        InlineKeyboardButton("Bots Channel", url="https://t.me/JAsuranbots")
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs")
                    ]
                ]
            )
        )
    else:
        try:
            try:
                file_id = int(b64_to_str(usr_cmd).split("_")[-1])
            except (Error, UnicodeDecodeError):
                file_id = int(usr_cmd.split("_")[-1])
            GetMessage = await bot.get_messages(chat_id=Config.DB_CHANNEL, message_ids=file_id)
            message_ids = []
            if GetMessage.text:
                message_ids = GetMessage.text.split(" ")
                _response_msg = await cmd.reply_text(
                    text=f"**Total Files:** `{len(message_ids)}`",
                    quote=True,
                    disable_web_page_preview=True
                )
            else:
                message_ids.append(int(GetMessage.id))
            for i in range(len(message_ids)):
                await send_media_and_reply(bot, user_id=cmd.from_user.id, file_id=int(message_ids[i]))
        except Exception as err:
            await cmd.reply_text(f"Something went wrong!\n\n**Error:** `{err}`")
MediaList = {}
user_batch_data = {}  # To hold messages for automatic batching
BATCH_PROCESS_TIMEOUT = 3  # Seconds to wait for more files

async def process_batch_after_delay(bot: Client, user_id: int):
    """
    Waits for a timeout, then processes the collected messages for a user.
    If multiple messages are collected, it generates a batch link.
    If only one, it directly generates a sharable link for that single file.
    """
    # Retrieve the collected messages and the message to edit
    batch_info = user_batch_data.get(user_id)
    if not batch_info:
        return

    messages = batch_info["messages"]
    editable = batch_info["editable"]

    try:
        if not messages:
            # This case is unlikely but good to have
            await editable.edit("No files were received.")
            return

        # If only one message was received, process it as a single file
        if len(messages) == 1:
            await editable.edit(f"**Detected 1 file. Please wait, generating sharable link...**")
            await save_media_in_channel(bot, editable=editable, message=messages[0])
        # If multiple messages were received, process them as a batch
        else:
            await editable.edit(f"**Detected {len(messages)} files. Please wait, generating batch link...**")
            message_ids = [msg.id for msg in messages]
            await save_batch_media_in_channel(bot=bot, editable=editable, message_ids=message_ids)

    except Exception as e:
        await editable.edit(f"An error occurred while processing your files!\n\n**Error:** `{e}`")
        traceback.print_exc()
    finally:
        # Important: Clean up the user's data after processing
        if user_id in user_batch_data:
            del user_batch_data[user_id]

@Bot.on_message((filters.document | filters.video | filters.audio | filters.photo) & ~filters.chat(Config.DB_CHANNEL))
async def main(bot: Client, message: Message):

    if message.chat.type == enums.ChatType.PRIVATE:
    
        await add_user_to_database(bot, message)

        if Config.UPDATES_CHANNEL is not None:
            back = await handle_force_sub(bot, message)
            if back == 400:
                return

        if message.from_user.id in Config.BANNED_USERS:
            await message.reply_text("Sorry, You are banned!\n\nContact [Support Group](https://t.me/AsuranMoviefinder)",
                                     disable_web_page_preview=True)
            return

        if Config.OTHER_USERS_CAN_SAVE_FILE is False:
            return

        # --- AUTOMATIC BATCH DETECTION AND DIRECT LINK LOGIC ---
        user_id = message.from_user.id
        
        # If a timer is already running for this user, cancel it to reset the countdown
        if user_id in user_batch_data and user_batch_data[user_id]["timer"]:
            user_batch_data[user_id]["timer"].cancel()

        # If this is the first file of a new batch, prepare the "shopping cart" for the user
        if user_id not in user_batch_data:
            # Send an initial message that we can edit later to show progress
            editable = await message.reply_text("`Collecting files... Please wait...`", quote=True)
            user_batch_data[user_id] = {
                "messages": [],
                "editable": editable,
                "timer": None
            }
        
        # Add the new file to the user's list
        user_batch_data[user_id]["messages"].append(message)
        
        # Start a new timer. If another file arrives, this timer will be cancelled and restarted.
        new_timer = asyncio.create_task(
            asyncio.sleep(BATCH_PROCESS_TIMEOUT)
        )
        user_batch_data[user_id]["timer"] = new_timer
        
        try:
            # Wait for the timer to complete
            await new_timer
            # If the timer completes without being cancelled, it means the user has stopped sending files.
            # Now, process everything we have collected.
            await process_batch_after_delay(bot, user_id)
        except asyncio.CancelledError:
            # This error means another file arrived. We have already reset the timer.
            # Let's update the message to let the user know we're still collecting.
            num_files = len(user_batch_data[user_id]["messages"])
            await user_batch_data[user_id]["editable"].edit(
                f"**Collected {num_files} files... Waiting for more...**"
            )
        # --- END OF AUTOMATIC LOGIC ---

    elif message.chat.type == enums.ChatType.CHANNEL:
        # This part for handling public channels remains the same.
        if (message.chat.id == int(Config.LOG_CHANNEL)) or (message.chat.id == int(Config.UPDATES_CHANNEL)) or message.forward_from_chat or message.forward_from:
            return
        elif int(message.chat.id) in Config.BANNED_CHAT_IDS:
            await bot.leave_chat(message.chat.id)
            return
        else:
            pass

        try:
            forwarded_msg = await message.forward(Config.DB_CHANNEL)
            file_er_id = str(forwarded_msg.id)
            share_link = f"https://t.me/{Config.BOT_USERNAME}?start=JAsuran_{str_to_b64(file_er_id)}"
            CH_edit = await bot.edit_message_reply_markup(message.chat.id, message.id,
                                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                                                              "Get Sharable Link", url=share_link)]]))
            if message.chat.username:
                await forwarded_msg.reply_text(
                    f"#CHANNEL_BUTTON:\n\n[{message.chat.title}](https://t.me/{message.chat.username}/{CH_edit.id}) Channel's Broadcasted File's Button Added!")
            else:
                private_ch = str(message.chat.id)[4:]
                await forwarded_msg.reply_text(
                    f"#CHANNEL_BUTTON:\n\n[{message.chat.title}](https://t.me/c/{private_ch}/{CH_edit.id}) Channel's Broadcasted File's Button Added!")
        except FloodWait as sl:
            await asyncio.sleep(sl.value)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#FloodWait:\nGot FloodWait of `{str(sl.value)}s` from `{str(message.chat.id)}` !!",
                disable_web_page_preview=True
            )
        except Exception as err:
            await bot.leave_chat(message.chat.id)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"#ERROR_TRACEBACK:\nGot Error from `{str(message.chat.id)}` !!\n\n**Traceback:** `{err}`",
                disable_web_page_preview=True
        )




@Bot.on_message(filters.private & filters.command("broadcast") & filters.user(Config.BOT_OWNER) & filters.reply)
async def broadcast_handler_open(_, m: Message):
    await main_broadcast_handler(m, db)


@Bot.on_message(filters.private & filters.command("status") & filters.user(Config.BOT_OWNER))
async def sts(_, m: Message):
    total_users = await db.total_users_count()
    await m.reply_text(
        text=f"**Total Users in DB:** `{total_users}`",
        quote=True
    )


@Bot.on_message(filters.private & filters.command("ban_user") & filters.user(Config.BOT_OWNER))
async def ban(c: Client, m: Message):
    
    if len(m.command) == 1:
        await m.reply_text(
            f"Use this command to ban any user from the bot.\n\n"
            f"Usage:\n\n"
            f"`/ban_user user_id ban_duration ban_reason`\n\n"
            f"Eg: `/ban_user 1234567 28 You misused me.`\n"
            f"This will ban user with id `1234567` for `28` days for the reason `You misused me`.",
            quote=True
        )
        return

    try:
        user_id = int(m.command[1])
        ban_duration = int(m.command[2])
        ban_reason = ' '.join(m.command[3:])
        ban_log_text = f"Banning user {user_id} for {ban_duration} days for the reason {ban_reason}."
        try:
            await c.send_message(
                user_id,
                f"You are banned to use this bot for **{ban_duration}** day(s) for the reason __{ban_reason}__ \n\n"
                f"**Message from the admin**"
            )
            ban_log_text += '\n\nUser notified successfully!'
        except:
            traceback.print_exc()
            ban_log_text += f"\n\nUser notification failed! \n\n`{traceback.format_exc()}`"

        await db.ban_user(user_id, ban_duration, ban_reason)
        print(ban_log_text)
        await m.reply_text(
            ban_log_text,
            quote=True
        )
    except:
        traceback.print_exc()
        await m.reply_text(
            f"Error occoured! Traceback given below\n\n`{traceback.format_exc()}`",
            quote=True
        )


@Bot.on_message(filters.private & filters.command("unban_user") & filters.user(Config.BOT_OWNER))
async def unban(c: Client, m: Message):

    if len(m.command) == 1:
        await m.reply_text(
            f"Use this command to unban any user.\n\n"
            f"Usage:\n\n`/unban_user user_id`\n\n"
            f"Eg: `/unban_user 1234567`\n"
            f"This will unban user with id `1234567`.",
            quote=True
        )
        return

    try:
        user_id = int(m.command[1])
        unban_log_text = f"Unbanning user {user_id}"
        try:
            await c.send_message(
                user_id,
                f"Your ban was lifted!"
            )
            unban_log_text += '\n\nUser notified successfully!'
        except:
            traceback.print_exc()
            unban_log_text += f"\n\nUser notification failed! \n\n`{traceback.format_exc()}`"
        await db.remove_ban(user_id)
        print(unban_log_text)
        await m.reply_text(
            unban_log_text,
            quote=True
        )
    except:
        traceback.print_exc()
        await m.reply_text(
            f"Error occurred! Traceback given below\n\n`{traceback.format_exc()}`",
            quote=True
        )


@Bot.on_message(filters.private & filters.command("banned_users") & filters.user(Config.BOT_OWNER))
async def _banned_users(_, m: Message):
    
    all_banned_users = await db.get_all_banned_users()
    banned_usr_count = 0
    text = ''

    async for banned_user in all_banned_users:
        user_id = banned_user['id']
        ban_duration = banned_user['ban_status']['ban_duration']
        banned_on = banned_user['ban_status']['banned_on']
        ban_reason = banned_user['ban_status']['ban_reason']
        banned_usr_count += 1
        text += f"> **user_id**: `{user_id}`, **Ban Duration**: `{ban_duration}`, " \
                f"**Banned on**: `{banned_on}`, **Reason**: `{ban_reason}`\n\n"
    reply_text = f"Total banned user(s): `{banned_usr_count}`\n\n{text}"
    if len(reply_text) > 4096:
        with open('banned-users.txt', 'w') as f:
            f.write(reply_text)
        await m.reply_document('banned-users.txt', True)
        os.remove('banned-users.txt')
        return
    await m.reply_text(reply_text, True)


@Bot.on_message(filters.private & filters.command("clear_batch"))
async def clear_user_batch(bot: Client, m: Message):
    MediaList[f"{str(m.from_user.id)}"] = []
    await m.reply_text("Cleared your batch files successfully!")


@Bot.on_callback_query()
async def button(bot: Client, cmd: CallbackQuery):

    cb_data = cmd.data
    if "aboutbot" in cb_data:
        await cmd.message.edit(
            Config.ABOUT_BOT_TEXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Source Codes of Bot",
                                             url="https://github.com/JAsuran/PyroFilesStoreBot")
                    ],
                    [
                        InlineKeyboardButton("Go Home", callback_data="gotohome"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs")
                    ]
                ]
            )
        )

    elif "aboutdevs" in cb_data:
        await cmd.message.edit(
            Config.ABOUT_DEV_TEXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Source Codes of Bot",
                                             url="https://github.com/JAsuran/PyroFilesStoreBot")
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("Go Home", callback_data="gotohome")
                    ]
                ]
            )
        )

    elif "gotohome" in cb_data:
        await cmd.message.edit(
            Config.HOME_TEXT.format(cmd.message.chat.first_name, cmd.message.chat.id),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Support Group", url="https://t.me/AsuranMoviefinder"),
                        InlineKeyboardButton("Bots Channel", url="https://t.me/JAsuranbots")
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs")
                    ]
                ]
            )
        )

    elif "refreshForceSub" in cb_data:
        if Config.UPDATES_CHANNEL:
            if Config.UPDATES_CHANNEL.startswith("-100"):
                channel_chat_id = int(Config.UPDATES_CHANNEL)
            else:
                channel_chat_id = Config.UPDATES_CHANNEL
            try:
                user = await bot.get_chat_member(channel_chat_id, cmd.message.chat.id)
                if user.status == "kicked":
                    await cmd.message.edit(
                        text="Sorry Sir, You are Banned to use me. Contact my [Support Group](https://t.me/AsuranMoviefinder).",
                        disable_web_page_preview=True
                    )
                    return
            except UserNotParticipant:
                invite_link = await get_invite_link(channel_chat_id)
                await cmd.message.edit(
                    text="**You Still Didn't Join ☹️, Please Join My Updates Channel to use this Bot!**\n\n"
                         "Due to Overload, Only Channel Subscribers can use the Bot!",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("🤖 Join Updates Channel", url=invite_link.invite_link)
                            ],
                            [
                                InlineKeyboardButton("🔄 Refresh 🔄", callback_data="refreshmeh")
                            ]
                        ]
                    )
                )
                return
            except Exception:
                await cmd.message.edit(
                    text="Something went Wrong. Contact my [Support Group](https://t.me/AsuranMoviefinder).",
                    disable_web_page_preview=True
                )
                return
        await cmd.message.edit(
            text=Config.HOME_TEXT.format(cmd.message.chat.first_name, cmd.message.chat.id),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Support Group", url="https://t.me/AsuranMoviefinder"),
                        InlineKeyboardButton("Bots Channel", url="https://t.me/JAsuranbots")
                    ],
                    [
                        InlineKeyboardButton("About Bot", callback_data="aboutbot"),
                        InlineKeyboardButton("About Dev", callback_data="aboutdevs")
                    ]
                ]
            )
        )

    elif cb_data.startswith("ban_user_"):
        user_id = cb_data.split("_", 2)[-1]
        if Config.UPDATES_CHANNEL is None:
            await cmd.answer("Sorry Sir, You didn't Set any Updates Channel!", show_alert=True)
            return
        if not int(cmd.from_user.id) == Config.BOT_OWNER:
            await cmd.answer("You are not allowed to do that!", show_alert=True)
            return
        try:
            await bot.kick_chat_member(chat_id=int(Config.UPDATES_CHANNEL), user_id=int(user_id))
            await cmd.answer("User Banned from Updates Channel!", show_alert=True)
        except Exception as e:
            await cmd.answer(f"Can't Ban Him!\n\nError: {e}", show_alert=True)

    if "addToBatchTrue" in cb_data:
        # Ensure MediaList exists for the user
        if cmd.from_user.id not in MediaList:
            MediaList[cmd.from_user.id] = []

        # Get the ID of the message that the button was replied to
        file_id = cmd.message.reply_to_message.id
        MediaList[cmd.from_user.id].append(file_id)

        # Confirm addition and offer next steps
        await cmd.message.edit(
            "File added to your batch!\n\n"
            "You can keep adding more files, or press the button below to get the batch link.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Get Batch Link", callback_data="getBatchLink")],
                [InlineKeyboardButton("Close Message", callback_data="closeMessage")]
            ])
        )

    # The 'addToBatchFalse' callback might become redundant if 'main' now auto-generates single links.
    # If you still want a button that explicitly triggers a single link save, keep this:
    elif "addToBatchFalse" in cb_data:
        await save_media_in_channel(bot, editable=cmd.message, message=cmd.message.reply_to_message)
        # You might want to update the message after saving to say "Link generated!"
        # The save_media_in_channel function should ideally handle editing 'editable' with the link.

    # This callback is for generating the final batch link from the collected MediaList.
    elif "getBatchLink" in cb_data:
        message_ids = MediaList.get(cmd.from_user.id, None)
        if message_ids is None or not message_ids: # Check if list is empty or None
            await cmd.answer("Your batch list is empty! Please add files first.", show_alert=True)
            return

        await cmd.message.edit("Please wait, generating batch link ...")
        # This function should update the 'editable' message with the final link
        await save_batch_media_in_channel(bot=bot, editable=cmd.message, message_ids=message_ids)
        MediaList[cmd.from_user.id] = [] # Clear the batch after processing

    # This remains the same, for closing the inline keyboard message.
    elif "closeMessage" in cb_data:
        await cmd.message.delete(True)

    # --- END OF MODIFIED BATCH HANDLING CALLBACKS ---

    try:
        await cmd.answer() # Always answer the callback query to remove the loading animation
    except QueryIdInvalid:
        # This can happen if the message was edited/deleted by another async task
        # or if the query ID has expired. It's safe to just pass here.
        pass

Bot.run()

