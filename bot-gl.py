"""
JOBAO - Discord Bot for Golike Automation
Support multiple Golike accounts | Auto farming jobs 24/7
Version: Discord v1.0
"""
# Thêm vào đầu file với các import khác
from flask import Flask, request
import threading

# Tạo Flask app để nhận ping từ UptimeRobot
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is alive!", 200

@flask_app.route('/ping')
def ping():
    # UptimeRobot sẽ ping vào đây mỗi 5 phút
    print("Received ping from UptimeRobot")
    return "pong", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

# Trong hàm main hoặc lúc khởi động bot, chạy Flask trong thread riêng
# threading.Thread(target=run_flask, daemon=True).start()


import os
import sys
import time
import json
import asyncio
import threading
from datetime import datetime
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    os.system("pip install requests")
    import requests

try:
    import discord
    from discord.ext import commands, tasks
except ImportError:
    os.system("pip install discord.py")
    import discord
    from discord.ext import commands, tasks

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DISCORD_TOKEN_FILE = "discord_token.txt"
GOLIKE_ACCOUNTS_FILE = "golike_accounts.json"
CONFIG_FILE = "bot_config.json"

# Default config
BOT_CONFIG = {
    "prefix": "!",
    "auto_farm_enabled": True,
    "farm_interval_minutes": 30,
    "jobs_per_session": 500,
    "delay_between_jobs": 5,
    "max_consecutive_errors": 5,
    "webhook_url": "",
    "notification_channel_id": None
}

# Store Golike accounts
# Format: {"account_name": {"auth": "xxx", "t": "xxx", "enabled": True, "total_earned": 0}}
GOLIKE_ACCOUNTS = {}

# Store running farm threads
ACTIVE_FARMS = {}

# ==============================================================================
# GOLIKE BOT CLASS (from original code)
# ==============================================================================
class MauSac:
    MAC_DINH = '\033[0m'
    DO = '\033[31m'
    XANH_LA = '\033[32m'
    VANG = '\033[33m'
    XANH_DUONG = '\033[34m'
    XANH_LO = '\033[36m'
    DAM_XANH_LA = '\033[1;32m'

class BotCoBan:
    def __init__(self, golike_auth: str, golike_t: str, nen_tang: str):
        self.golike_auth = golike_auth
        self.golike_t = golike_t
        self.nen_tang = nen_tang
        self.session = requests.Session()
        self.session.headers.update({
            'accept': 'application/json, text/plain, */*',
            'authorization': self.golike_auth,
            't': self.golike_t,
            'content-type': 'application/json;charset=utf-8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36',
        })

    def lay_danh_sach_tai_khoan(self):
        try:
            resp = self.session.get(f'https://gateway.golike.net/api/{self.nen_tang}-account', timeout=30)
            return resp.json()
        except Exception as e:
            return None

    def lay_job(self, account_id: str):
        try:
            resp = self.session.get(
                f'https://gateway.golike.net/api/advertising/publishers/{self.nen_tang}/jobs?account_id={account_id}&data=null',
                timeout=30
            )
            return resp.json()
        except Exception as e:
            return None

    def hoan_thanh_job(self, ads_id: str, account_id: str):
        try:
            du_lieu_json = {
                'ads_id': ads_id,
                'account_id': account_id,
                'async': True,
                'data': None
            }
            resp = self.session.post(
                f'https://gateway.golike.net/api/advertising/publishers/{self.nen_tang}/complete-jobs',
                json=du_lieu_json,
                timeout=30
            )
            return resp.json()
        except Exception as e:
            return None

    def bo_qua_job(self, ads_id: str, account_id: str, object_id: str):
        try:
            du_lieu_json = {
                'ads_id': ads_id,
                'account_id': account_id,
                'object_id': object_id
            }
            self.session.post(
                f'https://gateway.golike.net/api/advertising/publishers/{self.nen_tang}/skip-jobs',
                json=du_lieu_json,
                timeout=30
            )
        except:
            pass

class BotTwitter(BotCoBan):
    def __init__(self, golike_auth, golike_t):
        super().__init__(golike_auth, golike_t, "twitter")

class BotLinkedin(BotCoBan):
    def __init__(self, golike_auth, golike_t):
        super().__init__(golike_auth, golike_t, "linkedin")

class BotThreads(BotCoBan):
    def __init__(self, golike_auth, golike_t):
        super().__init__(golike_auth, golike_t, "threads")

class BotPinterest(BotCoBan):
    def __init__(self, golike_auth, golike_t):
        super().__init__(golike_auth, golike_t, "pinterest")

class BotSnapchat(BotCoBan):
    def __init__(self, golike_auth, golike_t):
        super().__init__(golike_auth, golike_t, "snapchat")

# ==============================================================================
# FARMING ENGINE
# ==============================================================================
class GolikeFarmer:
    def __init__(self, account_name: str, auth: str, t_token: str):
        self.account_name = account_name
        self.auth = auth
        self.t_token = t_token
        self.is_running = False
        self.total_jobs_completed = 0
        self.total_earned = 0
        self.platforms = [
            ("Twitter", BotTwitter),
            ("LinkedIn", BotLinkedin),
            ("Threads", BotThreads),
            ("Pinterest", BotPinterest),
            ("Snapchat", BotSnapchat)
        ]

    def check_auth(self) -> bool:
        """Kiểm tra auth có hợp lệ không"""
        try:
            headers = {
                'accept': 'application/json, text/plain, */*',
                'authorization': self.auth,
                't': self.t_token,
                'content-type': 'application/json;charset=utf-8',
                'user-agent': 'Mozilla/5.0 (Android 10; K) AppleWebKit/537.36'
            }
            resp = requests.get('https://gateway.golike.net/api/users/me', headers=headers, timeout=30)
            data = resp.json()
            if data.get('status') == 200:
                user_data = data.get('data', {})
                return True, user_data.get('username', 'Unknown'), user_data.get('coin', 0)
            return False, None, None
        except Exception as e:
            return False, None, None

    def farm_platform(self, platform_name: str, BotClass, max_jobs: int, delay: int) -> Dict:
        """Farm jobs trên một nền tảng"""
        results = {
            "success": 0,
            "failed": 0,
            "earned": 0,
            "errors": []
        }
        
        try:
            bot = BotClass(self.auth, self.t_token)
            
            # Lấy danh sách tài khoản mạng xã hội
            acc_response = bot.lay_danh_sach_tai_khoan()
            if not acc_response or acc_response.get('status') != 200:
                return results
            
            accounts = acc_response.get('data', [])
            if not accounts:
                return results
            
            account_errors = {acc.get('id'): 0 for acc in accounts}
            account_index = 0
            
            for job_count in range(max_jobs):
                if not self.is_running:
                    break
                    
                if account_index >= len(accounts):
                    account_index = 0
                
                current_acc = accounts[account_index]
                acc_id = current_acc.get('id')
                acc_name = current_acc.get('name', current_acc.get('username', 'Unknown'))
                
                # Bỏ qua tài khoản lỗi quá nhiều
                if account_errors.get(acc_id, 0) >= 3:
                    account_index += 1
                    continue
                
                # Lấy job
                job = bot.lay_job(acc_id)
                if not job or job.get('status') != 200:
                    account_errors[acc_id] = account_errors.get(acc_id, 0) + 1
                    account_index += 1
                    continue
                
                job_data = job.get('data', {})
                ads_id = job_data.get('id', '')
                object_id = job_data.get('object_id', '')
                job_type = job_data.get('type', 'unknown')
                
                # Hoàn thành job
                complete_response = bot.hoan_thanh_job(ads_id, acc_id)
                if complete_response and (complete_response.get('success') == True or complete_response.get('status') == 200):
                    earned = complete_response.get('data', {}).get('prices', 0)
                    results["success"] += 1
                    results["earned"] += earned
                    account_errors[acc_id] = 0
                else:
                    results["failed"] += 1
                    account_errors[acc_id] = account_errors.get(acc_id, 0) + 1
                    bot.bo_qua_job(ads_id, acc_id, object_id)
                
                account_index += 1
                
                # Delay giữa các job
                if delay > 0 and self.is_running:
                    time.sleep(delay)
                    
        except Exception as e:
            results["errors"].append(str(e))
        
        return results

    def run_farm(self, max_jobs: int = 500, delay: int = 5, on_progress=None) -> Dict:
        """Chạy farm trên tất cả nền tảng"""
        self.is_running = True
        total_results = {
            "total_success": 0,
            "total_failed": 0,
            "total_earned": 0,
            "platforms": {}
        }
        
        for platform_name, BotClass in self.platforms:
            if not self.is_running:
                break
                
            if on_progress:
                on_progress(f"🔄 Đang farm {platform_name}...")
            
            results = self.farm_platform(platform_name, BotClass, max_jobs, delay)
            total_results["total_success"] += results["success"]
            total_results["total_failed"] += results["failed"]
            total_results["total_earned"] += results["earned"]
            total_results["platforms"][platform_name] = results
            
            if on_progress:
                on_progress(f"✅ {platform_name}: {results['success']} jobs thành công, +{results['earned']} VND")
        
        self.total_jobs_completed += total_results["total_success"]
        self.total_earned += total_results["total_earned"]
        self.is_running = False
        
        return total_results

    def stop(self):
        self.is_running = False

# ==============================================================================
# DISCORD BOT
# ==============================================================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=BOT_CONFIG["prefix"], intents=intents)

# Lưu các farmer đang chạy
active_farmers = {}
farm_tasks = {}

def load_data():
    """Load dữ liệu từ file"""
    global GOLIKE_ACCOUNTS, BOT_CONFIG
    
    # Load Discord token
    if os.path.exists(DISCORD_TOKEN_FILE):
        with open(DISCORD_TOKEN_FILE, 'r') as f:
            BOT_CONFIG["discord_token"] = f.read().strip()
    
    # Load Golike accounts
    if os.path.exists(GOLIKE_ACCOUNTS_FILE):
        with open(GOLIKE_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            GOLIKE_ACCOUNTS = json.load(f)
    
    # Load bot config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
            BOT_CONFIG.update(saved_config)
            bot.command_prefix = BOT_CONFIG["prefix"]

def save_accounts():
    """Lưu danh sách tài khoản"""
    with open(GOLIKE_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(GOLIKE_ACCOUNTS, f, indent=4, ensure_ascii=False)

def save_config():
    """Lưu cấu hình bot"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(BOT_CONFIG, f, indent=4, ensure_ascii=False)

# ==============================================================================
# DISCORD COMMANDS
# ==============================================================================
@bot.event
async def on_ready():
    print(f"{bot.user} đã sẵn sàng!")
    await bot.change_presence(activity=discord.Game(name=f"{BOT_CONFIG['prefix']}help | Golike Farm"))
    
    # Gửi thông báo đến channel nếu có cấu hình
    if BOT_CONFIG.get("notification_channel_id"):
        channel = bot.get_channel(BOT_CONFIG["notification_channel_id"])
        if channel:
            await channel.send("✅ Bot đã khởi động và sẵn sàng!")

@bot.command(name="add")
async def add_account(ctx, name: str, auth: str, t_token: str = "VFZSamQwOUVSVEpQVkVFd1RrRTlQUT09"):
    """Thêm tài khoản Golike mới
    !add <tên> <authorization> [t_token]
    """
    # Kiểm tra auth
    farmer = GolikeFarmer(name, auth, t_token)
    is_valid, username, coin = farmer.check_auth()
    
    if not is_valid:
        embed = discord.Embed(
            title="❌ Thất bại",
            description="Authorization không hợp lệ! Vui lòng kiểm tra lại.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Thêm tài khoản
    GOLIKE_ACCOUNTS[name] = {
        "auth": auth,
        "t": t_token,
        "enabled": True,
        "total_earned": 0,
        "total_jobs": 0,
        "username": username,
        "coin": coin,
        "added_at": datetime.now().isoformat()
    }
    save_accounts()
    
    embed = discord.Embed(
        title="✅ Đã thêm tài khoản",
        description=f"**Tên:** {name}\n**Username:** {username}\n**Coin hiện tại:** {coin}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="list")
async def list_accounts(ctx):
    """Xem danh sách tài khoản Golike"""
    if not GOLIKE_ACCOUNTS:
        await ctx.send("📭 Chưa có tài khoản nào. Dùng `!add` để thêm.")
        return
    
    embed = discord.Embed(
        title="📋 Danh sách tài khoản Golike",
        color=discord.Color.blue()
    )
    
    for name, info in GOLIKE_ACCOUNTS.items():
        status = "🟢" if info.get("enabled", True) else "🔴"
        embed.add_field(
            name=f"{status} {name}",
            value=f"User: {info.get('username', 'N/A')}\nCoin: {info.get('coin', 0)}\nJobs: {info.get('total_jobs', 0)}\nEarned: {info.get('total_earned', 0)} VND",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="remove")
async def remove_account(ctx, name: str):
    """Xóa tài khoản Golike"""
    if name not in GOLIKE_ACCOUNTS:
        await ctx.send(f"❌ Không tìm thấy tài khoản `{name}`")
        return
    
    # Dừng farm nếu đang chạy
    if name in active_farmers:
        active_farmers[name].stop()
        del active_farmers[name]
    
    del GOLIKE_ACCOUNTS[name]
    save_accounts()
    
    await ctx.send(f"✅ Đã xóa tài khoản `{name}`")

@bot.command(name="farm")
async def start_farm(ctx, account_name: str = None, jobs: int = None):
    """Bắt đầu farm jobs
    !farm [tên_account] [số_lượng_jobs]
    """
    # Xác định tài khoản cần farm
    if account_name:
        if account_name not in GOLIKE_ACCOUNTS:
            await ctx.send(f"❌ Không tìm thấy tài khoản `{account_name}`")
            return
        accounts_to_farm = {account_name: GOLIKE_ACCOUNTS[account_name]}
    else:
        # Farm tất cả tài khoản đang bật
        accounts_to_farm = {name: info for name, info in GOLIKE_ACCOUNTS.items() if info.get("enabled", True)}
    
    if not accounts_to_farm:
        await ctx.send("❌ Không có tài khoản nào để farm.")
        return
    
    # Cài đặt số lượng jobs
    max_jobs = jobs if jobs else BOT_CONFIG["jobs_per_session"]
    
    # Thông báo bắt đầu
    embed = discord.Embed(
        title="🚀 BẮT ĐẦU FARM",
        description=f"**Số tài khoản:** {len(accounts_to_farm)}\n**Jobs mỗi nền tảng:** {max_jobs}\n**Delay:** {BOT_CONFIG['delay_between_jobs']}s",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)
    
    # Chạy farm cho từng tài khoản
    for name, info in accounts_to_farm.items():
        # Kiểm tra xem tài khoản đã được farm chưa
        if name in active_farmers and active_farmers[name].is_running:
            await ctx.send(f"⚠️ Tài khoản `{name}` đang được farm, bỏ qua...")
            continue
        
        # Tạo farmer mới
        farmer = GolikeFarmer(name, info["auth"], info.get("t", "VFZSamQwOUVSVEpQVkVFd1RrRTlQUT09"))
        active_farmers[name] = farmer
        
        # Hàm callback để gửi cập nhật
        async def send_update(account, message):
            channel = ctx.channel
            await channel.send(f"**{account}:** {message}")
        
        # Chạy farm trong thread riêng
        def run_farm():
            def progress_callback(msg):
                asyncio.run_coroutine_threadsafe(send_update(name, msg), bot.loop)
            
            results = farmer.run_farm(max_jobs, BOT_CONFIG["delay_between_jobs"], progress_callback)
            
            # Cập nhật thống kê
            if name in GOLIKE_ACCOUNTS:
                GOLIKE_ACCOUNTS[name]["total_jobs"] = GOLIKE_ACCOUNTS[name].get("total_jobs", 0) + results["total_success"]
                GOLIKE_ACCOUNTS[name]["total_earned"] = GOLIKE_ACCOUNTS[name].get("total_earned", 0) + results["total_earned"]
                save_accounts()
            
            # Gửi kết quả
            result_msg = f"✅ **Hoàn thành farm {name}**\n✅ Thành công: {results['total_success']}\n💰 Kiếm được: {results['total_earned']} VND\n📈 Tổng: {GOLIKE_ACCOUNTS[name].get('total_earned', 0)} VND"
            asyncio.run_coroutine_threadsafe(send_update(name, result_msg), bot.loop)
            
            # Xóa khỏi active farms
            if name in active_farmers:
                del active_farmers[name]
        
        thread = threading.Thread(target=run_farm)
        thread.start()
        
        await ctx.send(f"🔄 Đã bắt đầu farm cho tài khoản `{name}`")

@bot.command(name="stop")
async def stop_farm(ctx, account_name: str = None):
    """Dừng farm
    !stop [tên_account]
    """
    if account_name:
        if account_name in active_farmers:
            active_farmers[account_name].stop()
            del active_farmers[account_name]
            await ctx.send(f"🛑 Đã dừng farm cho tài khoản `{account_name}`")
        else:
            await ctx.send(f"❌ Tài khoản `{account_name}` không đang được farm")
    else:
        # Dừng tất cả
        for name, farmer in list(active_farmers.items()):
            farmer.stop()
            del active_farmers[name]
        await ctx.send("🛑 Đã dừng tất cả các phiên farm")

@bot.command(name="status")
async def farm_status(ctx):
    """Xem trạng thái các phiên farm đang chạy"""
    if not active_farmers:
        await ctx.send("📪 Không có phiên farm nào đang chạy")
        return
    
    embed = discord.Embed(
        title="🔄 Trạng thái farm",
        color=discord.Color.blue()
    )
    
    for name, farmer in active_farmers.items():
        embed.add_field(
            name=name,
            value=f"Trạng thái: {'🟢 Đang chạy' if farmer.is_running else '🔴 Dừng'}\nJobs hoàn thành: {farmer.total_jobs_completed}\nKiếm được: {farmer.total_earned} VND",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="config")
async def show_config(ctx, setting: str = None, value: str = None):
    """Xem hoặc thay đổi cấu hình bot"""
    if setting and value:
        # Thay đổi cấu hình
        if setting == "prefix":
            BOT_CONFIG["prefix"] = value
            bot.command_prefix = value
            await ctx.send(f"✅ Đã đổi prefix thành `{value}`")
        elif setting == "jobs":
            BOT_CONFIG["jobs_per_session"] = int(value)
            await ctx.send(f"✅ Đã đổi số jobs mỗi phiên thành `{value}`")
        elif setting == "delay":
            BOT_CONFIG["delay_between_jobs"] = int(value)
            await ctx.send(f"✅ Đã đổi delay thành `{value}` giây")
        elif setting == "errors":
            BOT_CONFIG["max_consecutive_errors"] = int(value)
            await ctx.send(f"✅ Đã đổi số lỗi tối đa thành `{value}`")
        elif setting == "interval":
            BOT_CONFIG["farm_interval_minutes"] = int(value)
            await ctx.send(f"✅ Đã đổi khoảng cách auto farm thành `{value}` phút")
        else:
            await ctx.send(f"❌ Không biết setting `{setting}`. Các setting có thể đổi: prefix, jobs, delay, errors, interval")
        
        save_config()
    else:
        # Hiển thị cấu hình
        embed = discord.Embed(
            title="⚙️ Cấu hình bot",
            color=discord.Color.blue()
        )
        embed.add_field(name="Prefix", value=f"`{BOT_CONFIG['prefix']}`", inline=True)
        embed.add_field(name="Auto farm", value="🟢 Bật" if BOT_CONFIG['auto_farm_enabled'] else "🔴 Tắt", inline=True)
        embed.add_field(name="Interval (phút)", value=f"{BOT_CONFIG['farm_interval_minutes']}", inline=True)
        embed.add_field(name="Jobs/session", value=f"{BOT_CONFIG['jobs_per_session']}", inline=True)
        embed.add_field(name="Delay (giây)", value=f"{BOT_CONFIG['delay_between_jobs']}", inline=True)
        embed.add_field(name="Max errors", value=f"{BOT_CONFIG['max_consecutive_errors']}", inline=True)
        
        await ctx.send(embed=embed)

@bot.command(name="enable")
async def enable_account(ctx, name: str):
    """Bật tài khoản (cho phép farm)"""
    if name not in GOLIKE_ACCOUNTS:
        await ctx.send(f"❌ Không tìm thấy tài khoản `{name}`")
        return
    
    GOLIKE_ACCOUNTS[name]["enabled"] = True
    save_accounts()
    await ctx.send(f"✅ Đã bật tài khoản `{name}`")

@bot.command(name="disable")
async def disable_account(ctx, name: str):
    """Tắt tài khoản (không farm)"""
    if name not in GOLIKE_ACCOUNTS:
        await ctx.send(f"❌ Không tìm thấy tài khoản `{name}`")
        return
    
    # Dừng farm nếu đang chạy
    if name in active_farmers:
        active_farmers[name].stop()
        del active_farmers[name]
    
    GOLIKE_ACCOUNTS[name]["enabled"] = False
    save_accounts()
    await ctx.send(f"✅ Đã tắt tài khoản `{name}`")

@bot.command(name="auto")
async def toggle_auto(ctx):
    """Bật/tắt chế độ auto farm"""
    BOT_CONFIG["auto_farm_enabled"] = not BOT_CONFIG["auto_farm_enabled"]
    save_config()
    
    status = "🟢 BẬT" if BOT_CONFIG["auto_farm_enabled"] else "🔴 TẮT"
    await ctx.send(f"✅ Chế độ auto farm: {status}")

@bot.command(name="check")
async def check_account(ctx, name: str):
    """Kiểm tra thông tin tài khoản Golike"""
    if name not in GOLIKE_ACCOUNTS:
        await ctx.send(f"❌ Không tìm thấy tài khoản `{name}`")
        return
    
    info = GOLIKE_ACCOUNTS[name]
    farmer = GolikeFarmer(name, info["auth"], info.get("t", "VFZSamQwOUVSVEpQVkVFd1RrRTlQUT09"))
    is_valid, username, coin = farmer.check_auth()
    
    embed = discord.Embed(
        title=f"📊 Thông tin tài khoản: {name}",
        color=discord.Color.green() if is_valid else discord.Color.red()
    )
    embed.add_field(name="Username", value=username if username else "N/A", inline=True)
    embed.add_field(name="Coin hiện tại", value=f"{coin} VND" if coin else "N/A", inline=True)
    embed.add_field(name="Trạng thái auth", value="✅ Hợp lệ" if is_valid else "❌ Không hợp lệ", inline=True)
    embed.add_field(name="Đã bật", value="🟢 Có" if info.get("enabled", True) else "🔴 Không", inline=True)
    embed.add_field(name="Tổng jobs đã làm", value=info.get("total_jobs", 0), inline=True)
    embed.add_field(name="Tổng đã kiếm", value=f"{info.get('total_earned', 0)} VND", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="help_farm")
async def help_command(ctx):
    """Hiển thị trợ giúp"""
    embed = discord.Embed(
        title="🤖 JOBAO - Golike Discord Bot",
        description="Bot tự động farm kiếm tiền từ Golike với hỗ trợ nhiều tài khoản",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="📋 Quản lý tài khoản",
        value="`!add <tên> <auth> [t]` - Thêm tài khoản\n`!list` - Xem danh sách\n`!remove <tên>` - Xóa tài khoản\n`!enable/disable <tên>` - Bật/tắt\n`!check <tên>` - Kiểm tra thông tin",
        inline=False
    )
    
    embed.add_field(
        name="🚀 Farm jobs",
        value="`!farm [tên] [số_lượng]` - Bắt đầu farm\n`!stop [tên]` - Dừng farm\n`!status` - Xem trạng thái đang chạy",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Cấu hình",
        value="`!config` - Xem cấu hình\n`!config <setting> <value>` - Thay đổi (prefix, jobs, delay, errors, interval)\n`!auto` - Bật/tắt auto farm",
        inline=False
    )
    
    embed.set_footer(text="Tool hỗ trợ 5 nền tảng: Twitter, LinkedIn, Threads, Pinterest, Snapchat")
    
    await ctx.send(embed=embed)

# ==============================================================================
# AUTO FARM TASK
# ==============================================================================
@tasks.loop(minutes=BOT_CONFIG["farm_interval_minutes"])
async def auto_farm():
    if not BOT_CONFIG["auto_farm_enabled"]:
        return
    
    if not BOT_CONFIG.get("notification_channel_id"):
        return
    
    channel = bot.get_channel(BOT_CONFIG["notification_channel_id"])
    if not channel:
        return
    
    # Lấy tất cả tài khoản đã bật
    enabled_accounts = {name: info for name, info in GOLIKE_ACCOUNTS.items() if info.get("enabled", True)}
    
    if not enabled_accounts:
        return
    
    await channel.send("🔄 **Auto farm** đang bắt đầu...")
    
    for name, info in enabled_accounts.items():
        if name in active_farmers and active_farmers[name].is_running:
            continue
        
        farmer = GolikeFarmer(name, info["auth"], info.get("t", "VFZSamQwOUVSVEpQVkVFd1RrRTlQUT09"))
        active_farmers[name] = farmer
        
        def run_auto_farm():
            results = farmer.run_farm(BOT_CONFIG["jobs_per_session"], BOT_CONFIG["delay_between_jobs"])
            
            if name in GOLIKE_ACCOUNTS:
                GOLIKE_ACCOUNTS[name]["total_jobs"] = GOLIKE_ACCOUNTS[name].get("total_jobs", 0) + results["total_success"]
                GOLIKE_ACCOUNTS[name]["total_earned"] = GOLIKE_ACCOUNTS[name].get("total_earned", 0) + results["total_earned"]
                save_accounts()
            
            if name in active_farmers:
                del active_farmers[name]
        
        thread = threading.Thread(target=run_auto_farm)
        thread.start()
        
        await channel.send(f"🔄 Đã bắt đầu auto farm cho `{name}`")
        await asyncio.sleep(5)

@auto_farm.before_loop
async def before_auto_farm():
    await bot.wait_until_ready()

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    load_data()
    
    # Kiểm tra Discord token
    if not BOT_CONFIG.get("discord_token"):
        print("⚠️ Chưa có Discord token!")
        token = input("Nhập Discord Bot Token: ").strip()
        if token:
            with open(DISCORD_TOKEN_FILE, 'w') as f:
                f.write(token)
            BOT_CONFIG["discord_token"] = token
    
    # Chạy bot
    token = BOT_CONFIG.get("discord_token")
    if token:
        # Khởi động auto farm task
        auto_farm.change_interval(minutes=BOT_CONFIG["farm_interval_minutes"])
        auto_farm.start()
        
        # Chạy bot
        bot.run(token)
    else:
        print("❌ Không có Discord token. Bot không thể chạy.")

if __name__ == "__main__":
    main()