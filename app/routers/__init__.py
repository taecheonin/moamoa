from .accounts import router as accounts_router
from .diaries import router as diaries_router
from .webs import router as webs_router

__all__ = ["accounts_router", "diaries_router", "webs_router"]
