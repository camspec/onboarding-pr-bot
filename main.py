import os
import sqlite3

import discord
from discord.ui import Label, Modal, Select, TextInput
from dotenv import load_dotenv
from loguru import logger


load_dotenv()
TOKEN = os.getenv("TOKEN")
if TOKEN is None:
    raise ValueError("TOKEN is not set in .env")

client = discord.Client(intents=discord.Intents.default())
tree = discord.app_commands.CommandTree(client)

logger.add("bot.log")


def init_db():
    try:
        with sqlite3.connect("database.db") as conn:
            cursor = conn.cursor()
            with open("schema.sql") as f:
                cursor.executescript(f.read())
            logger.info(
                f"Opened SQLite database with version {sqlite3.sqlite_version} successfully."
            )
    except sqlite3.Error as e:
        logger.error(f"Failed to open database: {e}")


@client.event
async def on_ready():
    await tree.sync()
    logger.info(f"We have logged on as {client.user}")


class PRSubmissionModal(Modal, title="Submit a PR"):
    name = TextInput(label="Name", placeholder="Your name")
    pr_link = TextInput(
        label="Link to PR", placeholder="https://github.com/UWOrbital/..."
    )

    onboarding_type = Label(
        text="Onboarding Type",
        component=Select(
            placeholder="Choose your onboarding type",
            options=[
                discord.SelectOption(label="Firmware"),
                discord.SelectOption(label="GS"),
            ],
        ),
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        name = self.name.value
        pr_link = self.pr_link.value
        onboarding_type = self.onboarding_type.component.values[0]
        try:
            with sqlite3.connect("database.db") as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO prs (user_id, name, pr_link, onboarding_type) VALUES (?, ?, ?, ?)""",
                    (user_id, name, pr_link, onboarding_type),
                )
            logger.info(
                f"PR Submitted: user_id={user_id}, name={name}, pr_link={pr_link}, onboarding_type={onboarding_type}"
            )
            await interaction.response.send_message(
                f"Thanks for your response, {self.name.value}! A Software Lead will get back to you when your PR is reviewed.",
                ephemeral=True,
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to insert PR: {e}")
            await interaction.response.send_message(
                "Sorry, we failed to submit your PR due to a database error. Please let Cameron know he messed up.",
                ephemeral=True,
            )


@tree.command(description="Submit an onboarding PR")
async def submit_onboarding(interaction: discord.Interaction):
    await interaction.response.send_modal(PRSubmissionModal())


@tree.command(description="Checks bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {client.latency}")


init_db()

client.run(TOKEN)
