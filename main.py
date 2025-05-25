import os
import sys
import re
import subprocess
import asyncio
import datetime
import traceback
from typing import Dict, Any, Tuple, Optional, List
from uuid import uuid4
from urllib.parse import urlparse
import aiohttp
import yt_dlp

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    LabeledPrice,
    constants,
    User,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    PicklePersistence,
    Defaults,
)
from telegram.error import TelegramError, Forbidden


# --- Configuration & Constants ---
BOT_TOKEN = "BOT_TOKEN_HERE"

# Owner and Admin IDs
OWNER_ID = 123456789  # Replace with your actual Telegram user ID
ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin user IDs

# Bot Settings
SUPPORT_CONTACT = "@FairyRoot"
DOWNLOAD_DIR = "bot_downloads"

# User Roles
ROLE_ADMIN = "admin"
ROLE_PREMIUM = "premium"
ROLE_STANDARD = "standard"
ROLE_BANNED = "banned"

# Download & File Size Limits
STANDARD_USER_DAILY_DOWNLOADS = 5
STANDARD_USER_FILE_SIZE_LIMIT_MB = 25.0
PREMIUM_ADMIN_DIRECT_SEND_LIMIT_MB = 49.5


# Premium Tiers (Telegram Stars)
PREMIUM_PRICES = {
    "3_days": {
        "stars": 50,
        "days": 3,
        "title": "Premium (3 Days)",
        "description": "3 days of unlimited downloads",
    },
    "30_days": {
        "stars": 250,
        "days": 30,
        "title": "Premium (30 Days)",
        "description": "30 days of unlimited downloads",
    },
    "365_days": {
        "stars": 1500,
        "days": 365,
        "title": "Premium (1 Year)",
        "description": "1 year of unlimited downloads",
    },
}

# Persistence Keys
CHANNEL_SUBSCRIPTION_CONFIG_KEY = "channel_subscription_config"
BANNED_USERS_KEY = "banned_user_ids"

# yt-dlp Constants
MAX_RETRIES_YTDLP = 3
RETRY_DELAY_YTDLP = 5
USER_AGENT_YTDLP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Other Constants
URL_REGEX = r"(?:(?:https?|ftp):\/\/)?(?:\S+(?::\S*)?@)?(?:(?!10(?:\.\d{1,3}){3})(?!127(?:\.\d{1,3}){3})(?!169\.254(?:\.\d{1,3}){2})(?!192\.168(?:\.\d{1,3}){2})(?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])(?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}(?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))|(?:(?:[a-z\u00a1-\uffff0-9]+-?)*[a-z\u00a1-\uffff0-9]+)(?:\.(?:[a-z\u00a1-\uffff0-9]+-?)*[a-z\u00a1-\uffff0-9]+)*(?:\.(?:[a-z\u00a1-\uffff]{2,})))(?::\d{2,5})?(?:\/[^\s]*)?"
TIKTOK_HOSTNAMES = ["tiktok.com", "www.tiktok.com", "vm.tiktok.com"]

# Persistence Setup
PERSISTENCE = PicklePersistence(filepath="bot_persistence.pickle")


# --- Utility Functions ---
def sanitize_filename(filename: str, max_length: int = 60) -> str:
    sane = re.sub(r'[\\/*?:"<>|]', "_", filename).strip(" .")
    sane = "".join(c for c in sane if c.isprintable() or c == " ")
    sane = re.sub(r"\s+", "_", sane)
    sane = re.sub(r"__+", "_", sane)
    return sane[:max_length] if sane else "downloaded_media"


try:
    FFMPEG_AVAILABLE = (
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        ).returncode
        == 0
    )
except FileNotFoundError:
    FFMPEG_AVAILABLE = False
except subprocess.TimeoutExpired:
    FFMPEG_AVAILABLE = False
    print("WARNING: FFmpeg check timed out.")
if FFMPEG_AVAILABLE:
    print("FFmpeg found and working.")
else:
    print(
        "WARNING: FFmpeg check failed or FFmpeg not found. Some features might be affected."
    )


async def fetch_http_content(
    session: aiohttp.ClientSession, url: str
) -> Optional[bytes]:
    try:
        async with session.get(url, timeout=30) as response:
            response.raise_for_status()
            return await response.read()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


# --- Core Download Logic ---
def download_media_ytdlp(
    url: str, output_dir: str, format_choice: str = "video", user_id: int = 0
) -> Tuple[bool, str, Optional[str], Optional[Dict[str, Any]]]:
    os.makedirs(output_dir, exist_ok=True)
    unique_prefix = uuid4().hex[:8]
    ydl_initial_info_opts = {
        "quiet": True,
        "no_warnings": True,
        "simulate": True,
        "extract_flat": False,
        "useragent": USER_AGENT_YTDLP,
        "skip_download": True,
        "verbose": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_initial_info_opts) as ydl_info_fetch:
            media_info = ydl_info_fetch.extract_info(url, download=False)
        if not media_info:
            return False, "Could not retrieve media information.", None, None
    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e).lower()
        if "unsupported url" in err_msg:
            return False, "Invalid or unsupported URL.", None, None
        return False, f"Error fetching media info: {e}", None, None
    except Exception as e:
        print(f"Unexpected YTDLP info error for {url} (User: {user_id}): {e}")
        return False, f"Unexpected error fetching media info: {e}", None, None

    title = media_info.get("title", "media")
    sanitized_title = sanitize_filename(title)
    base_filename = f"{unique_prefix}_{sanitized_title}"
    ydl_download_opts = {
        "quiet": True,
        "no_warnings": True,
        "useragent": USER_AGENT_YTDLP,
        "retries": MAX_RETRIES_YTDLP,
        "fragment_retries": MAX_RETRIES_YTDLP,
        "retry_sleep_functions": {
            "http": lambda n: RETRY_DELAY_YTDLP,
            "fragment": lambda n: RETRY_DELAY_YTDLP,
        },
        "outtmpl": os.path.join(output_dir, f"{base_filename}.%(ext)s"),
    }
    if format_choice == "video":
        ydl_download_opts["format"] = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best"
        )
        if FFMPEG_AVAILABLE:
            ydl_download_opts["merge_output_format"] = "mp4"
    elif format_choice == "audio":
        ydl_download_opts["format"] = "bestaudio/best"

    predicted_path = None
    try:
        temp_sim_opts = ydl_download_opts.copy()
        temp_sim_opts.update(
            {"simulate": True, "skip_download": True, "quiet": True, "verbose": False}
        )
        with yt_dlp.YoutubeDL(temp_sim_opts) as ydl_sim:
            sim_info = ydl_sim.extract_info(url, download=False)
            if sim_info and sim_info.get("requested_downloads"):
                predicted_path = sim_info["requested_downloads"][0]["filepath"]
            elif sim_info and sim_info.get("filename"):
                predicted_path = sim_info["filename"]
            else:
                ext = media_info.get(
                    "ext", "mp4" if format_choice == "video" else "m4a"
                )
                predicted_path = os.path.join(output_dir, f"{base_filename}.{ext}")
    except Exception as e_sim:
        print(
            f"WARNING: Filename prediction via simulation failed: {e_sim}. Using fallback."
        )
        ext = media_info.get("ext", "mp4" if format_choice == "video" else "m4a")
        predicted_path = os.path.join(output_dir, f"{base_filename}.{ext}")

    hook_data = {"actual_path": None}

    def _hook(d):
        if d["status"] == "finished":
            hook_data["actual_path"] = d["filename"]

    ydl_download_opts.update(
        {"progress_hooks": [_hook], "quiet": False, "verbose": False}
    )

    try:
        with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
            ydl.download([url])
        final_path_to_check = None
        actual_hook_path_val = hook_data["actual_path"]
        if actual_hook_path_val and os.path.exists(actual_hook_path_val):
            final_path_to_check = actual_hook_path_val
        elif predicted_path and os.path.exists(predicted_path):
            final_path_to_check = predicted_path
        else:
            possible_files = [
                f for f in os.listdir(output_dir) if f.startswith(base_filename)
            ]
            if possible_files:
                final_path_to_check = os.path.join(output_dir, possible_files[0])
        if final_path_to_check and os.path.exists(final_path_to_check):
            return True, "Download successful.", final_path_to_check, media_info
        print(
            f"ERROR: Download finished but final file not confirmed. Predicted='{predicted_path}', Hook='{actual_hook_path_val}'"
        )
        return (
            False,
            "Download completed, but final file path not confirmed.",
            None,
            media_info,
        )
    except yt_dlp.utils.DownloadError as e:
        print(f"ERROR: YTDLP DownloadError for {url} (User: {user_id}): {e}")
        return False, f"Failed to download: {e}", None, media_info
    except Exception as e:
        print(f"ERROR: Unexpected YTDLP error for {url} (User: {user_id}): {e}")
        return False, f"Unexpected download error: {type(e).__name__}", None, media_info


# --- User & Role Management ---
def get_user_role(
    user_id_to_check: int,
    context: ContextTypes.DEFAULT_TYPE,
    current_effective_user: Optional[User],
    for_display: bool = False,
) -> str:
    if user_id_to_check in context.bot_data.get(BANNED_USERS_KEY, set()):
        return ROLE_BANNED

    ud: Dict[str, Any]
    is_current_user_context = False

    if current_effective_user and user_id_to_check == current_effective_user.id:
        master_ud = context.application.persistence.user_data.get(user_id_to_check, {})
        premium_fields = ["is_premium", "premium_expiry_timestamp", "premium_tier"]
        for field in premium_fields:
            if field in master_ud:
                context.user_data[field] = master_ud[field]
            else:
                context.user_data.pop(field, None)
        context.user_data.setdefault("_id", user_id_to_check)
        ud = context.user_data
        is_current_user_context = True
    else:
        ud = context.application.persistence.user_data.get(user_id_to_check, {})

    if user_id_to_check in ADMIN_IDS:
        return ROLE_ADMIN

    premium_expiry_ts = ud.get("premium_expiry_timestamp")
    is_premium_flag = ud.get("is_premium", False)
    is_currently_premium = (
        is_premium_flag
        and premium_expiry_ts
        and premium_expiry_ts > datetime.datetime.now().timestamp()
    )

    if is_currently_premium:
        return ROLE_PREMIUM

    if not for_display and is_current_user_context:
        if ud.get("is_premium") or ud.get("premium_expiry_timestamp") is not None:
            ud.update(
                {
                    "is_premium": False,
                    "premium_expiry_timestamp": None,
                    "premium_tier": (
                        ud.get("premium_tier")
                        if str(ud.get("premium_tier", "")).startswith(
                            ("admin_", "revoked_")
                        )
                        else "expired_or_cleaned"
                    ),
                }
            )
    return ROLE_STANDARD


def check_and_update_daily_limit(
    user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    ud = context.user_data
    today = datetime.date.today().isoformat()
    ud.setdefault(
        "last_download_date",
        (datetime.date.today() - datetime.timedelta(days=1)).isoformat(),
    )
    ud.setdefault("daily_downloads_count", 0)
    if ud.get("last_download_date") != today:
        ud.update({"last_download_date": today, "daily_downloads_count": 0})
    if ud.get("daily_downloads_count", 0) < STANDARD_USER_DAILY_DOWNLOADS:
        ud["daily_downloads_count"] = ud.get("daily_downloads_count", 0) + 1
        return True
    return False


def revert_daily_limit_decrement(context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    if (
        ud.get("last_download_date") == datetime.date.today().isoformat()
        and ud.get("daily_downloads_count", 0) > 0
    ):
        ud["daily_downloads_count"] -= 1


async def get_channel_config(context: ContextTypes.DEFAULT_TYPE) -> Dict[str, Any]:
    return context.bot_data.get(
        CHANNEL_SUBSCRIPTION_CONFIG_KEY, {"enabled": False, "channels": []}
    )


async def set_channel_config(
    enabled: bool, channels: List[str], context: ContextTypes.DEFAULT_TYPE
):
    context.bot_data[CHANNEL_SUBSCRIPTION_CONFIG_KEY] = {
        "enabled": enabled,
        "channels": channels,
    }
    await context.application.persistence.flush()


async def check_channel_join(
    user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> Tuple[bool, Optional[str]]:
    config = await get_channel_config(context)
    if not config.get("enabled") or not config.get("channels"):
        return True, None
    missing_channels = []
    for ch_id_str in config["channels"]:
        try:
            ch_to_check = (
                str(ch_id_str) if not str(ch_id_str).startswith("@") else ch_id_str
            )
            if not await _is_user_in_channel(user_id, ch_to_check, context):
                missing_channels.append(ch_id_str)
        except Exception as e:
            print(f"WARNING: Error processing channel {ch_id_str} for join check: {e}")
            missing_channels.append(f"{ch_id_str} (config error?)")
    return (
        (False, f"Please join: {', '.join(missing_channels)}")
        if missing_channels
        else (True, None)
    )


async def _is_user_in_channel(
    user_id: int, channel_identifier: str, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    try:
        member = await context.bot.get_chat_member(
            chat_id=channel_identifier, user_id=user_id
        )
        return member.status in [
            constants.ChatMemberStatus.MEMBER,
            constants.ChatMemberStatus.ADMINISTRATOR,
            constants.ChatMemberStatus.CREATOR,
        ]
    except TelegramError as e:
        if isinstance(e, Forbidden):
            print(
                f"ERROR: Forbidden: Bot may not be an admin in channel {channel_identifier} or channel is inaccessible. Cannot check membership for user {user_id}."
            )
        else:
            print(
                f"WARNING: Failed to check membership for user {user_id} in {channel_identifier}: {e}"
            )
        return False


# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    context.user_data.setdefault("_id", user.id)
    role_name = get_user_role(user.id, context, user).capitalize()
    await context.application.persistence.flush()
    welcome_msg = (
        f"👋 Hello {user.mention_html()}!\n\n"
        "I'm your media downloader bot. Send me a link from supported platforms, and I'll fetch it for you!\n\n"
        f"✨ **Your Current Status:** {role_name}\n"
        "Type /help to see all available commands and learn more about what I can do.\n"
        "Happy downloading! 📥"
    )
    await update.message.reply_html(welcome_msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    effective_user = update.effective_user
    if not effective_user:
        return
    user_role_for_display = get_user_role(
        effective_user.id, context, effective_user, for_display=True
    )
    base_help = (
        "🌟 **Welcome to the Media Downloader Bot!** 🌟\n\n"
        "Here's how I can help you:\n"
        "1. Send me a link to a video or audio from platforms like TikTok, YouTube, Instagram, etc.\n"
        "2. I'll process it and send back the media file for you to save!\n\n"
        "🔗 **Available Commands for Everyone:**\n"
        "  /start - Initialize or restart the bot.\n"
        "  /help - Show this help message.\n"
        "  /myrole - Check your current user status, limits, and premium days.\n"
        "  /premium - Explore options to upgrade to Premium for more features!\n"
        f"  /support - Need help? Contact {SUPPORT_CONTACT}.\n\n"
    )
    standard_limits_info = (
        "💡 **Standard User Info:**\n"
        f"  - Download up to {STANDARD_USER_DAILY_DOWNLOADS} files per day.\n"
        f"  - Limited to TikTok videos only.\n"
        f"  - Video format only.\n"
        f"  - Max file size: {STANDARD_USER_FILE_SIZE_LIMIT_MB:.0f}MB.\n"
        "  Consider /premium for an unrestricted experience!\n"
    )
    premium_perks_info = (
        "💎 **Premium User Perks:**\n"
        "  - Unlimited daily downloads!\n"
        "  - Download from a wider range of platforms.\n"
        "  - Download audio & video formats.\n"
        "  - Higher file size limits (up to Telegram's max for direct send).\n"
    )
    final_help_msg = base_help
    is_admin_for_commands = effective_user.id in ADMIN_IDS
    ud_for_perks = context.user_data
    is_premium_active_for_perks = False
    if ud_for_perks.get("is_premium"):
        exp_ts_perks = ud_for_perks.get("premium_expiry_timestamp")
        if exp_ts_perks and exp_ts_perks > datetime.datetime.now().timestamp():
            is_premium_active_for_perks = True
    if user_role_for_display == ROLE_STANDARD and not is_admin_for_commands:
        final_help_msg += standard_limits_info
    elif user_role_for_display == ROLE_PREMIUM or (
        is_admin_for_commands and is_premium_active_for_perks
    ):
        final_help_msg += premium_perks_info
    if is_admin_for_commands:
        final_help_msg += (
            "\n👑 **Admin Exclusive Commands:**\n"
            "  /broadcast `[reply to message]` - Send message to all users.\n"
            "  /setuserpremium `[user_id] [days]` - Grant premium status.\n"
            "  /removeuserpremium `[user_id]` - Revoke premium status.\n"
            "  /banuser `[user_id]` - Ban a user.\n"
            "  /unbanuser `[user_id]` - Unban a user.\n"
            "  /togglechannelcheck - Enable/disable mandatory channel join.\n"
            "  /setrequiredchannels `[@ch1 ID2...]` or `none` - Set channels.\n"
            "  /stats - View bot usage statistics.\n"
            "  /viewusers - List users with details.\n"
        )
    await update.message.reply_html(final_help_msg)


async def myrole_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    role_actual = get_user_role(user_id, context, user)
    await context.application.persistence.flush()
    display_role = role_actual.capitalize()
    is_premium_active = False
    ud = context.user_data
    if ud.get("is_premium"):
        exp_ts = ud.get("premium_expiry_timestamp")
        if exp_ts and exp_ts > datetime.datetime.now().timestamp():
            is_premium_active = True
            if role_actual == ROLE_ADMIN:
                display_role = "Admin (Premium)"
    msg = [
        f"👤 **User ID:** <code>{user_id}</code>",
        f"🏅 **Role:** <b>{display_role}</b>",
    ]
    if is_premium_active:
        exp_ts = ud.get("premium_expiry_timestamp")
        if exp_ts:
            remaining_time_delta = (
                datetime.datetime.fromtimestamp(exp_ts) - datetime.datetime.now()
            )
            days, rem_secs = divmod(remaining_time_delta.total_seconds(), 86400)
            hours, rem_secs = divmod(rem_secs, 3600)
            minutes = rem_secs // 60
            msg.append(
                f"⏳ **Premium Expires In:** {int(days)}d {int(hours)}h {int(minutes)}m"
            )
    elif role_actual == ROLE_STANDARD:
        today = datetime.date.today().isoformat()
        ud.setdefault("daily_downloads_count", 0)
        ud.setdefault(
            "last_download_date",
            (datetime.date.today() - datetime.timedelta(days=1)).isoformat(),
        )
        if ud.get("last_download_date") != today:
            ud["daily_downloads_count"] = 0
        dl_today = ud.get("daily_downloads_count", 0)
        rem_dl = max(0, STANDARD_USER_DAILY_DOWNLOADS - dl_today)
        msg.extend(
            [
                f"📥 **Downloads Today:** {dl_today}/{STANDARD_USER_DAILY_DOWNLOADS} (Remaining: {rem_dl})",
                f"⚠️ **Restrictions:** TikTok videos only, video format only, max {STANDARD_USER_FILE_SIZE_LIMIT_MB:.0f}MB.",
            ]
        )
    await update.message.reply_html("\n".join(msg))


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        f"For assistance, please contact our support: {SUPPORT_CONTACT}"
    )


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [
            InlineKeyboardButton(
                f"{info['title']} - {info['stars']} Stars",
                callback_data=f"BUY_PREMIUM_{key}",
            )
        ]
        for key, info in PREMIUM_PRICES.items()
    ]
    await update.message.reply_html(
        "🌟 **Unlock Premium Features!** 🌟\n\n"
        "Enjoy unlimited downloads, access to more platforms, audio downloads, and larger file sizes.\n"
        "Choose your plan:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def is_tiktok_url(url_string: str) -> bool:
    try:
        parsed_url = urlparse(url_string.lower())
        return parsed_url.hostname in TIKTOK_HOSTNAMES
    except Exception:
        return False


async def process_url_from_message(
    url: str, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    role = get_user_role(user_id, context, user)
    await context.application.persistence.flush()
    if role == ROLE_BANNED:
        await update.message.reply_text("You are banned from using this bot.")
        return
    is_admin_check = user_id in ADMIN_IDS
    is_premium_active_check = False
    if context.user_data.get("is_premium"):
        exp_ts = context.user_data.get("premium_expiry_timestamp")
        if exp_ts and exp_ts > datetime.datetime.now().timestamp():
            is_premium_active_check = True
    allow_all = is_admin_check or is_premium_active_check
    if role == ROLE_STANDARD and not allow_all:
        can_download, reason = await _can_standard_user_download(user_id, url, context)
        if not can_download:
            await update.message.reply_html(reason or "Download not allowed")
            return
    context.user_data.update(
        {
            "current_url_to_download": url,
            "last_message_id_for_url": update.message.message_id,
        }
    )
    buttons = [[InlineKeyboardButton("🎬 Video", callback_data="dl_video")]]
    if allow_all:
        buttons[0].append(
            InlineKeyboardButton("🎵 Audio (Original)", callback_data="dl_audio")
        )
    message_text = "Choose your desired format:"
    if role == ROLE_STANDARD and not allow_all:
        message_text = (
            "Choose your desired format (TikTok video only for standard users):"
        )
    await update.message.reply_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        reply_to_message_id=update.message.message_id,
        parse_mode=constants.ParseMode.HTML,
    )


async def _can_standard_user_download(
    user_id: int, url: str, context: ContextTypes.DEFAULT_TYPE
) -> Tuple[bool, Optional[str]]:
    joined, ch_msg = await check_channel_join(user_id, context)
    if not joined:
        return False, ch_msg or "Please join our channel(s) to continue."
    if not is_tiktok_url(url):
        return (
            False,
            "Standard users can only download from TikTok. /premium for all supported sources.",
        )
    return True, None


async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (
        not update.message
        or not (update.message.text or update.message.caption)
        or not update.effective_user
    ):
        return
    text_to_search = update.message.text or update.message.caption
    urls_from_entities = [
        text_to_search[e.offset : e.offset + e.length]
        for el in [update.message.entities, update.message.caption_entities]
        if el
        for e in el
        if e.type == constants.MessageEntityType.URL
    ]
    found_urls = urls_from_entities or re.findall(URL_REGEX, text_to_search)
    if not found_urls:
        if (
            update.message.chat.type == constants.ChatType.PRIVATE
            and not text_to_search.startswith("/")
        ):
            await update.message.reply_text(
                "Please send a valid media link to download."
            )
        return
    url_to_process = found_urls[0].strip()
    if not url_to_process.startswith(("http://", "https://")):
        url_to_process = "https://" + url_to_process
    await process_url_from_message(url_to_process, update, context)


def format_media_caption(
    info: Optional[Dict[str, Any]], source_url: Optional[str] = None
) -> str:
    if not info:
        return ""
    title = info.get("title", "Media")
    uploader = info.get("uploader")
    duration_s = info.get("duration")
    parts = []
    if title:
        parts.append(f"🎬 <b>{title[:100]}{'...' if len(title) > 100 else ''}</b>")
    if uploader:
        parts.append(f"👤 <i>{uploader[:50]}</i>")
    if duration_s:
        try:
            mins, secs = divmod(int(duration_s), 60)
            parts.append(f"⏱️ {mins:02d}:{secs:02d}")
        except (ValueError, TypeError):
            pass
    caption = "\n".join(parts)
    return caption[:1020] + "..." if len(caption) > 1020 else caption


async def download_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not user:
        return
    choice = query.data
    format_type = "video" if choice == "dl_video" else "audio"
    url = context.user_data.get("current_url_to_download")
    if not url:
        try:
            await query.edit_message_text(
                "Error: URL context lost. Please send the link again."
            )
        except TelegramError:
            await context.bot.send_message(
                query.message.chat_id,
                "Error: URL context lost. Please send the link again.",
            )
        return
    user_id = user.id
    role = get_user_role(user_id, context, user)
    await context.application.persistence.flush()
    if role == ROLE_BANNED:
        try:
            await query.edit_message_text(
                "You are currently banned from using this service."
            )
        except TelegramError:
            pass
            return
    is_admin = user_id in ADMIN_IDS
    is_premium_active = False
    if context.user_data.get("is_premium"):
        exp_ts = context.user_data.get("premium_expiry_timestamp")
        if exp_ts and exp_ts > datetime.datetime.now().timestamp():
            is_premium_active = True
    can_download_audio = is_admin or is_premium_active
    is_standard_non_privileged = role == ROLE_STANDARD and not can_download_audio
    standard_user_limit_decremented_this_attempt = False
    if is_standard_non_privileged:
        if format_type == "audio":
            try:
                await query.edit_message_text(
                    "Standard users can only download videos. /premium for audio!"
                )
            except TelegramError:
                pass
                return
        if not check_and_update_daily_limit(user_id, context):
            try:
                await query.edit_message_text(
                    f"Daily download limit ({STANDARD_USER_DAILY_DOWNLOADS}) reached. /premium for more!"
                )
            except TelegramError:
                pass
                return
        standard_user_limit_decremented_this_attempt = True
        await context.application.persistence.flush()

    status_message_text = f"⏳ Preparing to download {format_type}..."
    try:
        await query.edit_message_text(text=status_message_text)
    except TelegramError as e:
        print(f"Error editing message in download_format_callback: {e}")

    file_path_final = None
    media_info_from_ytdlp = None
    download_successful_flag = False
    orig_msg_id_for_reply = context.user_data.get("last_message_id_for_url")

    try:
        success, message, file_path_final, media_info_from_ytdlp = (
            await asyncio.to_thread(
                download_media_ytdlp, url, DOWNLOAD_DIR, format_type, user_id
            )
        )
        if success and file_path_final and os.path.exists(file_path_final):
            file_size_mb = os.path.getsize(file_path_final) / (1024 * 1024)
            caption = format_media_caption(media_info_from_ytdlp, url)
            current_user_size_limit = (
                STANDARD_USER_FILE_SIZE_LIMIT_MB
                if is_standard_non_privileged
                else PREMIUM_ADMIN_DIRECT_SEND_LIMIT_MB
            )
            if file_size_mb > current_user_size_limit:
                size_err_msg = (
                    f"✅ Downloaded: {os.path.basename(file_path_final)}\n"
                    f"⚠️ File size ({file_size_mb:.2f}MB) exceeds your current limit of {current_user_size_limit:.0f}MB."
                )
                if is_standard_non_privileged:
                    size_err_msg += "\nUpgrade to /premium for larger files."
                else:
                    size_err_msg += "\n(Telegram's practical limit for direct bot uploads is ~50MB)."
                try:
                    await query.edit_message_text(size_err_msg)
                except TelegramError:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=size_err_msg,
                        reply_to_message_id=orig_msg_id_for_reply,
                    )
                if standard_user_limit_decremented_this_attempt:
                    revert_daily_limit_decrement(context)
            else:
                send_action = (
                    context.bot.send_video
                    if format_type == "video"
                    else context.bot.send_audio
                )
                media_kw = "video" if format_type == "video" else "audio"
                try:
                    try:
                        await query.edit_message_text(
                            f"🚀 Uploading {format_type} ({file_size_mb:.2f}MB)..."
                        )
                    except TelegramError:
                        pass
                    with open(file_path_final, "rb") as f:
                        await send_action(
                            chat_id=query.message.chat_id,
                            **{media_kw: f},
                            caption=caption,
                            parse_mode=constants.ParseMode.HTML,
                            reply_to_message_id=orig_msg_id_for_reply,
                        )
                    try:
                        await query.message.delete()
                    except TelegramError:
                        pass
                    download_successful_flag = True
                except TelegramError as te:
                    err_txt = f"Error sending file: {te}."
                    if (
                        "request entity too large" in str(te).lower()
                        or "file is too big" in str(te).lower()
                    ):
                        err_txt = f"File ({file_size_mb:.2f}MB) is too large for Telegram direct upload by bots (limit ~50MB)."
                    try:
                        await query.edit_message_text(err_txt)
                    except TelegramError:
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=err_txt,
                            reply_to_message_id=orig_msg_id_for_reply,
                        )
                    if standard_user_limit_decremented_this_attempt:
                        revert_daily_limit_decrement(context)
        else:
            fail_msg = f"❌ Download failed: {message}"
            try:
                await query.edit_message_text(fail_msg)
            except TelegramError:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=fail_msg,
                    reply_to_message_id=orig_msg_id_for_reply,
                )
            if standard_user_limit_decremented_this_attempt:
                revert_daily_limit_decrement(context)
    except Exception as e:
        print(f"ERROR: Error in download callback {url} (User: {user_id}): {e}")
        err_msg_unexpected = f"An unexpected error occurred: {type(e).__name__}."
        try:
            await query.edit_message_text(err_msg_unexpected)
        except TelegramError:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=err_msg_unexpected,
                reply_to_message_id=orig_msg_id_for_reply,
            )
        if (
            standard_user_limit_decremented_this_attempt
            and not download_successful_flag
        ):
            revert_daily_limit_decrement(context)
    finally:
        context.user_data.pop("current_url_to_download", None)
        context.user_data.pop("last_message_id_for_url", None)
        if file_path_final and os.path.exists(file_path_final):
            try:
                os.remove(file_path_final)
            except OSError as e_os:
                print(f"ERROR: Failed to delete temp file {file_path_final}: {e_os}")
        await context.application.persistence.flush()


async def premium_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    await query.answer()
    tier_key = query.data.replace("BUY_PREMIUM_", "")
    if tier_key not in PREMIUM_PRICES:
        try:
            await query.edit_message_text("Invalid tier.")
        except TelegramError:
            pass
            return
    info = PREMIUM_PRICES[tier_key]
    payload = f"premium_{tier_key}_{query.from_user.id}_{uuid4().hex[:6]}"
    prices = [LabeledPrice(label=info["title"], amount=info["stars"])]
    try:
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=info["title"],
            description=info["description"],
            payload=payload,
            currency="XTR",
            prices=prices,
            provider_token=None,
        )
        try:
            await query.message.delete()
        except TelegramError:
            pass
    except TelegramError as e:
        print(f"ERROR: Failed to send Stars invoice: {e}")
        try:
            await query.message.reply_text(
                f"Could not initiate payment: {e}. Please ensure bot is configured for Stars and you have Telegram Premium for Stars payments."
            )
        except TelegramError:
            pass


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if not query or not query.from_user:
        return
    parts = query.invoice_payload.split("_")
    if not query.invoice_payload.startswith("premium_") or len(parts) < 4:
        print(f"WARNING: Invalid precheckout payload: {query.invoice_payload}")
        await query.answer(ok=False, error_message="Invalid transaction details.")
        return
    tier_key = "_".join(parts[1:-2])
    user_id_payload = parts[-2]
    if tier_key not in PREMIUM_PRICES:
        print(
            f"WARNING: Precheckout for unknown tier: {tier_key} from payload {query.invoice_payload}"
        )
        await query.answer(
            ok=False, error_message="Selected plan is no longer available."
        )
        return
    if str(query.from_user.id) != user_id_payload:
        print(
            f"WARNING: Precheckout user ID mismatch: query.from_user.id={query.from_user.id}, payload_user_id={user_id_payload}"
        )
        await query.answer(
            ok=False,
            error_message="User ID mismatch. Please try selecting the plan again.",
        )
        return
    await query.answer(ok=True)


async def successful_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if (
        not update.message
        or not update.message.successful_payment
        or not update.effective_user
    ):
        return
    payment = update.message.successful_payment
    parts = payment.invoice_payload.split("_")
    tier_key = "_".join(parts[1:-2])
    user_id = update.effective_user.id
    if tier_key in PREMIUM_PRICES:
        days = PREMIUM_PRICES[tier_key]["days"]
        ud = context.application.persistence.user_data.setdefault(
            user_id, {"_id": user_id}
        )
        ud["is_premium"] = True
        current_expiry_ts = ud.get("premium_expiry_timestamp", 0.0)
        if current_expiry_ts is None:
            current_expiry_ts = 0.0
        now_ts = datetime.datetime.now().timestamp()
        start_date_for_new_premium = (
            datetime.datetime.fromtimestamp(current_expiry_ts)
            if current_expiry_ts > now_ts
            else datetime.datetime.now()
        )
        ud["premium_expiry_timestamp"] = (
            start_date_for_new_premium + datetime.timedelta(days=days)
        ).timestamp()
        ud["premium_tier"] = tier_key
        await context.application.persistence.flush()
        await update.message.reply_text(
            f"🎉 Thank you! Your Premium ({PREMIUM_PRICES[tier_key]['title']}) is now active for {days} days!"
        )
        print(
            f"User {user_id} successfully purchased {tier_key} premium for {days} days. New expiry: {datetime.datetime.fromtimestamp(ud['premium_expiry_timestamp'])}"
        )
    else:
        print(
            f"ERROR: Successful payment for unknown tier: {tier_key} from payload {payment.invoice_payload} by user {user_id}"
        )
        await update.message.reply_text(
            "Payment received, but there was an issue activating premium. Please contact support."
        )


async def admin_command_wrapper(
    update: Update, context: ContextTypes.DEFAULT_TYPE, command_func, *args, **kwargs
):
    if not update.effective_user or update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ This command is for admins only.")
        return
    await command_func(update, context, *args, **kwargs)


async def set_user_premium_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setuserpremium `[user_id] [days]`")
        return
    try:
        target_user_id = int(context.args[0])
        days = int(context.args[1])
        if days <= 0:
            await update.message.reply_text("Days must be a positive number.")
            return
    except ValueError:
        await update.message.reply_text(
            "Invalid user ID or days. Both must be numbers."
        )
        return
    target_ud = context.application.persistence.user_data.setdefault(
        target_user_id, {"_id": target_user_id}
    )
    target_ud["is_premium"] = True
    current_expiry_ts = target_ud.get("premium_expiry_timestamp", 0.0)
    if current_expiry_ts is None:
        current_expiry_ts = 0.0
    now_ts = datetime.datetime.now().timestamp()
    start_date_for_new_premium = (
        datetime.datetime.fromtimestamp(current_expiry_ts)
        if current_expiry_ts > now_ts
        else datetime.datetime.now()
    )
    target_ud["premium_expiry_timestamp"] = (
        start_date_for_new_premium + datetime.timedelta(days=days)
    ).timestamp()
    target_ud["premium_tier"] = f"admin_grant_{days}d"
    await context.application.persistence.flush()
    expiry_dt_str = datetime.datetime.fromtimestamp(
        target_ud["premium_expiry_timestamp"]
    ).strftime("%Y-%m-%d %H:%M:%S UTC")
    await update.message.reply_text(
        f"✅ User {target_user_id} has been granted Premium for {days} days. Their premium now expires on {expiry_dt_str}."
    )
    try:
        await context.bot.send_message(
            target_user_id,
            f"🎉 Congratulations! An admin has granted you Premium access for {days} days.",
        )
    except Exception as e:
        print(f"WARNING: Failed to notify user {target_user_id} of manual premium: {e}")


async def remove_user_premium_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /removeuserpremium `[user_id]`")
        return
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID. It must be a number.")
        return
    if target_user_id not in context.application.persistence.user_data:
        await update.message.reply_text(
            f"User {target_user_id} not found in bot data. Cannot remove premium."
        )
        return
    target_ud = context.application.persistence.user_data[target_user_id]
    if not target_ud.get("is_premium") and not target_ud.get(
        "premium_expiry_timestamp"
    ):
        await update.message.reply_text(
            f"User {target_user_id} is not currently premium or has no premium data."
        )
        return
    target_ud["is_premium"] = False
    target_ud["premium_expiry_timestamp"] = None
    target_ud["premium_tier"] = "admin_revoked"
    await context.application.persistence.flush()
    await update.message.reply_text(
        f"✅ Premium status for user {target_user_id} has been revoked."
    )
    try:
        await context.bot.send_message(
            target_user_id,
            "ℹ️ Your Premium access has been revoked by an administrator.",
        )
    except Exception as e:
        print(
            f"WARNING: Failed to notify user {target_user_id} of premium revocation: {e}"
        )


async def ban_user_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    try:
        target_user_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /banuser `[user_id]`")
        return
    if target_user_id == update.effective_user.id:
        await update.message.reply_text("You cannot ban yourself.")
        return
    if target_user_id in ADMIN_IDS:
        await update.message.reply_text("Admins cannot be banned.")
        return
    banned_users_set = context.bot_data.setdefault(BANNED_USERS_KEY, set())
    if target_user_id in banned_users_set:
        await update.message.reply_text(f"User {target_user_id} is already banned.")
        return
    banned_users_set.add(target_user_id)
    if target_user_id in context.application.persistence.user_data:
        target_ud = context.application.persistence.user_data[target_user_id]
        target_ud.update(
            {
                "is_premium": False,
                "premium_expiry_timestamp": None,
                "premium_tier": "revoked_banned",
            }
        )
    await context.application.persistence.flush()
    await update.message.reply_text(
        f"🚫 User {target_user_id} has been banned and their premium (if any) revoked."
    )


async def unban_user_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_user_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /unbanuser `[user_id]`")
        return
    banned_users_set = context.bot_data.setdefault(BANNED_USERS_KEY, set())
    if target_user_id in banned_users_set:
        banned_users_set.remove(target_user_id)
        await context.application.persistence.flush()
        await update.message.reply_text(f"✅ User {target_user_id} has been unbanned.")
    else:
        await update.message.reply_text(
            f"User {target_user_id} was not found in the ban list."
        )


async def broadcast_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Please reply to the message you want to broadcast."
        )
        return
    message_to_broadcast = update.message.reply_to_message
    all_user_ids_with_data = list(context.application.persistence.user_data.keys())
    if not all_user_ids_with_data:
        await update.message.reply_text("No users with data to broadcast to.")
        return
    status_msg = await update.message.reply_text(
        f"📢 Broadcasting to {len(all_user_ids_with_data)} users... This may take a while."
    )
    sent_count, failed_count = 0, 0
    banned_users = context.bot_data.get(BANNED_USERS_KEY, set())
    for i, user_id in enumerate(all_user_ids_with_data):
        if user_id in banned_users:
            continue
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message_to_broadcast.chat_id,
                message_id=message_to_broadcast.message_id,
            )
            sent_count += 1
        except Forbidden:
            failed_count += 1
            print(
                f"WARNING: Broadcast failed for user {user_id}: Bot blocked or user deactivated."
            )
        except TelegramError as e:
            failed_count += 1
            print(f"WARNING: Broadcast failed for user {user_id}: {e}")
        if (i + 1) % 20 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 Broadcasting... Sent: {sent_count}, Failed/Skipped: {failed_count} (Processed {i+1}/{len(all_user_ids_with_data)})"
                )
            except TelegramError:
                pass
            await asyncio.sleep(1)
    await status_msg.edit_text(
        f"Broadcast finished. ✅ Sent: {sent_count}, ❌ Failed/Skipped: {failed_count} out of {len(all_user_ids_with_data)} potential recipients."
    )


async def toggle_channel_check_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = await get_channel_config(context)
    new_state = not config.get("enabled", False)
    await set_channel_config(new_state, config.get("channels", []), context)
    await update.message.reply_text(
        f"📢 Mandatory channel subscription is now {'ENABLED' if new_state else 'DISABLED'}."
    )


async def set_required_channels_impl(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not context.args:
        await update.message.reply_text(
            "Usage: /setrequiredchannels `[@ch1 ID2...]` or `none` to clear.\nChannels must be public or bot must be admin in private channels."
        )
        return
    channels_to_set_str = " ".join(context.args)
    if channels_to_set_str.lower() == "none":
        channels_to_set = []
    else:
        channels_to_set_raw = [
            ch.strip()
            for ch in re.split(r"[\s,;\n]+", channels_to_set_str)
            if ch.strip()
        ]
        valid_channels = []
        invalid_formats = []
        for ch_raw in channels_to_set_raw:
            if (
                ch_raw.startswith("@")
                or (ch_raw.startswith("-") and ch_raw[1:].isdigit())
                or ch_raw.isdigit()
            ):
                valid_channels.append(ch_raw)
            else:
                invalid_formats.append(ch_raw)
        if invalid_formats:
            await update.message.reply_text(
                f"Invalid channel formats: {', '.join(invalid_formats)}. Use @username or numeric chat ID (e.g., -100123456789)."
            )
            return
        channels_to_set = valid_channels
    config = await get_channel_config(context)
    await set_channel_config(config.get("enabled", False), channels_to_set, context)
    current_config = await get_channel_config(context)
    response_msg = (
        "📢 Required channels list cleared."
        if not channels_to_set
        else f"📢 Required channels set to: {', '.join(channels_to_set)}"
    )
    if current_config.get("enabled", False) and channels_to_set:
        response_msg += "\nℹ️ Channel check is currently ENABLED."
    elif not current_config.get("enabled", False) and channels_to_set:
        response_msg += (
            "\n⚠️ Channel check is currently DISABLED. Enable with /togglechannelcheck."
        )
    elif not channels_to_set:
        response_msg += "\nℹ️ No channels are set as required."
    await update.message.reply_text(response_msg)


async def stats_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_user_data_items = list(context.application.persistence.user_data.items())
    roles_count = {
        ROLE_ADMIN: 0,
        ROLE_PREMIUM: 0,
        ROLE_STANDARD: 0,
        ROLE_BANNED: 0,
        "Admin (Premium)": 0,
    }
    total_users_with_data = len(all_user_data_items)
    users_who_had_premium = 0
    for user_id_key, data_val in all_user_data_items:
        actual_role = get_user_role(
            user_id_key, context, current_effective_user=None, for_display=True
        )
        is_premium_active_for_stat = False
        if data_val.get("is_premium"):
            exp_ts = data_val.get("premium_expiry_timestamp")
            if exp_ts and exp_ts > datetime.datetime.now().timestamp():
                is_premium_active_for_stat = True
        if actual_role == ROLE_ADMIN:
            if is_premium_active_for_stat:
                roles_count["Admin (Premium)"] += 1
            else:
                roles_count[ROLE_ADMIN] += 1
        elif actual_role == ROLE_PREMIUM:
            roles_count[ROLE_PREMIUM] += 1
        elif actual_role == ROLE_STANDARD:
            roles_count[ROLE_STANDARD] += 1
            if data_val.get("premium_tier") and data_val.get("premium_tier") not in [
                "admin_revoked",
                "revoked_banned",
                "expired_or_unknown",
                "expired_or_cleaned",
            ]:
                users_who_had_premium += 1
    banned_user_count_direct = len(context.bot_data.get(BANNED_USERS_KEY, set()))
    roles_count[ROLE_BANNED] = banned_user_count_direct
    interacted_admin_count = sum(
        1 for uid_key, _ in all_user_data_items if uid_key in ADMIN_IDS
    )
    channel_cfg = await get_channel_config(context)
    stats_lines = [
        "📊 **Bot Usage Statistics** 📊",
        f"  - Total Users with Data: {total_users_with_data}",
        f"  - Configured Admins (in ADMIN_IDS): {len(ADMIN_IDS)} (Interacted: {interacted_admin_count})",
        f"  - Roles Breakdown:",
        f"    - Admin: {roles_count[ROLE_ADMIN]}",
        f"    - Admin (Premium): {roles_count['Admin (Premium)']}",
        f"    - Premium Users: {roles_count[ROLE_PREMIUM]}",
        f"    - Standard Users: {roles_count[ROLE_STANDARD]} (of which ~{users_who_had_premium} previously had premium)",
        f"    - Banned Users: {roles_count[ROLE_BANNED]}",
        f"\n📢 **Channel Subscription:** {'ENABLED' if channel_cfg.get('enabled') else 'DISABLED'}",
        f"  - Required Channels: {', '.join(channel_cfg.get('channels', [])) or 'None'}",
    ]
    await update.message.reply_html("\n".join(stats_lines))


async def view_users_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_user_data_items = list(context.application.persistence.user_data.items())
    if not all_user_data_items:
        await update.message.reply_text("No user data found.")
        return
    user_details_list = [
        "👥 **User Details List (Max 50 users displayed per message):**"
    ]
    output_message_count = 0
    MAX_USERS_PER_MESSAGE = 50
    for i, (user_id, data) in enumerate(all_user_data_items):
        display_role_str = "Unknown"
        is_banned = user_id in context.bot_data.get(BANNED_USERS_KEY, set())
        is_admin = user_id in ADMIN_IDS
        is_premium_active = False
        premium_expiry_ts = data.get("premium_expiry_timestamp")
        if (
            data.get("is_premium")
            and premium_expiry_ts
            and premium_expiry_ts > datetime.datetime.now().timestamp()
        ):
            is_premium_active = True
        if is_banned:
            display_role_str = "Banned"
        elif is_admin:
            display_role_str = "Admin"
            if is_premium_active:
                display_role_str += " (Premium)"
        elif is_premium_active:
            display_role_str = "Premium"
        else:
            display_role_str = "Standard"
        user_line = [f"\n👤 ID: <code>{user_id}</code>", f"   Role: {display_role_str}"]
        if is_premium_active:
            user_line.append(
                f"   Tier: Active Premium ({data.get('premium_tier', 'N/A')})"
            )
        elif data.get("premium_tier"):
            user_line.append(f"   Tier: {data.get('premium_tier')}")
        if premium_expiry_ts:
            expiry_dt = datetime.datetime.fromtimestamp(premium_expiry_ts)
            now_dt = datetime.datetime.now()
            if expiry_dt > now_dt:
                remaining = expiry_dt - now_dt
                days, rem_secs = divmod(remaining.total_seconds(), 86400)
                hours, rem_secs = divmod(rem_secs, 3600)
                minutes = rem_secs // 60
                user_line.append(
                    f"   **Premium Ends:** {expiry_dt.strftime('%Y-%m-%d %H:%M')} UTC ({int(days)}d {int(hours)}h {int(minutes)}m left)"
                )
            else:
                user_line.append(
                    f"   **Premium Expired:** {expiry_dt.strftime('%Y-%m-%d %H:%M')} UTC"
                )
        if display_role_str == "Standard" and not is_admin:
            today_iso = datetime.date.today().isoformat()
            last_dl_date = data.get("last_download_date")
            downloads_today = (
                data.get("daily_downloads_count", 0) if last_dl_date == today_iso else 0
            )
            user_line.append(
                f"   **Downloads Today:** {downloads_today}/{STANDARD_USER_DAILY_DOWNLOADS}"
            )
        user_details_list.append("\n".join(user_line))
        if (i + 1) % MAX_USERS_PER_MESSAGE == 0 or (i + 1) == len(all_user_data_items):
            try:
                await update.message.reply_html(
                    "\n".join(user_details_list), disable_web_page_preview=True
                )
                output_message_count += 1
            except TelegramError as e:
                await update.message.reply_text(f"Error sending user list part: {e}")
                break
            user_details_list = (
                [f"... (continued - part {output_message_count+1}) ..."]
                if (i + 1) < len(all_user_data_items)
                else []
            )
            if (i + 1) < len(all_user_data_items):
                await asyncio.sleep(0.5)
    if (
        not output_message_count
        and len(user_details_list) <= 1
        and (not all_user_data_items or user_details_list[0].startswith("👥"))
    ):
        if not all_user_data_items:
            await update.message.reply_text("No user data found.")
        elif output_message_count == 0 and len(user_details_list) > 1:
            await update.message.reply_html(
                "\n".join(user_details_list), disable_web_page_preview=True
            )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id_for_error = "Unknown"
    if isinstance(update, Update) and update.effective_user:
        user_id_for_error = update.effective_user.id
    print(f"ERROR: Exception while handling an update for user {user_id_for_error}:")
    traceback.print_exception(
        type(context.error), context.error, context.error.__traceback__
    )
    if isinstance(update, Update) and update.effective_message:
        try:
            if isinstance(context.error, Forbidden):
                print(
                    f"WARNING: Forbidden error for user {user_id_for_error}. Bot might be blocked by this user."
                )
                return
            await update.effective_message.reply_text(
                "😔 Oops! Something went wrong on my end. Please try again or contact support if the issue persists."
            )
        except Forbidden:
            print(
                f"WARNING: Further Forbidden error while trying to send error message to user {user_id_for_error}."
            )
        except Exception as e_reply:
            print(
                f"ERROR: Failed to send error message to user during error handling: {e_reply}"
            )


def main():
    global BOT_TOKEN
    if (
        not BOT_TOKEN
        or BOT_TOKEN == "YOUR_BOT_TOKEN"
        or len(BOT_TOKEN.split(":")[0]) < 5
    ):
        print(
            "CRITICAL: BOT_TOKEN is not set or looks invalid! Please check your BOT_TOKEN. Exiting."
        )
        sys.exit(1)
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    app_defaults = Defaults(parse_mode=constants.ParseMode.HTML)
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(PERSISTENCE)
        .defaults(app_defaults)
        .read_timeout(30)
        .connect_timeout(30)
        .write_timeout(30)
        .build()
    )
    user_commands_list = [
        BotCommand("start", "🌟 Start Bot & View Status"),
        BotCommand("help", "ℹ️ Get Help & Command List"),
        BotCommand("myrole", "👤 My Account Details"),
        BotCommand("premium", "💎 Upgrade to Premium"),
        BotCommand("support", "📞 Contact Support"),
    ]
   
   
    handlers = [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CommandHandler("myrole", myrole_command),
        CommandHandler("support", support_command),
        CommandHandler("premium", premium_command),
        CommandHandler(
            "setuserpremium",
            lambda u, c: admin_command_wrapper(u, c, set_user_premium_impl),
        ),
        CommandHandler(
            "removeuserpremium",
            lambda u, c: admin_command_wrapper(u, c, remove_user_premium_impl),
        ),
        CommandHandler(
            "broadcast", lambda u, c: admin_command_wrapper(u, c, broadcast_impl)
        ),
        CommandHandler(
            "banuser", lambda u, c: admin_command_wrapper(u, c, ban_user_impl)
        ),
        CommandHandler(
            "unbanuser", lambda u, c: admin_command_wrapper(u, c, unban_user_impl)
        ),
        CommandHandler(
            "togglechannelcheck",
            lambda u, c: admin_command_wrapper(u, c, toggle_channel_check_impl),
        ),
        CommandHandler(
            "setrequiredchannels",
            lambda u, c: admin_command_wrapper(u, c, set_required_channels_impl),
        ),
        CommandHandler("stats", lambda u, c: admin_command_wrapper(u, c, stats_impl)),
        CommandHandler(
            "viewusers", lambda u, c: admin_command_wrapper(u, c, view_users_impl)
        ),
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & (
                filters.Entity(constants.MessageEntityType.URL)
                | filters.Entity(constants.MessageEntityType.TEXT_LINK)
            ),
            handle_url_message,
        ),
        MessageHandler(
            filters.CAPTION
            & ~filters.COMMAND
            & (
                filters.CaptionEntity(constants.MessageEntityType.URL)
                | filters.CaptionEntity(constants.MessageEntityType.TEXT_LINK)
            ),
            handle_url_message,
        ),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message),
        MessageHandler(filters.CAPTION & ~filters.COMMAND, handle_url_message),
        CallbackQueryHandler(download_format_callback, pattern=r"^dl_(video|audio)$"),
        CallbackQueryHandler(premium_tier_callback, pattern=r"^BUY_PREMIUM_"),
        PreCheckoutQueryHandler(precheckout_callback),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback),
    ]
    application.add_handlers(handlers)
    application.add_error_handler(error_handler)

    async def post_initialization(app_instance: Application):
        try:
           
            await app_instance.bot.set_my_commands(user_commands_list)
            if BANNED_USERS_KEY not in app_instance.bot_data:
                app_instance.bot_data[BANNED_USERS_KEY] = set()
            if CHANNEL_SUBSCRIPTION_CONFIG_KEY not in app_instance.bot_data:
                app_instance.bot_data[CHANNEL_SUBSCRIPTION_CONFIG_KEY] = {
                    "enabled": False,
                    "channels": [],
                }
            await app_instance.update_persistence()
            bot_me = await app_instance.bot.get_me()
            print(
                f"Bot commands set ({len(user_commands_list)} user commands). Bot @{bot_me.username} (ID: {bot_me.id}) started successfully!"
            )
        except Exception as e:
            print(f"ERROR: Error during post_initialization: {e}")
            traceback.print_exc()

    application.post_init = post_initialization
    print("Bot is starting up...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
