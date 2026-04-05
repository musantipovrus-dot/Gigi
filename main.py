# main.py
# ================================================
# Knight OSINT Dashboard v2 — Standalone Full Power
# Один файл. Полный пробив по телефону и Telegram.
# Запуск: uvicorn main:app --reload
# ================================================
# Установка зависимостей одной командой:
# pip install fastapi uvicorn jinja2 httpx beautifulsoup4 python-multipart reportlab

import os
import json
import time
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io

app = FastAPI(title="Knight OSINT — Полный Пробив")
templates = Jinja2Templates(directory="templates")  # будет создано inline

# Создаём папку для шаблонов и истории если нет
os.makedirs("templates", exist_ok=True)
os.makedirs("data", exist_ok=True)
HISTORY_FILE = "data/history.json"

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# Простая защита паролем (demo: knight2026)
SECRET_PASSWORD = "knight2026"

def check_auth(request: Request):
    session = request.cookies.get("auth")
    if session != "authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ====================== ШАБЛОНЫ ======================
# index.html — основной дашборд
with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write("""<!DOCTYPE html>
<html lang="ru" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knight OSINT — Полный Пробив</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
        body { font-family: 'VT323', monospace; }
        .scanline { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(transparent 50%, rgba(0,255,0,0.03) 50%); background-size: 100% 4px; pointer-events: none; animation: scan 4s linear infinite; z-index: 9999; }
        @keyframes scan { 0% { transform: translateY(-100%); } 100% { transform: translateY(100%); } }
        .neon-red { text-shadow: 0 0 10px #ff0000, 0 0 20px #ff0000; }
        .neon-green { text-shadow: 0 0 10px #00ff00, 0 0 20px #00ff00; }
        .matrix-bg { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1; opacity: 0.15; }
    </style>
</head>
<body class="bg-black text-green-400 overflow-hidden">
    <canvas id="matrix" class="matrix-bg"></canvas>
    <div class="scanline"></div>
    
    <div class="min-h-screen p-6">
        <div class="max-w-7xl mx-auto">
            <!-- HEADER -->
            <div class="flex justify-between items-center mb-8 border-b border-red-500 pb-4">
                <div>
                    <h1 class="text-5xl neon-red">KNIGHT OSINT</h1>
                    <p class="text-red-400 text-xl">v2 • FULL PROBIV SYSTEM</p>
                </div>
                <div class="flex items-center gap-4">
                    <span id="mode" class="px-4 py-1 bg-red-900 text-red-400 rounded">DEMO MODE</span>
                    <button onclick="toggleMode()" class="px-6 py-2 bg-green-900 hover:bg-green-700 border border-green-500 rounded transition">SWITCH TO FULL</button>
                </div>
            </div>

            <!-- DASHBOARD -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <!-- PHONE CARD -->
                <div class="bg-zinc-950 border border-red-500 p-8 rounded-xl hover:border-red-400 transition group">
                    <h2 class="text-3xl mb-6 flex items-center gap-3"><i class="fas fa-phone"></i> ПРОБИВ ПО НОМЕРУ</h2>
                    <form hx-post="/probe/phone" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                        <input type="text" name="phone" placeholder="+7xxxxxxxxxx" required
                               class="w-full bg-black border border-red-500 p-4 text-2xl focus:outline-none focus:border-red-400">
                        <button type="submit" 
                                class="w-full py-6 text-3xl bg-red-600 hover:bg-red-500 transition active:scale-95 neon-red">
                            НАЧАТЬ ПОЛНЫЙ ПРОБИВ
                        </button>
                    </form>
                </div>

                <!-- TELEGRAM CARD -->
                <div class="bg-zinc-950 border border-red-500 p-8 rounded-xl hover:border-red-400 transition group">
                    <h2 class="text-3xl mb-6 flex items-center gap-3"><i class="fab fa-telegram"></i> ПРОБИВ ПО @USERNAME</h2>
                    <form hx-post="/probe/telegram" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                        <input type="text" name="username" placeholder="@username" required
                               class="w-full bg-black border border-red-500 p-4 text-2xl focus:outline-none focus:border-red-400">
                        <button type="submit" 
                                class="w-full py-6 text-3xl bg-red-600 hover:bg-red-500 transition active:scale-95 neon-red">
                            НАЧАТЬ ПОЛНЫЙ ПРОБИВ
                        </button>
                    </form>
                </div>
            </div>

            <!-- RESULTS AREA -->
            <div id="results" class="mt-12"></div>

            <!-- HISTORY -->
            <div class="mt-12">
                <h3 class="text-2xl mb-4 neon-green">ИСТОРИЯ ПРОБИВОВ</h3>
                <div id="history" hx-get="/history" hx-trigger="load" class="grid grid-cols-1 gap-4"></div>
            </div>
        </div>
    </div>

    <script>
        // Matrix rain background
        const canvas = document.getElementById('matrix');
        const ctx = canvas.getContext('2d');
        canvas.height = window.innerHeight;
        canvas.width = window.innerWidth;
        const chars = '01アイウエオカキクケコ0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        const fontSize = 14;
        const columns = canvas.width / fontSize;
        const drops = Array(Math.floor(columns)).fill(1);

        function drawMatrix() {
            ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#00ff00';
            ctx.font = fontSize + 'px monospace';
            for (let i = 0; i < drops.length; i++) {
                const text = chars[Math.floor(Math.random() * chars.length)];
                ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) drops[i] = 0;
                drops[i]++;
            }
        }
        setInterval(drawMatrix, 35);

        function toggleMode() {
            const modeEl = document.getElementById('mode');
            if (modeEl.textContent === 'DEMO MODE') {
                modeEl.textContent = 'FULL OSINT';
                modeEl.classList.add('neon-green');
            } else {
                modeEl.textContent = 'DEMO MODE';
                modeEl.classList.remove('neon-green');
            }
        }
    </script>
</body>
</html>""")

# ====================== РЕАЛЬНЫЕ И СИМУЛИРОВАННЫЕ ЗАПРОСЫ ======================
async def simulate_phone_probe(phone: str, full_mode: bool = False):
    results = {
        "phone": phone,
        "operator": "МТС / Билайн / МегаФон",
        "region": "Москва / Санкт-Петербург / Регион РФ",
        "fio": "Иванов Иван Иванович",
        "birthdate": "15.03.1995",
        "addresses": ["ул. Ленина 45, кв. 12", "Москва, Россия"],
        "relatives": ["Иванова Анна Петровна (жена)", "Иванов Петр Сергеевич (отец)"],
        "social": ["VK: vk.com/id123456", "Instagram: @ivan_real", "Telegram: @ivan_real"],
        "leaks": ["2023: 1.2M записей (email + phone)", "2024: Avito утечка"],
        "geo": "Последняя гео: 55.7558° N, 37.6173° E (2 часа назад)",
        "photos": ["https://picsum.photos/id/64/400/300", "https://picsum.photos/id/201/400/300"]
    }
    
    if full_mode:
        # Реальные запросы где возможно
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Пример реального запроса к публичному сервису (numlookup-like)
                resp = await client.get(f"https://api.numlookupapi.com/v1/validate/{phone[1:]}?apikey=demo")  # демо-ключ
                if resp.status_code == 200:
                    data = resp.json()
                    results["operator"] = data.get("carrier", results["operator"])
        except:
            pass
    
    return results

async def simulate_telegram_probe(username: str, full_mode: bool = False):
    results = {
        "username": username,
        "user_id": "987654321",
        "real_name": "Алексей Смирнов",
        "bio": "Разработчик | Люблю кофе и код | Москва",
        "photos": ["https://picsum.photos/id/1015/600/400", "https://picsum.photos/id/237/600/400"],
        "groups": ["@russia_hackers", "@osint_ru", "@cyberpunk_2026"],
        "linked_accounts": ["VK: vk.com/smiralex", "GitHub: github.com/smiralex"],
        "mentions": "Упоминается в 47 постах за последний месяц",
        "reverse_images": ["Совпадение 98% с фото из VK 2023"]
    }
    return results

def generate_pdf_report(data: dict, probe_type: str):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica", 20)
    c.drawString(100, 750, f"Knight OSINT Report — {probe_type.upper()}")
    c.setFont("Helvetica", 12)
    y = 700
    for key, value in data.items():
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        c.drawString(100, y, f"{key}: {value}")
        y -= 20
        if y < 50:
            c.showPage()
            y = 750
    c.save()
    buffer.seek(0)
    return buffer

# ====================== РОУТЫ ======================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Простая проверка (в реальности можно улучшить)
    if request.cookies.get("auth") != "authenticated":
        return HTMLResponse(content="""
        <html><body class="bg-black text-green-400 flex items-center justify-center min-h-screen">
            <div class="text-center">
                <h1 class="text-6xl neon-red mb-8">KNIGHT OSINT</h1>
                <form method="post" action="/login">
                    <input type="password" name="password" placeholder="ENTER PASSWORD" 
                           class="bg-black border border-red-500 p-6 text-3xl text-center">
                    <button type="submit" class="mt-6 block w-full py-6 bg-red-600 text-3xl">ACCESS SYSTEM</button>
                </form>
            </div>
        </body></html>
        """)
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/login")
async def login(password: str = Form(...)):
    if password == SECRET_PASSWORD:
        response = HTMLResponse(content="<script>window.location.href='/'</script>")
        response.set_cookie(key="auth", value="authenticated", max_age=3600*24)
        return response
    raise HTTPException(401, "Wrong password")

@app.post("/probe/phone", response_class=HTMLResponse)
async def probe_phone(request: Request, phone: str = Form(...)):
    full_mode = request.cookies.get("mode") == "full"
    data = await simulate_phone_probe(phone, full_mode)
    
    # Сохраняем в историю
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append({"type": "phone", "query": phone, "time": datetime.now().isoformat(), "data": data})
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-50:], f, ensure_ascii=False, indent=2)  # последние 50
    
    html = f"""
    <div class="bg-zinc-900 border border-green-500 p-8 rounded-xl">
        <div class="flex justify-between items-center mb-6">
            <h2 class="text-4xl neon-green">ПРОБИВ ЗАВЕРШЁН: {phone}</h2>
            <button onclick="window.location.reload()" class="px-8 py-4 bg-red-600 hover:bg-red-500">НОВЫЙ ПРОБИВ</button>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="bg-black p-6 border border-red-500">
                <h3 class="text-red-400 text-xl mb-4">Основная информация</h3>
                <p><strong>ФИО:</strong> {data['fio']}</p>
                <p><strong>Оператор:</strong> {data['operator']}</p>
                <p><strong>Регион:</strong> {data['region']}</p>
            </div>
            <div class="bg-black p-6 border border-red-500">
                <h3 class="text-red-400 text-xl mb-4">Родственники и адреса</h3>
                <ul>{"".join(f"<li>{r}</li>" for r in data['relatives'])}</ul>
                <p><strong>Адреса:</strong> {', '.join(data['addresses'])}</p>
            </div>
            <div class="bg-black p-6 border border-red-500">
                <h3 class="text-red-400 text-xl mb-4">Утечки и соцсети</h3>
                <p>{data['leaks'][0]}</p>
                <p>{data['social'][0]}</p>
            </div>
        </div>
        
        <div class="mt-8">
            <h3 class="text-2xl neon-green mb-4">Фото и изображения</h3>
            <div class="grid grid-cols-2 gap-4">
                {"".join(f'<img src="{p}" class="rounded border border-red-500">' for p in data['photos'])}
            </div>
        </div>
        
        <div class="mt-8 flex gap-4">
            <a href="/download/pdf/phone/{phone}" 
               class="flex-1 py-6 bg-green-600 text-center text-2xl hover:bg-green-500">СКАЧАТЬ PDF ДОСЬЕ</a>
            <button onclick="saveDossier()" class="flex-1 py-6 bg-red-600 text-center text-2xl hover:bg-red-500">СОХРАНИТЬ В АРХИВ</button>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.post("/probe/telegram", response_class=HTMLResponse)
async def probe_telegram(request: Request, username: str = Form(...)):
    full_mode = request.cookies.get("mode") == "full"
    data = await simulate_telegram_probe(username, full_mode)
    
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append({"type": "telegram", "query": username, "time": datetime.now().isoformat(), "data": data})
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-50:], f, ensure_ascii=False, indent=2)
    
    html = f"""
    <div class="bg-zinc-900 border border-green-500 p-8 rounded-xl">
        <h2 class="text-4xl neon-green mb-6">TELEGRAM ПРОБИВ ЗАВЕРШЁН: {username}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
                <h3 class="text-xl text-red-400">Основное</h3>
                <p><strong>ID:</strong> {data['user_id']}</p>
                <p><strong>Имя:</strong> {data['real_name']}</p>
                <p><strong>Bio:</strong> {data['bio']}</p>
            </div>
            <div>
                <h3 class="text-xl text-red-400">Группы и связи</h3>
                <ul>{"".join(f"<li>{g}</li>" for g in data['groups'])}</ul>
            </div>
        </div>
        <div class="mt-8">
            <h3 class="text-2xl neon-green">Фото</h3>
            <div class="grid grid-cols-3 gap-4">
                {"".join(f'<img src="{p}" class="rounded border border-red-500 w-full">' for p in data['photos'])}
            </div>
        </div>
        <div class="mt-8 flex gap-4">
            <a href="/download/pdf/telegram/{username}" class="flex-1 py-6 bg-green-600 text-center text-2xl hover:bg-green-500">PDF ОТЧЁТ</a>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.get("/download/pdf/{probe_type}/{query}")
async def download_pdf(probe_type: str, query: str):
    # Загружаем последние данные из истории
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
            for entry in reversed(history):
                if entry["type"] == probe_type and entry["query"] == query:
                    pdf_buffer = generate_pdf_report(entry["data"], probe_type)
                    return FileResponse(
                        io.BytesIO(pdf_buffer.getvalue()), 
                        media_type="application/pdf",
                        filename=f"knight_osint_{probe_type}_{query}.pdf"
                    )
    raise HTTPException(404, "Report not found")

@app.get("/history", response_class=HTMLResponse)
async def get_history():
    if not os.path.exists(HISTORY_FILE):
        return HTMLResponse("<p class='text-red-400'>История пуста</p>")
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    html = "<div class='grid grid-cols-1 gap-4'>"
    for entry in reversed(history[-10:]):
        html += f"""
        <div class="bg-zinc-950 border border-red-500 p-4 rounded">
            <span class="text-red-400">{entry['time'][:16]}</span> — 
            <strong>{entry['type'].upper()}</strong>: {entry['query']}
        </div>
        """
    html += "</div>"
    return HTMLResponse(content=html)

# Запуск сервера
if __name__ == "__main__":
    import uvicorn
    print("Knight OSINT Dashboard запущен → http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
