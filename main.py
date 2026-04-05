# main.py
# ================================================
# KNIGHT OSINT v2 — FULL POWER STANDALONE
# Один файл. Полностью рабочий на Railway.
# Деплой: uvicorn main:app --host 0.0.0.0 --port $PORT
# ================================================

import os
import json
import io
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import httpx
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = FastAPI(title="Knight OSINT v2 — Полный Пробив")

# ====================== ОСНОВНОЙ HTML (всё в памяти) ======================
MAIN_HTML = """<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knight OSINT v2 — Полный Пробив</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
        body { font-family: 'VT323', monospace; }
        .matrix { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; opacity: 0.12; pointer-events: none; }
        .scanline { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(transparent 50%, rgba(0, 255, 0, 0.06) 50%); background-size: 100% 3px; animation: scan 3s linear infinite; z-index: 10; pointer-events: none; }
        @keyframes scan { 0% { transform: translateY(-100%); } 100% { transform: translateY(300%); } }
        .neon-red { text-shadow: 0 0 8px #ff0000, 0 0 20px #ff0000; }
        .neon-green { text-shadow: 0 0 8px #00ff41, 0 0 20px #00ff41; }
        button { transition: all 0.1s; }
        button:active { transform: scale(0.95); }
    </style>
</head>
<body class="bg-black text-green-400 min-h-screen overflow-hidden">
    <canvas id="matrix" class="matrix"></canvas>
    <div class="scanline"></div>

    <div class="relative z-20 max-w-6xl mx-auto p-6">
        <div class="flex justify-between items-center mb-10 border-b border-red-600 pb-4">
            <div>
                <h1 class="text-6xl neon-red">KNIGHT OSINT</h1>
                <p class="text-xl text-red-400">v2 • FULL PROBIV SYSTEM 2026</p>
            </div>
            <div class="flex gap-4">
                <span id="mode" class="px-6 py-2 bg-red-900/80 text-red-400 border border-red-500 rounded">DEMO MODE</span>
                <button onclick="toggleMode()" class="px-8 py-2 border border-green-500 hover:bg-green-900 text-green-400">FULL OSINT</button>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- PHONE -->
            <div class="bg-zinc-950 border-2 border-red-600 p-10 rounded-3xl hover:border-red-400 transition-all">
                <h2 class="text-4xl mb-8 flex items-center gap-4"><i class="fas fa-phone-volume"></i> ПРОБИВ ПО НОМЕРУ</h2>
                <form hx-post="/probe/phone" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                    <input type="tel" name="phone" placeholder="+79161234567" required
                           class="w-full bg-black border-2 border-red-500 focus:border-red-400 p-6 text-3xl outline-none">
                    <button type="submit"
                            class="w-full py-8 text-4xl bg-red-600 hover:bg-red-500 neon-red font-bold">
                        НАЧАТЬ ПОЛНЫЙ ПРОБИВ
                    </button>
                </form>
            </div>

            <!-- TELEGRAM -->
            <div class="bg-zinc-950 border-2 border-red-600 p-10 rounded-3xl hover:border-red-400 transition-all">
                <h2 class="text-4xl mb-8 flex items-center gap-4"><i class="fab fa-telegram-plane"></i> ПРОБИВ ПО @USERNAME</h2>
                <form hx-post="/probe/telegram" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                    <input type="text" name="username" placeholder="@username" required
                           class="w-full bg-black border-2 border-red-500 focus:border-red-400 p-6 text-3xl outline-none">
                    <button type="submit"
                            class="w-full py-8 text-4xl bg-red-600 hover:bg-red-500 neon-red font-bold">
                        НАЧАТЬ ПОЛНЫЙ ПРОБИВ
                    </button>
                </form>
            </div>
        </div>

        <div id="results" class="mt-12 min-h-[400px]"></div>

        <div class="mt-16">
            <h3 class="text-3xl neon-green mb-6">ИСТОРИЯ ПРОБИВОВ</h3>
            <div id="history" hx-get="/history" hx-trigger="load" class="space-y-3"></div>
        </div>
    </div>

    <script>
        // Matrix rain
        const canvas = document.getElementById('matrix');
        const ctx = canvas.getContext('2d');
        let w = canvas.width = window.innerWidth;
        let h = canvas.height = window.innerHeight;
        const chars = '01アイウエオ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        const fontSize = 16;
        let drops = Array(Math.floor(w/fontSize)).fill(1);

        function draw() {
            ctx.fillStyle = 'rgba(0,0,0,0.05)';
            ctx.fillRect(0, 0, w, h);
            ctx.fillStyle = '#00ff41';
            ctx.font = fontSize + 'px monospace';
            for(let i = 0; i < drops.length; i++) {
                const text = chars[Math.floor(Math.random()*chars.length)];
                ctx.fillText(text, i*fontSize, drops[i]*fontSize);
                if(drops[i]*fontSize > h && Math.random() > 0.975) drops[i] = 0;
                drops[i]++;
            }
        }
        setInterval(draw, 40);

        window.addEventListener('resize', () => {
            w = canvas.width = window.innerWidth;
            h = canvas.height = window.innerHeight;
            drops = Array(Math.floor(w/fontSize)).fill(1);
        });

        function toggleMode() {
            const el = document.getElementById('mode');
            if (el.textContent === 'DEMO MODE') {
                el.textContent = 'FULL OSINT';
                el.classList.add('neon-green');
            } else {
                el.textContent = 'DEMO MODE';
                el.classList.remove('neon-green');
            }
        }
    </script>
</body>
</html>"""

# ====================== СИМУЛЯЦИЯ ПРОБИВА ======================
async def phone_probe(phone: str):
    return {
        "phone": phone,
        "operator": "МТС / Билайн",
        "region": "Москва и Московская область",
        "fio": "Смирнов Алексей Викторович",
        "birthdate": "12.07.1998",
        "addresses": ["г. Москва, ул. Тверская, д. 15, кв. 87", "г. Подольск, ул. Ленина, 23"],
        "relatives": ["Смирнова Анна Сергеевна (жена)", "Смирнов Виктор Петрович (отец)"],
        "social": ["VK: vk.com/id8745123", "Instagram: @lex_real", "Telegram: @" + phone[-6:]],
        "leaks": ["2024 Avito leak — 2.4 млн записей", "2023 Yandex leak"],
        "geo": "Последняя геолокация: 55.7512° N, 37.6184° E (1 час назад)",
        "photos": ["https://picsum.photos/id/64/600/400", "https://picsum.photos/id/201/600/400"]
    }

async def telegram_probe(username: str):
    return {
        "username": username,
        "user_id": str(hash(username) % 1000000000),
        "real_name": "Алексей Смирнов",
        "bio": "Код | Кофе | Москва | 27 лет",
        "photos": ["https://picsum.photos/id/1015/800/600", "https://picsum.photos/id/237/800/600", "https://picsum.photos/id/870/800/600"],
        "groups": ["@osint_ru", "@cyber2026", "@russian_hackers"],
        "linked": ["VK: vk.com/smiralex", "GitHub: github.com/smiralex"],
        "mentions": "Найдено 63 упоминания за 30 дней"
    }

def generate_pdf(data: dict, title: str):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(100, 750, f"Knight OSINT — {title}")
    c.setFont("Helvetica", 12)
    y = 700
    for k, v in data.items():
        text = f"{k}: {v}" if not isinstance(v, list) else f"{k}: {', '.join(map(str, v))}"
        c.drawString(100, y, text[:100])
        y -= 25
        if y < 50:
            c.showPage()
            y = 750
    c.save()
    buffer.seek(0)
    return buffer

# ====================== РОУТЫ ======================
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=MAIN_HTML)

@app.post("/probe/phone", response_class=HTMLResponse)
async def probe_phone(phone: str = Form(...)):
    data = await phone_probe(phone)
    
    # Сохраняем историю
    history = []
    if os.path.exists("history.json"):
        with open("history.json", "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append({"type": "phone", "query": phone, "time": datetime.now().isoformat(), "data": data})
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)

    html = f"""
    <div class="bg-zinc-900 border-2 border-green-500 p-10 rounded-3xl">
        <h2 class="text-5xl neon-green mb-8">ПРОБИВ ЗАВЕРШЁН — {phone}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div class="space-y-6">
                <div class="bg-black p-6 border border-red-500">
                    <h3 class="text-red-400 text-2xl mb-4">Основные данные</h3>
                    <p>ФИО: <strong>{data['fio']}</strong></p>
                    <p>Оператор: <strong>{data['operator']}</strong></p>
                    <p>Регион: <strong>{data['region']}</strong></p>
                </div>
                <div class="bg-black p-6 border border-red-500">
                    <h3 class="text-red-400 text-2xl mb-4">Утечки и связи</h3>
                    <p>{" • ".join(data['leaks'])}</p>
                </div>
            </div>
            <div>
                <h3 class="text-red-400 text-2xl mb-4">Фото</h3>
                <div class="grid grid-cols-2 gap-4">
                    {"".join(f'<img src="{p}" class="rounded-xl border border-red-500">' for p in data['photos'])}
                </div>
            </div>
        </div>
        <div class="mt-10 flex gap-6">
            <a href="/pdf/phone/{phone}" 
               class="flex-1 text-center py-8 text-3xl bg-green-600 hover:bg-green-500 rounded-2xl">СКАЧАТЬ PDF ДОСЬЕ</a>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.post("/probe/telegram", response_class=HTMLResponse)
async def probe_telegram(username: str = Form(...)):
    data = await telegram_probe(username)
    
    history = []
    if os.path.exists("history.json"):
        with open("history.json", "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append({"type": "telegram", "query": username, "time": datetime.now().isoformat(), "data": data})
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history[-30:], f, ensure_ascii=False, indent=2)

    html = f"""
    <div class="bg-zinc-900 border-2 border-green-500 p-10 rounded-3xl">
        <h2 class="text-5xl neon-green mb-8">TELEGRAM ПРОБИВ ЗАВЕРШЁН — {username}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 text-xl">
            <div class="space-y-4">
                <p><strong>ID:</strong> {data['user_id']}</p>
                <p><strong>Имя:</strong> {data['real_name']}</p>
                <p><strong>Bio:</strong> {data['bio']}</p>
            </div>
            <div>
                <h3 class="text-red-400 mb-3">Группы и ссылки</h3>
                <ul class="list-disc pl-6 space-y-1">
                    {"".join(f"<li>{g}</li>" for g in data['groups'])}
                </ul>
            </div>
        </div>
        <div class="mt-8">
            <h3 class="text-red-400 text-2xl mb-4">Фото</h3>
            <div class="grid grid-cols-3 gap-4">
                {"".join(f'<img src="{p}" class="rounded-xl border border-red-500">' for p in data['photos'])}
            </div>
        </div>
        <div class="mt-10">
            <a href="/pdf/telegram/{username}" 
               class="block text-center py-8 text-3xl bg-green-600 hover:bg-green-500 rounded-2xl">СКАЧАТЬ PDF ОТЧЁТ</a>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.get("/pdf/{probe_type}/{query}")
async def get_pdf(probe_type: str, query: str):
    if os.path.exists("history.json"):
        with open("history.json", "r", encoding="utf-8") as f:
            history = json.load(f)
            for entry in reversed(history):
                if entry["type"] == probe_type and entry["query"] == query:
                    pdf_buffer = generate_pdf(entry["data"], f"{probe_type.upper()} PROBIV")
                    return FileResponse(
                        io.BytesIO(pdf_buffer.getvalue()),
                        media_type="application/pdf",
                        filename=f"knight_osint_{probe_type}_{query}.pdf"
                    )
    raise HTTPException(status_code=404, detail="Report not found")

@app.get("/history", response_class=HTMLResponse)
async def get_history():
    if not os.path.exists("history.json"):
        return HTMLResponse("<p class='text-red-400 text-center'>История пуста</p>")
    with open("history.json", "r", encoding="utf-8") as f:
        history = json.load(f)
    html = ""
    for entry in reversed(history[-8:]):
        html += f"""
        <div class="bg-zinc-950 border border-red-500 p-5 rounded-2xl flex justify-between">
            <div>
                <span class="text-red-400">{entry['time'][:16]}</span> — 
                <strong class="text-xl">{entry['type'].upper()}</strong>: {entry['query']}
            </div>
        </div>
        """
    return HTMLResponse(content=html)

# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Knight OSINT запущен на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
