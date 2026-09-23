# -*- coding: utf-8 -*-
import aiohttp
from shared.twitch.auth import TwitchAuth

class TwitchProfile:
    """
    Gère la personnalisation du profil Twitch (bio, couleur).
    """
    def __init__(self, bot_id: str, logger, client_id: str, auth: TwitchAuth):
        self.bot_id = bot_id
        self.logger = logger
        self.client_id = client_id
        self.auth = auth

    async def update_profile(self, bio: str | None = None, chat_color: str | None = None) -> str | None:
        """
        Met à jour la bio et/ou la couleur de chat en best-effort.

        Rend "bio_refusee" si Twitch a refusé la bio par sa modération (400
        « failed moderation »), sinon None. La couleur n'entre pas dans ce retour.
        """
        if not bio and not chat_color:
            return

        token = await self.auth.get_valid_token()
        if not token:
            self.logger.warning(f"⚠️ [TWITCH_PROFILE:{self.bot_id}] Aucun token valide pour mettre à jour le profil.")
            return

        headers = {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {token}"
        }

        resultat = None
        async with aiohttp.ClientSession() as session:
            # 1. Update Bio (description)
            if bio:
                clean_bio = bio[:300]
                url_bio = "https://api.twitch.tv/helix/users"
                try:
                    # Twitch "Update User" = PUT (PATCH renvoie 404, méthode non routée)
                    async with session.put(url_bio, params={"description": clean_bio}, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            self.logger.info(f"✅ [TWITCH_PROFILE:{self.bot_id}] Description mise à jour avec succès.")
                        elif resp.status == 401:
                            self.logger.info(f"🔑 [TWITCH_PROFILE:{self.bot_id}] Bio non posée (scope user:edit absent / code 401)")
                        else:
                            err_text = await resp.text()
                            self.logger.warning(f"⚠️ [TWITCH_PROFILE:{self.bot_id}] Erreur mise à jour bio ({resp.status}): {err_text}")
                            if resp.status == 400 and "moderation" in err_text.lower():
                                resultat = "bio_refusee"
                except Exception as e:
                    self.logger.error(f"❌ [TWITCH_PROFILE:{self.bot_id}] Exception lors de la mise à jour de la bio: {e}")

            # 2. Update Chat Color
            if chat_color:
                user_id = None
                try:
                    async with session.get("https://api.twitch.tv/helix/users", headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("data"):
                                user_id = data["data"][0].get("id")
                        else:
                            err_text = await resp.text()
                            self.logger.warning(f"⚠️ [TWITCH_PROFILE:{self.bot_id}] Échec récupération user_id ({resp.status}): {err_text}")
                except Exception as e:
                    self.logger.error(f"❌ [TWITCH_PROFILE:{self.bot_id}] Exception lors de la récupération du user_id: {e}")

                if user_id:
                    url_color = "https://api.twitch.tv/helix/chat/color"
                    try:
                        async with session.put(url_color, params={"user_id": user_id, "color": chat_color}, headers=headers, timeout=10) as resp:
                            if resp.status == 204:
                                self.logger.info(f"✅ [TWITCH_PROFILE:{self.bot_id}] Couleur du chat mise à jour ({chat_color}).")
                            elif resp.status == 401:
                                self.logger.info(f"🔑 [TWITCH_PROFILE:{self.bot_id}] Couleur non posée (scope user:manage:chat_color absent / code 401)")
                            else:
                                err_text = await resp.text()
                                self.logger.warning(f"⚠️ [TWITCH_PROFILE:{self.bot_id}] Erreur mise à jour couleur ({resp.status}): {err_text}")
                    except Exception as e:
                        self.logger.error(f"❌ [TWITCH_PROFILE:{self.bot_id}] Exception lors de la mise à jour de la couleur: {e}")

        return resultat

