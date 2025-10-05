import os
import sqlite3

import discord
from dotenv import load_dotenv


load_dotenv()
TOKEN = os.getenv("TOKEN")
if TOKEN is None:
    raise ValueError("TOKEN is not set in .env")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


def init_db():
    try:
        with sqlite3.connect("my.db") as conn:
            cursor = conn.cursor()
            with open("schema.sql") as f:
                cursor.executescript(f.read())
            print(
                f"Opened SQLite database with version {sqlite3.sqlite_version} successfully."
            )
    except sqlite3.OperationalError as e:
        print("Failed to open database:", e)


@client.event
async def on_ready():
    await tree.sync()
    print(f"We have logged on as {client.user}")


@tree.command(description="Checks bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {client.latency}")


init_db()

client.run(TOKEN)
