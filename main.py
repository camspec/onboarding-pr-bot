from datetime import datetime, timezone
import os
import sqlite3

import discord
from discord.ui import Button, Label, Modal, Select, TextInput, View
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


def is_software_lead(member: discord.Member):
    return (
        discord.utils.find(lambda r: r.name == "Software Lead", member.roles)
        is not None
    )


def get_unix_epoch(utc_string: str):
    utc = datetime.strptime(utc_string, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    return int(utc.timestamp())


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

        if isinstance(self.onboarding_type.component, Select):
            onboarding_type = self.onboarding_type.component.values[0]
        else:
            onboarding_type = None

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


class PRQueueView(View):
    def __init__(self, prs: list, user_is_lead: bool):
        super().__init__()
        self.prs = prs
        self.selected_pr = None

        options = [
            discord.SelectOption(
                label=f"{i + 1}. {pr[1]} ({pr[3]} {'⌨️' if pr[3] == 'Firmware' else '🌎'})",
                description=pr[2],
                value=str(i),
            )
            for i, pr in enumerate(prs)
        ]

        self.select = Select(placeholder="Choose a PR to act on", options=options)
        self.select.callback = self.pr_selected
        self.add_item(self.select)

        self.approve_button = Button(
            label="Approve",
            style=discord.ButtonStyle.green,
            disabled=not user_is_lead,
        )
        self.request_changes_button = Button(
            label="Request Changes",
            style=discord.ButtonStyle.red,
            disabled=not user_is_lead,
        )

        self.approve_button.callback = self.mark_approved
        self.request_changes_button.callback = self.mark_request_changes

        self.add_item(self.approve_button)
        self.add_item(self.request_changes_button)

    async def pr_selected(self, interaction: discord.Interaction):
        self.selected_pr = self.prs[int(self.select.values[0])]
        await interaction.response.defer()

    async def mark_approved(self, interaction: discord.Interaction):
        if not self.selected_pr:
            await interaction.response.send_message(
                "Please select a PR first!", ephemeral=True
            )
            return

        user_id, name, pr_link, onboarding_type, _ = self.selected_pr
        logger.info(
            f"{interaction.user.name} ({interaction.user.id}) approved PR: user_id={user_id}, name={name}, pr_link={pr_link}, onboarding_type={onboarding_type}"
        )
        await interaction.response.send_message(
            f"You approved <@{user_id}>'s PR.", ephemeral=True
        )

    async def mark_request_changes(self, interaction: discord.Interaction):
        if not self.selected_pr:
            await interaction.response.send_message(
                "Please select a PR first!", ephemeral=True
            )
            return

        user_id, name, pr_link, onboarding_type, _ = self.selected_pr
        logger.info(
            f"{interaction.user.name} ({interaction.user.id}) requested changes for PR: user_id={user_id}, name={name}, pr_link={pr_link}, onboarding_type={onboarding_type}"
        )
        await interaction.response.send_message(
            f"You requested changes for <@{user_id}>'s PR.", ephemeral=True
        )


@tree.command(description="Submit an onboarding PR")
async def submit_onboarding(interaction: discord.Interaction):
    logger.info(
        f"User {interaction.user.name} ({interaction.user.id}) used /submit_onboarding"
    )
    await interaction.response.send_modal(PRSubmissionModal())


@tree.command(description="View the onboarding PR queue")
async def view_onboarding_queue(interaction: discord.Interaction):
    logger.info(
        f"User {interaction.user.name} ({interaction.user.id}) used /view_onboarding_queue"
    )
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This command can only be used in a server.", ephemeral=True
        )
        return

    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, name, pr_link, onboarding_type, submitted_at FROM prs"
        )
        prs = cursor.fetchall()

    if not prs:
        await interaction.response.send_message(
            "The PR queue is empty.", ephemeral=True
        )
        return

    embed = discord.Embed(title="Onboarding PR Queue")
    for i, pr in enumerate(prs):
        user_id, name, pr_link, onboarding_type, submitted_at = pr
        embed.add_field(
            name=f"{i + 1}. {name} ({onboarding_type} {'⌨️' if onboarding_type == 'Firmware' else '🌎'})",
            value=f"<@{user_id}>\nSubmitted at: <t:{get_unix_epoch(submitted_at)}:f>\n[View PR]({pr_link})",
            inline=False,
        )
    await interaction.response.send_message(
        embed=embed, view=PRQueueView(prs, is_software_lead(interaction.user))
    )


init_db()

client.run(TOKEN)
