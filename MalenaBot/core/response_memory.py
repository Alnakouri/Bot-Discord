# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/response_memory.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

class ResponseMemory:
    """Anti-repetition memory per guild (shared by all bots)."""
    def __init__(self, max_size=10):
        self.memory = {}  # {guild_id: [responses]}
        self.max_size = max_size
    
    def add(self, guild_id, response):
        if guild_id not in self.memory:
            self.memory[guild_id] = []
        if self.memory[guild_id] and self.memory[guild_id][-1] == response:
            return
        self.memory[guild_id].append(response)
        if len(self.memory[guild_id]) > self.max_size:
            self.memory[guild_id].pop(0)

    def get_recent(self, guild_id):
        return self.memory.get(guild_id, [])


def merge_recent_responses(*sources, limit=8):
    """Fusionne des listes de réponses récentes (None-safe), dédoublonne en gardant l'ordre."""
    seen, out = set(), []
    for src in sources:
        for r in (src or []):
            if r and r not in seen:
                seen.add(r)
                out.append(r)
    return out[-limit:]
