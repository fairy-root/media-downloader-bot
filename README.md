# Media Downloader Bot

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-Official-informational.svg)
![yt-dlp](https://img.shields.io/badge/Powered%20by-yt--dlp-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

A versatile Telegram bot powered by `yt-dlp` that allows users to download videos and audio from a wide range of supported platforms, including TikTok, YouTube, Instagram, and more. It features a robust role-based access system with standard and premium tiers, admin controls, and optional channel subscription checks.

## Table of Contents

-   [Features](#features)
-   [Requirements](#requirements)
-   [Installation & Setup](#installation--setup)
-   [Usage](#usage)
    -   [User Commands](#user-commands)
    -   [How to Download Media](#how-to-download-media)
    -   [Premium Features](#premium-features)
    -   [Admin Commands](#admin-commands)
-   [Persistence](#persistence)
-   [Contributing](#contributing)
-   [License](#license)
-   [Support](#support)

## Features

This bot provides a rich set of features for both standard users and administrators:

### General
*   **Broad Platform Support:** Leverages `yt-dlp` to download media from a vast array of websites.
*   **Flexible Downloads:** Offers options to download media as video or (for privileged users) as audio.
*   **File Naming:** Automatically sanitizes and names downloaded files for easy identification.

### User Features
*   **Standard User Tier:**
    *   Limited to **TikTok** video downloads only.
    *   Daily download limit of **5 files**.
    *   Max file size of **25MB**.
*   **Premium User Tier:**
    *   **Unlimited** daily downloads.
    *   Access to a **wider range of platforms**.
    *   Option to download **audio** format.
    *   Higher file size limits (up to Telegram's direct upload limit, typically ~50MB).
    *   Purchase premium access directly via **Telegram Stars**.
*   **User Roles:** Manages users with `Standard`, `Premium`, `Admin`, and `Banned` roles.

### Admin Features
*   **User Management:**
    *   Grant/revoke premium status to any user.
    *   Ban and unban users.
*   **Broadcast Messaging:** Send messages to all users who have interacted with the bot.
*   **Channel Subscription Check:**
    *   Enable/disable mandatory channel joining before users can download.
    *   Configure multiple required channels (by `@username` or numeric ID).
*   **Bot Statistics:** View detailed statistics on user distribution (Standard, Premium, Admin, Banned) and channel configuration.
*   **User Listing:** List all users with stored data, showing their roles, premium expiry, and download stats.

## Requirements

Before running the bot, ensure you have the following:

*   **Python 3.8+**: The bot is developed using modern Python syntax.
*   **pip**: Python package installer (usually comes with Python).
*   **ffmpeg**: A powerful multimedia framework required by `yt-dlp` for format conversion and merging.
    *   **Linux/macOS:** `sudo apt install ffmpeg` (Debian/Ubuntu) or `brew install ffmpeg` (macOS).
    *   **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to your system's PATH.
*   **Telegram Bot Token**: Obtain this from BotFather on Telegram.
*   **Your Telegram User ID**: For the `OWNER_ID` and `ADMIN_IDS` configuration. You can get this by sending `/id` to bots like `@userinfobot`.

## Installation & Setup

Follow these steps to get your Media Downloader Bot up and running:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/fairy-root/media-downloader-bot.git
    cd media-downloader-bot
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    ```

3.  **Activate the Virtual Environment:**
    *   **Linux/macOS:**
        ```bash
        source venv/bin/activate
        ```
    *   **Windows (Command Prompt):**
        ```bash
        venv\Scripts\activate.bat
        ```
    *   **Windows (PowerShell):**
        ```powershell
        .\venv\Scripts\Activate.ps1
        ```

4.  **Install Dependencies:**
    Create a `requirements.txt` file in the root directory of your project with the following content:
    ```
    python-telegram-bot==20.8
    yt-dlp==2023.12.30 # Or latest stable version
    aiohttp
    ```
    Then, install them:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure the Bot:**
    Open the `main.py` file and replace the placeholder values:

    ```python
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE" # Get this from @BotFather
    OWNER_ID = 123456789             # Your Telegram User ID
    ADMIN_IDS = [123456789, 987654321] # A list of admin User IDs (can include OWNER_ID)
    SUPPORT_CONTACT = "@YourTelegramUsername" # Your support contact
    ```

6.  **Run the Bot:**
    ```bash
    python main.py
    ```
    The bot should start, and you will see output indicating its successful initialization.

## Usage

### User Commands

These commands are visible to all users when they interact with the bot's command menu.

*   `/start` - Initializes the bot and displays a welcome message with your current status.
*   `/help` - Shows a detailed help message including all available commands for your role (admin commands are only shown to admins here).
*   `/myrole` - Displays your current user role, premium status, and download limits.
*   `/premium` - Presents options to upgrade to premium using Telegram Stars.
*   `/support` - Provides the contact information for bot support.

### How to Download Media

1.  **Send a Link:** Send any supported media link (e.g., from TikTok, YouTube, Instagram, etc.) directly to the bot in a private chat.
2.  **Choose Format:** The bot will respond with inline buttons asking you to choose between "Video" and "Audio" (audio option is only available for Premium/Admin users).
3.  **Receive Media:** The bot will process the link, download the media, and send it back to you.

    *   **Standard Users:** Can only download TikTok videos. Downloads count towards a daily limit and are restricted by file size.
    *   **Premium Users:** Enjoy unlimited downloads from all supported platforms, including audio and larger file sizes.

### Premium Features

To unlock unlimited downloads, broader platform support, and audio downloads, you can purchase premium access via Telegram Stars using the `/premium` command. The bot will present various premium tiers, and you can complete the purchase through Telegram's in-app payment system.

### Admin Commands

Admin commands are not displayed in the general Telegram command list for regular users. They are only revealed in the `/help` command's output if the user sending `/help` is an Admin. All admin commands are protected by an `admin_command_wrapper` to ensure only configured `ADMIN_IDS` can execute them.

*   `/broadcast [reply to message]`
    *   **Usage:** Reply to any message (text, photo, video, etc.) and then send `/broadcast`.
    *   **Function:** Copies the replied message and forwards it to all users who have previously interacted with the bot.

*   `/setuserpremium [user_id] [days]`
    *   **Usage:** `/setuserpremium 123456789 30` (grants user 123456789 premium for 30 days).
    *   **Function:** Grants premium status to a specific user for a given number of days. If the user already has premium, the new days are added to their existing expiry.

*   `/removeuserpremium [user_id]`
    *   **Usage:** `/removeuserpremium 123456789`
    *   **Function:** Revokes premium status from a specific user.

*   `/banuser [user_id]`
    *   **Usage:** `/banuser 123456789`
    *   **Function:** Adds a user to the banned list, preventing them from using the bot. Also revokes any active premium.

*   `/unbanuser [user_id]`
    *   **Usage:** `/unbanuser 123456789`
    *   **Function:** Removes a user from the banned list, allowing them to use the bot again.

*   `/togglechannelcheck`
    *   **Usage:** `/togglechannelcheck`
    *   **Function:** Toggles the mandatory channel subscription check on or off. If enabled, users must join the configured channels before downloading.

*   `/setrequiredchannels [@channel_username1 -100123456789 etc.]` or `/setrequiredchannels none`
    *   **Usage:**
        *   `/setrequiredchannels @my_public_channel -100123456789` (sets multiple channels).
        *   `/setrequiredchannels none` (clears the list of required channels).
    *   **Function:** Sets the list of channels that users must be subscribed to. The bot must be an administrator in private channels to check membership.

*   `/stats`
    *   **Usage:** `/stats`
    *   **Function:** Displays detailed statistics about the bot's user base (total users, role breakdown, channel check status).

*   `/viewusers`
    *   **Usage:** `/viewusers`
    *   **Function:** Lists all users who have interacted with the bot, showing their user ID, current role, premium status, and daily download count. Results are paginated for large user bases.

## Persistence

The bot uses `PicklePersistence` to store user data (roles, premium expiry, download counts) and bot-wide configurations (banned users, channel settings) in a file named `bot_persistence.pickle`.

**Important:**
*   **Backup `bot_persistence.pickle` regularly!** This file contains all your bot's operational data.
*   If this file is deleted or corrupted, all user data and bot configurations will be lost.

---

## Donation

Your support is appreciated:

-   **USDt (TRC20)**: `TGCVbSSJbwL5nyXqMuKY839LJ5q5ygn2uS`
-   **BTC**: `13GS1ixn2uQAmFQkte6qA5p1MQtMXre6MT`
-   **ETH (ERC20)**: `0xdbc7a7dafbb333773a5866ccf7a74da15ee654cc`
-   **LTC**: `Ldb6SDxUMEdYQQfRhSA3zi4dCUtfUdsPou`

## Author

-   **GitHub**: [FairyRoot](https://github.com/fairy-root)
-   **Telegram**: [@FairyRoot](https://t.me/FairyRoot)

## Contributing

Contributions are welcome! If you have suggestions for improvements, bug fixes, or new features, please feel free to:

1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/your-feature-name`).
3.  Make your changes.
4.  Commit your changes (`git commit -m 'Add new feature'`).
5.  Push to the branch (`git push origin feature/your-feature-name`).
6.  Open a Pull Request.

## License

This project is open-source and distributed under the MIT License. See the `LICENSE` file for more details.

---