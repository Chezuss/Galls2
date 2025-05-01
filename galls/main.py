import time
import re
import pyautogui
import os
from dotenv import load_dotenv
from fish import *
import math
from collections import defaultdict
import json

# Track recent command timestamps per user
user_command_timestamps = defaultdict(list)
rate_limited_users = set()
rate_limited_users = {}

# Configurable limits
COMMAND_LIMIT = 2
COMMAND_WINDOW = 1  # seconds
COOLDOWN_TIME = 10
SAVE_FILE = "player_data.json"

RODS = {
    "basic": {"cost": 0, "multiplier": 1.0},
    "bronze": {"cost": 1000, "multiplier": 1.5},
    "silver": {"cost": 5000, "multiplier": 2.0},
    "gold": {"cost": 10000, "multiplier": 3.0},
    "diamond": {"cost": 50000000, "multiplier": 20.0},
}


load_dotenv()

CONSOLE_FILE = os.getenv('CONSOLE_FILE')
EXEC_FILE = os.getenv('EXEC_FILE')

class Player:
    def __init__(self, username, balance=10000.0, rod="basic"):
        self.username = username
        self.balance = balance
        self.rod = rod

    def get_balance(self):
        return self.balance

    def add_winnings(self, amount):
        self.balance += amount

    def set_balance(self, amount):
        self.balance = amount

    def set_rod(self, rod):
        self.rod = rod

    def get_rod(self):
        return self.rod

    def to_dict(self):
        return {
            "username": self.username,
            "balance": self.balance,
            "rod": self.rod
        }

    @staticmethod
    def from_dict(data):
        return Player(
            username=data["username"],
            balance=data["balance"],
            rod=data.get("rod", "basic")  # fallback to basic for legacy saves
        )

class Bank:
    def __init__(self):
        self.players = {}
        self.load_players()

    def load_players(self):
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, 'r') as f:
                data = json.load(f)
                for username, pdata in data.items():
                    self.players[username] = Player.from_dict(pdata)

    def save_players(self):
        with open(SAVE_FILE, 'w') as f:
            json.dump({user: player.to_dict() for user, player in self.players.items()}, f, indent=4)

    def get_player(self, username):
        if username not in self.players:
            if username.lower() == "padr3":
                self.players[username] = Player(username, 500000)
            elif username.lower() == "cheezus":
                self.players[username] = Player(username, 500000)
            else:
                self.players[username] = Player(username)
            self.save_players()
        return self.players[username]

    def update_player_balance(self, username, amount, set_balance=False):
        player = self.get_player(username)
        if set_balance:
            player.set_balance(amount)
        else:
            player.add_winnings(amount)
        self.save_players()

    def get_player_balance(self, username):
        return self.get_player(username).get_balance()

bank = Bank()

def listen(logFile):
    logFile.seek(0, os.SEEK_END)
    last_size = logFile.tell()

    while True:
        current_size = os.stat(logFile.name).st_size
        if current_size < last_size:
            logFile.seek(0, os.SEEK_SET)
            last_size = current_size

        line = logFile.readline()
        if not line:
            time.sleep(0.1)
            continue

        print(line.strip())
        parse(line)
        last_size = logFile.tell()

def parse(line):
    # Updated regex to capture chat type (ALL, T, CT)
    regex = re.search(r"\[(ALL|T|CT)\]\s+(.*?)\s*(?:\[DEAD\])?:\s*(\S+)?\s*(.*)?", line)
    if not regex:
        return

    print("Full match groups:", regex.groups())

    chat_type = regex.group(1)
    raw_username = regex.group(2)
    username = raw_username.split('\u200e﹫', 1)[0].strip()
    command = regex.group(3)
    args = regex.group(4).strip() if regex.group(4) else None

    is_team_chat = chat_type in ["T", "CT"]

    print(f"{username} ({chat_type}): {command} {args if args else ''}")

    if not command or not command.startswith("!"):
        return

    now = time.time()
    timestamps = user_command_timestamps[username]
    user_command_timestamps[username] = [ts for ts in timestamps if now - ts < COMMAND_WINDOW]

    if len(user_command_timestamps[username]) >= COMMAND_LIMIT:
        if username not in rate_limited_users:
            rate_limited_users[username] = {'blocked_until': now + COOLDOWN_TIME}
        else:
            rate_limited_users[username]['blocked_until'] = now + COOLDOWN_TIME
        
        write_command(f"say {username}, you're doing that too much. Cooldown: {COOLDOWN_TIME}s, Limit: {COMMAND_LIMIT} commands.", team_chat=is_team_chat)
        press_key(username)
        return

    user_command_timestamps[username].append(now)
    command = command.lower()

    if command == "!fish":
        cast_line(username, bank, team_chat=is_team_chat)
        write_command(f"say {username}'s balance: ${round(bank.get_player_balance(username), 2)}", team_chat=is_team_chat)
        press_key(username)

    elif command == "!gamble":
        try:
            if args is None:
                raise ValueError("No amount provided.")
            if args.lower() == "all":
                gamble_amount = bank.get_player_balance(username) - 0.01
                gamble_amount = truncate_to_hundredths(gamble_amount)
            else:
                gamble_amount = float(args)
            if not isinstance(gamble_amount, (int, float)) or math.isnan(gamble_amount):
                raise ValueError("Invalid number.")
            if gamble_amount <= 0:
                write_command("say Enter a positive number!", team_chat=is_team_chat)
            else:
                gamble(username, gamble_amount, bank, is_team_chat)
        except ValueError:
            write_command("say Invalid input. Please enter a number or 'all'.", team_chat=is_team_chat)
        finally:
            press_key(username)

    elif command == "!balance":
        balance = round(bank.get_player_balance(username), 2)
        write_command(f"say {username}, your current balance is: ${balance}", team_chat=is_team_chat)
        press_key(username)

    elif command == "!leaderboard":
        top_players = sorted(bank.players.values(), key=lambda p: p.balance, reverse=True)[:5]
        leaderboard_lines = [f"{i+1}. {p.username}: ${round(p.balance, 2)}" for i, p in enumerate(top_players)]
        for line in leaderboard_lines:
            write_command(f"say {line}", team_chat=is_team_chat)
            press_key(username)

    elif command == "!buyrod":
        if not args:
            write_command(f"say {username}, usage: !buyrod <type>. Available: {', '.join(RODS.keys())}", team_chat=is_team_chat)
            press_key(username)
            return

        rod_type = args.lower()
        if rod_type not in RODS:
            write_command(f"say {username}, unknown rod type '{rod_type}'. Options: {', '.join(RODS.keys())}", team_chat=is_team_chat)
            press_key(username)
            return

        player = bank.get_player(username)
        current_rod = player.get_rod()
        if RODS[rod_type]["cost"] == 0:
            write_command(f"say {username}, the basic rod is already yours.", team_chat=is_team_chat)
            press_key(username)
            return
        if RODS[rod_type]["cost"] <= RODS[current_rod]["cost"]:
            write_command(f"say {username}, you already have a rod of equal or better quality.", team_chat=is_team_chat)
            press_key(username)
            return
        if player.get_balance() < RODS[rod_type]["cost"]:
            write_command(f"say {username}, you can't afford the {rod_type} rod. Cost: ${RODS[rod_type]['cost']}", team_chat=is_team_chat)
            press_key(username)
            return

        bank.update_player_balance(username, -RODS[rod_type]["cost"])
        player.set_rod(rod_type)
        bank.save_players()
        write_command(f"say {username} purchased the {rod_type} rod! Fish value multiplier: {RODS[rod_type]['multiplier']}x", team_chat=is_team_chat)
        press_key(username)

    elif command == "!listrods":
        sorted_rods = sorted(RODS.items(), key=lambda x: x[1]["cost"])
        for rod_name, rod_info in sorted_rods:
            rod_message = f"• {rod_name.capitalize()} Rod: ${rod_info['cost']} | Multiplier: x{rod_info['multiplier']}"
            write_command(f"say {rod_message}", team_chat=is_team_chat)
            press_key()
            time.sleep(1)

    elif command == "!help":
        help_messages = [
            "Available Commands:",
            "-!fish - Cast your line and try to catch a fish.",
            "-!gamble <amount|all> - Gamble an amount of money or all your balance.",
            "-!balance - Check your current money balance.",
            "-!leaderboard - View the top 5 players by balance.",
            "-!buyrod <type> - Buy a better fishing rod to increase fish value.",
            "-!listrods - List all available rods and their effects.",
            "-!help - Show this list of commands."
        ]
        for line in help_messages:
            write_command(f"say {line}", team_chat=is_team_chat)
            press_key()
            time.sleep(0.3)
            

def truncate_to_hundredths(value):
    return math.trunc(value * 100) / 100

def gamble(username, amount, bank, team_chat=False):
    current_balance = bank.get_player_balance(username)

    if current_balance < amount:
        write_command(f"say {username}, you don't have enough money to gamble that amount!", team_chat=team_chat)
        return

    roll = random.randint(1, 15)

    if 1 <= roll <= 6:
        new_balance = truncate_to_hundredths(current_balance - amount)
        write_command(f"say {username} gambled ${amount} and lost. New balance: ${new_balance}.", team_chat=team_chat)
        bank.update_player_balance(username, new_balance, set_balance=True)
    elif 7 <= roll <= 10:
        new_balance = truncate_to_hundredths(current_balance + amount * 2)
        write_command(f"say {username} gambled ${amount} and won 2x! New balance: ${new_balance}.", team_chat=team_chat)
        bank.update_player_balance(username, new_balance, set_balance=True)
    elif 10 <= roll <= 12:
        new_balance = truncate_to_hundredths(current_balance + amount * 5)
        write_command(f"say {username} gambled ${amount} and won 5x! New balance: ${new_balance}.", team_chat=team_chat)
        bank.update_player_balance(username, new_balance, set_balance=True)
    elif 13 <= roll <= 14:
        new_balance = truncate_to_hundredths(current_balance + amount * 20)
        write_command(f"say {username} gambled ${amount} and won 20x! New balance: ${new_balance}.", team_chat=team_chat)
        bank.update_player_balance(username, new_balance, set_balance=True)
    elif roll == 15:
        new_balance = truncate_to_hundredths(current_balance + amount * 777)
        write_command(f"say {username} hit the JACKPOT!!! New balance: ${new_balance}.", team_chat=team_chat)
        bank.update_player_balance(username, new_balance, set_balance=True)

    

        

def write_command(command, team_chat=False):
    with open(EXEC_FILE, 'w', encoding='utf-8') as f:
        if command.startswith("say") or command.startswith("say_team"):
            if team_chat:
                command = command.replace("say ", "say_team ", 1)
            else:
                command = command.replace("say_team ", "say ", 1)
        f.write(command)

def press_key(username=None):
    if username and username in rate_limited_users:
        blocked_until = rate_limited_users[username]['blocked_until']
        if time.time() < blocked_until:
            print(f"[BLOCKED] {username} is rate-limited until {blocked_until - time.time():.1f}s.")
            return  # Don't press the key, they're still in cooldown
        else:
            # Cooldown has passed, unblock the user
            del rate_limited_users[username]
            print(f"[UNBLOCKED] {username} is no longer rate-limited.")
    
    time.sleep(0.2)
    pyautogui.press('multiply')

def press_key_no_delay(username=None):
    if username and username in rate_limited_users:
        blocked_until = rate_limited_users[username]['blocked_until']
        if time.time() < blocked_until:
            print(f"[BLOCKED] {username} is rate-limited until {blocked_until - time.time():.1f}s.")
            return
        else:
            # Cooldown has passed, unblock the user
            del rate_limited_users[username]
            print(f"[UNBLOCKED] {username} is no longer rate-limited.")
    
    pyautogui.press('multiply')


if __name__ == '__main__':
    log_file = open(CONSOLE_FILE, "r", encoding="utf-8")
    try:
        while True:
            listen(log_file)
    except KeyboardInterrupt:
        print("Shutting down, saving player data...")
        bank.save_players()