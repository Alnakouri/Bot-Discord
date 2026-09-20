# Laya — trieur « System One » partage par les six bots. CPU uniquement.
#
# ⚠️ TORCH CPU, PAS LA ROUE PAR DEFAUT. La roue PyPI par defaut tire les paquets CUDA
# (plusieurs Go) pour rien : le GPU est pris par `chatterbox-server` et Laya n'en a pas
# besoin (105 ms de mediane sur CPU, mesure du 2026-09-20).
#
# ⚠️ TORCH >= 2.5 EST OBLIGATOIRE. `transformers` 5.x le refuse en dessous, et l'echec
# ne le dit pas : il ressort en « Could not import module ModernBertModel », qui ne
# designe pas la cause. Deux heures perdues le 20/09.
#
# ⚠️ PAS DE torchvision. Il n'apporte rien ici et casse l'import de `transformers`
# des que sa version ne suit pas celle de torch (« operator torchvision::nms does not
# exist »). Le Dockerfile de chatterbox le desinstalle explicitement pour la meme raison.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
      "torch>=2.5" \
 && pip install --no-cache-dir \
      "laya>=0.3.4" \
      "transformers>=4.48" \
      fastapi \
      "uvicorn[standard]"

# Les poids sont EMBARQUES, pas montes : l'image est ainsi autonome et se deplacera
# telle quelle le jour ou les bots partiront sur un serveur a part. ~650 Mo.
ENV HF_HOME=/opt/hf
RUN python -c "import laya; m,r = laya.DEFAULT_MODELS['multilingual']; laya.agent.load(m, subfolder=r, device='cpu')"

COPY server.py /app/server.py

# Pas de root : les bots tournent deja non-root, ce service aussi.
RUN useradd --create-home --uid 10001 laya && chown -R laya:laya /app /opt/hf
USER laya

EXPOSE 8700

# Un seul worker, et c'est VOULU : chaque worker chargerait ses propres 1,7 Go, ce qui
# reviendrait exactement au probleme que ce service existe pour eviter.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8700", "--workers", "1"]
