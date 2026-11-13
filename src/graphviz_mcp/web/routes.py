"""Server-rendered Web UI: plain HTML forms generated from the tool table; no JavaScript, no cookies."""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib import resources
from typing import Any
from urllib.parse import parse_qs

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from ..app import App
from ..extras import _data, capabilities_document, render_attributes, validate_document
from ..meta import INSTRUCTIONS
from ..security import allowed_origins, origin_allowed
from ..tools.service import ToolFailure
from ..tools.specs import PROGRAMS
from . import envinfo
from .content import read_doc, render_markdown, rendered_doc
from .render import SECURITY_HEADERS, FormError, build_fields, parse_form, present

GROUPS = [
    ("layout", "Layout and rendering"),
    ("processing", "Graph processing and analysis"),
    ("generator", "Generators"),
    ("converter", "Converters"),
    ("extension", "MCP extensions"),
]
EXTENSIONS = {
    "validate_dot": "Check DOT syntax without laying the graph out (MCP extension).",
    "get_capabilities": "Graphviz version, engines, formats, tools, limits and attribute policy (MCP extension).",
}
FORM_TYPE = "application/x-www-form-urlencoded"
GITHUB_PROJECT_URL = "https://github.com/rodw/graphviz-mcp"


def ui_tools(app: App) -> list[dict[str, str]]:
    """The tools shown in the UI: exactly the set registered on the MCP surface."""
    items = [{"name": n, "group": p.group, "summary": p.summary} for n, p in PROGRAMS.items() if n in app.caps.programs]
    items += [{"name": n, "group": "extension", "summary": s} for n, s in EXTENSIONS.items()]
    return items


def register_web_routes(app: App) -> Callable[[int, str], Response]:
    """Register the UI routes; returns the responder that words body-limit rejections as a themed error page."""
    server = app.server
    env = Environment(
        loader=PackageLoader("graphviz_mcp.web", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    css = resources.files("graphviz_mcp.web").joinpath("static", "style.css").read_text("utf-8")
    origins = allowed_origins(app.allowed_hosts)
    favicon = resources.files("graphviz_mcp.web").joinpath("static", "favicon.ico").read_bytes()

    # versions shown in every page footer; fixed for the life of the process
    base = capabilities_document(app)
    footer = {
        "server": base["server"],
        "graphviz_version_line": base["graphviz_version_line"],
    }

    def page(template: str, status: int = 200, headers: dict[str, str] | None = None, **ctx: Any) -> HTMLResponse:
        html = env.get_template(template).render(
            tools=ui_tools(app), groups=GROUPS, footer=footer, github_url=GITHUB_PROJECT_URL, **ctx
        )
        return HTMLResponse(html, status_code=status, headers={**SECURITY_HEADERS, **(headers or {})})

    def tool_page(name: str, status: int = 200, **ctx: Any) -> HTMLResponse:
        prog = PROGRAMS.get(name)
        summary = prog.summary if prog else EXTENSIONS[name]
        if prog:
            fields = build_fields(prog, app, ctx.pop("values", None), ctx.pop("checked", None))
        else:
            values = ctx.pop("values", None) or {}
            ctx.pop("checked", None)
            from .render import SAMPLE_DOT, FieldView

            fields = [FieldView("input", "input", "textarea", "The graph in DOT language.", required=True,
                                value=values.get("input", SAMPLE_DOT), rows=14, flag="input")]  # fmt: skip
        return page("tool.html", status, name=name, summary=summary, fields=fields, **ctx)

    def known(name: str) -> bool:
        return name in EXTENSIONS or (name in PROGRAMS and name in app.caps.programs)

    @server.custom_route("/", methods=["GET"])
    async def root(request: Request) -> Response:
        return RedirectResponse("/ui", status_code=302)

    @server.custom_route("/ui", methods=["GET"])
    async def home(request: Request) -> Response:
        return page("home.html", instructions=render_markdown(INSTRUCTIONS))

    @server.custom_route("/ui/", methods=["GET"])
    async def home_slash(request: Request) -> Response:
        return page("home.html", instructions=render_markdown(INSTRUCTIONS))

    @server.custom_route("/ui/tools", methods=["GET"])
    async def tools_index(request: Request) -> Response:
        return page("tools.html")

    @server.custom_route("/favicon.ico", methods=["GET"])
    async def favicon_ico(request: Request) -> Response:
        return Response(favicon, media_type="image/x-icon", headers={"Cache-Control": "public, max-age=86400"})

    @server.custom_route("/ui/static/style.css", methods=["GET"])
    async def style(request: Request) -> Response:
        return Response(
            css, media_type="text/css", headers={**SECURITY_HEADERS, "Cache-Control": "public, max-age=3600"}
        )

    async def capabilities_page(request: Request) -> Response:
        doc = capabilities_document(app)
        return page("capabilities.html", doc=doc, raw=json.dumps(doc, indent=2))

    server.custom_route("/ui/capabilities", methods=["GET"])(capabilities_page)

    def simple(path: str, template: str, **ctx: Any) -> None:
        async def handler(request: Request) -> Response:
            return page(template, **{k: v() if callable(v) else v for k, v in ctx.items()})

        server.custom_route(path, methods=["GET"])(handler)

    simple("/ui/resources", "resources.html")
    simple("/ui/resources/dot-language", "document.html", title="DOT language",
           body=lambda: render_markdown(_data("dot-language.md")), uri="graphviz://dot-language")  # fmt: skip
    simple("/ui/resources/attributes", "document.html", title="Attributes",
           body=lambda: render_markdown(render_attributes(app)), uri="graphviz://attributes")  # fmt: skip
    simple("/ui/resources/capabilities", "resource_capabilities.html",
           raw=lambda: json.dumps(capabilities_document(app), indent=2))  # fmt: skip
    simple("/ui/status", "status.html")
    simple("/ui/status/current-env", "current_env.html", rows=lambda: envinfo.rows(app.settings))
    simple("/ui/docs", "docs.html")
    simple("/ui/docs/env-vars", "env_vars.html", vars=envinfo.ENV_VARS, env_groups=envinfo.GROUPS)
    simple("/ui/docs/attribute-security-policy", "document.html", title="Attribute security policy",
           body=lambda: rendered_doc("attribute-security-policy.md", "docs"))  # fmt: skip
    simple("/ui/legal", "legal.html")
    simple("/ui/legal/license", "license.html", text=lambda: read_doc("LICENSE"))
    simple("/ui/legal/third-party-notices", "document.html", title="Third-party notices",
           body=lambda: rendered_doc("THIRD_PARTY_NOTICES.md"))  # fmt: skip

    @server.custom_route("/ui/tools/{name}", methods=["GET", "POST"])
    async def tool(request: Request) -> Response:
        name = request.path_params["name"]
        if not known(name):
            return page("error.html", 404, title="Unknown tool", message=f"There is no tool named {name[:60]!r}.")
        if request.method == "GET":
            if name == "get_capabilities":
                return await capabilities_page(request)
            return tool_page(name)
        return await submit(request, name)

    async def submit(request: Request, name: str) -> Response:
        fail = _check_request(request)
        if fail:
            return page("error.html", fail[0], title=fail[1], message=fail[2])
        body = await request.body()  # its size is already bounded by the BodyLimit middleware (server.http_app)
        parsed = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True, max_num_fields=200)
        form = {k: v[0] for k, v in parsed.items()}
        values = dict(form)
        checked = {k for k, v in form.items() if v.lower() in ("on", "true", "1")}
        try:
            if name == "validate_dot":
                doc = await validate_document(app, form.get("input", ""))
                return tool_page(name, 200, values=values, checked=checked, validation=doc,
                                 validation_json=json.dumps(doc, indent=2))  # fmt: skip
            prog = PROGRAMS[name]
            try:
                args = parse_form(prog, form)
            except FormError as exc:
                raise ToolFailure("args", str(exc)) from None
            result = await app.service.call(name, args, surface="ui")
        except ToolFailure as exc:
            headers = {"Retry-After": "1"} if exc.kind == "busy" else None
            return tool_page(name, exc.status, values=values, checked=checked, failure=exc, headers=headers)
        return tool_page(name, 200, values=values, checked=checked, blocks=present(prog, result))

    def _check_request(request: Request) -> tuple[int, str, str] | None:
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != FORM_TYPE:
            return 415, "Unsupported content type", "Forms are submitted as application/x-www-form-urlencoded."
        # Fetch metadata is set by the browser and cannot be forged by a page: trust "same-origin"/"none".
        # Browsers send `Origin: null` for same-origin form posts under some referrer policies, so a null Origin
        # is accepted only together with that assertion.
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        if site is not None and site not in ("same-origin", "none"):
            return 403, "Cross-site request refused", "This form can only be submitted from this site."
        if origin == "null":
            if site is None:
                return 403, "Cross-origin request refused", "The Origin of this request is not allowed."
        elif not origin_allowed(origin, origins):
            return 403, "Cross-origin request refused", "The Origin of this request is not allowed."
        return None

    def reject(status: int, message: str) -> Response:
        if status == 413:
            return page("error.html", 413, title="Too large", message="The submitted form is too large.")
        return page("error.html", status, title="Bad request", message=message)

    return reject
