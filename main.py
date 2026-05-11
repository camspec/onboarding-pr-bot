import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from discord.ui import Button, Label, Modal, Select, TextInput, View
from dotenv import load_dotenv
from loguru import logger


def require_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"{var_name} is not set in .env")
    return value


load_dotenv()
TOKEN: str = require_env("TOKEN")
SOFTWARE_LEAD_ROLE_ID: str = require_env("SOFTWARE_LEAD_ROLE_ID")
PM_ROLE_ID: str = require_env("PM_ROLE_ID")
SOFTWARE_ROLE_ID: str = require_env("SOFTWARE_ROLE_ID")
FW_ROLE_ID: str = require_env("FW_ROLE_ID")
GS_ROLE_ID: str = require_env("GS_ROLE_ID")
FW_ONBOARDING_ROLE_ID: str = require_env("FW_ONBOARDING_ROLE_ID")
GS_ONBOARDING_ROLE_ID: str = require_env("GS_ONBOARDING_ROLE_ID")
FW_ONBOARDING_CHANNEL_ID: str = require_env("FW_ONBOARDING_CHANNEL_ID")
GS_ONBOARDING_CHANNEL_ID: str = require_env("GS_ONBOARDING_CHANNEL_ID")

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

logger.remove()
logger.add("bot.log")


@dataclass
class PR:
    pr_id: int
    user_id: int
    name: str
    pr_link: str
    onboarding_type: str
    notion_email: str
    submitted_at: str


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
        log_error("Failed to open database", e)


def get_unix_epoch(utc_string: str):
    utc = datetime.strptime(utc_string, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    return int(utc.timestamp())


def approve_pr(approver_id: int, pr_id: int):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE prs SET status = 'Approved', approved_at = CURRENT_TIMESTAMP, approver_id = ? WHERE pr_id = ?",
            (approver_id, pr_id),
        )


def remove_pr(pr_id: int):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM prs WHERE pr_id = ?", (pr_id,))


def log_error(message: str, error: Exception | None = None):
    if error:
        logger.error(f"{message}: {error}")
    else:
        logger.error(message)


async def send_client_error(message: str, interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Sorry, {message}. Please let Cameron know he messed up.", ephemeral=True
    )


async def update_roles(interaction: discord.Interaction, pr: PR) -> bool:
    if interaction.guild:
        member = interaction.guild.get_member(pr.user_id)
        if not member:
            log_error(f"Couldn't find the user {pr.user_id} in the server.")
            await send_client_error(
                f"we couldn't find the user <@{pr.user_id}> in the server", interaction
            )
            return False

        software_role = interaction.guild.get_role(int(SOFTWARE_ROLE_ID))
        fw_role = interaction.guild.get_role(int(FW_ROLE_ID))
        gs_role = interaction.guild.get_role(int(GS_ROLE_ID))
        fw_onboarding_role = interaction.guild.get_role(int(FW_ONBOARDING_ROLE_ID))
        gs_onboarding_role = interaction.guild.get_role(int(GS_ONBOARDING_ROLE_ID))
        if not all(
            [
                software_role,
                fw_role,
                gs_role,
                fw_onboarding_role,
                gs_onboarding_role,
            ]
        ):
            log_error("One or more required roles are missing in the server.")
            await send_client_error(
                "one or more required roles are missing in the server", interaction
            )
            return False

        assert software_role is not None
        assert fw_role is not None
        assert gs_role is not None
        assert fw_onboarding_role is not None
        assert gs_onboarding_role is not None

        try:
            if pr.onboarding_type == "Firmware":
                await member.remove_roles(fw_onboarding_role)
                await member.add_roles(software_role, fw_role)
            else:
                await member.remove_roles(gs_onboarding_role)
                await member.add_roles(software_role, gs_role)
        except discord.DiscordException as e:
            log_error(f"Failed to update roles for {pr.user_id}", e)
            await send_client_error("we failed to update roles", interaction)
            return False

        return True
    return False


@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="/submit_onboarding"
        )
    )
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

    notion_email = TextInput(
        label="Notion Email", placeholder="The email you use for Notion"
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        name = self.name.value
        pr_link = self.pr_link.value

        if isinstance(self.onboarding_type.component, Select):
            onboarding_type = self.onboarding_type.component.values[0]
        else:
            onboarding_type = None

        notion_email = self.notion_email.value

        try:
            with sqlite3.connect("database.db") as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO prs (user_id, name, pr_link, onboarding_type, notion_email) VALUES (?, ?, ?, ?, ?)""",
                    (user_id, name, pr_link, onboarding_type, notion_email),
                )
        except sqlite3.Error as e:
            log_error("Failed to insert PR", e)
            await send_client_error(
                "we failed to submit your PR due to a database error", interaction
            )
            return
        logger.info(
            f"PR Submitted: user_id={user_id}, name={name}, pr_link={pr_link}, onboarding_type={onboarding_type}, notion_email={notion_email}"
        )
        await interaction.response.send_message(
            f"Thanks for your response, {self.name.value}! I'll let you know when a Software Lead reviews your PR.",
            ephemeral=True,
        )
        embed = discord.Embed(
            title="New Onboarding PR Submitted",
            color=discord.Color.green(),
        )
        embed.add_field(name="User", value=interaction.user.mention, inline=True)
        embed.add_field(
            name="Type",
            value=f"{onboarding_type} {'⌨️' if onboarding_type == 'Firmware' else '🌎'}",
            inline=True,
        )
        embed.add_field(name="PR Link", value=f"[View PR]({pr_link})", inline=False)

        channel_id: int = int(
            FW_ONBOARDING_CHANNEL_ID
            if onboarding_type == "Firmware"
            else GS_ONBOARDING_CHANNEL_ID
        )
        channel = interaction.client.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(content=f"<@&{SOFTWARE_LEAD_ROLE_ID}>", embed=embed)
        else:
            log_error(
                f"There was a channel configuration error for channel {channel_id}"
            )
            await send_client_error(
                "there was a channel configuration error", interaction
            )


class PRQueueView(View):
    def __init__(self, prs: list[PR], user_is_lead: bool):
        super().__init__()
        self.prs = prs
        self.selected_pr = None

        options = [
            discord.SelectOption(
                label=f"{i + 1}. {pr.name} ({pr.onboarding_type} {'⌨️' if pr.onboarding_type == 'Firmware' else '🌎'})",
                description=pr.pr_link[:100],
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

        try:
            approve_pr(interaction.user.id, self.selected_pr.pr_id)
        except sqlite3.Error as e:
            log_error("Failed to approve PR", e)
            await send_client_error(
                "we failed to approve the PR due to a database error", interaction
            )
            return

        success = await update_roles(interaction, self.selected_pr)

        if not success:
            return

        user = client.get_user(self.selected_pr.user_id)
        if user is None:
            log_error(f"Could not find user with id {self.selected_pr.user_id}")
            await send_client_error(
                "we couldn't find the user that made this PR", interaction
            )
            return

        logger.info(
            f"{interaction.user.name} ({interaction.user.id}) approved PR: "
            f"user_id={self.selected_pr.user_id}, "
            f"name={self.selected_pr.name}, "
            f"pr_link={self.selected_pr.pr_link}, "
            f"onboarding_type={self.selected_pr.onboarding_type}, "
            f"notion_email={self.selected_pr.notion_email}"
        )
        await interaction.response.send_message(
            f"You approved <@{self.selected_pr.user_id}>'s PR. Their roles have been updated and they have been notified. "
            f"\nPlease add them to the Notion with their email: {self.selected_pr.notion_email}\nDon't forget the GitHub as well.",
            ephemeral=True,
        )
        await user.send(
            f"Hi <@{self.selected_pr.user_id}>! "
            f"Your [onboarding PR]({self.selected_pr.pr_link}) ({'Firmware' if self.selected_pr.onboarding_type == 'Firmware' else 'GS'}) "
            f"was reviewed by <@{interaction.user.id}> and approved. "
            f"Welcome to the team :)"
        )

    async def mark_request_changes(self, interaction: discord.Interaction):
        if not self.selected_pr:
            await interaction.response.send_message(
                "Please select a PR first!", ephemeral=True
            )
            return

        try:
            remove_pr(self.selected_pr.pr_id)
        except sqlite3.Error as e:
            log_error("Failed to remove PR", e)
            await send_client_error(
                "we failed to remove the PR due to a database error", interaction
            )
            return

        user = client.get_user(self.selected_pr.user_id)
        if user is None:
            log_error(f"Could not find user with id {self.selected_pr.user_id}")
            await send_client_error(
                "we couldn't find the user that made this PR", interaction
            )
            return

        logger.info(
            f"{interaction.user.name} ({interaction.user.id}) requested changes for PR: "
            f"user_id={self.selected_pr.user_id}, "
            f"name={self.selected_pr.name}, "
            f"pr_link={self.selected_pr.pr_link}, "
            f"onboarding_type={self.selected_pr.onboarding_type}, "
            f"notion_email={self.selected_pr.notion_email}"
        )
        await interaction.response.send_message(
            f"You requested changes to <@{self.selected_pr.user_id}>'s PR.",
            ephemeral=True,
        )
        await user.send(
            f"Hi <@{self.selected_pr.user_id}>! "
            f"Your [onboarding PR]({self.selected_pr.pr_link}) ({'Firmware' if self.selected_pr.onboarding_type == 'Firmware' else 'GS'}) "
            f"was reviewed by <@{interaction.user.id}> and they requested changes. "
            f"Please look over your PR and make the changes, resolving comments as you go through. When you're done, resubmit your PR to me. "
            f"Thanks :)"
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
            "SELECT pr_id, user_id, name, pr_link, onboarding_type, notion_email, submitted_at FROM prs WHERE status = 'Pending'"
        )
        prs = [PR(*row) for row in cursor.fetchall()]

    if not prs:
        await interaction.response.send_message(
            "The PR queue is empty.", ephemeral=True
        )
        return

    embed = discord.Embed(title="Onboarding PR Queue")
    for i, pr in enumerate(prs):
        embed.add_field(
            name=f"{i + 1}. {pr.name} ({pr.onboarding_type} {'⌨️' if pr.onboarding_type == 'Firmware' else '🌎'})",
            value=f"<@{pr.user_id}>\nSubmitted at: <t:{get_unix_epoch(pr.submitted_at)}:f>\n[View PR]({pr.pr_link})",
            inline=False,
        )
    await interaction.response.send_message(
        embed=embed,
        view=PRQueueView(
            prs, any(interaction.user.get_role(int(r)) for r in [SOFTWARE_LEAD_ROLE_ID, PM_ROLE_ID])
        ),
        ephemeral=True,
    )


init_db()

client.run(TOKEN)
