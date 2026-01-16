async def save_batch_media_in_channel(bot: Client, editable: Message, message_ids: list):
    try:
        if not Config.DB_CHANNEL:
            await editable.edit("Bot owner has not configured the DB_CHANNEL.")
            return

        # --- UPDATE START: Counting Message with Delay ---
        try:
            # Edit text to "Counting..."
            await editable.edit("Asuran Bot counting your files... 🧐")
            # Wait 1 second so the user actually sees this message
            await asyncio.sleep(1) 
        except Exception:
            # If the edit fails (e.g. rate limit), we just ignore and continue
            pass 
        # --- UPDATE END ---

        message_ids_str = ""
        file_names_list = []
        
        messages_to_process = []
        for msg_id in message_ids:
            try:
                msg = await bot.get_messages(chat_id=editable.chat.id, message_ids=msg_id)
                if msg and msg.media:
                    messages_to_process.append(msg)
            except Exception as e:
                print(f"Error fetching message {msg_id}: {e}")

        if not messages_to_process:
            await editable.edit("No valid media files found in the batch.")
            return
            
        # This will now replace the "Counting" message
        await editable.edit(f"Processing {len(messages_to_process)} files... ⏳")

        for message in messages_to_process:
            # --- NAME EXTRACTION LOGIC ---
            media_name = "Unknown File"
            
            if message.caption:
                media_name = message.caption.splitlines()[0]
            elif message.document and message.document.file_name:
                media_name = message.document.file_name
            elif message.video and message.video.file_name:
                media_name = message.video.file_name
            elif message.audio and message.audio.file_name:
                media_name = message.audio.file_name
            
            sent_message = await forward_to_channel(bot, message, editable)
            if sent_message is None:
                continue
            
            file_names_list.append(f"**{media_name}**")
            
            message_ids_str += f"{str(sent_message.id)} "
            await asyncio.sleep(2) 

        if not message_ids_str.strip():
            await editable.edit("Failed to save files.")
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

        # --- FINAL TEXT GENERATION ---
        files_summary = "\n\n".join(file_names_list)
        
        final_text = (
            f"**{files_summary}\n\n**"
            f"**{share_link}**"
        )
        
        if len(final_text) > 4096:
             final_text = (
                f"**Batch Link Created!** ✅\n\n"
                f"__List contains {len(file_names_list)} files.__\n"
                f"__(Names hidden because the list is too long for Telegram)__\n\n"
                f"**Link:** {share_link}"
            )

        await editable.edit(
            final_text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open Link", url=share_link)],
                 [InlineKeyboardButton("Bots Channel", url="https://telegram.me/AS_botzz"),
                  InlineKeyboardButton("Support Group", url="https://telegram.me/moviekoodu1")]]
            ),
            disable_web_page_preview=True
        )
        
    except Exception as err:
        traceback.print_exc()
        await editable.edit(f"Error: {err}")
