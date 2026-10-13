from typing import Optional, List
from vkBot import Bot, Message


class MessageCopier:
    """
    Класс для копирования сообщений (полная републикация контента)
    без использования пересылки.
    """
    def __init__(self, bot: Bot):
        self.bot = bot
        # self.session = aiohttp.ClientSession()

    async def copy_message(
        self,
        source_message: Message,
        target_peer_ids: Optional[List[int]] = None,
        target_peer_id: Optional[int] = None,
        target_message: Optional[str] = None
    ) -> bool:
        """
        Копирует сообщение в указанную беседу, создавая независимые копии вложений.
        
        Args:
            source_message: Исходное сообщение
            target_peer_id: ID целевого чата/пользователя
            target_message: Дополнительный текст к копии
            
        Returns:
            True в случае успеха, False при ошибке
        """
        try:
            # Получаем полную информацию о сообщении с вложениями
            full_message = await source_message.get_full_message()
            attachments = []

            # Обрабатываем каждое вложение по типу
            for attachment in full_message.attachments:
                attachment_type = attachment.type
                
                if attachment_type == "photo":
                    photo_att = await self._copy_photo(attachment.photo)
                    if photo_att:
                        attachments.append(photo_att)
                
                elif attachment_type == "doc":
                    doc_att = await self._copy_document(attachment.doc)
                    if doc_att:
                        attachments.append(doc_att)
                
                elif attachment_type == "video":
                    video_att = await self._copy_video(attachment.video)
                    if video_att:
                        attachments.append(video_att)
                
                elif attachment_type == "audio":
                    audio_att = await self._copy_audio(attachment.audio)
                    if audio_att:
                        attachments.append(audio_att)
                
                elif attachment_type == "graffiti":
                    graffiti_att = await self._copy_graffiti(attachment.graffiti)
                    if graffiti_att:
                        attachments.append(graffiti_att)
                
                elif attachment_type == "sticker":
                    # Стикеры можно копировать только прямым ID
                    sticker_att = self._copy_sticker(attachment.sticker)
                    return await self.bot.api.messages.send(
                            peer_ids=target_peer_ids,
                            peer_id=target_peer_id,
                            sticker_id=sticker_att,
                            random_id=0
                        )

            # Формируем текст сообщения
            text = target_message or source_message.text
            
            # Если нет текста и нет вложений, пропускаем
            if not text and not attachments:
                return False

            # Отправляем скопированное сообщение
            await self.bot.api.messages.send(
                peer_ids=target_peer_ids,
                peer_id=target_peer_id,
                message=text,
                attachment=",".join(attachments) if attachments else None,
                random_id=0,
            )
            return True

        except Exception as e:
            print(f"Ошибка копирования сообщения: {e}")
            return False

    # ========== Методы копирования отдельных типов вложений ==========

    async def _copy_photo(self, photo_obj) -> Optional[str]:
        """Копирование фотографии через перезагрузку"""
        try:
            # Получаем URL оригинала (самый большой размер)
            if hasattr(photo_obj, "sizes") and photo_obj.sizes:
                # Берем последний (самый большой) размер
                original_url = photo_obj.sizes[-1].url
            else:
                # Fallback: используем прямые ссылки из объекта
                original_url = photo_obj.url if hasattr(photo_obj, "url") else None
            
            if not original_url:
                return None

            # Скачиваем файл во временную память
            # async with aiohttp.ClientSession() as session:
            #     async with session.get(original_url) as resp:
            #         if resp.status == 200:
            #             file_bytes = await resp.read()
            
            # # Загружаем как новое фото через uploader
            # uploader = PhotoMessageUploader(self.bot.api)
            # attachment = await uploader.upload(file_source=file_bytes)
            # return attachment

        except Exception as e:
            print(f"Ошибка копирования фото: {e}")
            return None

    async def _copy_document(self, doc_obj) -> Optional[str]:
        """Копирование документа"""
        try:
            # Получаем URL документа
            doc_url = doc_obj.url if hasattr(doc_obj, "url") else None
            if not doc_url:
                return None

            # Скачиваем файл
            # async with aiohttp.ClientSession() as session:
            #     async with session.get(doc_url) as resp:
            #         if resp.status == 200:
            #             file_bytes = await resp.read()
            # # file_bytes = await download_file(doc_url, self.session)
            
            # # Загружаем как новый документ
            # uploader = DocMessagesUploader(self.bot.api)
            # attachment = await uploader.upload(
            #     file_source=file_bytes,
            #     title=getattr(doc_obj, "title", "document"),
            # )
            # return attachment

        except Exception as e:
            print(f"Ошибка копирования документа: {e}")
            return None

    async def _copy_video(self, video_obj) -> Optional[str]:
        """Копирование видео"""
        try:
            # Для видео используем прямой метод републикации
            # Видео принадлежит пользователю, бот не может его скачать
            
            # Получаем идентификаторы видео
            owner_id = getattr(video_obj, "owner_id", None)
            video_id = getattr(video_obj, "id", None)
            
            if owner_id and video_id:
                # Републикуем видео на стену бота
                result = await self.bot.api.video.repost(
                    video_id=video_id,
                    owner_id=owner_id,
                )
                # Получаем новое видео бота
                if hasattr(result, "owner_id"):
                    return f"video{result.owner_id}_{result.video_id}"
            
            return None

        except Exception as e:
            print(f"Ошибка копирования видео: {e}")
            return None

    async def _copy_audio(self, audio_obj) -> Optional[str]:
        """Копирование аудиозаписи"""
        try:
            # Аудиозаписи могут копироваться пользователем, но не ботом
            # Единственный способ - републикация
            owner_id = getattr(audio_obj, "owner_id", None)
            audio_id = getattr(audio_obj, "id", None)
            
            if owner_id and audio_id:
                # Сохраняем аудио в аудиозаписи бота (требуются права аудио)
                # !!! Требуется отдельное расширенное разрешение от пользователя
                # и статус standalone-приложения
                # Для обычного бота этот метод недоступен
                return f"audio{owner_id}_{audio_id}"
            
            return None

        except Exception as e:
            print(f"Ошибка копирования аудио: {e}")
            return None

    async def _copy_graffiti(self, graffiti_obj) -> Optional[str]:
        """Копирование граффити"""
        try:
            # Граффити обрабатывается как документ
            # if hasattr(graffiti_obj, "url"):
            #     async with aiohttp.ClientSession() as session:
            #         async with session.get(graffiti_obj.url) as resp:
            #             if resp.status == 200:
            #                 file_bytes = await resp.read()
                
            #     uploader = GraffitiUploader(self.bot.api)
            #     attachment = await uploader.upload(file_source=file_bytes)
            #     return attachment
            
            return None

        except Exception as e:
            print(f"Ошибка копирования граффити: {e}")
            return None

    def _copy_sticker(self, sticker_obj) -> Optional[str]:
        """Копирование стикера (прямая ссылка)"""
        try:
            # Стикеры копируются через прямой ID
            # Убеждаемся, что ID корректен для отправки
            return getattr(sticker_obj, "sticker_id", None)
        except Exception as e:
            print(f"Ошибка копирования стикера: {e}")
            return None



# ========== ИНТЕГРАЦИЯ С БОТОМ ==========

# Создаем экземпляр бота
# bot = Bot(token="YOUR_GROUP_TOKEN")
# message_copier = MessageCopier(bot)


# @bot.on.message(text="/copy")
# async def copy_command_handler(message: Message):
#     """
#     Команда для копирования сообщения с REPLY (ответом)
#     Использование: /copy в ответ на сообщение
#     """
#     # Проверяем, есть ли ответное сообщение
#     reply_msg = message.reply_message
#     if not reply_msg:
#         await message.answer(
#             "❌ Чтобы скопировать сообщение, ответьте на него командой /copy"
#         )
#         return
    
#     # Целевой чат (можно указать другой ID)
#     target_peer_id = message.peer_id  # копируем в этот же чат
    
#     # Выполняем копирование
#     success = await message_copier.copy_message(
#         source_message=reply_msg,
#         target_peer_id=target_peer_id,
#         target_message="📋 Копия сообщения:"
#     )
    
#     if success:
#         await message.answer("✅ Сообщение успешно скопировано!")
#     else:
#         await message.answer("❌ Не удалось скопировать сообщение")


# @bot.on.message(text="/copyto <peer_id>")
# async def copy_to_command_handler(message: Message, peer_id: int):
#     """
#     Копирование сообщения в другую беседу
#     Использование: /copyto 2000000001 в ответ на сообщение
#     """
#     reply_msg = message.reply_message
#     if not reply_msg:
#         await message.answer(
#             "❌ Ответьте на сообщение, которое хотите скопировать"
#         )
#         return
    
#     success = await message_copier.copy_message(
#         source_message=reply_msg,
#         target_peer_id=peer_id,
#         target_message=f"📋 Копия из беседы {message.peer_id}"
#     )
    
#     if success:
#         await message.answer(f"✅ Сообщение скопировано в беседу {peer_id}")
#     else:
#         await message.answer("❌ Ошибка при копировании")


# # Закрытие сессии при остановке бота
# @bot.on.shutdown
# async def shutdown_handler():
#     await message_copier.close()

