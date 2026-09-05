import discord
from discord.ext import commands
import random
import logging

from shared.games.engines import (
    TicTacToe, get_ttt_best_move,
    Connect4, get_c4_best_col,
    RPSGame,
    BlackjackGame,
    QuizGame
)
from shared.games.rewards import try_award, REWARD_VALUES

logger = logging.getLogger("shared_game_views")

# Active games registry: user_id -> message_id
active_games = {}

def register_player(user_id: int, message_id: int) -> bool:
    if user_id in active_games:
        return False
    active_games[user_id] = message_id
    return True

def register_players(user1: int, user2: int, message_id: int) -> bool:
    if user1 in active_games or user2 in active_games:
        return False
    active_games[user1] = message_id
    active_games[user2] = message_id
    return True

def unregister_player(user_id: int):
    active_games.pop(user_id, None)

def unregister_players(user1: int, user2: int):
    active_games.pop(user1, None)
    active_games.pop(user2, None)


# ==========================================
# Duel Invitation & Choice Views
# ==========================================

class DuelInviteView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, game_type: str, on_accept_callback, timeout=60.0):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.opponent = opponent
        self.game_type = game_type
        self.on_accept_callback = on_accept_callback
        self.accepted = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Ce n'est pas ton invitation, voyageur.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = True
        self.stop()
        await self.on_accept_callback(interaction)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        unregister_players(self.challenger.id, self.opponent.id)
        embed = discord.Embed(
            title="Duel refusé",
            description=f"{self.opponent.mention} a refusé d'affronter {self.challenger.mention}.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        if not self.accepted:
            unregister_players(self.challenger.id, self.opponent.id)
            if hasattr(self, 'message') and self.message:
                try:
                    embed = discord.Embed(
                        title="Duel expiré",
                        description=f"{self.opponent.mention} n'a pas répondu à l'invitation de {self.challenger.mention}.",
                        color=discord.Color.dark_gray()
                    )
                    await self.message.edit(embed=embed, view=None)
                except Exception:
                    pass


class DefiSelectView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent, persona: dict, is_vs_bot=False, timeout=60.0):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.opponent = opponent
        self.persona = persona
        self.is_vs_bot = is_vs_bot
        self.chosen = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenger.id:
            await interaction.response.send_message("Ce n'est pas ton menu de défi, voyageur.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Morpion", style=discord.ButtonStyle.primary, emoji="❌")
    async def ttt(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen = True
        self.stop()
        if self.is_vs_bot:
            await start_bot_game_direct(interaction, self.challenger, "tictactoe", self.persona)
        else:
            await start_duel_invite(interaction, self.challenger, self.opponent, "tictactoe", self.persona)

    @discord.ui.button(label="Puissance 4", style=discord.ButtonStyle.primary, emoji="🟡")
    async def c4(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen = True
        self.stop()
        if self.is_vs_bot:
            await start_bot_game_direct(interaction, self.challenger, "connect4", self.persona)
        else:
            await start_duel_invite(interaction, self.challenger, self.opponent, "connect4", self.persona)

    @discord.ui.button(label="Pierre-Feuille-Ciseaux", style=discord.ButtonStyle.primary, emoji="✂️")
    async def rps(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen = True
        self.stop()
        if self.is_vs_bot:
            await start_bot_game_direct(interaction, self.challenger, "rps", self.persona)
        else:
            await start_duel_invite(interaction, self.challenger, self.opponent, "rps", self.persona)

    async def on_timeout(self):
        if not self.chosen:
            if self.is_vs_bot:
                unregister_player(self.challenger.id)
            else:
                unregister_players(self.challenger.id, self.opponent.id)
            if hasattr(self, 'message') and self.message:
                try:
                    await self.message.edit(content="Le choix du défi a expiré.", view=None)
                except Exception:
                    pass


# ==========================================
# TicTacToe (Morpion) Views
# ==========================================

class TicTacToeButton(discord.ui.Button):
    def __init__(self, idx: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=row)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        await view.handle_click(interaction, self.idx)


class TicTacToeView(discord.ui.View):
    def __init__(self, player_x: discord.Member, player_o, persona: dict, timeout=180.0):
        super().__init__(timeout=timeout)
        self.player_x = player_x
        self.player_o = player_o
        self.persona = persona
        self.is_vs_bot = isinstance(player_o, str) or (hasattr(player_o, 'bot') and player_o.bot)
        self.engine = TicTacToe()
        
        for i in range(9):
            self.add_item(TicTacToeButton(i, i // 3))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        current_player = self.player_x if self.engine.current_turn == "X" else self.player_o
        if self.is_vs_bot:
            if interaction.user.id != self.player_x.id:
                await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
                return False
        else:
            if interaction.user.id not in [self.player_x.id, self.player_o.id]:
                await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
                return False
            if interaction.user.id != current_player.id:
                await interaction.response.send_message("Ce n'est pas ton tour, voyageur.", ephemeral=True)
                return False
        return True

    async def handle_click(self, interaction: discord.Interaction, idx: int):
        if not self.engine.play(idx):
            await interaction.response.send_message("Coup invalide.", ephemeral=True)
            return

        self.update_buttons()
        winner = self.engine.winner()
        if winner:
            await self.end_game(interaction, winner)
            return

        if self.is_vs_bot:
            bot_move = get_ttt_best_move(self.engine.board, "O", difficulty="normal")
            if bot_move is not None:
                self.engine.play(bot_move)
                self.update_buttons()
                winner = self.engine.winner()
                if winner:
                    await self.end_game(interaction, winner)
                    return

        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self):
        for item in self.children:
            if isinstance(item, TicTacToeButton):
                val = self.engine.board[item.idx]
                if val == "X":
                    item.label = "X"
                    item.style = discord.ButtonStyle.primary
                    item.disabled = True
                elif val == "O":
                    item.label = "O"
                    item.style = discord.ButtonStyle.danger
                    item.disabled = True
                else:
                    item.label = "\u200b"
                    item.style = discord.ButtonStyle.secondary
                    item.disabled = False

    def build_embed(self) -> discord.Embed:
        bot_name = self.persona["name"]
        title = f"🎮 Morpion vs {bot_name}" if self.is_vs_bot else f"🎮 Morpion : {self.player_x.display_name} vs {self.player_o.display_name}"
        color = discord.Color.gold()
        
        turn_str = ""
        winner = self.engine.winner()
        if not winner:
            current = self.player_x if self.engine.current_turn == "X" else self.player_o
            turn_str = f"Tour de : **{bot_name}**" if (isinstance(current, str) or (hasattr(current, 'bot') and current.bot)) else f"Tour de : {current.mention}"

        embed = discord.Embed(title=title, description=turn_str, color=color)
        return embed

    async def end_game(self, interaction: discord.Interaction, winner: str):
        self.update_buttons()
        for item in self.children:
            item.disabled = True
        self.stop()
        
        bot_name = self.persona["name"]
        unregister_players(self.player_x.id, 0 if self.is_vs_bot else self.player_o.id)

        embed = self.build_embed()
        flavor_text = ""
        points_awarded = 0
        
        if winner == "draw":
            embed.description = "Match nul !"
            flavor_text = random.choice(self.persona["draw_lines"])
            if self.is_vs_bot:
                points_awarded = try_award(self.player_x.id, "tictactoe", REWARD_VALUES["tictactoe"]["draw"], bot_name)
            else:
                p1 = try_award(self.player_x.id, "tictactoe", REWARD_VALUES["tictactoe"]["draw"], bot_name, self.player_o.id)
                p2 = try_award(self.player_o.id, "tictactoe", REWARD_VALUES["tictactoe"]["draw"], bot_name, self.player_x.id)
                points_awarded = (p1, p2)
        elif winner == "X":
            embed.description = f"{self.player_x.mention} a gagné !"
            flavor_text = random.choice(self.persona["lose_lines"]) if self.is_vs_bot else "Un beau combat !"
            if self.is_vs_bot:
                points_awarded = try_award(self.player_x.id, "tictactoe", REWARD_VALUES["tictactoe"]["win"], bot_name)
            else:
                points_awarded = try_award(self.player_x.id, "tictactoe", REWARD_VALUES["tictactoe"]["win"], bot_name, self.player_o.id)
        else:
            if self.is_vs_bot:
                embed.description = f"{bot_name} a gagné !"
                flavor_text = random.choice(self.persona["win_lines"])
            else:
                embed.description = f"{self.player_o.mention} a gagné !"
                flavor_text = "Un beau combat !"
                points_awarded = try_award(self.player_o.id, "tictactoe", REWARD_VALUES["tictactoe"]["win"], bot_name, self.player_x.id)

        rep_str = ""
        if isinstance(points_awarded, tuple):
            rep_str = f"\n\n🏆 *Gain réputation : {self.player_x.display_name} (+{points_awarded[0]}), {self.player_o.display_name} (+{points_awarded[1]})*"
        else:
            if points_awarded > 0:
                rep_str = f"\n\n🏆 *Gain réputation : +{points_awarded}*"
            elif points_awarded == 0 and winner != "draw" and (winner == "X" or (winner == "O" and not self.is_vs_bot)):
                rep_str = f"\n\n*Le gain de réputation a échoué (cooldown ou plafond journalier atteint).*"

        embed.description += f"\n\n*« {flavor_text} »*{rep_str}"
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        unregister_players(self.player_x.id, 0 if self.is_vs_bot else self.player_o.id)
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                embed = self.build_embed()
                embed.description = f"Temps écoulé. \n\n*« {random.choice(self.persona['timeout_lines'])} »*"
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ==========================================
# Connect4 (Puissance 4) Views
# ==========================================

class Connect4Button(discord.ui.Button):
    def __init__(self, col: int):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
        super().__init__(style=discord.ButtonStyle.secondary, label=emojis[col], row=0)
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view: Connect4View = self.view
        await view.handle_click(interaction, self.col)


class Connect4View(discord.ui.View):
    def __init__(self, player_r: discord.Member, player_y, persona: dict, timeout=180.0):
        super().__init__(timeout=timeout)
        self.player_r = player_r
        self.player_y = player_y
        self.persona = persona
        self.is_vs_bot = isinstance(player_y, str) or (hasattr(player_y, 'bot') and player_y.bot)
        self.engine = Connect4()
        
        for col in range(7):
            self.add_item(Connect4Button(col))
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        current_player = self.player_r if self.engine.current_turn == "R" else self.player_y
        if self.is_vs_bot:
            if interaction.user.id != self.player_r.id:
                await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
                return False
        else:
            if interaction.user.id not in [self.player_r.id, self.player_y.id]:
                await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
                return False
            if interaction.user.id != current_player.id:
                await interaction.response.send_message("Ce n'est pas ton tour, voyageur.", ephemeral=True)
                return False
        return True

    async def handle_click(self, interaction: discord.Interaction, col: int):
        if not self.engine.drop(col):
            await interaction.response.send_message("Colonne pleine.", ephemeral=True)
            return

        self.update_buttons()
        winner = self.engine.winner()
        if winner:
            await self.end_game(interaction, winner)
            return

        if self.is_vs_bot:
            bot_col = get_c4_best_col(self.engine.board, "Y", depth=4)
            if bot_col is not None:
                self.engine.drop(bot_col)
                self.update_buttons()
                winner = self.engine.winner()
                if winner:
                    await self.end_game(interaction, winner)
                    return

        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self):
        valid = self.engine.valid_cols()
        for item in self.children:
            if isinstance(item, Connect4Button):
                item.disabled = (item.col not in valid)

    def build_embed(self) -> discord.Embed:
        bot_name = self.persona["name"]
        title = f"🎮 Puissance 4 vs {bot_name}" if self.is_vs_bot else f"🎮 Puissance 4 : {self.player_r.display_name} vs {self.player_y.display_name}"
        color = discord.Color.gold()
        
        turn_str = ""
        winner = self.engine.winner()
        if not winner:
            current = self.player_r if self.engine.current_turn == "R" else self.player_y
            turn_str = f"Tour de : **{bot_name}**" if (isinstance(current, str) or (hasattr(current, 'bot') and current.bot)) else f"Tour de : {current.mention}"

        grid_text = self.engine.serialize() + "\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        embed = discord.Embed(title=title, description=f"{turn_str}\n\n{grid_text}", color=color)
        return embed

    async def end_game(self, interaction: discord.Interaction, winner: str):
        for item in self.children:
            item.disabled = True
        self.stop()
        
        bot_name = self.persona["name"]
        unregister_players(self.player_r.id, 0 if self.is_vs_bot else self.player_y.id)

        embed = self.build_embed()
        flavor_text = ""
        points_awarded = 0
        grid_text = self.engine.serialize() + "\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
        
        res_header = ""
        if winner == "draw":
            res_header = "Match nul !"
            flavor_text = random.choice(self.persona["draw_lines"])
            if self.is_vs_bot:
                points_awarded = try_award(self.player_r.id, "connect4", REWARD_VALUES["connect4"]["draw"], bot_name)
            else:
                p1 = try_award(self.player_r.id, "connect4", REWARD_VALUES["connect4"]["draw"], bot_name, self.player_y.id)
                p2 = try_award(self.player_y.id, "connect4", REWARD_VALUES["connect4"]["draw"], bot_name, self.player_r.id)
                points_awarded = (p1, p2)
        elif winner == "R":
            res_header = f"{self.player_r.mention} a gagné !"
            flavor_text = random.choice(self.persona["lose_lines"]) if self.is_vs_bot else "Un beau combat !"
            if self.is_vs_bot:
                points_awarded = try_award(self.player_r.id, "connect4", REWARD_VALUES["connect4"]["win"], bot_name)
            else:
                points_awarded = try_award(self.player_r.id, "connect4", REWARD_VALUES["connect4"]["win"], bot_name, self.player_y.id)
        else:
            if self.is_vs_bot:
                res_header = f"{bot_name} a gagné !"
                flavor_text = random.choice(self.persona["win_lines"])
            else:
                res_header = f"{self.player_y.mention} a gagné !"
                flavor_text = "Un beau combat !"
                points_awarded = try_award(self.player_y.id, "connect4", REWARD_VALUES["connect4"]["win"], bot_name, self.player_r.id)

        rep_str = ""
        if isinstance(points_awarded, tuple):
            rep_str = f"\n\n🏆 *Gain réputation : {self.player_r.display_name} (+{points_awarded[0]}), {self.player_y.display_name} (+{points_awarded[1]})*"
        else:
            if points_awarded > 0:
                rep_str = f"\n\n🏆 *Gain réputation : +{points_awarded}*"
            elif points_awarded == 0 and winner != "draw" and (winner == "R" or (winner == "Y" and not self.is_vs_bot)):
                rep_str = f"\n\n*Le gain de réputation a échoué (cooldown ou plafond journalier atteint).*"

        embed.description = f"**{res_header}**\n\n{grid_text}\n\n*« {flavor_text} »*{rep_str}"
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        unregister_players(self.player_r.id, 0 if self.is_vs_bot else self.player_y.id)
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                embed = self.build_embed()
                grid_text = self.engine.serialize() + "\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
                embed.description = f"**Temps écoulé.**\n\n{grid_text}\n\n*« {random.choice(self.persona['timeout_lines'])} »*"
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ==========================================
# Pierre-Feuille-Ciseaux (RPS) Views
# ==========================================

class RPSView(discord.ui.View):
    def __init__(self, player_a: discord.Member, player_b, persona: dict, timeout=180.0):
        super().__init__(timeout=timeout)
        self.player_a = player_a
        self.player_b = player_b
        self.persona = persona
        self.is_vs_bot = isinstance(player_b, str) or (hasattr(player_b, 'bot') and player_b.bot)
        self.engine = RPSGame()
        self.round_moves = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.is_vs_bot:
            if interaction.user.id != self.player_a.id:
                await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
                return False
        else:
            if interaction.user.id not in [self.player_a.id, self.player_b.id]:
                await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
                return False
        return True

    @discord.ui.button(label="Pierre 🪨", style=discord.ButtonStyle.primary)
    async def pierre(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.record_move(interaction, "pierre")

    @discord.ui.button(label="Feuille 📄", style=discord.ButtonStyle.primary)
    async def feuille(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.record_move(interaction, "feuille")

    @discord.ui.button(label="Ciseaux ✂️", style=discord.ButtonStyle.primary)
    async def ciseaux(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.record_move(interaction, "ciseaux")

    async def record_move(self, interaction: discord.Interaction, choice: str):
        user_id = interaction.user.id
        
        if self.is_vs_bot:
            bot_choice = random.choice(["pierre", "feuille", "ciseaux"])
            res = self.engine.resolve_round(choice, bot_choice)
            
            winner = self.engine.winner()
            if winner:
                await self.end_game(interaction, winner, last_round=(choice, bot_choice, res))
            else:
                embed = self.build_embed(last_round=(choice, bot_choice, res))
                await interaction.response.edit_message(embed=embed, view=self)
        else:
            if user_id in self.round_moves:
                await interaction.response.send_message("Tu as déjà fait ton choix pour cette manche.", ephemeral=True)
                return
                
            self.round_moves[user_id] = choice
            
            if len(self.round_moves) == 2:
                choice_a = self.round_moves[self.player_a.id]
                choice_b = self.round_moves[self.player_b.id]
                res = self.engine.resolve_round(choice_a, choice_b)
                
                self.round_moves.clear()
                winner = self.engine.winner()
                if winner:
                    await self.end_game(interaction, winner, last_round=(choice_a, choice_b, res))
                else:
                    embed = self.build_embed(last_round=(choice_a, choice_b, res))
                    await interaction.response.edit_message(embed=embed, view=self)
            else:
                embed = self.build_embed()
                await interaction.response.edit_message(embed=embed, view=self)
                await interaction.followup.send("Choix enregistré !", ephemeral=True)

    def build_embed(self, last_round=None) -> discord.Embed:
        bot_name = self.persona["name"]
        title = f"🎮 Pierre-Feuille-Ciseaux vs {bot_name}" if self.is_vs_bot else f"🎮 Pierre-Feuille-Ciseaux : {self.player_a.display_name} vs {self.player_b.display_name}"
        color = discord.Color.gold()
        
        desc = f"**Score :**\n"
        desc += f"- {self.player_a.display_name} : **{self.engine.score_a}**\n"
        if self.is_vs_bot:
            desc += f"- {bot_name} : **{self.engine.score_b}**\n"
        else:
            desc += f"- {self.player_b.display_name} : **{self.engine.score_b}**\n"
            
        desc += "\n*Premier à 2 points gagne la partie.*\n"
        
        if not self.is_vs_bot:
            status = []
            if self.player_a.id in self.round_moves:
                status.append(f"✅ {self.player_a.display_name} a choisi.")
            else:
                status.append(f"⏳ {self.player_a.display_name} choisit...")
            if self.player_b.id in self.round_moves:
                status.append(f"✅ {self.player_b.display_name} a choisi.")
            else:
                status.append(f"⏳ {self.player_b.display_name} choisit...")
            desc += "\n" + "\n".join(status)

        if last_round:
            choice_a, choice_b, res = last_round
            emojis = {"pierre": "🪨", "feuille": "📄", "ciseaux": "✂️"}
            name_b = bot_name if self.is_vs_bot else self.player_b.display_name
            desc += f"\n\n**Dernière manche :**\n"
            desc += f"- {self.player_a.display_name} a joué {emojis[choice_a]}\n"
            desc += f"- {name_b} a joué {emojis[choice_b]}\n"
            if res == "draw":
                desc += "➔ **Égalité !**"
            elif res == "a":
                desc += f"➔ **Point pour {self.player_a.display_name} !**"
            else:
                desc += f"➔ **Point pour {name_b} !**"

        embed = discord.Embed(title=title, description=desc, color=color)
        return embed

    async def end_game(self, interaction: discord.Interaction, winner: str, last_round=None):
        for item in self.children:
            item.disabled = True
        self.stop()
        
        bot_name = self.persona["name"]
        unregister_players(self.player_a.id, 0 if self.is_vs_bot else self.player_b.id)

        embed = self.build_embed(last_round)
        flavor_text = ""
        points_awarded = 0
        
        res_header = ""
        if winner == "a":
            res_header = f"{self.player_a.mention} a gagné le match !"
            flavor_text = random.choice(self.persona["lose_lines"]) if self.is_vs_bot else "Un beau combat !"
            if self.is_vs_bot:
                points_awarded = try_award(self.player_a.id, "rps", REWARD_VALUES["rps"]["win"], bot_name)
            else:
                points_awarded = try_award(self.player_a.id, "rps", REWARD_VALUES["rps"]["win"], bot_name, self.player_b.id)
        else:
            if self.is_vs_bot:
                res_header = f"{bot_name} a gagné le match !"
                flavor_text = random.choice(self.persona["win_lines"])
            else:
                res_header = f"{self.player_b.mention} a gagné le match !"
                flavor_text = "Un beau combat !"
                points_awarded = try_award(self.player_b.id, "rps", REWARD_VALUES["rps"]["win"], bot_name, self.player_a.id)

        rep_str = ""
        if points_awarded > 0:
            rep_str = f"\n\n🏆 *Gain réputation : +{points_awarded}*"
        elif points_awarded == 0 and (winner == "a" or (winner == "b" and not self.is_vs_bot)):
            rep_str = f"\n\n*Le gain de réputation a échoué (cooldown ou plafond journalier atteint).*"

        embed.description += f"\n\n**{res_header}**\n\n*« {flavor_text} »*{rep_str}"
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        unregister_players(self.player_a.id, 0 if self.is_vs_bot else self.player_b.id)
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                embed = self.build_embed()
                embed.description += f"\n\n**Temps écoulé.**\n\n*« {random.choice(self.persona['timeout_lines'])} »*"
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ==========================================
# Blackjack Views
# ==========================================

class BlackjackView(discord.ui.View):
    def __init__(self, player: discord.Member, persona: dict, timeout=180.0):
        super().__init__(timeout=timeout)
        self.player = player
        self.persona = persona
        self.engine = BlackjackGame()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("Ce n'est pas ta partie, voyageur.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Tirer 🃏", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        status = self.engine.player_hit()
        if status == "player_bust":
            await self.end_game(interaction, "dealer")
        else:
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Rester 🛑", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.engine.player_stand()
        res = self.engine.result()
        await self.end_game(interaction, res)

    def build_embed(self, reveal=False) -> discord.Embed:
        bot_name = self.persona["name"]
        title = f"🃏 Blackjack vs {bot_name}"
        color = discord.Color.gold()
        
        p_val = self.engine.hand_value(self.engine.player_hand)
        p_cards = ", ".join(self.engine.player_hand)
        
        if reveal:
            d_val = self.engine.hand_value(self.engine.dealer_hand)
            d_cards = ", ".join(self.engine.dealer_hand)
        else:
            d_val = "?"
            d_cards = f"{self.engine.dealer_hand[0]}, ❓"
            
        desc = f"**Ta main :** {p_cards} *(Total: {p_val})*\n"
        desc += f"**Main de {bot_name} :** {d_cards} *(Total: {d_val})*\n"
        embed = discord.Embed(title=title, description=desc, color=color)
        return embed

    async def end_game(self, interaction: discord.Interaction, result: str):
        for item in self.children:
            item.disabled = True
        self.stop()
        
        bot_name = self.persona["name"]
        unregister_player(self.player.id)

        embed = self.build_embed(reveal=True)
        flavor_text = ""
        points_awarded = 0
        
        res_header = ""
        if result == "blackjack":
            res_header = f"🎉 Blackjack naturel ! Tu as gagné !"
            flavor_text = random.choice(self.persona["lose_lines"])
            points_awarded = try_award(self.player.id, "blackjack", REWARD_VALUES["blackjack"]["blackjack"], bot_name)
        elif result == "player":
            res_header = "🏆 Tu as gagné !"
            flavor_text = random.choice(self.persona["lose_lines"])
            points_awarded = try_award(self.player.id, "blackjack", REWARD_VALUES["blackjack"]["win"], bot_name)
        elif result == "push":
            res_header = "🤝 Égalité (Push) !"
            flavor_text = random.choice(self.persona["draw_lines"])
            points_awarded = try_award(self.player.id, "blackjack", REWARD_VALUES["blackjack"]["draw"], bot_name)
        else:
            res_header = f"❌ {bot_name} a gagné !"
            flavor_text = random.choice(self.persona["win_lines"])
            points_awarded = 0

        rep_str = ""
        if points_awarded > 0:
            rep_str = f"\n\n🏆 *Gain réputation : +{points_awarded}*"
        elif points_awarded == 0 and result in ["player", "blackjack", "push"]:
            rep_str = f"\n\n*Le gain de réputation a échoué (cooldown ou plafond journalier atteint).*"

        embed.description += f"\n\n**{res_header}**\n\n*« {flavor_text} »*{rep_str}"
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        unregister_player(self.player.id)
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                embed = self.build_embed(reveal=True)
                embed.description += f"\n\n**Temps écoulé.**\n\n*« {random.choice(self.persona['timeout_lines'])} »*"
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ==========================================
# Quiz Views
# ==========================================

class QuizButton(discord.ui.Button):
    def __init__(self, idx: int):
        labels = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        super().__init__(style=discord.ButtonStyle.secondary, label=labels[idx], row=0)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: QuizView = self.view
        await view.handle_click(interaction, self.idx)


class QuizView(discord.ui.View):
    def __init__(self, player: discord.Member, persona: dict, timeout=180.0):
        super().__init__(timeout=timeout)
        self.player = player
        self.persona = persona
        self.engine = QuizGame(persona["quiz_questions"], num_questions=5)
        self.last_answer_correct = None
        
        for idx in range(4):
            self.add_item(QuizButton(idx))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("Ce n'est pas ton quiz, voyageur.", ephemeral=True)
            return False
        return True

    async def handle_click(self, interaction: discord.Interaction, choice_idx: int):
        self.last_answer_correct = self.engine.answer_question(choice_idx)
        
        if self.engine.is_finished():
            await self.end_game(interaction)
        else:
            embed = self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    def build_embed(self) -> discord.Embed:
        bot_name = self.persona["name"]
        title = f"🎯 Quiz Persona de {bot_name}"
        color = discord.Color.gold()
        
        q = self.engine.get_current_question()
        desc = f"Progression : **Question {self.engine.current_index + 1}/5**\n"
        desc += f"Score actuel : **{self.engine.score}**\n\n"
        
        if self.last_answer_correct is not None:
            status = "✅ Correct !" if self.last_answer_correct else "❌ Incorrect !"
            desc += f"*{status}*\n\n"
            
        desc += f"**{q['q']}**\n\n"
        labels = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        for idx, choice in enumerate(q["choices"]):
            desc += f"{labels[idx]} {choice}\n"
            
        embed = discord.Embed(title=title, description=desc, color=color)
        return embed

    async def end_game(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        self.stop()

        # ⚠️ Sans cette ligne, l'embed de fin levait un NameError : `end_game` etait la
        # SEULE des six methodes qui construisent un embed a ne pas definir `color`.
        # L'ecran de fin de quiz ne s'affichait donc jamais, et l'exception partait dans
        # un callback discord.py — donc nulle part de visible.
        color = discord.Color.gold()

        bot_name = self.persona["name"]
        unregister_player(self.player.id)

        points = self.engine.score * REWARD_VALUES["quiz"]["per_correct"]
        points_awarded = try_award(self.player.id, "quiz", points, bot_name)
        
        title = "🎯 Quiz Terminé !"
        desc = f"Score final : **{self.engine.score}/5**\n\n"
        
        if self.engine.score == 5:
            flavor = f"{bot_name} est impressionné. Vous savez presque autant de choses que lui !"
        elif self.engine.score >= 3:
            flavor = f"Pas mal. Mais {bot_name} en sait beaucoup plus."
        else:
            flavor = f"{bot_name} pense que vous devriez relire vos livres."
            
        rep_str = ""
        if points_awarded > 0:
            rep_str = f"\n\n🏆 *Gain réputation : +{points_awarded}*"
        elif points_awarded == 0:
            rep_str = f"\n\n*Le gain de réputation a échoué (cooldown ou plafond journalier atteint).*"
            
        desc += f"*« {flavor} »*{rep_str}"
        embed = discord.Embed(title=title, description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        unregister_player(self.player.id)
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                embed = discord.Embed(
                    title="🎯 Quiz Expiré",
                    description="Tu as mis trop de temps à répondre.",
                    color=discord.Color.dark_gray()
                )
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


# ==========================================
# PvP & Bot Invitation Dispatchers
# ==========================================

async def start_bot_game_direct(interaction: discord.Interaction, challenger: discord.Member, game_type: str, persona: dict):
    # Plays vs the bot immediately, bypassing invitation
    bot_name = persona["name"]
    if game_type == "tictactoe":
        view = TicTacToeView(challenger, bot_name, persona)
    elif game_type == "connect4":
        view = Connect4View(challenger, bot_name, persona)
    else:
        view = RPSView(challenger, bot_name, persona)
        
    embed = view.build_embed()
    await interaction.response.edit_message(content=None, embed=embed, view=view)
    view.message = interaction.message
    active_games[challenger.id] = interaction.message.id


async def start_duel_invite(interaction: discord.Interaction, challenger: discord.Member, opponent: discord.Member, game_type: str, persona: dict):
    async def on_accept(inter: discord.Interaction):
        if game_type == "tictactoe":
            view = TicTacToeView(challenger, opponent, persona)
        elif game_type == "connect4":
            view = Connect4View(challenger, opponent, persona)
        else:
            view = RPSView(challenger, opponent, persona)
            
        embed = view.build_embed()
        await inter.response.edit_message(content=None, embed=embed, view=view)
        view.message = inter.message
        active_games[challenger.id] = inter.message.id
        active_games[opponent.id] = inter.message.id

    view = DuelInviteView(challenger, opponent, game_type, on_accept)
    game_names = {"tictactoe": "Morpion", "connect4": "Puissance 4", "rps": "Pierre-Feuille-Ciseaux"}
    embed = discord.Embed(
        title="⚔️ Invitation au Duel ⚔️",
        description=f"{opponent.mention}, tu es défié(e) au jeu **{game_names[game_type]}** par {challenger.mention} !",
        color=discord.Color.gold()
    )
    await interaction.response.edit_message(content=None, embed=embed, view=view)
    view.message = interaction.message


async def start_duel_invite_with_ctx(ctx, challenger: discord.Member, opponent: discord.Member, game_type: str, persona: dict):
    async def on_accept(inter: discord.Interaction):
        if game_type == "tictactoe":
            view = TicTacToeView(challenger, opponent, persona)
        elif game_type == "connect4":
            view = Connect4View(challenger, opponent, persona)
        else:
            view = RPSView(challenger, opponent, persona)
            
        embed = view.build_embed()
        await inter.response.edit_message(content=None, embed=embed, view=view)
        view.message = inter.message
        active_games[challenger.id] = inter.message.id
        active_games[opponent.id] = inter.message.id

    view = DuelInviteView(challenger, opponent, game_type, on_accept)
    game_names = {"tictactoe": "Morpion", "connect4": "Puissance 4", "rps": "Pierre-Feuille-Ciseaux"}
    embed = discord.Embed(
        title="⚔️ Invitation au Duel ⚔️",
        description=f"{opponent.mention}, tu es défié(e) au jeu **{game_names[game_type]}** par {challenger.mention} !",
        color=discord.Color.gold()
    )
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg
    active_games[challenger.id] = msg.id
    active_games[opponent.id] = msg.id


async def handle_pvp_start(ctx, challenger, opponent, game_type, persona: dict):
    bot_name = persona["name"]
    if opponent.id == challenger.id:
        return await ctx.send("Tu ne peux pas te défier toi-même, voyageur.")
    if opponent.bot:
        return await ctx.send(f"M'aiq pense que les autres automates n'ont pas le temps pour tes jeux.")
    if challenger.id in active_games or opponent.id in active_games:
        return await ctx.send("L'un de vous est déjà occupé par une partie.")
        
    register_players(challenger.id, opponent.id, 0)
    await start_duel_invite_with_ctx(ctx, challenger, opponent, game_type, persona)


# ==========================================
# commands Registration
# ==========================================

def setup_games(bot: commands.Bot, logger_param, persona: dict):
    """Hooks all games commands onto M'aiq or any other bot."""
    global logger
    logger = logger_param
    
    bot_name = persona["name"]
    is_default = persona.get("is_default_host", False)
    
    @bot.command(name="jeux", aliases=["games"])
    async def cmd_jeux(ctx):
        """Affiche la liste des jeux disponibles et comment y jouer."""
        if not is_default:
            return  # Default host M'aiq only

        embed = discord.Embed(
            title="🎮 Les Jeux de M'aiq",
            description="M'aiq adore jouer. Voici les divertissements qu'il propose :",
            color=discord.Color.gold()
        )
        embed.add_field(name="❌ Morpion (`!morpion` ou `!ttt [@membre]`)", value="Alignez 3 symboles contre M'aiq ou en duel.", inline=False)
        embed.add_field(name="🟡 Puissance 4 (`!puissance4` ou `!p4` / `!c4 [@membre]`)", value="Alignez 4 jetons dans la grille.", inline=False)
        embed.add_field(name="✂️ Pierre-Feuille-Ciseaux (`!pfc` ou `!rps [@membre]`)", value="Le classique en best-of-3.", inline=False)
        embed.add_field(name="🃏 Blackjack (`!blackjack` ou `!bj`)", value="Battez la banque (M'aiq).", inline=False)
        embed.add_field(name="🎯 Quiz (`!quiz`)", value="5 questions sur Tamriel et la culture générale.", inline=False)
        embed.add_field(name="⚔️ Défi (`!defi @membre`)", value="Défiez un joueur et choisissez le jeu.", inline=False)
        embed.set_footer(text="Tous les jeux se jouent avec des boutons interactifs !")
        await ctx.send(embed=embed)

    @bot.command(name="morpion", aliases=["ttt"])
    async def cmd_morpion(ctx, opponent: discord.Member = None):
        """Lance une partie de Morpion (TicTacToe)."""
        challenger = ctx.author
        
        # Target bot resolution
        is_me = False
        is_other_bot = False
        is_human = False
        
        if opponent is not None:
            if opponent.bot:
                if opponent.id == bot.user.id:
                    is_me = True
                else:
                    is_other_bot = True
            else:
                is_human = True
        
        if is_other_bot:
            return # Silence total
            
        if is_me:
            # Play vs this bot
            if not register_player(challenger.id, 0):
                return await ctx.send("Tu as déjà une partie en cours, voyageur.")
            view = TicTacToeView(challenger, bot.user, persona)
            embed = view.build_embed()
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            active_games[challenger.id] = msg.id
        elif is_human:
            # Duel
            if is_default:
                await handle_pvp_start(ctx, challenger, opponent, "tictactoe", persona)
            else:
                return # Silence total
        else:
            # No target -> vs default host M'aiq
            if is_default:
                if not register_player(challenger.id, 0):
                    return await ctx.send("Tu as déjà une partie en cours, voyageur.")
                view = TicTacToeView(challenger, bot.user, persona)
                embed = view.build_embed()
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
                active_games[challenger.id] = msg.id
            else:
                return # Silence total

    @bot.command(name="puissance4", aliases=["p4", "c4"])
    async def cmd_puissance4(ctx, opponent: discord.Member = None):
        """Lance une partie de Puissance 4 (Connect4)."""
        challenger = ctx.author
        
        is_me = False
        is_other_bot = False
        is_human = False
        
        if opponent is not None:
            if opponent.bot:
                if opponent.id == bot.user.id:
                    is_me = True
                else:
                    is_other_bot = True
            else:
                is_human = True
        
        if is_other_bot:
            return
            
        if is_me:
            if not register_player(challenger.id, 0):
                return await ctx.send("Tu as déjà une partie en cours, voyageur.")
            view = Connect4View(challenger, bot.user, persona)
            embed = view.build_embed()
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            active_games[challenger.id] = msg.id
        elif is_human:
            if is_default:
                await handle_pvp_start(ctx, challenger, opponent, "connect4", persona)
            else:
                return
        else:
            if is_default:
                if not register_player(challenger.id, 0):
                    return await ctx.send("Tu as déjà une partie en cours, voyageur.")
                view = Connect4View(challenger, bot.user, persona)
                embed = view.build_embed()
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
                active_games[challenger.id] = msg.id
            else:
                return

    @bot.command(name="pfc", aliases=["rps"])
    async def cmd_pfc(ctx, opponent: discord.Member = None):
        """Lance une partie de Pierre-Feuille-Ciseaux (RPS)."""
        challenger = ctx.author
        
        is_me = False
        is_other_bot = False
        is_human = False
        
        if opponent is not None:
            if opponent.bot:
                if opponent.id == bot.user.id:
                    is_me = True
                else:
                    is_other_bot = True
            else:
                is_human = True
        
        if is_other_bot:
            return
            
        if is_me:
            if not register_player(challenger.id, 0):
                return await ctx.send("Tu as déjà une partie en cours, voyageur.")
            view = RPSView(challenger, bot.user, persona)
            embed = view.build_embed()
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            active_games[challenger.id] = msg.id
        elif is_human:
            if is_default:
                await handle_pvp_start(ctx, challenger, opponent, "rps", persona)
            else:
                return
        else:
            if is_default:
                if not register_player(challenger.id, 0):
                    return await ctx.send("Tu as déjà une partie en cours, voyageur.")
                view = RPSView(challenger, bot.user, persona)
                embed = view.build_embed()
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
                active_games[challenger.id] = msg.id
            else:
                return

    @bot.command(name="blackjack", aliases=["bj"])
    async def cmd_blackjack(ctx, opponent: discord.Member = None):
        """Lance une partie de Blackjack contre la banque."""
        challenger = ctx.author
        
        is_me = False
        is_other_bot = False
        
        if opponent is not None:
            if opponent.bot:
                if opponent.id == bot.user.id:
                    is_me = True
                else:
                    is_other_bot = True
            else:
                # opponent is human
                if not is_default:
                    return # Silence total
        else:
            # no target
            if not is_default:
                return
                
        if is_other_bot:
            return
            
        if not register_player(challenger.id, 0):
            return await ctx.send("Tu as déjà une partie en cours, voyageur.")
            
        view = BlackjackView(challenger, persona)
        embed = view.build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        active_games[challenger.id] = msg.id

    @bot.command(name="quiz")
    async def cmd_quiz(ctx, opponent: discord.Member = None):
        """Démarre un quiz persona solo de 5 questions."""
        challenger = ctx.author
        
        is_me = False
        is_other_bot = False
        
        if opponent is not None:
            if opponent.bot:
                if opponent.id == bot.user.id:
                    is_me = True
                else:
                    is_other_bot = True
            else:
                # opponent is human
                if not is_default:
                    return
        else:
            if not is_default:
                return
                
        if is_other_bot:
            return
            
        if not register_player(challenger.id, 0):
            return await ctx.send("Tu as déjà une partie en cours, voyageur.")
            
        view = QuizView(challenger, persona)
        embed = view.build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        active_games[challenger.id] = msg.id

    @bot.command(name="defi")
    async def cmd_defi(ctx, opponent: discord.Member):
        """Propose un menu de défis PvP ou PvE (contre un bot)."""
        challenger = ctx.author
        
        is_me = False
        is_other_bot = False
        if opponent.bot:
            if opponent.id == bot.user.id:
                is_me = True
            else:
                is_other_bot = True
        
        if is_other_bot:
            return # Silence total
            
        if not is_me:
            # Opponent is human -> Default host M'aiq handles it
            if not is_default:
                return # Silence total
                
            if opponent.id == challenger.id:
                return await ctx.send("Tu ne peux pas te défier toi-même, voyageur.")
            if challenger.id in active_games or opponent.id in active_games:
                return await ctx.send("L'un de vous est déjà occupé par une partie.")
                
            register_players(challenger.id, opponent.id, 0)
            view = DefiSelectView(challenger, opponent, persona, is_vs_bot=False)
            msg = await ctx.send(f"{challenger.mention} défie {opponent.mention} ! Choisissez le jeu :", view=view)
            view.message = msg
            active_games[challenger.id] = msg.id
            active_games[opponent.id] = msg.id
        else:
            # Opponent is ME (the bot) -> play vs ME
            if challenger.id in active_games:
                return await ctx.send("Tu as déjà une partie en cours, voyageur.")
                
            register_player(challenger.id, 0)
            view = DefiSelectView(challenger, opponent, persona, is_vs_bot=True)
            msg = await ctx.send(f"{challenger.mention}, tu défies {bot.user.mention} ! Choisis ton jeu :", view=view)
            view.message = msg
            active_games[challenger.id] = msg.id

    logger.info(f"🐱 [{bot_name} GAMES] Les mini-jeux ont été initialisés avec succès.")
