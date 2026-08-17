import logging
import traceback

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.utils import env
from src.utils.errors import AppError
from src.controller import parse_controller, task_controller, export_controller, image_controller, models_controller

logger = logging.getLogger("pdf_parser")

app = FastAPI(title="PDF Parser Demo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

api_v1 = FastAPI()
api_v1.include_router(parse_controller.router)
api_v1.include_router(task_controller.router)
api_v1.include_router(export_controller.router)
api_v1.include_router(image_controller.router)
api_v1.include_router(models_controller.router)
app.mount("/api/v1", api_v1)


@api_v1.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = exc.detail if isinstance(exc.detail, str) else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": code},
    )


@api_v1.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


@api_v1.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "code": "INTERNAL_ERROR"},
    )


def main() -> None:
    uvicorn.run(app, host=env.HOST, port=env.PORT)


if __name__ == "__main__":
    main()
