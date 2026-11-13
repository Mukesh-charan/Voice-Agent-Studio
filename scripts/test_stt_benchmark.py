import httpx, os, time, edge_tts, asyncio
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('LLM_API_KEY')

async def make_speech():
    c = edge_tts.Communicate('Hi, my name is John Doe and I would like to book an appointment for tomorrow at 2 PM.', 'en-US-AriaNeural')
    b = bytearray()
    async for chunk in c.stream():
        if chunk['type'] == 'audio':
            b.extend(chunk['data'])
    return bytes(b)

speech_bytes = asyncio.run(make_speech())
print('Generated speech audio bytes:', len(speech_bytes))

for m in ['whisper-large-v3', 'whisper-large-v3-turbo']:
    t0 = time.time()
    r = httpx.post('https://api.groq.com/openai/v1/audio/transcriptions',
        files={'file': ('speech.mp3', speech_bytes, 'audio/mpeg')},
        data={'model': m, 'temperature': '0.0', 'language': 'en', 'prompt': 'Conversational phone call for customer appointments, bookings, names, phone numbers, and dates.'},
        headers={'Authorization': f'Bearer {key}'},
        timeout=10)
    dur = round(time.time()-t0, 3)
    res = r.json()
    print(f'Model: {m} | Time: {dur}s | Status: {r.status_code} | Text: "{res.get("text")}"')
