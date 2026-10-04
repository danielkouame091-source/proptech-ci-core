from fastapi import FastAPI

app = FastAPI(title="PropTech CI Core API")

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API PropTech CI Core"}
