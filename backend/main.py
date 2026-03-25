from fastapi import FastAPI
from api import uploads

app = FastAPI()

app.include_router(uploads.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
