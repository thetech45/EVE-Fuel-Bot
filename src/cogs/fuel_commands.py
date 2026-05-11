# -*- coding: utf-8 -*-
"""
cogs/fuel_commands.py - All /fuel slash commands.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import time

import database as db
import fuel_utils as fu


class FuelCommands(commands.Cog):
    """Slash commands for managing EVE structure fuel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /fuel add ─────────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_add", description="Add a new structure to track.")
    @app_commands.describe(
        name="Structure name (e.g. 'Jita 4-4 Keepstar')",
        structure_type="Structure type (Fortizar, Keepstar, Raitaru, etc.)",
        system="Solar system name",
        fuel="Current fuel blocks in bay",
        burn_rate="Fuel blocks burned per hour (leave 0 to use default for type)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_add(
        self,
        interaction: discord.Interaction,
        name: str,
        structure_type: str,
        system: str,
        fuel: int,
        burn_rate: float = 0,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Use default burn rate for known types if not provided
        if burn_rate <= 0:
            burn_rate = fu.BURN_RATES.get(structure_type, 12.0)

        existing = await db.get_structure_by_name(name)
        if existing:
            await interaction.followup.send(
                f"❌ A structure named **{name}** already exists (ID `{existing['id']}`).\n"
                f"Use `/fuel update` to change its fuel level.",
                ephemeral=True,
            )
            return

        sid = await db.add_structure(name, structure_type, system, fuel, burn_rate)
        hours = fu.hours_remaining(fuel, burn_rate)
        empty_ts = fu.predict_empty_timestamp(fuel, burn_rate, int(time.time()))

        embed = discord.Embed(
            title="✅ Structure Added",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="ID",         value=str(sid),                              inline=True)
        embed.add_field(name="Name",       value=name,                                  inline=True)
        embed.add_field(name="Type",       value=structure_type,                        inline=True)
        embed.add_field(name="System",     value=system,                                inline=True)
        embed.add_field(name="Fuel",       value=f"{fuel:,} blocks",                   inline=True)
        embed.add_field(name="Burn Rate",  value=f"{burn_rate:.1f} blk/hr",            inline=True)
        embed.add_field(name="Time Left",  value=fu.format_duration(hours),            inline=True)
        embed.add_field(name="Empty At",   value=f"<t:{empty_ts}:F>",                  inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /fuel remove ──────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_remove", description="Stop tracking a structure.")
    @app_commands.describe(structure_id="Structure ID (use /fuel list to find it)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_remove(self, interaction: discord.Interaction, structure_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await db.get_structure(structure_id)
        if not s:
            await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.", ephemeral=True)
            return
        await db.remove_structure(structure_id)
        await interaction.followup.send(
            f"🗑️ **{s['name']}** (ID `{structure_id}`) removed from tracking.", ephemeral=True
        )

    # ── /fuel update ──────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_update", description="Update the fuel level for a structure.")
    @app_commands.describe(
        structure_id="Structure ID",
        fuel="New fuel block count",
        note="Optional note (e.g. 'refueled by Capsuleer X')",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_update(
        self,
        interaction: discord.Interaction,
        structure_id: int,
        fuel: int,
        note: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await db.get_structure(structure_id)
        if not s:
            await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.", ephemeral=True)
            return

        await db.update_fuel(structure_id, fuel, note)
        hours = fu.hours_remaining(fuel, s["burn_rate"])
        empty_ts = fu.predict_empty_timestamp(fuel, s["burn_rate"], int(time.time()))
        emoji = fu.fuel_status_emoji(hours)

        embed = discord.Embed(
            title=f"{emoji} Fuel Updated – {s['name']}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="New Fuel",   value=f"{fuel:,} blocks",        inline=True)
        embed.add_field(name="Burn Rate",  value=f"{s['burn_rate']:.1f} blk/hr", inline=True)
        embed.add_field(name="Time Left",  value=fu.format_duration(hours), inline=True)
        embed.add_field(name="Empty At",   value=f"<t:{empty_ts}:F> (<t:{empty_ts}:R>)", inline=False)
        if note:
            embed.add_field(name="Note", value=note, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /fuel status ──────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_status", description="Show fuel status for one or all structures.")
    @app_commands.describe(structure_id="Leave blank to show all structures")
    async def fuel_status(
        self, interaction: discord.Interaction, structure_id: int | None = None
    ) -> None:
        await interaction.response.defer()

        if structure_id is not None:
            structures = [await db.get_structure(structure_id)]
            if not structures[0]:
                await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.")
                return
        else:
            structures = await db.list_structures()
            if not structures:
                await interaction.followup.send("No structures are being tracked yet. Use `/fuel_add` to add one.")
                return

        embeds = []
        for s in structures:
            est_fuel = fu.current_fuel_estimate(s["fuel_amount"], s["burn_rate"], s["updated_at"])
            hours    = fu.hours_remaining(est_fuel, s["burn_rate"])
            empty_ts = fu.predict_empty_timestamp(s["fuel_amount"], s["burn_rate"], s["updated_at"])
            emoji    = fu.fuel_status_emoji(hours)

            color = (
                discord.Color.red()    if hours <= 24  else
                discord.Color.orange() if hours <= 72  else
                discord.Color.yellow() if hours <= 168 else
                discord.Color.green()
            )

            embed = discord.Embed(
                title=f"{emoji} {s['name']}",
                color=color,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="ID",           value=str(s["id"]),                       inline=True)
            embed.add_field(name="Type",         value=s["type"],                          inline=True)
            embed.add_field(name="System",       value=s["system"],                        inline=True)
            embed.add_field(name="Est. Fuel",    value=f"{est_fuel:,} blocks",             inline=True)
            embed.add_field(name="Burn Rate",    value=f"{s['burn_rate']:.1f} blk/hr",    inline=True)
            embed.add_field(name="Time Left",    value=fu.format_duration(hours),          inline=True)
            embed.add_field(name="Empty At",     value=f"<t:{empty_ts}:F> (<t:{empty_ts}:R>)", inline=False)

            # Show assigned reminder roles
            role_ids = await db.get_reminder_roles(s["id"])
            if role_ids:
                embed.add_field(
                    name="Alert Roles",
                    value=" ".join(f"<@&{rid}>" for rid in role_ids),
                    inline=False,
                )
            embeds.append(embed)

        # Discord allows max 10 embeds per message
        for i in range(0, len(embeds), 10):
            await interaction.followup.send(embeds=embeds[i:i+10])

    # ── /fuel list ────────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_list", description="Compact list of all tracked structures.")
    async def fuel_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        structures = await db.list_structures()
        if not structures:
            await interaction.followup.send("No structures tracked yet.")
            return

        lines = []
        for s in structures:
            est = fu.current_fuel_estimate(s["fuel_amount"], s["burn_rate"], s["updated_at"])
            hrs = fu.hours_remaining(est, s["burn_rate"])
            emoji = fu.fuel_status_emoji(hrs)
            lines.append(
                f"{emoji} `[{s['id']:>3}]` **{s['name']}** — "
                f"{est:,} blk — {fu.format_duration(hrs)} left"
            )

        embed = discord.Embed(
            title="📋 Tracked Structures",
            description="\n".join(lines),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="🟢 >7d  🟡 ≤7d  🟠 ≤3d  🔴 ≤1d")
        await interaction.followup.send(embed=embed)

    # ── /fuel history ─────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_history", description="Show recent fuel log entries for a structure.")
    @app_commands.describe(structure_id="Structure ID", entries="Number of entries to show (default 10)")
    async def fuel_history(
        self, interaction: discord.Interaction, structure_id: int, entries: int = 10
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await db.get_structure(structure_id)
        if not s:
            await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.", ephemeral=True)
            return

        logs = await db.get_fuel_history(structure_id, limit=min(entries, 25))
        if not logs:
            await interaction.followup.send("No fuel history recorded yet.", ephemeral=True)
            return

        lines = []
        for entry in logs:
            ts = entry["recorded_at"]
            note = f" — *{entry['note']}*" if entry["note"] else ""
            lines.append(f"<t:{ts}:f> — **{entry['fuel_amount']:,}** blocks{note}")

        embed = discord.Embed(
            title=f"📜 Fuel History – {s['name']}",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /fuel burnrate ────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_burnrate", description="Update the burn rate for a structure.")
    @app_commands.describe(
        structure_id="Structure ID",
        burn_rate="Fuel blocks burned per hour",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_burnrate(
        self, interaction: discord.Interaction, structure_id: int, burn_rate: float
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await db.get_structure(structure_id)
        if not s:
            await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.", ephemeral=True)
            return
        await db.update_burn_rate(structure_id, burn_rate)
        await interaction.followup.send(
            f"✅ Burn rate for **{s['name']}** updated to **{burn_rate:.1f} blk/hr**.",
            ephemeral=True,
        )

    # ── /fuel role_add ────────────────────────────────────────────────────────
    @app_commands.command(name="fuel_role_add", description="Add a role to receive fuel alerts for a structure.")
    @app_commands.describe(structure_id="Structure ID", role="Role to ping")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_role_add(
        self, interaction: discord.Interaction, structure_id: int, role: discord.Role
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await db.get_structure(structure_id)
        if not s:
            await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.", ephemeral=True)
            return
        await db.add_reminder_role(structure_id, str(role.id))
        await interaction.followup.send(
            f"✅ {role.mention} will now be pinged for **{s['name']}** fuel alerts.",
            ephemeral=True,
        )

    # ── /fuel role_remove ─────────────────────────────────────────────────────
    @app_commands.command(name="fuel_role_remove", description="Remove a role from fuel alerts for a structure.")
    @app_commands.describe(structure_id="Structure ID", role="Role to remove")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_role_remove(
        self, interaction: discord.Interaction, structure_id: int, role: discord.Role
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        s = await db.get_structure(structure_id)
        if not s:
            await interaction.followup.send(f"❌ No structure with ID `{structure_id}`.", ephemeral=True)
            return
        removed = await db.remove_reminder_role(structure_id, str(role.id))
        if removed:
            await interaction.followup.send(
                f"✅ {role.mention} removed from **{s['name']}** alerts.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ {role.mention} was not assigned to **{s['name']}**.", ephemeral=True
            )

    # ── /fuel check_now ───────────────────────────────────────────────────────
    @app_commands.command(name="fuel_check_now", description="Manually trigger a fuel check right now.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fuel_check_now(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        import reminders
        await reminders.check_all_structures(self.bot)
        await interaction.followup.send("✅ Fuel check complete. Any due alerts have been sent.", ephemeral=True)

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need **Manage Server** permission to use this command.", ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FuelCommands(bot))
