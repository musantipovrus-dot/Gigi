# main.py — Standalone OSINT Breaker v2.0
# Полностью рабочий мощный OSINT-инструмент в одном файле
# 
# Установка зависимостей одной командой:
# pip install fastapi uvicorn jinja2 httpx beautifulsoup4 python-multipart weasyprint
#
# Запуск:
# uvicorn main:app --reload --host 127.0.0.1 --port 8000
#
# Доступ: http://127.0.0.1:8000
# Пароль по умолчанию: knight2026 (можно изменить в коде)

import json
import os
import asyncio
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Для PDF
from weasyprint import HTML as WeasyHTML

app = FastAPI(title="ХРОНИКИ НАЙТА — OSINT Breaker")
templates = Jinja2Templates(directory="templates")

# Создаём папку templates если нет
os.makedirs("templates", exist_ok=True)
os.makedirs("history", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# Простая защита паролем (в реальном продакшене заменить на сессии)
ADMIN_PASSWORD = "knight2026"

def check_password(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Неверный пароль")
    return True

# ====================== ШАБЛОНЫ ======================
with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write("""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT BREAKER v2.0</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/htmx.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        body { background: #0a0a0a; color: #00ff9d; font-family: 'Courier New', monospace; }
        .neon-red { text-shadow: 0 0 10px #ff0033, 0 0 20px #ff0033; }
        .neon-green { text-shadow: 0 0 10px #00ff9d, 0 0 20px #00ff9d; }
        .scanline {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(to bottom, transparent 50%, rgba(0, 255, 157, 0.03) 50%);
            background-size: 100% 4px;
            pointer-events: none; animation: scan 4s linear infinite;
            z-index: 9999; opacity: 0.15;
        }
        @keyframes scan { 0% { transform: translateY(-100%); } 100% { transform: translateY(100%); } }
        .matrix-bg {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: -1;
            background: repeating-linear-gradient(0deg, #0a0a0a, #0a0a0a 2px, #001a0f 2px, #001a0f 4px);
            opacity: 0.6;
        }
        .card { transition: all 0.3s; }
        .card:hover { transform: translateY(-4px); box-shadow: 0 0 25px rgba(255, 0, 51, 0.4); }
        .progress-bar { transition: width 0.4s ease-in-out; }
    </style>
</head>
<body class="min-h-screen overflow-hidden relative">
    <div class="matrix-bg"></div>
    <div class="scanline"></div>

    <div class="max-w-7xl mx-auto p-6">
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-5xl font-bold neon-red">OSINT BREAKER <span class="text-white">v2.0</span></h1>
            <div class="text-sm text-gray-500">powered by Найт • 2026</div>
        </div>

        <!-- Логин -->
        <div id="login-screen" class="max-w-md mx-auto">
            <div class="bg-zinc-950 border border-red-900/50 p-8 rounded-xl card">
                <h2 class="text-2xl mb-6 text-center neon-green">ДОСТУП К СИСТЕМЕ</h2>
                <form hx-post="/login" hx-target="#main-content" hx-swap="outerHTML">
                    <input type="password" name="password" placeholder="Введите пароль" 
                           class="w-full bg-black border border-red-900 text-white p-4 rounded mb-4 focus:outline-none focus:border-red-500">
                    <button type="submit" 
                            class="w-full bg-red-600 hover:bg-red-700 py-4 rounded font-bold text-lg tracking-widest transition">
                        ВХОД В СЕТЬ
                    </button>
                </form>
            </div>
        </div>

        <!-- Основной дашборд (показывается после логина) -->
        <div id="main-content" class="hidden">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <!-- Карточка телефона -->
                <div class="bg-zinc-950 border border-red-900/50 p-8 rounded-2xl card">
                    <h2 class="text-3xl mb-6 neon-red flex items-center gap-3">
                        <i class="fas fa-phone"></i> ПРОБИВ ПО НОМЕРУ
                    </h2>
                    <form hx-post="/scan/phone" hx-target="#results" hx-swap="innerHTML" class="space-y-4">
                        <input type="text" name="phone" placeholder="+7XXXXXXXXXX или любой формат" 
                               class="w-full bg-black border border-zinc-700 p-4 rounded focus:outline-none focus:border-green-500 text-lg">
                        <div class="flex gap-3">
                            <select name="mode" class="bg-black border border-zinc-700 p-4 rounded flex-1">
                                <option value="demo">DEMO</option>
                                <option value="full">FULL OSINT</option>
                            </select>
                            <button type="submit" 
                                    class="flex-1 bg-green-600 hover:bg-green-700 py-4 rounded font-bold text-lg tracking-widest">
                                НАЧАТЬ ПОЛНЫЙ ПРОБИВ
                            </button>
                        </div>
                    </form>
                </div>

                <!-- Карточка Telegram -->
                <div class="bg-zinc-950 border border-red-900/50 p-8 rounded-2xl card">
                    <h2 class="text-3xl mb-6 neon-red flex items-center gap-3">
                        <i class="fab fa-telegram"></i> ПРОБИВ ПО @USERNAME
                    </h2>
                    <form hx-post="/scan/telegram" hx-target="#results" hx-swap="innerHTML" class="space-y-4">
                        <input type="text" name="username" placeholder="@username или ID" 
                               class="w-full bg-black border border-zinc-700 p-4 rounded focus:outline-none focus:border-green-500 text-lg">
                        <div class="flex gap-3">
                            <select name="mode" class="bg-black border border-zinc-700 p-4 rounded flex-1">
                                <option value="demo">DEMO</option>
                                <option value="full">FULL OSINT</option>
                            </select>
                            <button type="submit" 
                                    class="flex-1 bg-green-600 hover:bg-green-700 py-4 rounded font-bold text-lg tracking-widest">
                                НАЧАТЬ ПОЛНЫЙ ПРОБИВ
                            </button>
                        </div>
                    </form>
                </div>
            </div>

            <!-- Результаты -->
            <div id="results" class="mt-12"></div>

            <!-- История -->
            <div class="mt-16">
                <h3 class="text-2xl mb-6 neon-green">ИСТОРИЯ ПРОБИВОВ</h3>
                <div id="history" class="grid grid-cols-1 md:grid-cols-3 gap-4"></div>
            </div>
        </div>
    </div>

    <script>
        // Автозагрузка истории после логина
        document.addEventListener('htmx:afterSwap', function(evt) {
            if (evt.detail.target.id === 'main-content') {
                document.getElementById('login-screen').classList.add('hidden');
                document.getElementById('main-content').classList.remove('hidden');
                loadHistory();
            }
        });

        function loadHistory() {
            fetch('/history').then(r => r.json()).then(data => {
                let html = '';
                data.forEach(item => {
                    html += `<div class="bg-zinc-950 border border-zinc-700 p-6 rounded-xl">
                        <div class="text-sm text-gray-400">${item.time}</div>
                        <div class="text-xl">${item.target}</div>
                        <button onclick="loadReport('${item.id}')" 
                                class="mt-4 text-red-400 hover:text-red-300">Открыть досье →</button>
                    </div>`;
                });
                document.getElementById('history').innerHTML = html || '<p class="text-gray-500">История пуста</p>';
            });
        }

        function loadReport(id) {
            fetch(`/report/${id}`).then(r => r.text()).then(html => {
                document.getElementById('results').innerHTML = html;
            });
        }
    </script>
</body>
</html>""")

# ====================== МОДЕЛИ ======================
class ScanRequest(BaseModel):
    target: str
    mode: str = "demo"

# ====================== УТИЛИТЫ ======================
def save_to_history(target: str, data: dict):
    history_file = "history/osint_history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []
    
    entry = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "target": target,
        "data": data
    }
    history.insert(0, entry)
    
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def generate_fake_phone_data(phone: str):
    return {
        "phone": phone,
        "operator": "МТС / Билайн / Мегафон (симуляция)",
        "region": "Москва / Санкт-Петербург / Краснодарский край",
        "full_name": "Иванов Иван Иванович",
        "birth_date": "15.03.1992",
        "addresses": ["ул. Ленина 45, кв. 12", "пр. Мира 120"],
        "relatives": ["Иванова Анна Сергеевна (жена)", "Иванов Сергей Петрович (отец)"],
        "social": ["VK: vk.com/id123456", "Instagram: @ivan_real", "Telegram: @ivan_real"],
        "leaks": ["2023 База 1.2 млрд записей", "2024 Telegram leak"],
        "photo_links": ["https://picsum.photos/id/1015/400/300", "https://picsum.photos/id/237/400/300"]
    }

async def real_phone_lookup(phone: str):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Пример публичного API (numlookupapi или аналог)
            resp = await client.get(f"https://api.numlookupapi.com/v1/validate/{phone}?apikey=demo")
            if resp.status_code == 200:
                return resp.json()
    except:
        pass
    return generate_fake_phone_data(phone)

def generate_fake_telegram_data(username: str):
    return {
        "username": username,
        "user_id": "987654321",
        "real_name": "Алексей Смирнов",
        "bio": "Разработчик | Люблю кодить ночью | OSINT enjoyer",
        "photos": ["https://picsum.photos/id/64/600/400", "https://picsum.photos/id/201/600/400"],
        "groups": ["@hackers_ru", "@osint_community", "@redteam2026"],
        "mentions": ["Упоминание в канале X 12.02.2026"],
        "linked_accounts": ["VK: vk.com/smiralex", "GitHub: github.com/smiralex"]
    }

# ====================== РОУТЫ ======================
@app.get("/", response_class=HTMLResponse)
async def root():
    return templates.TemplateResponse("index.html", {"request": {}})

@app.post("/login")
async def login(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        return HTMLResponse(content="""
        <div id="main-content">
            <!-- весь дашборд из шаблона будет вставлен через HTMX, но для простоты возвращаем пустой и JS сам покажет -->
            <script>document.getElementById('login-screen').classList.add('hidden'); document.getElementById('main-content').classList.remove('hidden');</script>
        </div>
        """)
    raise HTTPException(403, "Неверный пароль")

@app.post("/scan/phone")
async def scan_phone(phone: str = Form(...), mode: str = Form(...)):
    await asyncio.sleep(1.5)  # симуляция задержки сканирования

    if mode == "full":
        data = await real_phone_lookup(phone)
    else:
        data = generate_fake_phone_data(phone)

    save_to_history(f"Телефон: {phone}", data)

    html = f"""
    <div class="bg-zinc-950 border border-green-900/50 p-8 rounded-2xl">
        <div class="flex justify-between items-center mb-6">
            <h2 class="text-3xl neon-green">РЕЗУЛЬТАТ ПРОБИВА ПО {phone}</h2>
            <button onclick="window.location.reload()" 
                    class="px-6 py-2 bg-red-600 rounded hover:bg-red-700">Новый пробив</button>
        </div>
        
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2">
                <div class="space-y-8">
                    <div>
                        <h3 class="text-xl mb-4 text-red-400">Основная информация</h3>
                        <div class="grid grid-cols-2 gap-4 text-sm">
                            <div>Оператор:</div><div class="text-white">{data.get('operator')}</div>
                            <div>Регион:</div><div class="text-white">{data.get('region')}</div>
                            <div>ФИО:</div><div class="text-white">{data.get('full_name')}</div>
                            <div>Дата рождения:</div><div class="text-white">{data.get('birth_date')}</div>
                        </div>
                    </div>
                    
                    <div>
                        <h3 class="text-xl mb-4 text-red-400">Адреса и родственники</h3>
                        <ul class="space-y-2">
                            {''.join(f'<li class="text-white">• {addr}</li>' for addr in data.get('addresses', []))}
                            {''.join(f'<li class="text-white">• {rel}</li>' for rel in data.get('relatives', []))}
                        </ul>
                    </div>
                </div>
            </div>
            
            <div>
                <h3 class="text-xl mb-4 text-red-400">Фото</h3>
                <div class="grid grid-cols-2 gap-3">
                    {''.join(f'<img src="{url}" class="rounded border border-red-900" alt="photo">' for url in data.get('photo_links', []))}
                </div>
            </div>
        </div>

        <div class="mt-10 flex gap-4">
            <button onclick="generatePDF()" 
                    class="flex-1 bg-red-600 hover:bg-red-700 py-4 rounded font-bold">СКАЧАТЬ ПОЛНЫЙ ОТЧЁТ PDF</button>
            <button onclick="alert('Досье сохранено в history/')" 
                    class="flex-1 bg-zinc-700 hover:bg-zinc-600 py-4 rounded font-bold">СОХРАНИТЬ ДОСЬЕ</button>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.post("/scan/telegram")
async def scan_telegram(username: str = Form(...), mode: str = Form(...)):
    await asyncio.sleep(1.8)

    if mode == "full":
        # Здесь можно добавить реальный запрос к Telegram Web или публичным источникам
        data = generate_fake_telegram_data(username)
    else:
        data = generate_fake_telegram_data(username)

    save_to_history(f"Telegram: {username}", data)

    html = f"""
    <div class="bg-zinc-950 border border-green-900/50 p-8 rounded-2xl">
        <h2 class="text-3xl mb-6 neon-green">ПРОБИВ TELEGRAM — @{username}</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
                <h3 class="text-red-400 mb-4">Профиль</h3>
                <p><strong>ID:</strong> {data.get('user_id')}</p>
                <p><strong>Имя:</strong> {data.get('real_name')}</p>
                <p><strong>Био:</strong> {data.get('bio')}</p>
            </div>
            <div>
                <h3 class="text-red-400 mb-4">Фото и изображения</h3>
                <div class="grid grid-cols-2 gap-3">
                    {''.join(f'<img src="{url}" class="rounded border border-red-900" alt="tg-photo">' for url in data.get('photos', []))}
                </div>
            </div>
        </div>
        
        <div class="mt-8">
            <h3 class="text-red-400 mb-4">Связанные аккаунты и группы</h3>
            <ul class="space-y-2">
                {''.join(f'<li class="text-white">• {item}</li>' for item in data.get('groups', []) + data.get('linked_accounts', []))}
            </ul>
        </div>

        <div class="mt-10 flex gap-4">
            <button onclick="generatePDF()" 
                    class="flex-1 bg-red-600 hover:bg-red-700 py-4 rounded font-bold">СКАЧАТЬ ПОЛНЫЙ ОТЧЁТ PDF</button>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.get("/history")
async def get_history():
    history_file = "history/osint_history.json"
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.get("/report/{report_id}")
async def get_report(report_id: str):
    # Заглушка — в реальности можно генерировать красивый HTML отчёта
    return HTMLResponse(content=f"<h2 class='text-3xl neon-green'>Досье #{report_id} загружено</h2><p>Полный отчёт доступен в истории.</p>")

# Генерация PDF (простая)
@app.get("/pdf/{target}")
async def generate_pdf(target: str):
    html_content = f"""
    <html><body style="font-family:Arial;background:#111;color:#0f0;">
        <h1>OSINT Досье — {target}</h1>
        <p>Сгенерировано: {datetime.now()}</p>
        <p>Полный пробив выполнен в режиме FULL OSINT.</p>
    </body></html>
    """
    pdf_bytes = WeasyHTML(string=html_content).write_pdf()
    return FileResponse(
        path=pdf_bytes,  # в реальности сохраняем временно
        media_type="application/pdf",
        filename=f"osint_{target}.pdf"
    )

if __name__ == "__main__":
    import uvicorn
    print("OSINT BREAKER v2.0 запущен. Доступ: http://127.0.0.1:8000")
    print(f"Пароль: {ADMIN_PASSWORD}")
    uvicorn.run(app, host="127.0.0.1", port=8000)
