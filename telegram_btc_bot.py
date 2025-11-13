import requests
import time
import sys
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == 'win32':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Don't wrap stdout/stderr to avoid I/O errors
    # The environment variable should be enough

# Telegram Bot Configuration
BOT_TOKEN = "8388090013:AAF0oRF7fJepJIl6BZnJn4CRktH54Fh0Srg"
# Channels list - can add multiple channels via /addchannel command
CHANNELS = ["@cryptopricebd1"]  # List of channel usernames/IDs

# Admin Configuration - Add your Telegram User ID here
# To get your User ID, message @userinfobot on Telegram
# Or use /getmyid command when bot is running
ADMIN_USER_IDS = [7127437250]  # Admin user IDs

# API endpoints
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price"

# Global variables for bot control
bot_running = True
last_update_id = 0
post_interval = 60  # Default: 60 seconds (1 minute)
last_successful_price = None  # Cache last successful price
last_successful_change = None
api_fail_count = 0  # Track consecutive API failures
MAX_API_RETRIES = 3  # Maximum retries for API calls

# ============================================================================
# Bot Status & Info Functions
# ============================================================================

def get_bot_info():
    """Get bot information"""
    try:
        url = f"{TELEGRAM_API}/getMe"
        response = requests.get(url, timeout=10)
        bot_info = response.json()
        if bot_info.get("ok"):
            return bot_info["result"]
        return None
    except Exception as e:
        print(f"[ERROR] Error getting bot info: {e}")
        return None

def get_channel_info(channel=None):
    """Get channel information"""
    import telegram_btc_bot as bot_module
    if not channel:
        channels = bot_module.CHANNELS
        if channels:
            channel = channels[0]  # Get first channel
        else:
            return None
    
    try:
        url = f"{TELEGRAM_API}/getChat"
        payload = {"chat_id": channel}
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        if result.get("ok"):
            return result["result"]
        return None
    except Exception as e:
        print(f"[ERROR] Error getting channel info: {e}")
        return None

def get_bot_member_status(channel=None):
    """Get bot's member status in channel"""
    bot_info = get_bot_info()
    if not bot_info:
        return None
    
    if not channel:
        if CHANNELS:
            channel = CHANNELS[0]  # Get first channel
        else:
            return None
    
    try:
        url = f"{TELEGRAM_API}/getChatMember"
        payload = {
            "chat_id": channel,
            "user_id": bot_info["id"]
        }
        response = requests.post(url, json=payload, timeout=10)
        member_info = response.json()
        if member_info.get("ok"):
            return member_info["result"]
        return None
    except Exception as e:
        print(f"[ERROR] Error getting member status: {e}")
        return None

# ============================================================================
# BTC Price Bot Functions
# ============================================================================

def get_btc_price(retry_count=0):
    """Fetch BTC price from CoinGecko API with retry logic"""
    global last_successful_price, last_successful_change, api_fail_count
    
    try:
        params = {
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        # Increase timeout for better reliability
        response = requests.get(COINGECKO_API, params=params, timeout=15)
        data = response.json()
        
        if "bitcoin" in data:
            btc_data = data["bitcoin"]
            price = btc_data.get("usd", 0)
            change_24h = btc_data.get("usd_24h_change", 0)
            
            # Validate price data
            if price and price > 0:
                # Update cache on success
                last_successful_price = price
                last_successful_change = change_24h
                api_fail_count = 0
                return price, change_24h
        
        # If we get here, data is invalid
        if retry_count < MAX_API_RETRIES:
            time.sleep(2)  # Wait 2 seconds before retry
            return get_btc_price(retry_count + 1)
        
        # Return cached price if available
        if last_successful_price:
            print(f"[INFO] Using cached price (API failed)")
            return last_successful_price, last_successful_change
        
        return None, None
        
    except requests.exceptions.Timeout:
        api_fail_count += 1
        print(f"[WARNING] API timeout (attempt {retry_count + 1}/{MAX_API_RETRIES})")
        
        if retry_count < MAX_API_RETRIES:
            # Exponential backoff: wait longer on each retry
            wait_time = (retry_count + 1) * 2
            time.sleep(wait_time)
            return get_btc_price(retry_count + 1)
        
        # Return cached price if available
        if last_successful_price:
            print(f"[INFO] Using cached price (API timeout)")
            return last_successful_price, last_successful_change
        
        return None, None
        
    except requests.exceptions.RequestException as e:
        api_fail_count += 1
        print(f"[WARNING] API request error: {type(e).__name__} (attempt {retry_count + 1}/{MAX_API_RETRIES})")
        
        if retry_count < MAX_API_RETRIES:
            time.sleep(2)
            return get_btc_price(retry_count + 1)
        
        # Return cached price if available
        if last_successful_price:
            print(f"[INFO] Using cached price (API error)")
            return last_successful_price, last_successful_change
        
        return None, None
        
    except Exception as e:
        api_fail_count += 1
        print(f"[ERROR] Unexpected error fetching BTC price: {type(e).__name__}: {e}")
        
        # Return cached price if available
        if last_successful_price:
            print(f"[INFO] Using cached price (error occurred)")
            return last_successful_price, last_successful_change
        
        return None, None

def send_message_to_user(user_id, message, parse_mode="HTML"):
    """Send message to a specific user"""
    try:
        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": parse_mode
        }
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        return result.get("ok", False)
    except Exception as e:
        print(f"[ERROR] Error sending message to user: {e}")
        return False

def send_message_to_channel(message):
    """Send message to all channels in the list"""
    channels = CHANNELS.copy()
    
    if not channels:
        print("[ERROR] No channels configured!")
        return False
    
    success_count = 0
    failed_channels = []
    
    for channel in channels:
        sent = False
        for chat_id in [channel]:
            try:
                url = f"{TELEGRAM_API}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
                response = requests.post(url, json=payload, timeout=10)
                result = response.json()
                
                if result.get("ok"):
                    msg_id = result["result"].get("message_id", "N/A")
                    print(f"[SUCCESS] Message sent to {channel} (ID: {msg_id}) at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    sys.stdout.flush()
                    success_count += 1
                    sent = True
                    break
                else:
                    error_code = result.get("error_code", "Unknown")
                    error_desc = result.get("description", "Unknown error")
                    
                    if chat_id == channel_ids[-1]:
                        print(f"[ERROR] Failed to send to {channel}: {error_code} - {error_desc}")
                        sys.stdout.flush()
                        failed_channels.append(f"{channel} ({error_desc})")
                    
                    continue
                    
            except Exception as e:
                if chat_id == channel_ids[-1]:
                    print(f"[ERROR] Error sending to {channel}: {e}")
                    sys.stdout.flush()
                    failed_channels.append(f"{channel} (Error: {e})")
                continue
        
        if not sent:
            failed_channels.append(channel)
    
    # Summary
    if success_count > 0:
        print(f"[INFO] Successfully sent to {success_count}/{len(channels)} channel(s)")
        if failed_channels:
            print(f"[WARNING] Failed channels: {', '.join(failed_channels)}")
        sys.stdout.flush()
        return True
    else:
        print(f"[ERROR] Failed to send to all channels!")
        sys.stdout.flush()
        return False

def format_price_message(price, change_24h):
    """Format the price message with emoji and formatting"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_time_display = datetime.now().strftime("%I:%M %p")
    
    # Determine emoji and color based on 24h change
    if change_24h and change_24h > 0:
        trend_emoji = "📈"
        change_text = f"+{change_24h:.2f}%"
        change_color = "🟢"  # Green for positive
    elif change_24h and change_24h < 0:
        trend_emoji = "📉"
        change_text = f"{change_24h:.2f}%"
        change_color = "🔴"  # Red for negative
    else:
        trend_emoji = "➡️"
        change_text = "N/A"
        change_color = "⚪"
    
    # Format price with better spacing
    price_formatted = f"${price:,.2f}"
    
    message = f"""
━━━━━━━━━━━━━━━━━━━━
<b>₿ BITCOIN (BTC) PRICE</b>
━━━━━━━━━━━━━━━━━━━━

<b>💰 Current Price:</b>
<code>{price_formatted}</code>

<b>{trend_emoji} 24h Change:</b>
<code>{change_color} {change_text}</code>

<b>🕐 Updated:</b> {current_time}
<b>⏰ Time:</b> {current_time_display}

━━━━━━━━━━━━━━━━━━━━
<b>#BTC</b> <b>#Bitcoin</b> <b>#CryptoPrice</b>
━━━━━━━━━━━━━━━━━━━━
"""
    return message.strip()

def test_bot_access():
    """Test if bot can access all channels"""
    channels = CHANNELS.copy()
    
    if not channels:
        print("[WARNING] No channels configured!")
        return False
    
    accessible = 0
    for channel in channels:
        try:
            url = f"{TELEGRAM_API}/getChat"
            payload = {"chat_id": channel}
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()
            
            if result.get("ok"):
                print(f"[OK] Bot can access channel: {channel}")
                accessible += 1
            else:
                print(f"[ERROR] Bot cannot access channel {channel}: {result.get('description')}")
        except Exception as e:
            print(f"[ERROR] Error testing access to {channel}: {e}")
    
    sys.stdout.flush()
    return accessible > 0

def get_updates():
    """Get updates from Telegram bot"""
    global last_update_id
    try:
        url = f"{TELEGRAM_API}/getUpdates"
        payload = {
            "offset": last_update_id + 1,
            "timeout": 1
        }
        response = requests.post(url, json=payload, timeout=5)
        result = response.json()
        if result.get("ok"):
            updates = result.get("result", [])
            for update in updates:
                last_update_id = max(last_update_id, update.get("update_id", 0))
            return updates
        return []
    except Exception as e:
        return []

def is_admin(user_id):
    """Check if user is admin"""
    if not ADMIN_USER_IDS:
        # If no admin IDs set, allow all users (for testing)
        return True
    return user_id in ADMIN_USER_IDS

def handle_command(update):
    """Handle bot commands"""
    global bot_running, post_interval
    
    if "message" not in update:
        return
    
    message = update["message"]
    if "text" not in message:
        return
    
    text = message["text"]
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    username = message["from"].get("username", "Unknown")
    
    # Check if it's a command
    if not text.startswith("/"):
        return
    
    command = text.split()[0].lower()
    
    # Check admin access
    if not is_admin(user_id):
        send_message_to_user(chat_id, "❌ You are not authorized to use admin commands.")
        return
    
    # Handle commands
    if command == "/start":
        channels_list = "\n".join([f"  • {ch}" for ch in CHANNELS]) if CHANNELS else "  No channels"
        minutes = post_interval // 60
        seconds = post_interval % 60
        interval_display = f"{minutes} min {seconds} sec" if seconds > 0 else f"{minutes} minute(s)"
        
        help_text = f"""
🤖 <b>BTC PRICE BOT - ADMIN PANEL</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📋 ALL COMMANDS:</b>

<b>Bot Control:</b>
/start - Show this help message
/stop - Stop posting prices (bot continues running)
/startpost - Resume posting prices
/status - Check bot and channel status
/current - Show current bot settings

<b>Price & Testing:</b>
/price - Get current BTC price
/test - Send test message to all channels

<b>Channel Management:</b>
/addchannel @name - Add a channel
  Example: /addchannel @cryptopricebd1
/removechannel @name - Remove a channel
  Example: /removechannel @cryptopricebd1
/channels - List all channels

<b>Settings:</b>
/interval 5m - Set posting interval (minutes)
  Example: /interval 5m (5 minutes)
/interval 30s - Set posting interval (seconds)
  Example: /interval 30s (30 seconds)
/interval - Show current interval

<b>Information:</b>
/info - Get bot information
/getmyid - Get your User ID (to add as admin)
/help - Show help message

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚙️ CURRENT SETTINGS:</b>

Posting Interval: {interval_display} ({post_interval} seconds)
Bot Status: {'Running ✅' if bot_running else 'Stopped ⏸️'}
Channels ({len(CHANNELS)}):
{channels_list}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💡 TIPS:</b>
• Use /getmyid to get your User ID
• Add your User ID to ADMIN_USER_IDS in the script
• Bot posts to all channels simultaneously
• Minimum interval: 10 seconds
• Maximum interval: 24 hours

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        send_message_to_user(chat_id, help_text)
        
    elif command == "/help":
        minutes = post_interval // 60
        seconds = post_interval % 60
        interval_display = f"{minutes} min {seconds} sec" if seconds > 0 else f"{minutes} minute(s)"
        
        help_text = f"""
📋 <b>BTC PRICE BOT - COMMAND LIST</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🤖 Bot Control:</b>
/start - Show full help menu
/stop - Stop posting prices
/startpost - Resume posting prices
/status - Check bot status
/current - Show current settings

<b>💰 Price & Testing:</b>
/price - Get current BTC price
/test - Send test message to all channels

<b>📢 Channel Management:</b>
/addchannel @name - Add a channel
  Example: /addchannel @cryptopricebd1
/removechannel @name - Remove a channel
  Example: /removechannel @cryptopricebd1
/channels - List all channels

<b>⏱️ Interval Settings:</b>
/interval 5m - Set to 5 minutes
/interval 30s - Set to 30 seconds
/interval 90s - Set to 90 seconds
/interval - Show current interval

<b>ℹ️ Information:</b>
/info - Bot information
/getmyid - Get your User ID
/help - Show this help

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Current Interval:</b> {interval_display} ({post_interval}s)
<b>Channels:</b> {len(CHANNELS)} channel(s)
<b>Bot Status:</b> {'Running ✅' if bot_running else 'Stopped ⏸️'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        send_message_to_user(chat_id, help_text)
        
    elif command == "/status":
        bot_info = get_bot_info()
        channel_info = get_channel_info()
        member_status = get_bot_member_status()
        
        status_text = "📊 <b>Bot Status</b>\n\n"
        
        if bot_info:
            status_text += f"Bot: @{bot_info.get('username', 'Unknown')}\n"
            status_text += f"Name: {bot_info.get('first_name', 'Unknown')}\n\n"
        
        channels_list = ", ".join(CHANNELS) if CHANNELS else "No channels"
        status_text += f"Channels ({len(CHANNELS)}): {channels_list}\n\n"
        
        if member_status:
            status = member_status.get("status", "unknown")
            status_text += f"Bot Status: {status}\n"
            if status == "administrator":
                can_post = member_status.get("can_post_messages", False)
                status_text += f"Can Post: {'Yes ✅' if can_post else 'No ❌'}\n"
        
        status_text += f"\nBot Running: {'Yes ✅' if bot_running else 'No ⏸️'}"
        minutes = post_interval // 60
        seconds = post_interval % 60
        if seconds > 0:
            status_text += f"\nPosting Interval: {minutes} min {seconds} sec ({post_interval}s)"
        else:
            status_text += f"\nPosting Interval: {minutes} minute(s) ({post_interval}s)"
        send_message_to_user(chat_id, status_text)
        
    elif command == "/price":
        price, change_24h = get_btc_price()
        if price:
            if change_24h:
                if change_24h > 0:
                    emoji = "📈"
                    change_text = f"+{change_24h:.2f}%"
                else:
                    emoji = "📉"
                    change_text = f"{change_24h:.2f}%"
            else:
                emoji = "➡️"
                change_text = "N/A"
            
            price_text = f"""
💰 <b>Current BTC Price</b>

Price: <b>${price:,.2f}</b>
24h Change: {change_text} {emoji}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            send_message_to_user(chat_id, price_text)
        else:
            send_message_to_user(chat_id, "❌ Could not fetch BTC price")
            
    elif command == "/test":
        test_message = f"""
🧪 <b>Test Message</b>

This is a test message from BTC Price Bot Admin Panel.

⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

If you see this message, the bot is working correctly!
"""
        if send_message_to_channel(test_message.strip()):
            send_message_to_user(chat_id, "✅ Test message sent to channel!")
        else:
            send_message_to_user(chat_id, "❌ Failed to send test message")
            
    elif command == "/stop":
        bot_running = False
        send_message_to_user(chat_id, "⏸️ Price posting stopped. Bot is still running. Use /startpost to resume.")
        
    elif command == "/startpost":
        bot_running = True
        send_message_to_user(chat_id, f"▶️ Price posting resumed!\nInterval: {post_interval // 60} minute(s)")
        
    elif command == "/interval":
        # Get interval from command: /interval 5 (for 5 minutes) or /interval 30s (for 30 seconds)
        parts = text.split()
        if len(parts) > 1:
            try:
                interval_str = parts[1].lower()
                
                # Check if it's seconds (ends with 's')
                if interval_str.endswith('s'):
                    seconds = int(interval_str[:-1])
                    if seconds < 10:
                        send_message_to_user(chat_id, "❌ Interval must be at least 10 seconds")
                    elif seconds > 86400:  # Max 24 hours
                        send_message_to_user(chat_id, "❌ Interval cannot be more than 86400 seconds (24 hours)")
                    else:
                        post_interval = seconds
                        if seconds < 60:
                            send_message_to_user(chat_id, f"✅ Posting interval set to {seconds} second(s)\nBot will post every {seconds} second(s)")
                        else:
                            minutes = seconds // 60
                            remaining_seconds = seconds % 60
                            if remaining_seconds > 0:
                                send_message_to_user(chat_id, f"✅ Posting interval set to {minutes} minute(s) {remaining_seconds} second(s) ({seconds} seconds)\nBot will post every {seconds} second(s)")
                            else:
                                send_message_to_user(chat_id, f"✅ Posting interval set to {minutes} minute(s) ({seconds} seconds)\nBot will post every {minutes} minute(s)")
                # Check if it's minutes (ends with 'm' or just a number)
                elif interval_str.endswith('m'):
                    minutes = int(interval_str[:-1])
                    if minutes < 1:
                        send_message_to_user(chat_id, "❌ Interval must be at least 1 minute")
                    elif minutes > 1440:  # Max 24 hours
                        send_message_to_user(chat_id, "❌ Interval cannot be more than 1440 minutes (24 hours)")
                    else:
                        post_interval = minutes * 60
                        send_message_to_user(chat_id, f"✅ Posting interval set to {minutes} minute(s)\nBot will post every {minutes} minute(s)")
                # Default: treat as minutes if just a number
                else:
                    minutes = int(interval_str)
                    if minutes < 1:
                        send_message_to_user(chat_id, "❌ Interval must be at least 1 minute")
                    elif minutes > 1440:  # Max 24 hours
                        send_message_to_user(chat_id, "❌ Interval cannot be more than 1440 minutes (24 hours)")
                    else:
                        post_interval = minutes * 60
                        send_message_to_user(chat_id, f"✅ Posting interval set to {minutes} minute(s)\nBot will post every {minutes} minute(s)")
            except ValueError:
                send_message_to_user(chat_id, "❌ Invalid interval format.\n\nExamples:\n/interval 5 - 5 minutes\n/interval 5m - 5 minutes\n/interval 30s - 30 seconds\n/interval 90s - 90 seconds")
        else:
            # Show current interval in both minutes and seconds
            minutes = post_interval // 60
            seconds = post_interval % 60
            if seconds > 0:
                interval_display = f"{minutes} minute(s) {seconds} second(s) ({post_interval} seconds)"
            else:
                interval_display = f"{minutes} minute(s) ({post_interval} seconds)"
            
            send_message_to_user(chat_id, f"📊 <b>Current Interval:</b> {interval_display}\n\n<b>To change:</b>\n/interval 5 - 5 minutes\n/interval 5m - 5 minutes\n/interval 30s - 30 seconds\n/interval 90s - 90 seconds")
            
    elif command == "/addchannel":
        # Add channel: /addchannel @channelname
        parts = text.split()
        if len(parts) > 1:
            new_channel = parts[1].strip()
            
            # Validate channel format
            if not (new_channel.startswith("@") or new_channel.startswith("-")):
                send_message_to_user(chat_id, "❌ Invalid channel format.\n\nUse: /addchannel @channelname\nExample: /addchannel @cryptopricebd1")
                return
            
            import telegram_btc_bot as bot_module
            channels = bot_module.CHANNELS.copy()
            
            # Check if already exists
            if new_channel in channels:
                send_message_to_user(chat_id, f"⚠️ Channel {new_channel} is already in the list!")
                return
            
            # Test if bot can access the channel
            try:
                url = f"{TELEGRAM_API}/getChat"
                payload = {"chat_id": new_channel}
                response = requests.post(url, json=payload, timeout=10)
                result = response.json()
                
                if result.get("ok"):
                    # Add channel
                    bot_module.CHANNELS.append(new_channel)
                    channel_info = result["result"]
                    channel_title = channel_info.get("title", "Unknown")
                    
                    channels_list = "\n".join([f"• {ch}" for ch in bot_module.CHANNELS])
                    send_message_to_user(chat_id, f"✅ Channel added successfully!\n\n<b>New Channel:</b> {new_channel}\n<b>Title:</b> {channel_title}\n\n<b>All Channels ({len(bot_module.CHANNELS)}):</b>\n{channels_list}")
                else:
                    error_desc = result.get("description", "Unknown error")
                    send_message_to_user(chat_id, f"❌ Cannot access channel: {error_desc}\n\nPlease make sure:\n1. Bot is added to the channel\n2. Bot is an administrator\n3. Channel username is correct")
            except Exception as e:
                send_message_to_user(chat_id, f"❌ Error adding channel: {e}\n\nPlease check the channel username and try again.")
        else:
            import telegram_btc_bot as bot_module
            channels_list = "\n".join([f"• {ch}" for ch in bot_module.CHANNELS]) if bot_module.CHANNELS else "No channels"
            send_message_to_user(chat_id, f"📊 <b>Current Channels ({len(bot_module.CHANNELS)}):</b>\n{channels_list}\n\n<b>To add:</b>\n/addchannel @channelname\nExample: /addchannel @cryptopricebd1")
            
    elif command == "/removechannel":
        # Remove channel: /removechannel @channelname
        parts = text.split()
        if len(parts) > 1:
            channel_to_remove = parts[1].strip()
            
            import telegram_btc_bot as bot_module
            if channel_to_remove in bot_module.CHANNELS:
                bot_module.CHANNELS.remove(channel_to_remove)
                channels_list = "\n".join([f"• {ch}" for ch in bot_module.CHANNELS]) if bot_module.CHANNELS else "No channels"
                send_message_to_user(chat_id, f"✅ Channel removed!\n\n<b>Remaining Channels ({len(bot_module.CHANNELS)}):</b>\n{channels_list}")
            else:
                send_message_to_user(chat_id, f"❌ Channel {channel_to_remove} not found in the list!")
        else:
            import telegram_btc_bot as bot_module
            channels_list = "\n".join([f"• {ch}" for ch in bot_module.CHANNELS]) if bot_module.CHANNELS else "No channels"
            send_message_to_user(chat_id, f"📊 <b>Current Channels ({len(bot_module.CHANNELS)}):</b>\n{channels_list}\n\n<b>To remove:</b>\n/removechannel @channelname")
            
    elif command == "/channels":
        # List all channels
        channels_list = "\n".join([f"• {ch}" for ch in CHANNELS]) if CHANNELS else "No channels configured"
        send_message_to_user(chat_id, f"📊 <b>All Channels ({len(CHANNELS)}):</b>\n{channels_list}\n\n<b>Commands:</b>\n/addchannel @name - Add channel\n/removechannel @name - Remove channel")
            
    elif command == "/current":
        channels_list = "\n".join([f"• {ch}" for ch in CHANNELS]) if CHANNELS else "No channels"
        status_text = f"""
⚙️ <b>Current Bot Settings</b>

Posting Interval: {post_interval // 60} minute(s) ({post_interval} seconds)
Bot Status: {'Running ✅' if bot_running else 'Stopped ⏸️'}
Channels ({len(CHANNELS)}):
{channels_list}

<b>Commands:</b>
/interval 5m - Set interval to 5 minutes
/interval 30s - Set interval to 30 seconds
/addchannel @name - Add channel
/removechannel @name - Remove channel
/channels - List all channels
/stop - Stop posting
/startpost - Resume posting
"""
        send_message_to_user(chat_id, status_text)
        
    elif command == "/info":
        bot_info = get_bot_info()
        if bot_info:
            info_text = f"""
🤖 <b>Bot Information</b>

Name: {bot_info.get('first_name', 'Unknown')}
Username: @{bot_info.get('username', 'Unknown')}
ID: {bot_info.get('id', 'Unknown')}
Can Join Groups: {'Yes' if bot_info.get('can_join_groups', False) else 'No'}
Can Read All Group Messages: {'Yes' if bot_info.get('can_read_all_group_messages', False) else 'No'}
"""
            send_message_to_user(chat_id, info_text)
        else:
            send_message_to_user(chat_id, "❌ Could not get bot information")
            
    elif command == "/getmyid":
        user_info = f"""
🆔 <b>Your User Information</b>

User ID: <code>{user_id}</code>
Username: @{username if username != 'Unknown' else 'Not set'}
First Name: {message['from'].get('first_name', 'Unknown')}

<b>To add yourself as admin:</b>
1. Copy your User ID: <code>{user_id}</code>
2. Open telegram_btc_bot.py
3. Find ADMIN_USER_IDS = []
4. Change to: ADMIN_USER_IDS = [{user_id}]
5. Restart the bot
"""
        send_message_to_user(chat_id, user_info)
    else:
        send_message_to_user(chat_id, f"❌ Unknown command: {command}\nUse /help to see available commands.")

def run_bot():
    """Main function to run the bot"""
    global bot_running, last_update_id, post_interval, api_fail_count
    
    # Force immediate output
    print("", flush=True)
    print("=" * 50, flush=True)
    print("BTC Price Bot Starting...", flush=True)
    print("=" * 50, flush=True)
    print("", flush=True)
    
    print(f"Channels: {len(CHANNELS)} channel(s)")
    for ch in CHANNELS:
        print(f"  • {ch}")
    minutes = post_interval // 60
    seconds = post_interval % 60
    if seconds > 0:
        print(f"Posting interval: {minutes} min {seconds} sec ({post_interval} seconds)")
    else:
        print(f"Posting interval: {minutes} minute(s) ({post_interval} seconds)")
    if ADMIN_USER_IDS:
        print(f"Admin Users: {len(ADMIN_USER_IDS)}")
    else:
        print("⚠️  WARNING: No admin users configured. All users can control the bot!")
    print()
    sys.stdout.flush()
    
    # Test bot access first
    print("Testing bot access to channel...")
    sys.stdout.flush()
    if not test_bot_access():
        print()
        print("WARNING: Bot may not have access to the channel!")
        print("Please ensure:")
        print("1. Bot is added to channel as administrator")
        print("2. Bot has 'Post Messages' permission enabled")
        print("3. Check all channels are correct")
        print()
        print("Continuing anyway...")
        print()
    else:
        print()
    sys.stdout.flush()
    
    print("Bot is running. Waiting for first post...")
    print("Admin commands are enabled. Message the bot to control it.")
    print("Press Ctrl+C to stop the bot.")
    print("-" * 50)
    print()
    print("[INFO] API retry logic enabled (max 3 retries)")
    print("[INFO] Cached price will be used if API fails")
    print()
    sys.stdout.flush()
    
    # Initialize last_update_id
    updates = get_updates()
    
    last_price_post = 0
    
    while True:
        try:
            current_time = time.time()
            
            # Check for commands
            updates = get_updates()
            for update in updates:
                handle_command(update)
            
            # Post price if bot is running and interval has passed
            if bot_running and (current_time - last_price_post) >= post_interval:
                # Get BTC price with retry logic
                price, change_24h = get_btc_price()
                
                if price:
                    # Format and send message
                    message = format_price_message(price, change_24h)
                    if send_message_to_channel(message):
                        last_price_post = current_time
                        print(f"[SUCCESS] Price posted at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        sys.stdout.flush()
                    else:
                        print(f"[WARNING] Failed to send message at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        sys.stdout.flush()
                        # Don't update last_price_post, will retry on next cycle
                else:
                    # Only log if we don't have cached price
                    if not last_successful_price:
                        print(f"[WARNING] Failed to fetch BTC price at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        sys.stdout.flush()
                    # Don't update last_price_post if we failed completely
                    # Wait a bit before next attempt to avoid API spam
                    if api_fail_count > 0:
                        wait_time = min(api_fail_count * 5, 30)  # Max 30 seconds
                        print(f"[INFO] Waiting {wait_time} seconds before next API attempt...")
                        sys.stdout.flush()
                        time.sleep(wait_time)
            
            # Small sleep to avoid high CPU usage
            time.sleep(1)
            
        except KeyboardInterrupt:
            print()
            print()
            print("=" * 50)
            print("Bot stopped by user")
            print("=" * 50)
            sys.stdout.flush()
            break
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            sys.stdout.flush()
            time.sleep(5)  # Wait before retrying

# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n\nBot stopped by user")
    except Exception as e:
        print(f"\n[FATAL ERROR] Bot crashed: {e}")
        import traceback
        traceback.print_exc()
        if sys.platform == 'win32':
            input("\nPress Enter to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()
