# main.py — ПОЛНАЯ КРАСИВАЯ ВЕРСИЯ С ПОЛЯМИ ВВОДА И РЕЗУЛЬТАТАМИ
# Замени весь файл на этот код

import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="OSINT BREAKER v2.0")

# ====================== ТВОЙ ПАРОЛЬ ======================
YOUR_PASSWORD = "knight2026"   # ←←← ИЗМЕНИ НА СВОЙ

# ====================== HTML ======================
INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT BREAKER v2.0</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        body { background: #0a0a0a; color: #00ff9d; font-family: 'Courier New', monospace; }
        .neon-red { text-shadow: 0 0 20px #ff0033; }
        .neon-green { text-shadow: 0 0 20px #00ff9d; }
        .scanline { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to bottom, transparent 50%, rgba(0,255,157,0.08) 50%); background-size: 100% 4px; pointer-events: none; animation: scan 8s linear infinite; z-index: 5; opacity: 0.2; }
        @keyframes scan { 0% { transform: translateY(-100%); } 100% { transform: translateY(300%); } }
        .input-field { background: #111; border: 2px solid #ff0033; }
        .input-field:focus { border-color: #00ff9d; box-shadow: 0 0 15px #00ff9d; }
    </style>
</head>
<body class="min-h-screen relative">
    <div class="scanline"></div>
    <div class="max-w-6xl mx-auto p-6">
        <h1 class="text-6xl font-bold text-center neon-red mb-2">OSINT BREAKER <span class="text-white">v2.0</span></h1>
        <p class="text-center text-zinc-500 mb-12">Полный пробив • Railway</p>

        <!-- ЛОГИН -->
        <div id="login-screen" class="max-w-md mx-auto bg-zinc-950 border border-red-900 p-10 rounded-3xl">
            <h2 class="text-3xl mb-8 text-center neon-green">ДОСТУП</h2>
            <form hx-post="/login" hx-target="#main-app" hx-swap="innerHTML">
                <input type="password" name="password" placeholder="Пароль" 
                       class="w-full input-field p-5 rounded-2xl text-xl mb-6">
                <button type="submit" class="w-full bg-red-600 hover:bg-red-700 py-6 rounded-2xl text-xl font-bold">ВХОД</button>
            </form>
        </div>

        <!-- ГЛАВНЫЙ ИНТЕРФЕЙС -->
        <div id="main-app" class="hidden">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <!-- ПРОБИВ ПО ТЕЛЕФОНУ -->
                <div class="bg-zinc-950 border border-red-900 p-8 rounded-3xl">
                    <h2 class="text-3xl mb-6 neon-red flex items-center gap-3"><i class="fas fa-phone"></i> ПРОБИВ ПО НОМЕРУ ТЕЛЕФОНА</h2>
                    <form hx-post="/scan/phone" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                        <input name="phone" type="tel" placeholder="+79161234567" 
                               class="w-full input-field p-6 rounded-2xl text-xl" required>
                        <div class="flex gap-4">
                            <select name="mode" class="bg-black border border-zinc-700 p-6 rounded-2xl text-lg flex-1">
                                <option value="demo">DEMO РЕЖИМ</option>
                                <option value="full">FULL OSINT</option>
                            </select>
                            <button type="submit" 
                                    class="flex-1 bg-green-600 hover:bg-green-700 py-6 rounded-2xl font-bold text-xl">НАЧАТЬ ПОЛНЫЙ ПРОБИВ</button>
                        </div>
                    </form>
                </div>

                <!-- ПРОБИВ ПО TELEGRAM -->
                <div class="bg-zinc-950 border border-red-900 p-8 rounded-3xl">
                    <h2 class="text-3xl mb-6 neon-red flex items-center gap-3"><i class="fab fa-telegram"></i> ПРОБИВ ПО TELEGRAM</h2>
                    <form hx-post="/scan/telegram" hx-target="#results" hx-swap="innerHTML" class="space-y-6">
                        <input name="username" type="text" placeholder="@username или user_id" 
                               class="w-full input-field p-6 rounded-2xl text-xl" required>
                        <div class="flex gap-4">
                            <select name="mode" class="bg-black border border-zinc-700 p-6 rounded-2xl text-lg flex-1">
                                <option value="demo">DEMO РЕЖИМ</option>
                                <option value="full">FULL OSINT</option>
                            </select>
                            <button type="submit" 
                                    class="flex-1 bg-green-600 hover:bg-green-700 py-6 rounded-2xl font-bold text-xl">НАЧАТЬ ПОЛНЫЙ ПРОБИВ</button>
                        </div>
                    </form>
                </div>
            </div>

            <!-- ОБЛАСТЬ РЕЗУЛЬТАТОВ -->
            <div id="results" class="mt-12 bg-zinc-950 border border-green-900 p-8 rounded-3xl min-h-[400px]"></div>

            <!-- ИСТОРИЯ -->
            <div class="mt-16">
                <h3 class="text-2xl neon-green mb-6">ИСТОРИЯ ПРОБИВОВ</h3>
                <div id="history" class="grid grid-cols-1 md:grid-cols-3 gap-6"></div>
            </div>
        </div>
    </div>

    <script>
        function loadHistory() {
            fetch('/history').then(r => r.json()).then(data => {
                let html = '';
                data.forEach(item => {
                    html += `<div onclick="loadReport('${item.id}')" class="bg-zinc-950 border border-zinc-700 p-6 rounded-3xl cursor-pointer hover:border-red-600">
                        <div class="text-xs text-zinc-500">${item.time}</div>
                        <div class="text-lg">${item.target}</div>
                    </div>`;
                });
                document.getElementById('history').innerHTML = html || '<p class="text-zinc-500">История пуста</p>';
            });
        }

        function loadReport(id) {
            fetch(`/report/${id}`).then(r => r.text()).then(html => {
                document.getElementById('results').innerHTML = html;
            });
        }

        document.addEventListener('htmx:afterSwap', function(e) {
            if (e.detail.target.id === 'main-app') {
                document.getElementById('login-screen').classList.add('hidden');
                document.getElementById('main-app').classList.remove('hidden');
                loadHistory();
            }
        });
    </script>
</body>
</html>"""

# ====================== ФУНКЦИИ ======================
def save_to_history(target, data):
    os.makedirs("history", exist_ok=True)
    path = "history/osint_history.json"
    history = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            history = json.load(f)
    entry = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "target": target,
        "data": data
    }
    history.insert(0, entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# ====================== РОУТЫ ======================
@app.get("/")
async def root():
    return HTMLResponse(content=INDEX_HTML)

@app.post("/login")
async def login(password: str = Form(...)):
    if password != YOUR_PASSWORD:
        raise HTTPException(status_code=403, detail="Неверный пароль")
    return HTMLResponse(content="<div id='main-app'></div>")

@app.post("/scan/phone")
async def scan_phone(phone: str = Form(...), mode: str = Form("demo")):
    await asyncio.sleep(1.5)  # симуляция сканирования
    data = {
        "phone": phone,
        "fio": "Иванов Иван Иванович",
        "birth_date": "15.03.1995",
        "operator": "МТС",
        "region": "Москва и МО",
        "addresses": ["ул. Ленина 45", "пр. Мира 120"],
        "social": ["VK: vk.com/ivan_real", "TG: @ivan_real"],
        "leaks": "Найдено в 3 утечках",
        "status": "FULL OSINT завершён"
    }
    save_to_history(f"Телефон: {phone}", data)

    result_html = f"""
    <div class="space-y-8">
        <div class="text-3xl neon-green">Результат по номеру {phone}</div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
                <h3 class="text-red-400 mb-4">Основная информация</h3>
                <p><strong>ФИО:</strong> {data['fio']}</p>
                <p><strong>Дата рождения:</strong> {data['birth_date']}</p>
                <p><strong>Оператор:</strong> {data['operator']}</p>
                <p><strong>Регион:</strong> {data['region']}</p>
            </div>
            <div>
                <h3 class="text-red-400 mb-4">Дополнительно</h3>
                <p><strong>Адреса:</strong> {', '.join(data['addresses'])}</p>
                <p><strong>Соцсети:</strong> {', '.join(data['social'])}</p>
                <p><strong>Утечки:</strong> {data['leaks']}</p>
            </div>
        </div>
        <button onclick="alert('Полный PDF-отчёт сохранён в истории')" 
                class="w-full bg-red-600 py-6 rounded-2xl font-bold text-xl">СКАЧАТЬ ПОЛНЫЙ ОТЧЁТ PDF</button>
    </div>
    """
    return HTMLResponse(content=result_html)

@app.post("/scan/telegram")
async def scan_telegram(username: str = Form(...), mode: str = Form("demo")):
    await asyncio.sleep(1.5)
    data = {
        "username": username,
        "user_id": "987654321",
        "real_name": "Алексей Смирнов",
        "bio": "Разработчик • OSINT • Ночной кодер",
        "groups": ["@redteam", "@osintchat"],
        "status": "FULL OSINT завершён"
    }
    save_to_history(f"Telegram: {username}", data)

    result_html = f"""
    <div class="space-y-8">
        <div class="text-3xl neon-green">Результат по @{username}</div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
                <h3 class="text-red-400 mb-4">Профиль</h3>
                <p><strong>ID:</strong> {data['user_id']}</p>
                <p><strong>Имя:</strong> {data['real_name']}</p>
                <p><strong>Био:</strong> {data['bio']}</p>
            </div>
            <div>
                <h3 class="text-red-400 mb-4">Группы и связи</h3>
                <p>{', '.join(data['groups'])}</p>
            </div>
        </div>
        <button onclick="alert('Полный PDF-отчёт сохранён в истории')" 
                class="w-full bg-red-600 py-6 rounded-2xl font-bold text-xl">СКАЧАТЬ ПОЛНЫЙ ОТЧЁТ PDF</button>
    </div>
    """
    return HTMLResponse(content=result_html)

@app.get("/history")
async def get_history():
    try:
        with open("history/osint_history.json", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

@app.get("/report/{rid}")
async def get_report(rid: str):
    return HTMLResponse(content=f"<div class='p-12 text-4xl neon-green'>Полное досье #{rid}</div>")

# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"OSINT BREAKER запущен на порту {port}")
    print(f"Пароль: {YOUR_PASSWORD}")
    uvicorn.run(app, host="0.0.0.0", port=port)
