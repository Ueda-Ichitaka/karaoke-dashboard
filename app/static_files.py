"""About me: the /static mount (app/main.py). Starlette's StaticFiles sends
no Cache-Control, which lets a browser keep a saved copy of style.css or
app.js after an image update and show new pages with old styling. Every
response here says "no-cache": the browser asks on each page load and gets
a 304 (by ETag/Last-Modified) when the file is unchanged.
"""

from __future__ import annotations

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response


class RevalidatedStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response
