from fastapi import FastAPI, HTTPException, Depends, Request
from dotenv import load_dotenv
import requests

app = FastAPI()

@app.post("/telegram-webhook")
async def telegram_webhook(request : Request):
    data = await request.json()
    print(data)
    return {"ok":True}