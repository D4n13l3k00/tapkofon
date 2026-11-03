from fastapi import Request

from .preferences import get_preferences


def render(request: Request, name: str, *, status_code: int = 200, **context):
    context["csrf_token"] = request.state.csrf_token
    context["shared"] = request.state.common
    context["can_admin"] = request.state.can_admin
    context["prefs"] = get_preferences(request)
    return request.app.state.templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )
