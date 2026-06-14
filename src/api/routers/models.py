"""Model configuration route stubs (placeholder responses for now)."""


from fastapi import APIRouter, Depends

from src.api.middleware import get_current_user

router = APIRouter()


@router.get("")
async def list_models(
    user_id: str = Depends(get_current_user),
):
    """List available model configurations for the current user."""
    return {"models": []}


@router.post("")
async def add_model(
    body: dict,
    user_id: str = Depends(get_current_user),
):
    """Add a new model configuration (BYOK or platform)."""
    return {"id": "placeholder", **body}


@router.delete("/{model_id}")
async def remove_model(
    model_id: str,
    user_id: str = Depends(get_current_user),
):
    """Remove a model configuration."""
    return None
