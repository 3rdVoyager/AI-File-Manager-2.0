"""System endpoints: shutdown and factory reset."""

import os
import signal
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.reset_service import factory_reset

router = APIRouter(tags=["system"])


class ResetRequest(BaseModel):
    confirm: str


@router.post("/shutdown")
def shutdown_server():
    def _stop():
        import time
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGINT)

    threading.Thread(target=_stop, daemon=True).start()
    return {"shutting_down": True}


@router.post("/reset")
def reset_all(body: ResetRequest):
    if body.confirm != "RESET":
        raise HTTPException(400, 'Type RESET to confirm.')
    factory_reset()
    return {"success": True}
