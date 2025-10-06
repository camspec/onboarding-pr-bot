from dataclasses import dataclass
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

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

logger.add("bot.log")


@dataclass
class PR:
    pr_id: int
    user_id: int
    name: str
    pr_link: str
    onboarding_type: str
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


def approve_pr(pr_id: int):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE prs SET status = 'Approved' WHERE pr_id = ?", (pr_id,))


def remove_pr(pr_id: int):
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM prs WHERE pr_id = ?", (pr_id,))


async def update_roles(interaction: discord.Interaction, pr: PR):
    if interaction.guild:
        print(interaction.guild.members)
        member = interaction.guild.get_member(pr.user_id)
        if not member:
            logger.error(f"Couldn't find the user {pr.user_id} in the server.")
            await interaction.response.send_message(
                f"Sorry, we couldn't find the user <@{pr.user_id}> in the server. Please let Cameron know he messed up.",
                ephemeral=True,
            )
            return False

        software_role = discord.utils.find(
            lambda r: r.name == "Software", interaction.guild.roles
        )
        firmware_role = discord.utils.find(
            lambda r: r.name == "Firmware", interaction.guild.roles
        )
        gs_role = discord.utils.find(lambda r: r.name == "GS", interaction.guild.roles)
        fw_onboarding_role = discord.utils.find(
            lambda r: r.name == "FW-Onboarding", interaction.guild.roles
        )
        gs_onboarding_role = discord.utils.find(
            lambda r: r.name == "GS-Onboarding", interaction.guild.roles
        )
        if not all(
            [
                software_role,
                firmware_role,
                gs_role,
                fw_onboarding_role,
                gs_onboarding_role,
            ]
        ):
            logger.error("One or more required roles are missing in the server.")
            await interaction.response.send_message(
                "One or more required roles are missing in the server.", ephemeral=True
            )
            return False

        assert software_role is not None
        assert firmware_role is not None
        assert gs_role is not None
        assert fw_onboarding_role is not None
        assert gs_onboarding_role is not None

        try:
            if pr.onboarding_type == "Firmware":
                await member.remove_roles(fw_onboarding_role)
                await member.add_roles(software_role, firmware_role)
            else:
                await member.remove_roles(gs_onboarding_role)
                await member.add_roles(software_role, gs_role)
        except discord.DiscordException as e:
            logger.error(f"Failed to update roles for {pr.user_id}: {e}")
            await interaction.response.send_message(
                "Sorry, we failed to update roles. Please let Cameron know he messed up.",
                ephemeral=True,
            )

        return True


@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="Weezer")
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
    def __init__(self, prs: list[PR], user_is_lead: bool):
        super().__init__()
        self.prs = prs
        self.selected_pr = None

        options = [
            discord.SelectOption(
                label=f"{i + 1}. {pr.name} ({pr.onboarding_type} {'⌨️' if pr.onboarding_type == 'Firmware' else '🌎'})",
                description=pr.pr_link,
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
            approve_pr(self.selected_pr.pr_id)
        except sqlite3.Error as e:
            logger.error(f"Failed to approve PR: {e}")
            await interaction.response.send_message(
                "Sorry, we failed to approve the PR due to a database error. Please let Cameron know he messed up.",
                ephemeral=True,
            )
            return

        success = await update_roles(interaction, self.selected_pr)

        if not success:
            return

        logger.info(
            f"{interaction.user.name} ({interaction.user.id}) approved PR: "
            f"user_id={self.selected_pr.user_id}, "
            f"name={self.selected_pr.name}, "
            f"pr_link={self.selected_pr.pr_link}, "
            f"onboarding_type={self.selected_pr.onboarding_type}"
        )
        await interaction.response.send_message(
            f"You approved <@{self.selected_pr.user_id}>'s PR.", ephemeral=True
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
            logger.error(f"Failed to remove PR: {e}")
            await interaction.response.send_message(
                "Sorry, we failed to remove the PR due to a database error. Please let Cameron know he messed up.",
                ephemeral=True,
            )
            return

        logger.info(
            f"{interaction.user.name} ({interaction.user.id}) requested changes for PR: "
            f"user_id={self.selected_pr.user_id}, "
            f"name={self.selected_pr.name}, "
            f"pr_link={self.selected_pr.pr_link}, "
            f"onboarding_type={self.selected_pr.onboarding_type}"
        )
        await interaction.response.send_message(
            f"You requested changes for <@{self.selected_pr.user_id}>'s PR.",
            ephemeral=True,
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
            "SELECT pr_id, user_id, name, pr_link, onboarding_type, submitted_at FROM prs WHERE status = 'Pending'"
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
        embed=embed, view=PRQueueView(prs, is_software_lead(interaction.user))
    )


init_db()

client.run(TOKEN)
