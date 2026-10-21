"""FastAPI Service for Intent Classification on Port 8001."""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status

# Ensure root workspace is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import IntentPredictionRequest, IntentPredictionResponse
from services.intent_service.src.pipeline.train import train_and_persist
from services.intent_service.src.predictor import IntentPredictor

MODEL_PATH = Path(os.getenv("MODEL_PATH", str(ROOT_DIR / "artifacts" / "models" / "intent_model.pkl")))
predictor_instance: IntentPredictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor_instance
    print(f"[intent_service] Checking model artifact: {MODEL_PATH.name}...")
    if not MODEL_PATH.exists():
        print(f"[intent_service] Model not found. Training baseline model now...")
        train_and_persist(MODEL_PATH)
    predictor_instance = IntentPredictor(MODEL_PATH)
    print(f"[intent_service] Model loaded successfully. Service ready.")
    yield


app = FastAPI(
    title="Intent Classification Service",
    description="ML Intent Classification serving port 8001",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    """Health check endpoint confirming model status."""
    is_healthy = predictor_instance is not None and predictor_instance.is_loaded
    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "intent_service",
        "model_loaded": is_healthy,
        "model_path": str(MODEL_PATH),
    }


@app.post("/predict", response_model=IntentPredictionResponse)
def predict_intent(request: IntentPredictionRequest):
    """Predict customer intent with confidence and probability distribution."""
    if not predictor_instance or not predictor_instance.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not loaded",
        )
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty",
        )
    return predictor_instance.predict(request.query)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8005))
    uvicorn.run("services.intent_service.src.main:app", host="0.0.0.0", port=port, reload=False)
