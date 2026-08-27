"""
Test standalone de la vision Moondream via Ollama.
Usage: python shared/test_ollama_vision.py [url_image_optionnelle]
"""
import asyncio
import aiohttp
import base64
import sys
import os

OLLAMA_URL = os.getenv("OLLAMA_VISION_URL", "http://localhost:11445")
TEST_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Cat_November_2010-1a.jpg/220px-Cat_November_2010-1a.jpg"


async def test_vision(image_url: str = None):
    url = image_url or TEST_IMAGE_URL
    print(f"🔍 Test Moondream via {OLLAMA_URL}")
    print(f"📷 Image: {url}")
    
    # 1. Check service
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{OLLAMA_URL}/api/tags") as r:
                if r.status != 200:
                    print(f"❌ Ollama non accessible (HTTP {r.status})")
                    return
                data = await r.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                print(f"✅ Ollama up — Modèles: {models}")
                if not any("moondream" in m for m in models):
                    print("❌ Moondream non installé! Lancez: ollama pull moondream")
                    return
    except Exception as e:
        print(f"❌ Ollama injoignable: {e}")
        return
    
    # 2. Download test image
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            img_data = await r.read()
    
    img_b64 = base64.b64encode(img_data).decode()
    print(f"📦 Image téléchargée ({len(img_data)} bytes)")
    
    # 3. Call Moondream
    print("⏳ Appel Moondream...")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
        async with s.post(f"{OLLAMA_URL}/api/generate", json={
            "model": "moondream",
            "prompt": "Describe this image in detail.",
            "images": [img_b64],
            "stream": False
        }) as r:
            if r.status == 200:
                data = await r.json()
                result = data.get("response", "")
                print(f"\n✅ RÉSULTAT ({len(result)} chars):\n{result}")
            else:
                print(f"❌ Erreur: {r.status} — {await r.text()}")


if __name__ == "__main__":
    img = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(test_vision(img))
