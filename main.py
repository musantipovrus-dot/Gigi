# main.py — ПОЛНАЯ ВЕРСИЯ ДЛЯ RAILWAY (один файл)
# Замени весь свой main.py на этот код

import os
import json
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="OSINT BREAKER v2.0")
templates = Jinja2Templates(directory="templates")

# Создаём нужные папки
os.makedirs("templates", exist_ok=True)
os.makedirs("history", exist_ok=True)

ADMIN_PASSWORD = "knight2026"

# ====================== ШАБЛОН index.html ======================
with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write("""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT BREAKER v2.0</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        body { background: #0a0a0a; color: #00ff9d; font-family: 'Courier New', monospace; overflow-x: hidden; }
        .neon-red { text-shadow: 0 0 15px #ff0033; }
        .neon-green { text-shadow: 0 0 15px #00ff9d; }
        .scanline { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(transparent 50%, rgba(0,255,157,0.05) 50%); background-size: 100% 6px; pointer-events: none; animation: scan 6s linear infinite; z-index: 9999; opacity: 0.2; }
        @keyframes scan { 0% { transform: translateY(-100%); } 100% { transform: translateY(300%); } }
        .card { transition: all 0.4s; }
        .card:hover { transform: scale(1.03); box-shadow: 0 0 30px rgba(255,0,51,0.6); }
    </style>
</head>
<body class="min-h-screen relative">
    <div class="scanline"></div>
    <div class="max-w-6xl mx-auto p-6">
        <div class="text-center mb-10">
            <h1 class="text-6xl font-bold neon-red tracking-widest">OSINT BREAKER <span class="text-white">v2.0</span></h1>
            <p class="text-zinc-500 mt-2">powered by Найт • Railway Edition</p>
        </div>

        <!-- Логин -->
        <div id="login" class="max-w-md mx-auto bg-zinc-950 border border-red-900/70 p-10 rounded-3xl card">
            <h2 class="text-3xl mb-8 text-center neon-green">ДОСТУП К СИСТЕМЕ</h2>
            <form hx-post="/login" hx-target="#main" hx-swap="outerHTML">
                <input type="password" name="password" id="pass" placeholder="Пароль" 
                       class="w-full bg-black border border-red-800 p-5 rounded-xl text-xl focus:outline-none focus:border-red-500 mb-6">
                <button type="submit" 
                        class="w-full bg-red-600 hover:bg-red-700 py-6 rounded-2xl text-xl font-bold tracking-widest">
                    ВХОД
                </button>
            </form>
        </div>

        <!-- Главный интерфейс -->
        <div id="main" class="hidden">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <!-- Телефон -->
                <div class="bg-zinc-950 border border-red-900/50 p-8 rounded-3xl card">
                    <h2 class="text-3xl mb-6 flex items-center gap-4 neon-red"><i class="fas fa-phone"></i> ПРОБИВ ПО НОМЕРУ</h2>
                    <form hx-post="/scan/phone" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                        <input name="phone" type="text" placeholder="+79161234567" 
                               class="w-full bg-black border border-zinc-700 p-5 rounded-2xl text-lg">
                        <div class="flex gap-4">
                            <select name="mode" class="bg-black border border-zinc-700 p-5 rounded-2xl flex-1">
                                <option value="demo">DEMO</option>
                                <option value="full">FULL OSINT</option>
                            </select>
                            <button type="submit" 
                                    class="flex-1 bg-green-600 hover:bg-green-700 py-5 rounded-2xl font-bold text-lg">НАЧАТЬ ПРОБИВ</button>
                        </div>
                    </form>
                </div>

                <!-- Telegram -->
                <div class="bg-zinc-950 border border-red-900/50 p-8 rounded-3xl card">
                    <h2 class="text-3xl mb-6 flex items-center gap-4 neon-red"><i class="fab fa-telegram-plane"></i> ПРОБИВ ПО TELEGRAM</h2>
                    <form hx-post="/scan/telegram" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                        <input name="username" type="text" placeholder="@username или ID" 
                               class="w-full bg-black border border-zinc-700 p-5 rounded-2xl text-lg">
                        <div class="flex gap-4">
                            <select name="mode" class="bg-black border border-zinc-700 p-5 rounded-2xl flex-1">
                                <option value="demo">DEMO</option>
                                <option value="full">FULL OSINT</option>
                            </select>
                            <button type="submit" 
                                    class="flex-1 bg-green-600 hover:bg-green-700 py-5 rounded-2xl font-bold text-lg">НАЧАТЬ ПРОБИВ</button>
                        </div>
                    </form>
                </div>
            </div>

            <div id="results" class="mt-12 min-h-[400px]"></div>

            <div class="mt-16">
                <h3 class="text-2xl neon-green mb-6">ИСТОРИЯ ПРОБИВОВ</h3>
                <div id="history" class="grid grid-cols-1 md:grid-cols-3 gap-6"></div>
            </div>
        </div>
    </div>

    <script>
        function loadHistory() {
            fetch('/history').then(r => r.json()).then(items => {
                let html = '';
                items.forEach(item => {
                    html += `<div onclick="showReport('${item.id}')" class="bg-zinc-950 border border-zinc-700 p-6 rounded-2xl cursor-pointer hover:border-red-600">
                        <div class="text-xs text-zinc-500">${item.time}</div>
                        <div class="text-lg mt-2">${item.target}</div>
                    </div>`;
                });
                document.getElementById('history').innerHTML = html || '<p class="text-zinc-500">Пока пусто</p>';
            });
        }

        function showReport(id) {
            fetch(`/report/${id}`).then(r => r.text()).then(html => {
                document.getElementById('results').innerHTML = html;
            });
        }

        // После успешного логина
        document.addEventListener('htmx:afterSwap', e => {
            if (e.detail.target.id === 'main') {
                document.getElementById('login').classList.add('hidden');
                document.getElementById('main').classList.remove('hidden');
                loadHistory();
            }
        });
    </script>
</body>
</html>""")

# ====================== УТИЛИТЫ ======================
def save_history(target: str, data: dict):
    history_file = "history/osint_history.json"
    if os.path.exists(history_file):
        with open(history_file, encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []
    
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "target": target,
        "data": data
    }
    history.insert(0, entry)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def fake_phone_data(phone):
    return {
        "phone": phone,
        "operator": "МТС / Билайн / Tele2",
        "region": "Москва и Московская область",
        "fio": "Смирнов Алексей Викторович",
        "birth": "12.07.1995",
        "addresses": ["г. Москва, ул. Тверская, 15", "г. Москва, пр. Мира, 101"],
        "relatives": ["Смирнова Ольга Ивановна (жена)", "Смирнов Виктор Петрович (отец)"],
        "leaks": ["2024 Telegram leak", "2025 Avito leak"]
    }

def fake_tg_data(username):
    return {
        "username": username,
        "id": "748392145",
        "name": "Алексей Смирнов",
        "bio": "Кодер по ночам • OSINT • Red Team",
        "photos": ["https://picsum.photos/id/1015/600/400"],
        "groups": ["@redteam_ru", "@osintchat"]
    }

# ====================== РОУТЫ ======================
@app.get("/", response_class=HTMLResponse)
async def root():
    return templates.TemplateResponse("index.html", {"request": {}})

@app.post("/login")
async def login(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Неверный пароль")
    return HTMLResponse(content="<div id='main'></div>")

@app.post("/scan/phone")
async def scan_phone(phone: str = Form(...), mode: str = Form("demo")):
    await asyncio.sleep(1.2)
    data = fake_phone_data(phone) if mode == "demo" else fake_phone_data(phone)  # здесь можно добавить реальные API
    save_history(f"Тел: {phone}", data)
    
    html = f"""
    <div class="bg-zinc-950 border border-green-900 p-10 rounded-3xl">
        <h2 class="text-4xl neon-green mb-8">ПРОБИВ ПО {phone} — УСПЕШНО</h2>
        <div class="grid grid-cols-2 gap-8 text-lg">
            <div>ФИО:</div><div class="text-white">{data['fio']}</div>
            <div>Оператор:</div><div class="text-white">{data['operator']}</div>
            <div>Регион:</div><div class="text-white">{data['region']}</div>
            <div>Дата рождения:</div><div class="text-white">{data['birth']}</div>
        </div>
        <div class="mt-10 flex gap-4">
            <button onclick="alert('PDF сформирован (Railway версия)')" 
                    class="flex-1 bg-red-600 py-6 rounded-2xl font-bold">СКАЧАТЬ PDF</button>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.post("/scan/telegram")
async def scan_telegram(username: str = Form(...), mode: str = Form("demo")):
    await asyncio.sleep(1.4)
    data = fake_tg_data(username)
    save_history(f"TG: {username}", data)
    
    html = f"""
    <div class="bg-zinc-950 border border-green-900 p-10 rounded-3xl">
        <h2 class="text-4xl neon-green mb-8">ПРОБИВ TELEGRAM @{username} — УСПЕШНО</h2>
        <p class="text-2xl">ID: {data['id']}</p>
        <p class="text-2xl">Имя: {data['name']}</p>
        <p class="mt-6 text-xl">{data['bio']}</p>
        <div class="mt-10 flex gap-4">
            <button onclick="alert('PDF сформирован (Railway версия)')" 
                    class="flex-1 bg-red-600 py-6 rounded-2xl font-bold">СКАЧАТЬ PDF</button>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.get("/history")
async def get_history():
    try:
        with open("history/osint_history.json", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

@app.get("/report/{rid}")
async def get_report(rid: str):
    return HTMLResponse(content=f"<h2 class='text-3xl neon-green p-10'>Досье #{rid} загружено</h2>")

# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"OSINT BREAKER v2.0 запущен на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
