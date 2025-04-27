import discord
import os
from dotenv import load_dotenv
import asyncio
import base64
import requests
from discord import ui
import json
import datetime

load_dotenv(dotenv_path="HissBOT.env")
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

load_dotenv(dotenv_path="Google.env")
api_key = os.getenv("GOOGLE_API_KEY")

# ================= OCR =================
def recognize_text_google(image_path):
    with open(image_path, "rb") as image_file:
        content = base64.b64encode(image_file.read()).decode('utf-8')

    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"

    data = {
        "requests": [{
            "image": {"content": content},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    response = requests.post(url, json=data)
    result = response.json()

    if 'responses' in result and 'textAnnotations' in result['responses'][0]:
        return result['responses'][0]['textAnnotations'][0]['description']
    else:
        print("result:", result)
        return ""

# ================= 紀錄 =================
MEMBERSHIP_LOG_CHANNEL_ID = 1366064300682383482 # test: 1366059232046223440, Hiss: 1366064300682383482

async def log_verification_success(user, role_name):
    now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
    log_message = f"✅ {now.strftime('%Y/%m/%d %H:%M:%S')} User: {user.mention} (ID: {user.id}) verified as: {role_name}"

    channel = client.get_channel(MEMBERSHIP_LOG_CHANNEL_ID)
    if channel:
        await channel.send(log_message)

# ================= 按鈕 =================
# TODO: Change channel IDs here
CHANNEL_ID = 1365293969306681406 # test: 1365649281536626751, Hiss: 1365293969306681406

class VerifyButtonView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔰 我要驗證", style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id != CHANNEL_ID:
            await interaction.response.send_message("❌ 請到指定頻道點擊驗證按鈕！", ephemeral=True)
            return

        verify_channel = interaction.guild.get_channel(CHANNEL_ID)
        if not verify_channel:
            await interaction.response.send_message("❌ 驗證頻道設定錯誤，請通知管理員！", ephemeral=True)
            return

        thread_name = f"verify-{interaction.user.name}-{interaction.user.id}"

        thread = await verify_channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=60,
            invitable=False
        )

        await thread.add_user(interaction.user)
        await thread.send(f"{interaction.user.mention} 請上傳你的會員截圖進行驗證 ✨")
        await interaction.response.send_message("✅ 已建立你的私人驗證區，請進入 thread 上傳截圖！", ephemeral=True)

# ================= on_ready =================
@client.event
async def on_ready():
    print(f"Bot is online: {client.user}")
    client.add_view(VerifyButtonView())
    client.loop.create_task(daily_check_and_remove_roles_from_membership_channel())

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        async for msg in channel.history(limit=10):
            if msg.author == client.user and msg.components:
                # 已經有自己的按鈕了，不重發
                print(f"按鈕訊息已存在於 {channel.name}，略過發送")
                break
        else:
            # 沒有找到按鈕訊息，送一個新的
            await channel.send("請點下方按鈕開始驗證：", view=VerifyButtonView())
            print(f"發送新的按鈕訊息到 {channel.name}")

# ================= 背景 Thread 任務 =================
async def to_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)

# ================= 驗證流程 =================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if isinstance(message.channel, discord.Thread):
        if message.attachments:
            for attachment in message.attachments:
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
                    status_msg = await message.channel.send("📷 圖片已收到，驗證中請稍等...")

                    image_bytes = await attachment.read()
                    with open("temp.jpg", "wb") as f:
                        f.write(image_bytes)

                    texts = await to_thread(recognize_text_google, "temp.jpg")

                    if ("Hisser" in texts) or ("$750" in texts):
                        member = "hisser"
                    elif ("Hiss Squad" in texts) or ("$450" in texts):
                        member = "hiss squad"
                    elif ("Hiss" in texts) or ("$75" in texts):
                        member = "hiss"
                    else:
                        member = "unknown"

                    role_list = {
                        "hiss": ["hiss"],
                        "hiss squad": ["hiss", "hiss squad"],
                        "hisser": ["hiss", "hiss squad", "hisser"]
                    }

                    all_possible_roles = set(r for roles in role_list.values() for r in roles)

                    if member in role_list:
                        target_roles = set(role_list[member])
                        current_roles = set(role.name for role in message.author.roles if role.name in all_possible_roles)

                        roles_to_add = target_roles - current_roles
                        roles_to_remove = current_roles - target_roles

                        try:
                            for role_name in roles_to_add:
                                role = discord.utils.get(message.guild.roles, name=role_name)
                                if role:
                                    await message.author.add_roles(role)

                            for role_name in roles_to_remove:
                                role = discord.utils.get(message.guild.roles, name=role_name)
                                if role:
                                    await message.author.remove_roles(role)

                            role_display = "、".join(role_list[member])
                            await message.channel.send(f"✅ 驗證成功！已成功將您加入 {role_display} 身分組！")
                            await status_msg.edit(content="✅ 驗證完成，thread 將在 1 分鐘後自動封存！")
                            
                            await log_verification_success(message.author, member)
                            now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
                            print(f"{now.strftime('%Y/%m/%d %H:%M:%S')} User {message.author}: valid {member}.")
                            await asyncio.sleep(60)
                            await message.channel.edit(archived=True)
                            await message.channel.leave()


                        except Exception as error:
                            print("An error occurred:", error)
                            await message.channel.send("❌ 無法新增或移除身份組，請確認 BOT 權限。")

                    else:
                        await message.channel.send("❌ 圖片未通過驗證，無法自動加入身分組。請重新檢查截圖內容！")
                        now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
                        print(f"{now.strftime('%Y/%m/%d %H:%M:%S')} User {message.author}: invalid.")
                    break

# ================= 拔除過期身分組 =================
async def daily_check_and_remove_roles_from_membership_channel():
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
        next_run = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()

        print(f"Next membership check will be in {wait_seconds/3600:.2f} hours")
        await asyncio.sleep(wait_seconds)

        membership_channel = client.get_channel(MEMBERSHIP_LOG_CHANNEL_ID)
        if not membership_channel:
            print("Membership log channel not found!")
            continue

        logs = []
        messages_to_delete = []

        async for msg in membership_channel.history(limit=1000):  # 根據需要調大limit
            if msg.content.startswith("✅"):
                try:
                    parts = msg.content.split()
                    date_str = parts[1] + " " + parts[2]
                    user_id = int(parts[6].strip("()"))
                    verified_role = parts[-1]
                    tz = datetime.timezone(datetime.timedelta(hours=8))
                    verified_time = datetime.datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=tz)
                    logs.append((user_id, verified_role, verified_time))

                    if (now - verified_time).days > 60:
                        messages_to_delete.append(msg)

                except Exception as e:
                    print(f"Error parsing log message: {msg.content} Error: {e}")

        now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
        
        # 把最新的一次驗證時間記下來
        latest_verified = {}
        for user_id, role, verified_time in logs:
            if user_id not in latest_verified or latest_verified[user_id][1] < verified_time:
                latest_verified[user_id] = (role, verified_time)

        guild = client.guilds[1]  # TODO
        for user_id, (role_key, verified_time) in latest_verified.items():
            days_passed = (now - verified_time).days
            if days_passed > 30:
                member = await guild.fetch_member(user_id)
                if member:
                    role_names = {
                        "hiss": ["hiss"],
                        "hiss squad": ["hiss", "hiss squad"],
                        "hisser": ["hiss", "hiss squad", "hisser"]
                    }.get(role_key, [])

                    for role_name in role_names:
                        role = discord.utils.get(guild.roles, name=role_name)
                        if role and role in member.roles:
                            await member.remove_roles(role)
                            print(f"Removed {role.name} from {member.name} (expired {days_passed} days ago)")

        for msg in messages_to_delete:
            try:
                await msg.delete()
                print(f"Deleted old log message: {msg.id}")
            except Exception as e:
                print(f"Failed to delete message {msg.id}: {e}")

client.run(TOKEN)
