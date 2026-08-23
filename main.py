from fastapi import FastAPI, Depends, Request
from dotenv import load_dotenv
import requests
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date
from sqlalchemy.orm import Session, declarative_base, sessionmaker
import os
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv(override=True)

app = FastAPI(title="PSYCHO_TASKS_BOT")
schedular = BackgroundScheduler()

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"
    task_id = Column(Integer, primary_key=True)
    task = Column(String)
    created_on = Column(Date, default=date.today)
    dead_line = Column(Date)
    status = Column(Boolean, default=False)
    finished_on = Column(Date)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_telegram_msg(text, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def send_main_menu(chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "What do you wanna do?",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "➕ Add Task", "callback_data": "menu_add"}],
                [{"text": "📋 List Tasks", "callback_data": "menu_list"}],
                [{"text": "✅ Mark Done", "callback_data": "menu_done"}]
            ]
        }
    }
    requests.post(url, json=payload)

def send_task_buttons(chat_id, tasks, prefix):
    buttons = [[{"text": t.task, "callback_data": f"{prefix}_{t.task_id}"}] for t in tasks]
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "Tap a task:",
        "reply_markup": {"inline_keyboard": buttons}
    }
    requests.post(url, json=payload)

user_states = {}

@app.get("/health")
def health():
    return {"msg":"ok"}

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    
    if "callback_query" in data:
        callback_data = data["callback_query"]["data"]
        chat_id = data["callback_query"]["message"]["chat"]["id"]

        if callback_data == "menu_add":
            user_states[chat_id] = "waiting_for_task"
            send_telegram_msg("Send task text and deadline day", chat_id)

        elif callback_data == "menu_list":
            tasks = db.query(Task).filter(Task.status == False).all()
            if not tasks:
                send_telegram_msg("No pending tasks 🎉", chat_id)
                send_main_menu(chat_id)
            else:
                task_list = "\n".join([f"{t.task} (due {t.dead_line})" if t.dead_line else f"{t.task} (no deadline mentioned)"
                                       for t in tasks])
                send_telegram_msg(task_list, chat_id)
                send_main_menu(chat_id)

        elif callback_data == "menu_done":
            tasks = db.query(Task).filter(Task.status == False).all()
            if not tasks:
                send_telegram_msg("No pending tasks 🎉", chat_id)
                send_main_menu(chat_id)
            else:
                send_task_buttons(chat_id, tasks, prefix="done")
                

        elif callback_data.startswith("done_"):
            task_id = int(callback_data.replace("done_", ""))
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if task:
                task.status = True
                task.finished_on = date.today()
                db.commit()
                send_telegram_msg(f"Marked done: {task.task}", chat_id)
                send_main_menu(chat_id)

        return {"ok": True}

    
    message_text = data["message"]["text"]
    chat_id = data["message"]["chat"]["id"]

    if message_text == "/start":
        send_main_menu(chat_id)

    elif user_states.get(chat_id) == "waiting_for_task":
        parts = message_text.split("/")
        task_text = parts[0].strip()
        deadline = None
        if len(parts) > 1:
            try:
                day = int(parts[1].strip())
                today = date.today()
                deadline = date(today.year, today.month, day)

                if deadline < today:
                    if today.month == 12:
                        deadline = date(today.year + 1, day)
                    else:
                        deadline = date(today.year, today.month+1, day)
            except ValueError:
                send_telegram_msg("Bad day format, just send a no. Task saved without deadline", chat_id)
        new_task = Task(task=task_text, dead_line=deadline)
        db.add(new_task)
        db.commit()
        user_states[chat_id] = None
        send_telegram_msg(f"Added: {task_text}" + (f" (due {deadline})" if deadline else ""), chat_id)
        send_main_menu(chat_id)

    return {"ok": True}


@app.get("/daily-reminder")
def daily_reminder(db : Session = Depends(get_db)):
    pending = db.query(Task).filter(Task.status == False).all()

    if pending:
        pending_tasks_list = f"Pending Tasks List as of : {date.today()}"+"\n"+"\n".join([f"{t.task}" for t in pending])
        roast = get_roast(pending)
        send_telegram_msg(pending_tasks_list, TELEGRAM_CHAT_ID)
        send_telegram_msg(roast, TELEGRAM_CHAT_ID)
        send_main_menu(TELEGRAM_CHAT_ID)

    return {"pending tasks":len(pending)}

schedular.add_job(daily_reminder, "cron", hour=18, minute=0)
schedular.start()


def get_roast(pending_tasks):
    task_list = ", ".join([t.task for t in pending_tasks])
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization" : f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type":"application/json"
        },
        json={
            "model" : "openrouter/free",
            "messages":[
                {"role":"system", "content":"""You're a savage, sarcastic roast bot. 
                Roast user for having pending tasks.
                Keep it short, funny, brutal. No sugarcoating or sympathy"""
                },
                {"role":"user", "content": f"My pending tasks : {task_list}"}
            ]
        }    
    )
    return response.json()["choices"][0]["message"]["content"]

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)