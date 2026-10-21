"""Intent API: load explicit artifacts once; degrade clearly if unavailable."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from fastapi import FastAPI, HTTPException
from contracts.schemas import IntentPredictionRequest, IntentPredictionResponse
from services.intent_service.src.predictor import IntentPredictor

logger = logging.getLogger(__name__)
predictor_instance = None
load_error = None


@asynccontextmanager
async def lifespan(app):
    global predictor_instance, load_error
    try:
        predictor_instance = IntentPredictor()
        load_error = None
    except Exception as exc:
        predictor_instance = None
        load_error = str(exc)
        logger.exception('NLU artifacts unavailable. Run Module 1 training/deployment commands; automatic training is disabled.')
    yield
    predictor_instance = None


app = FastAPI(title='Bilingual Intent Service', version='2.0.0', lifespan=lifespan)


@app.get('/health')
def health_check():
    healthy = predictor_instance is not None and predictor_instance.is_loaded
    return {'status': 'healthy' if healthy else 'degraded', 'service': 'intent_service',
            'model_loaded': healthy, 'routing_mode': os.getenv('INTENT_ROUTING_MODE', 'router'),
            'models': predictor_instance.models if healthy else {}, 'error': load_error}


@app.post('/predict', response_model=IntentPredictionResponse)
def predict_intent(request: IntentPredictionRequest):
    if not request.query.strip():
        raise HTTPException(400, 'Query string cannot be empty')
    if predictor_instance is None:
        raise HTTPException(503, 'Intent artifacts unavailable; inspect /health and README_MODULE1.md')
    return predictor_instance.predict(request.query)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('services.intent_service.src.main:app', host='0.0.0.0', port=int(os.getenv('PORT', 8005)))
