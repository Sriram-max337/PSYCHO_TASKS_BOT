from fastapi import FastAPI, HTTPException, Depends, Request 
from dotenv import load_dotenv 
import requests 
from pydantic import BaseModel 
import uvicorn 
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date 
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

def send_with_buttons(text, chat_id, task_id): 
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" 
    payload = { 
        "chat_id": chat_id, 
        "text": text, 
        "reply_markup": { 
            "inline_keyboard": [[{ 
                "text": "✅Done", 
                "callback_data": f"done_{task_id}" 
            }]] 
        } 
    } 
    requests.post(url, json=payload)  

@app.post("/telegram-webhook") 
async def telegram_webhook(request: Request, db: Session = Depends(get_db)): 
    data = await request.json()  # Fixed: Called only once
    
    if "callback_query" in data: 
        callback_data = data["callback_query"]["data"] 
        chat_id = data["callback_query"]["message"]["chat"]["id"]  # Fixed: Extracted missing chat_id
        
        if callback_data.startswith("done_"):
            task_id = int(callback_data.replace("done_", "")) 
            task = db.query(Task).filter(Task.task_id == task_id).first() 
            
            if task and not task.status: 
                task.status = True 
                task.finished_on = date.today() 
                db.commit() 
                send_telegram_msg(f"Marked done : {task.task_id}", chat_id) 
        
        
        callback_query_id = data["callback_query"]["id"]
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_query_id})
        return {"ok": True} 

    
    if "message" in data and "text" in data["message"]:
        message_text = data["message"]["text"] 
        chat_id = data["message"]["chat"]["id"] 

        if message_text.startswith("/add"): 
            task_text = message_text.replace("/add", "").strip() 
            if not task_text:
                send_telegram_msg("Please provide a task description. Example: /add Buy milk", chat_id)
                return {"ok": True}
            
            new_task = Task(task=task_text) 
            db.add(new_task) 
            db.commit() 
            db.refresh(new_task) 
            
            
            send_with_buttons(f"Added: {task_text}", chat_id, new_task.task_id) 

        elif message_text.startswith("/list"): 
            tasks = db.query(Task).filter(Task.status == False).all() 
            task_list = "\n".join([f"{t.task_id} : {t.task}" for t in tasks]) or "No Pending Tasks" 
            send_telegram_msg(task_list, chat_id) 

        elif message_text.startswith("/mark_done"): 
            try:
                task_id = int(message_text.replace("/mark_done", "").strip()) 
                task = db.query(Task).filter(Task.task_id == task_id).first() 
                if task: 
                    task.status = True 
                    task.finished_on = date.today()  # Fixed: spelling typo
                    db.commit() 
                    send_telegram_msg(f"Marked done : {task_id}", chat_id) 
                else:
                    send_telegram_msg("Task not found.", chat_id)
            except ValueError:
                send_telegram_msg("Please provide a valid numeric Task ID.", chat_id)

    return {"ok": True} 

if __name__ == "__main__": 
    uvicorn.run("main:app", reload=True)
