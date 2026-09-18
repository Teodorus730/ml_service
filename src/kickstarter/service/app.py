import time
import uuid

from contextlib import asynccontextmanager

import joblib
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from pydantic import BaseModel, Field
from datetime import datetime

from kickstarter import db
from kickstarter.config import settings


class Features(BaseModel):
    model_config = {"extra": "forbid"}
    
    name: str | None = None
    category: str = Field(min_length=3)
    main_category: str = Field(min_length=3)
    currency: str = Field(min_length=1)
    deadline: datetime
    goal: float = Field(gt=0)
    launched: datetime
    country: str = Field(min_length=1)
    usd_goal_real: float = Field(gt=0)



class Prediction(BaseModel):
    #model_config = {"protected_namespaces": ()}
    score: float
    target: bool
    model_version: str
    request_id: str
    latency_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    bundle = joblib.load(settings.model_path)
    app.state.pipeline = bundle["pipeline"]
    app.state.meta = bundle["metadata"]
    app.state.version = bundle["metadata"]["model_version"]

    db.init()
    yield
    app.state.pipeline = None


app = FastAPI(title="kickstarter-service", version="1.0", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok", "model_version": getattr(app.state, "version", "unknown")}

@app.get("/ready")
def ready():
    if getattr(app.state, "pipeline", "None") is  None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {"status": "ready"}


@app.post("/v1/predict")
def predict(x: Features, request: Request) -> Prediction:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())
    payload = x.model_dump()
    
    for key, value in payload.items():
        if value is None:
            payload[key] = ""
            
    frame = pd.DataFrame([payload]).reindex(columns=app.state.meta["features"])
    score = float(app.state.pipeline.predict_proba(frame)[0, 1])
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    request.state.request_id = request_id
    request.state.log_payload = payload
    request.state.score = score
    request.state.latency = latency_ms

    target = score >= app.state.meta["threshold"]

    return Prediction(
        score=score, 
        target=target, 
        model_version=app.state.version, 
        request_id=request_id, 
        latency_ms=latency_ms
    )
    

# Мидлваря ловит статус ответа и пишет в бд (хз мб неправильно понял задание)
@app.middleware("http")
async def log_predictions_middleware(request: Request, call_next):
    if request.url.path != "/v1/predict" or request.method != "POST":
        return await call_next(request)
    
    response = await call_next(request)    
    http_status = response.status_code

    if hasattr(request.state, "log_payload"):
        bg = BackgroundTasks()
        bg.add_task(
            db.save_prediction,
            request.state.request_id,
            request.state.log_payload,
            request.state.score,
            app.state.version,
            request.state.latency,
            http_status
        )
        await bg()

    return response



