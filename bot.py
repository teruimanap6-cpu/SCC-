"""定例の出欠をリアクションで管理する Discord ボット"""

import os
from datetime import datetime, timedelta, time

import discord
from discord import app_commands
from discord.ext import tasks
from zoneinfo import ZoneInfo

import config

JST = ZoneInfo("Asia/Tokyo")
WEEKDAYS = "月火水木金土日"
WINDOW = timedelta(minutes=10)  # 再起動などで時刻を逃しても実行できる猶予

TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
CHANNEL_ID = int(os.environ["ATTENDANCE_CHANNEL_ID"])

intents = discord.Intents.default()
intents.members = True  # 未回答者を調べるために必要


class AttendanceBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.done: set[tuple[str, str]] = set()

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        scheduler.start()


bot = AttendanceBot()


# ---------- 補助関数 ----------

def hm(text: str) -> time:
    h, m = map(int, text.split(":"))
    return time(h, m)


def at(d, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=JST)


def upcoming(now: datetime):
    """投稿対象になりうる定例を (key, title, start) で返す"""
    for offset in range(config.POST_DAYS_BEFORE + 1):
        d = now.date() + timedelta(days=offset)
        if d.isoformat() in config.SKIP_DATES:
            continue
        for m in config.MEETINGS:
            if m["weekday"] != d.weekday():
                continue
            start = at(d, hm(m["time"]))
            if now < start:
                title = f"{m['time']}〜{m['end']} {m['title']}" if m.get("end") else f"{m['time']}〜 {m['title']}"
                yield f"{d.isoformat()}-{m['time']}", title, start


def deadline(start: datetime) -> datetime:
    return start - timedelta(minutes=config.SUMMARY_MINUTES_BEFORE)


def build_text(key: str, title: str, start: datetime) -> str:
    choices = "　".join(f"{e} {name}" for e, name in config.OPTIONS.items())
    day = f"{start.month}/{start.day}（{WEEKDAYS[start.weekday()]}）"
    return (
        f"📋 **出欠確認｜{day} {title}**\n"
        f"リアクションで回答してください。\n{choices}\n"
        f"締切：{deadline(start):%H:%M}　遅刻・早退の連絡はこのメッセージのスレッドへ\n"
        f"`id:{key}`"
    )


async def post_attendance(channel, key, title, start) -> discord.Message:
    msg = await channel.send(build_text(key, title, start))
    for emoji in config.OPTIONS:
        await msg.add_reaction(emoji)
    return msg


async def find_message(channel, key: str | None = None):
    """ボットが投稿した出欠確認を探す。key が無ければ最新のもの"""
    async for msg in channel.history(limit=100):
        if msg.author.id != bot.user.id or "`id:" not in msg.content:
            continue
        if key is None or f"`id:{key}`" in msg.content:
            return msg
    return None


async def tally(msg: discord.Message):
    answers = {e: [] for e in config.OPTIONS}
    answered = set()
    for r in msg.reactions:
        e = str(r.emoji)
        if e not in answers:
            continue
        async for user in r.users():
            if not user.bot:
                answers[e].append(user)
                answered.add(user.id)

    guild = msg.guild
    role = discord.utils.get(guild.roles, name=config.MEMBER_ROLE_NAME)
    targets = role.members if role else guild.members
    unanswered = [m for m in targets if not m.bot and m.id not in answered]
    return answers, unanswered


def format_tally(answers, unanswered) -> str:
    lines = []
    for e, users in answers.items():
        names = "、".join(u.display_name for u in users) or "なし"
        lines.append(f"{e} {config.OPTIONS[e]}（{len(users)}）：{names}")
    names = "、".join(m.display_name for m in unanswered) or "なし"
    lines.append(f"❔ 未回答（{len(unanswered)}）：{names}")
    return "\n".join(lines)


# ---------- 定期処理 ----------

@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(JST)
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        return

    for key, title, start in upcoming(now):
        post_at = at(start.date() - timedelta(days=config.POST_DAYS_BEFORE), hm(config.POST_TIME))
        summary_at = deadline(start)

        # 1. 出欠確認の投稿（二重投稿しないよう既存の投稿を確認）
        if post_at <= now and ("post", key) not in bot.done:
            if await find_message(channel, key) is None:
                await post_attendance(channel, key, title, start)
            bot.done.add(("post", key))

        # 2. 未回答者へのリマインド
        if config.REMIND_TIME and ("remind", key) not in bot.done:
            remind_at = at(start.date(), hm(config.REMIND_TIME))
            if remind_at <= now < remind_at + WINDOW and remind_at < summary_at:
                msg = await find_message(channel, key)
                if msg:
                    _, unanswered = await tally(msg)
                    if unanswered:
                        mentions = " ".join(m.mention for m in unanswered)
                        await msg.reply(
                            f"{mentions}\n{summary_at:%H:%M} までにリアクションで出欠を教えてください。"
                        )
                bot.done.add(("remind", key))

        # 3. 締切時の集計
        if summary_at <= now < summary_at + WINDOW and ("summary", key) not in bot.done:
            msg = await find_message(channel, key)
            if msg:
                answers, unanswered = await tally(msg)
                await msg.reply(
                    f"📊 **締切時点の出欠**\n{format_tally(answers, unanswered)}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            bot.done.add(("summary", key))


@scheduler.before_loop
async def before_scheduler():
    await bot.wait_until_ready()


# ---------- リアクションの整理（1人1つまで） ----------

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.channel_id != CHANNEL_ID or payload.user_id == bot.user.id:
        return
    channel = bot.get_channel(CHANNEL_ID)
    msg = await channel.fetch_message(payload.message_id)
    if msg.author.id != bot.user.id or "`id:" not in msg.content:
        return

    member = payload.member
    emoji = str(payload.emoji)
    if emoji not in config.OPTIONS:
        await msg.remove_reaction(payload.emoji, member)
        return
    for r in msg.reactions:
        if str(r.emoji) in config.OPTIONS and str(r.emoji) != emoji and r.count > 1:
            await msg.remove_reaction(r.emoji, member)


# ---------- スラッシュコマンド ----------

@bot.tree.command(name="attendance", description="最新の出欠状況を表示します（自分だけに見えます）")
async def attendance(interaction: discord.Interaction):
    msg = await find_message(bot.get_channel(CHANNEL_ID))
    if msg is None:
        await interaction.response.send_message("出欠確認が見つかりませんでした。", ephemeral=True)
        return
    answers, unanswered = await tally(msg)
    title = msg.content.splitlines()[0]
    await interaction.response.send_message(
        f"{title}\n{format_tally(answers, unanswered)}", ephemeral=True
    )


@bot.tree.command(name="attendance_create", description="臨時の出欠確認を作成します")
@app_commands.describe(date="日付（例：2026-11-20）", start="開始時刻（例：18:30）", title="名前（例：大学祭準備）")
@app_commands.default_permissions(manage_messages=True)
async def attendance_create(interaction: discord.Interaction, date: str, start: str, title: str):
    try:
        start_dt = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    except ValueError:
        await interaction.response.send_message(
            "日付は 2026-11-20、時刻は 18:30 の形で入力してください。", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True)
    key = f"{date}-{start}"
    await post_attendance(bot.get_channel(CHANNEL_ID), key, f"{start}〜 {title}", start_dt)
    await interaction.followup.send("出欠確認を投稿しました。", ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)
