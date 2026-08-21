from fastapi import FastAPI, HTTPException, Depends, Request
from dotenv import load_dotenv
import requests
from pydantic import BaseModel
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Boolean,Date
from sqlalchemy.orm import Session, declarative_base, sessionmaker
import os
from datetime import date

load_dotenv()
app = FastAPI(title="PSYCHO_TASKS_BOT")

DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Task(Base):
    __tablename__="tasks"
    task_id = Column(Integer, primary_key=True)
    task = Column(String)
    created_on = Column(Date, default=date.today)
    dead_line = Column(Date)
    status = Column(Boolean, default=False)
    finished_on = Column(Date)

class Tasks():
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_telegram_msg(text, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id":chat_id, "text":text}
    requests.post(url, json=payload)

@app.post("/telegram-webhook")
async def telegram_webhook(request : Request, db : Session = Depends(get_db)):
    data = await request.json()

    message_text = data["message"]["text"]
    chat_id = data["message"]["chat"]["id"]

    if message_text.startswith("/add"):
        task_text = message_text.replace("/add","").strip()
        new_task = Task(task=task_text)
        db.add(new_task)
        db.commit()
        send_telegram_msg(f"Added : {task_text}", chat_id)

    elif message_text.startswith("/list"):
        tasks = db.query(Task).filter(Task.status == False).all()
        task_list = "\n".join([f"{t.task_id} : {t.task}" for t in tasks]) or "No Pending Tasks"
        send_telegram_msg(task_list, chat_id)

    elif message_text.startswith("/mark_done"):
        task_id = int(message_text.replace("/mark_done","").strip())
        task = db.query(Task).filter(Task.task_id==task_id).first()
        if task:
            task.status = True
            task.finised_on = date.today()
            db.commit()
            send_telegram_msg(f"Marked done : {task_id}", chat_id)

    return {"ok" : True}

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
