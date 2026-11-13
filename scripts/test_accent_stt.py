import httpx, os, time, edge_tts, asyncio
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('LLM_API_KEY')

async def make_speech():
    c = edge_tts.Communicate('Give me all the tools for CI CD pipelines in agentic AI.', 'en-IN-PrabhatNeural')
    b = bytearray()
    async for chunk in c.stream():
        if chunk['type'] == 'audio':
            b.extend(chunk['data'])
    return bytes(b)

speech_bytes = asyncio.run(make_speech())
print('Generated Indian English speech bytes:', len(speech_bytes))

for m in ['whisper-large-v3-turbo', 'whisper-large-v3']:
    # Without language/prompt (what was happening before)
    r_old = httpx.post('https://api.groq.com/openai/v1/audio/transcriptions',
        files={'file': ('speech.mp3', speech_bytes, 'audio/mpeg')},
        data={'model': m},
        headers={'Authorization': f'Bearer {key}'}, timeout=10).json()

    # With temperature=0.0, language='en', and domain prompt
    t0 = time.time()
    r_new = httpx.post('https://api.groq.com/openai/v1/audio/transcriptions',
        files={'file': ('speech.mp3', speech_bytes, 'audio/mpeg')},
        data={'model': m, 'temperature': '0.0', 'language': 'en', 'prompt': 'Conversational voice call. Vocabulary: agentic AI, CI/CD, pipelines, GitHub, tools, bookings, schedule.'},
        headers={'Authorization': f'Bearer {key}'}, timeout=10)
    dur = round(time.time()-t0, 3)
    res_new = r_new.json()
    print(f'Model: {m}')
    print(f'  BEFORE (no lang/prompt): "{r_old.get("text")}"')
    print(f'  AFTER  (opt lang/prompt): "{res_new.get("text")}" in {dur}s')
