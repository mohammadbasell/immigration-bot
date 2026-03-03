import os
import time
import threading
from typing import Dict, Any, List

from flask import Flask, request, jsonify
import discord
from discord import app_commands

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
API_KEY = os.environ["API_KEY"]

DECISIONS: List[Dict[str, Any]] = []
APPLICATIONS: List[Dict[str, Any]] = []

def now_ts() -> int:
    return int(time.time())

def make_fn() -> str:
    yyyy = time.gmtime().tm_year
    return f"FN-{yyyy}-{str(int(time.time()*1000))[-8:]}"


app = Flask(__name__)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/decisions")
def get_decisions():
    key = request.args.get("key", "")
    if key != API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    since = int(request.args.get("since", "0"))
    out = [d for d in DECISIONS if int(d["decidedAt"]) > since]
    return jsonify({"decisions": out, "serverTime": now_ts()})


def run_api():
    app.run(host="0.0.0.0", port=8080)


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

APPLICATIONS_CHANNEL = "applications"

class ApplyModal(discord.ui.Modal, title="Immigration Application"):
    app_type = discord.ui.TextInput(label="Application Type (visitor_2w / resident / overstay)", required=True)
    roblox_username = discord.ui.TextInput(label="Roblox Username", required=True)
    roblox_userid = discord.ui.TextInput(label="Roblox UserId (numbers only)", required=True)
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, required=True)
    sponsor_employer_uni = discord.ui.TextInput(label="Sponsor/Employer/University (optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        fn = make_fn()
        data = {
            "fn": fn,
            "type": str(self.app_type.value).strip().lower(),
            "robloxUsername": str(self.roblox_username.value).strip(),
            "robloxUserId": int(str(self.roblox_userid.value).strip()),
            "reason": str(self.reason.value).strip(),
            "extra": str(self.sponsor_employer_uni.value).strip(),
            "submittedAt": now_ts(),
            "status": "Pending",
        }
        APPLICATIONS.append(data)

        channel = discord.utils.get(interaction.guild.text_channels, name=APPLICATIONS_CHANNEL)
        if channel is None:
            await interaction.response.send_message(
                f"Error: create a channel named #{APPLICATIONS_CHANNEL} first.",
                ephemeral=True
            )
            return

        embed = discord.Embed(title=f"Application {fn}", description="New application submitted", color=0x2b2d31)
        embed.add_field(name="Type", value=data["type"], inline=False)
        embed.add_field(name="Roblox", value=f'{data["robloxUsername"]} / {data["robloxUserId"]}', inline=False)
        embed.add_field(name="Reason", value=data["reason"][:1024], inline=False)
        if data["extra"]:
            embed.add_field(name="Extra", value=data["extra"][:1024], inline=False)
        embed.set_footer(text="Officer actions: Approve / Reject / Return for Modification")

        view = OfficerView(fn=fn)
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"Submitted! Case: {fn}. Track it in #{APPLICATIONS_CHANNEL}.",
            ephemeral=True
        )


class OfficerView(discord.ui.View):
    def __init__(self, fn: str):
        super().__init__(timeout=None)
        self.fn = fn

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, decision="Approved")

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, decision="Rejected")

    @discord.ui.button(label="Return for Modification", style=discord.ButtonStyle.secondary)
    async def rfm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, decision="Returned for Modification")

    async def _decide(self, interaction: discord.Interaction, decision: str):
        app_rec = next((a for a in APPLICATIONS if a["fn"] == self.fn), None)
        if not app_rec:
            await interaction.response.send_message("Could not find application record.", ephemeral=True)
            return

        app_rec["status"] = decision

        DECISIONS.append({
            "fn": self.fn,
            "action": decision,
            "type": app_rec["type"],
            "robloxUserId": app_rec["robloxUserId"],
            "meta": {
                "extra": app_rec.get("extra", ""),
                "reason": app_rec.get("reason", "")
            },
            "decidedBy": str(interaction.user),
            "decidedAt": now_ts()
        })

        await interaction.response.send_message(f"{decision} recorded for {self.fn}.", ephemeral=True)


@tree.command(name="apply", description="Submit an immigration application")
async def apply_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(ApplyModal())


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


if __name__ == "__main__":
    threading.Thread(target=run_api, daemon=True).start()
    client.run(DISCORD_TOKEN)
