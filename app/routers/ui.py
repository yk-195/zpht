"""固定页面与资源白名单，永不挂载项目目录或配置文件。"""
import json

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..core.config import settings
from ..core.errors import NotFound

router = APIRouter(tags=["ui"])
ASSETS = {"app.js", "app.css"}


def render_page() -> HTMLResponse:
    path = settings.static_path / "test-console.html"
    if not path.is_file():
        raise NotFound("页面文件缺失")
    config = json.dumps({
        "apiPrefix": settings.api_prefix,
        "questionnairePath": settings.questionnaire_prefix,
    }, ensure_ascii=True).replace("<", "\\u003c")
    return HTMLResponse(path.read_text(encoding="utf-8").replace("{{client_config}}", config))


@router.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse("/ui", status_code=307)


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
@router.get("/static/test-console.html", response_class=HTMLResponse, include_in_schema=False)
def ui_page() -> HTMLResponse:
    if not settings.ui_enabled:
        raise NotFound("控制台已关闭")
    return render_page()


@router.get("/static/{asset}", include_in_schema=False)
def static_asset(asset: str) -> FileResponse:
    if asset not in ASSETS:
        raise NotFound()
    return FileResponse(settings.static_path / asset)


@router.get(f"{settings.questionnaire_prefix}/{{token}}", response_class=HTMLResponse, include_in_schema=False)
def fill_page(token: str) -> HTMLResponse:
    return render_page()
