"""Un appel qui transporte une image n'a pas le meme budget qu'un « bonjour ».

Le 2026-09-03, M'aiq a echoue DEUX fois a 15 secondes d'intervalle sur une image de
142 Ko : `timeout=15`, la valeur du TEXTE, avait ete recopiee telle quelle sur les appels
vision. Ces tests fixent les deux moities de la regle :

* les echelons qui **transportent** le media (Gemini, OpenRouter) prennent la borne media ;
* ceux qui le **jettent** (Mistral, Groq) gardent la borne texte — sans quoi on annule le
  garde-fou pose contre le 429 Groq, qui coute 36 secondes avant de rendre la main.
"""
import os
import re
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

# Les 4 bots qui portent leur cascade EN LIGNE. Johnny et Sugar passent par
# `shared/llm_cascade.py`, dont la borne est deja choisie sur `has_image`/`has_audio`.
BOTS_CASCADE_INLINE = {
    "Sheogorath": "bot_sheogorath.py",
    "Alfred": "bot_alfred.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
}

BORNE_MEDIA = "45 if media_data else 15"
_CLIENT = re.compile(r'client_type == "(\w+)"')
TRANSPORTENT_LE_MEDIA = {"gemini", "openrouter"}


def _timeouts_par_client(chemin):
    """Rend {client_type: [lignes de timeout]} en suivant le dernier `client_type ==` vu."""
    par_client = {}
    courant = None
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            m = _CLIENT.search(ligne)
            if m:
                courant = m.group(1)
            if "timeout=" in ligne and courant:
                par_client.setdefault(courant, []).append(ligne.strip())
    return par_client


class TestBorneMedia(unittest.TestCase):
    def test_seuls_les_echelons_qui_portent_le_media_ont_la_borne_longue(self):
        inspectes = 0
        for bot, fichier in BOTS_CASCADE_INLINE.items():
            chemin = os.path.join(RACINE, bot, fichier)
            self.assertTrue(os.path.exists(chemin), f"{chemin} introuvable")
            inspectes += 1

            par_client = _timeouts_par_client(chemin)

            for client in TRANSPORTENT_LE_MEDIA:
                lignes = par_client.get(client, [])
                self.assertTrue(
                    lignes,
                    f"{bot} : aucun timeout trouve dans la branche {client} — "
                    "le test n'a pas trouve sa matiere.",
                )
                # ⚠️ TOUS, pas « au moins un » : avec `any`, remettre 15 s sur le
                # premier appel Gemini passait inapercu parce que la seconde passe
                # (retour d'outil) portait encore la bonne borne.
                fautifs = [l for l in lignes if BORNE_MEDIA not in l]
                self.assertFalse(
                    fautifs,
                    f"{bot}/{client} : ces appels transportent le media mais gardent "
                    f"la borne texte — une image y serait coupee a 15 s. {fautifs}",
                )

            for client in ("mistral", "groq"):
                for l in par_client.get(client, []):
                    self.assertNotIn(
                        BORNE_MEDIA, l,
                        f"{bot}/{client} : cet echelon JETTE le media, il ne doit pas "
                        "attendre 45 s. Cela annule la borne posee contre le 429 Groq "
                        f"(36 s avant de rendre la main). {l}",
                    )

        # ⚠️ Deriver le compte de la liste de depart, jamais de la boucle.
        self.assertEqual(inspectes, len(BOTS_CASCADE_INLINE))
        self.assertEqual(inspectes, 4)


class FakeAttachment:
    def __init__(self, content_type="image/jpeg", filename="test.jpg"):
        self.content_type = content_type
        self.filename = filename
        self.size = 1024
        self.url = "http://x"

    def is_voice_message(self):
        return False


class TestBorneMediaEnVrai(unittest.IsolatedAsyncioTestCase):
    """La preuve par l'execution : ce que `asyncio.wait_for` recoit vraiment."""

    async def test_sheo_borne_a_45s_quand_l_image_est_la(self):
        sheo_dir = os.path.join(RACINE, "Sheogorath")
        if sheo_dir not in sys.path:
            sys.path.insert(0, sheo_dir)
        import bot_sheogorath as sheo

        message = MagicMock()
        message.author.bot = False
        message.author.id = 123
        message.author.name = "TestUser"
        message.content = "Regarde"
        message.channel = AsyncMock()
        message.channel.send = AsyncMock()
        message.channel.id = 456
        message.attachments = [FakeAttachment()]

        class AsyncIter:
            def __init__(self, items):
                self.items = items

            async def __aiter__(self):
                for item in self.items:
                    yield item

        message.channel.history = MagicMock(return_value=AsyncIter([]))

        vrai_wait_for = sheo.asyncio.wait_for
        vus = []

        async def espion(coro, timeout=None):
            vus.append(timeout)
            return await vrai_wait_for(coro, timeout=timeout)

        with (
            patch("bot_sheogorath.download_media", new_callable=AsyncMock) as dl,
            patch("bot_sheogorath.key_manager.get_key", return_value="FAKE_KEY"),
            patch("bot_sheogorath.get_model_cascade") as cascade,
            patch("bot_sheogorath.get_safe_genai_client") as get_client,
            patch("bot_sheogorath.fact_brain.get_facts", return_value=[]),
            patch("bot_sheogorath.faveur_system.get_rank_context", return_value=""),
            patch("bot_sheogorath.asyncio.wait_for", espion),
        ):
            dl.return_value = (b"fake_image_data", "image/jpeg")
            cascade.return_value = [("gemini", "test-model")]
            client = MagicMock()
            reponse = MagicMock()
            reponse.text = "Mock response"
            reponse.candidates[0].content.parts[0].function_call = None
            client.models.generate_content.return_value = reponse
            get_client.return_value = client

            with patch("discord.Client.user", new_callable=unittest.mock.PropertyMock) as u:
                u.return_value = MagicMock(id=999)
                await sheo.on_message(message)

        self.assertTrue(vus, "Aucun appel borne : la cascade n'a pas ete atteinte.")
        self.assertIn(
            45, vus,
            f"L'appel vision n'a pas ete borne a 45 s. Bornes vues : {vus}",
        )


if __name__ == "__main__":
    unittest.main()
