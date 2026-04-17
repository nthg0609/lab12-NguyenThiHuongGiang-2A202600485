from fastapi import FastAPI
from .config import settings

app = FastAPI(title=settings.app_name)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/readiness")
def readiness_check():
    return {"status": "ready"}

@app.get("/answer")
def answer_question(question: str):
    # Placeholder logic for answering a question
    return {"question": question, "answer": "This is a placeholder answer."}