"""
Telethon Account Skills.

Provides tools for profile personalization, managing self-biography, avatars,
adding contacts, and checking external user information.
"""

from typing import Union

from telethon.tl.functions.account import UpdateProfileRequest, UpdatePersonalChannelRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
)

from src.utils.dtime import format_datetime
from src.utils.logger import main_logger
from src.utils._tools import format_size, validate_sandbox_path, parse_int_or_str

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonAccount:
    """Skills for managing profile credentials, avatars, and contacts."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def change_username(self, name: str, surname: str = "") -> SkillResult:
        """
        Changes public profile first and optional last name.
        """

        try:
            client = self.tg_client.client()

            await client(UpdateProfileRequest(first_name=name, last_name=surname))

            # Trigger state update to refresh system context
            await self.tg_client.update_profile_state()

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error changing profile name: {e}")

    @skill()
    async def change_bio(self, text: str) -> SkillResult:
        """
        Changes profile bio.
        Max length 70 characters.
        """

        try:
            client = self.tg_client.client()
            await client(UpdateProfileRequest(about=text))
            await self.tg_client.update_profile_state()

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error changing profile bio: {e}")

    @skill()
    async def change_avatar(self, filepath: str) -> SkillResult:
        """
        Sets new profile avatar.

        filepath: Relative sandbox/ path.
        """

        try:
            safe_path = validate_sandbox_path(filepath)

            if not safe_path.exists():
                return SkillResult.fail(f"Error: Avatar file not found ({safe_path.name}).")

            client = self.tg_client.client()
            uploaded_file = await client.upload_file(str(safe_path))
            await client(UploadProfilePhotoRequest(file=uploaded_file))

            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error changing avatar: {e}")

    @skill()
    async def add_contact(
        self, user_id: Union[int, str], first_name: str, last_name: str = ""
    ) -> SkillResult:
        """
        Adds user to contacts.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(parse_int_or_str(user_id))

            await client(
                AddContactRequest(
                    id=target_entity,
                    first_name=first_name,
                    last_name=last_name,
                    phone="",
                    add_phone_privacy_exception=False,
                )
            )

            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail(
                f"Error: User '{user_id}' not found. Verify ID or username."
            )
        except Exception as e:
            return SkillResult.fail(f"Error adding contact: {e}")

    @skill()
    async def download_avatar(
        self, user_or_chat_id: Union[int, str], dest_filename: str, avatar_index: int = 0
    ) -> SkillResult:
        """
        Downloads user/chat profile photo to sandbox.

        avatar_index: 0 is current, 1 is previous.
        """

        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(user_or_chat_id))

            # Fetch profile photos up to targeted index
            photos = await client.get_profile_photos(entity, limit=avatar_index + 1)

            if not photos or avatar_index >= len(photos):
                count = len(photos) if photos else 0
                return SkillResult.fail(
                    f"Error: Avatar with index {avatar_index} not found. Total available avatars: {count}."
                )

            target_photo = photos[avatar_index]

            main_logger.info(
                f"[Telegram Telethon] Downloading profile photo (index {avatar_index})..."
            )
            downloaded_path = await client.download_media(target_photo, file=str(safe_path))

            if not downloaded_path:
                return SkillResult.fail("Failed to download avatar.")

            size_str = format_size(safe_path.stat().st_size)
            main_logger.info(
                f"[Telegram Telethon] Avatar downloaded: {safe_path.name} ({size_str})"
            )

            return SkillResult.ok(
                f"Avatar downloaded successfully and saved as: sandbox/{safe_path.name} ({size_str})"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except ValueError:
            return SkillResult.fail("Error: User or chat not found.")
        except Exception as e:
            return SkillResult.fail(f"Error downloading avatar: {e}")

    @skill()
    async def get_user_info(self, user_id: Union[int, str]) -> SkillResult:
        """
        Returns detailed info about specific user.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(parse_int_or_str(user_id))

            full_user = await client(GetFullUserRequest(target_entity))
            user = full_user.users[0]

            lines = [f"User profile details for {user_id}:"]
            lines.append(f"Name: {user.first_name or ''} {user.last_name or ''}".strip())

            if user.username:
                lines.append(f"Username: @{user.username}")

            if full_user.full_user.about:
                lines.append(f"Bio: {full_user.full_user.about}")

            # Parsing network status
            status_str = "Hidden / Restricted by privacy settings"
            if isinstance(user.status, UserStatusOnline):
                status_str = "Online"
            elif isinstance(user.status, UserStatusOffline):
                dt_str = format_datetime(user.status.was_online, self.tg_client.timezone)
                status_str = f"Last seen: {dt_str}"
            elif isinstance(user.status, UserStatusRecently):
                status_str = "Last seen recently"
            elif isinstance(user.status, UserStatusLastWeek):
                status_str = "Last seen within a week"
            elif isinstance(user.status, UserStatusLastMonth):
                status_str = "Last seen within a month"

            lines.append(f"Status: {status_str}")

            if user.bot:
                lines.append("Profile Type: Bot")
            if user.restricted:
                lines.append("[Attention: Account is restricted by Telegram]")
            if user.scam or user.fake:
                lines.append("[Attention: Account has SCAM or FAKE label]")

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail("Error: User not found. Please verify ID or username.")
        except Exception as e:
            return SkillResult.fail(f"Error fetching user info: {e}")

    @skill()
    async def set_personal_channel(self, channel_id: Union[int, str]) -> SkillResult:
        """
        Sets specified channel as personal (shows in bio).
        Pass empty string to remove.
        """

        try:
            client = self.tg_client.client()

            if not channel_id or str(channel_id).strip() == "":
                target_entity = None
            else:
                target_entity = await client.get_input_entity(parse_int_or_str(channel_id))

            await client(UpdatePersonalChannelRequest(channel=target_entity))

            # Trigger state update
            await self.tg_client.update_profile_state()

            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail(
                f"Error: Channel '{channel_id}' not found. Verify ID or username."
            )
        except Exception as e:
            if "CHANNEL_PRIVATE" in str(e):
                return SkillResult.fail(
                    "Error: Channel is private, or you do not have permission to access it."
                )
            return SkillResult.fail(f"Error updating personal channel: {e}")
