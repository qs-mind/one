from qsone.cli.commands import Commands


def test_pending_card_waits_for_local_reading(monkeypatch):
    monkeypatch.setattr("qsone.cli.commands.time.sleep", lambda _: None)
    monkeypatch.setattr("qsone.cli.commands.session.save", lambda *a: None)

    class Core:
        polls = 0

        def get(self, route, **kwargs):
            if route.endswith("/messages"):
                return {
                    "messages": [
                        {
                            "parts": [
                                {
                                    "type": "data-card",
                                    "id": "c",
                                    "data": {"kind": "cost", "status": "pending"},
                                }
                            ]
                        }
                    ]
                }
            self.polls += 1
            return {"files": [], "status": {"waiting": int(self.polls < 3), "reading": 0}}

    client = Core()
    assert Commands(client, {"cards": {}}, None).map("p", wait=10)["state"] == "waiting_engineer"
    assert client.polls == 3
