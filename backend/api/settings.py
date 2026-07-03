from fastapi import APIRouter, HTTPException

from config.settings import load_settings, save_settings, settings_public_dict, GROQ_MODELS
from backend.models.schemas import SettingsUpdate, SettingsTestRequest
from backend.providers.groq import GroqProvider

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings():
    return settings_public_dict(load_settings())


@router.post("")
def update_settings(body: SettingsUpdate):
    s = load_settings()
    if body.api_key is not None:
        s.api_key = body.api_key
    if body.model is not None and body.model in GROQ_MODELS:
        s.model = body.model
    if body.theme is not None:
        s.theme = body.theme
    if body.setup_complete is not None:
        s.setup_complete = body.setup_complete
    save_settings(s)
    return settings_public_dict(s)


@router.post("/test")
async def test_settings(body: SettingsTestRequest):
    key = body.api_key or load_settings().api_key
    if not key:
        raise HTTPException(400, "No API key provided. Paste your key and try again.")
    model = body.model
    if model is not None and model not in GROQ_MODELS:
        raise HTTPException(400, f"Unknown model: {model}")
    provider = GroqProvider(api_key=key, model=model)
    ok = await provider.test_connection()
    if not ok:
        raise HTTPException(400, "Could not connect to Groq. Check your API key and try again.")
    return {"success": True, "message": "Connected successfully!"}
