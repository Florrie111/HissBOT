import discord
import os
# from dotenv import load_dotenv
import asyncio
import base64
import requests
from discord import ui
import datetime

# load_dotenv(dotenv_path="HissBOT.env")
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

CHANNEL_WHITELIST = [1365293969306681406]  # Test: 1365649281536626751

# load_dotenv(dotenv_path="Google.env")
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

# ================= 按鈕 =================
class VerifyButtonView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # @ui.button(label="🔰 我要驗證", style=discord.ButtonStyle.success)
    @discord.ui.button(label="🔰 我要驗證", style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.channel.id not in CHANNEL_WHITELIST:
            await interaction.response.send_message("❌ 這裡不能使用驗證！", ephemeral=True)
            return

        thread_name = f"verify-{interaction.user.name}-{interaction.user.id}"
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=60,
            invitable=False
        )
        await thread.add_user(interaction.user)
        await thread.send(f"{interaction.user.mention} 請上傳你的會員截圖進行驗證 ✨")
        await interaction.response.send_message("✅ 已建立你的驗證區，請進入 thread 上傳截圖！", ephemeral=True)

# ================= on_ready =================
@client.event
async def on_ready():
    print(f"Bot is online: {client.user}")
    client.add_view(VerifyButtonView())

    for ch_id in CHANNEL_WHITELIST:
        channel = client.get_channel(ch_id)
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
                            await asyncio.sleep(60)
                            await message.channel.edit(archived=True)
                            await message.channel.leave()
                            now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
                            print(f"{now.strftime('%Y/%m/%d %H:%M:%S')} User {message.author}: valid {member}.")

                        except Exception as error:
                            print("An error occurred:", error)
                            await message.channel.send("❌ 無法新增或移除身份組，請確認 BOT 權限。")

                    else:
                        await message.channel.send("❌ 圖片未通過驗證，無法自動加入身分組。請重新檢查截圖內容！")
                        now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
                        print(f"{now.strftime('%Y/%m/%d %H:%M:%S')} User {message.author}: invalid.")
                    break

client.run(TOKEN)
