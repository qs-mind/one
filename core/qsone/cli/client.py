"""Authenticated loopback requests; never echo request bodies or validation input."""

import httpx

from qsone.cli.texts import CliError


class Client:
    def __init__(self, session):
        self.http = httpx.Client(
            base_url=f"http://127.0.0.1:{session['port']}",
            headers={"Authorization": f"Bearer {session['secret']}"},
            trust_env=False,
            timeout=60,
        )

    def close(self):
        self.http.close()

    def check(self, response):
        if response.is_success:
            return
        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get("error")
        text = error if isinstance(error, dict) and {"en", "ar"} <= error.keys() else None
        raise CliError(
            text=text,
            detail={
                "status": response.status_code,
                **({"brief_id": body["brief_id"]} if "brief_id" in body else {}),
            },
        )

    def request(self, method, route, **kwargs):
        response = self.http.request(method, route, **kwargs)
        self.check(response)
        return response.json() if response.content else {}

    def get(self, route, **params):
        return self.request(
            "GET",
            route,
            params={k: v for k, v in params.items() if v is not None},
            **({"timeout": 5} if route == "/costs" else {}),
        )

    def post(self, route, body=None):
        return self.request("POST", route, json=body)
