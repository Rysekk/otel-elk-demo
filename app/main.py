from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def message():
    return {"status": "Bonjour voici le get"}


@app.get("/items/{item_id}")
async def item(item_id):
    return {"status": f"Voici l'items: {item_id}"}
