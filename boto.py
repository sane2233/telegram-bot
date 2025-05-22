#!/usr/bin/env python3
import time
import threading
import logging

from telegram import Bot, Update
from telegram.error import TelegramError
from telegram.utils.request import Request

# ─── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "7761522081:AAGzRduDI8GjVSosqLFz4M0WqXs8ZATPiPI"
POLL_INTERVAL = 1  # seconds between get_updates calls

# follow-up delays (in seconds): 1m, 15m, 2h, 8h, 24h
FOLLOW_UP_INTERVALS = [60, 15*60, 2*3600, 8*3600, 24*3600]
FOLLOW_UP_MESSAGES = [
    "Just checking in—if you're ready to begin or have any questions, feel free to type here anytime.",
    "Still here if you need help. Whether it's your first deposit, platform walkthrough, or trading tips, we've got you!",
    "Let's not miss the opportunity to grow today. We can help you place your first trade in just a few minutes.",
    "Hello again! Our team is ready whenever you are. We don't want you to miss the ongoing signals and guidance.",
    "This will be our final message for today. We're always here when you're ready to continue—just say hi anytime!"
]
# ────────────────────────────────────────────────────────────────────────────────

# Increase HTTP connection pool to suppress warnings
request = Request(con_pool_size=8, connect_timeout=5.0, read_timeout=5.0)
bot = Bot(token=BOT_TOKEN, request=request)

offset = 0
user_timers = {}  # chat_id → list of threading.Timer

def safe_send(chat_id: int, text: str):
    """Attempt to send; on 'Forbidden', cancel any follow-ups."""
    try:
        bot.send_message(chat_id=chat_id, text=text)
    except TelegramError as e:
        if "Forbidden" in str(e):
            # user blocked or never started → stop scheduling
            cancel_timers(chat_id)
        else:
            logging.error(f"send_message failed for {chat_id}: {e}")

def cancel_timers(chat_id: int):
    """Cancel all follow-up timers for this chat."""
    for t in user_timers.get(chat_id, []):
        t.cancel()
    user_timers.pop(chat_id, None)

def schedule_followups(chat_id: int):
    """Schedule the chain of follow-up messages."""
    cancel_timers(chat_id)
    timers = []
    for delay, msg in zip(FOLLOW_UP_INTERVALS, FOLLOW_UP_MESSAGES):
        t = threading.Timer(delay, safe_send, args=(chat_id, msg))
        t.daemon = True
        t.start()
        timers.append(t)
    user_timers[chat_id] = timers

def handle_update(update: Update):
    global offset
    offset = update.update_id + 1

    # 1) GROUP: someone joined via link or request
    if update.message and update.message.new_chat_members:
        group_id = update.message.chat.id
        for member in update.message.new_chat_members:
            if member.is_bot:
                continue
            name = member.first_name or member.username or "there"
            # public welcome
            safe_send(group_id, f"Welcome, {name}! 🎉")
            # DM greeting + start follow-ups
            safe_send(member.id,
                f"Hey, {name}! Welcome to {update.message.chat.title}!\n"
                "I’m Mr. Bull—tell me where you’re from and your trading experience."
            )
            schedule_followups(member.id)
        return

    # 2) CHANNEL: approved join-request
    if update.chat_member:
        cm = update.chat_member
        if (cm.chat.type in ('channel','supergroup') and
            cm.old_chat_member.status in ('left','kicked') and
            cm.new_chat_member.status == 'member'):
            user = cm.new_chat_member.user
            name = user.first_name or user.username or "there"
            # DM greeting + follow-ups
            safe_send(user.id, f"Hey, {name}! Welcome to {cm.chat.title}!")
            safe_send(user.id,
                "I’m Mr. Bull—tell me where you’re from and your trading experience."
            )
            schedule_followups(user.id)
        return

    # 3) DIRECT: /start & manual replies
    msg = update.message
    if not msg or not msg.text:
        return

    chat_id = msg.chat.id
    text = msg.text.strip()
    user = msg.from_user
    name = user.first_name or user.username or "Trader"

    if text == "/start":
        safe_send(chat_id, f"Hey, {name}! Let's get to know each other first!")
        safe_send(chat_id, "I’m Mr. Bull—please tell me where you’re from and your trading experience.")
        schedule_followups(chat_id)
    else:
        cancel_timers(chat_id)
        print(f"\n--- New message from {name} ({chat_id}) ---")
        print(text)
        reply = input("Type your reply (and press Enter): ").strip()
        if reply:
            safe_send(chat_id, reply)
            schedule_followups(chat_id)

def main():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    print("Bot is running. Waiting for updates...")

    global offset
    while True:
        try:
            # No allowed_updates filter, to receive all update types
            updates = bot.get_updates(offset=offset, timeout=30)
            for upd in updates:
                handle_update(upd)

        except TelegramError as e:
            logging.error(f"TelegramError: {e}")
            time.sleep(5)
        except Exception:
            logging.exception("Unexpected error")
            time.sleep(5)
        finally:
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
