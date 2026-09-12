"""End-to-end tests for the karaoke dashboard."""

from __future__ import annotations


def test_song_list_public_and_parsed(client):
    r = client.get("/songs")
    assert r.status_code == 200
    assert "Bohemian Rhapsody" in r.text
    assert "Queen" in r.text
    # Synology/hidden folders are excluded
    assert "@eaDir" not in r.text
    assert ".hidden" not in r.text


def test_song_search_filters(client):
    r = client.get("/songs", params={"q": "abba"})
    assert r.status_code == 200
    assert "Dancing Queen" in r.text
    assert "Take On Me" not in r.text


def test_song_partial_endpoint(client):
    r = client.get("/songs/partial", params={"q": "africa"})
    assert r.status_code == 200
    assert "Africa" in r.text
    assert "Toto" in r.text
    assert "<html" not in r.text.lower()


def test_report_requires_login(client):
    r = client.get("/report", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_request_requires_login(client):
    r = client.get("/request", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_login_next_is_relative_and_honoured(client):
    r = client.get("/report", follow_redirects=False)
    # next must be a same-site relative path, not an absolute URL
    assert "next=%2Freport" in r.headers["location"]
    r = client.post(
        "/login",
        data={"username": "admin", "password": "adminadmin", "next": "/request"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/request"
    # an off-site next is ignored
    client.post("/logout")
    r = client.post(
        "/login",
        data={"username": "admin", "password": "adminadmin", "next": "https://evil.example/x"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/songs"


def test_bad_login_rejected(client):
    r = client.post("/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 401


def test_admin_can_login_and_see_admin_tabs(admin_client):
    r = admin_client.get("/songs")
    assert "/admin/reports" in r.text


def test_report_flow_and_admin_view(admin_client):
    # missing fields -> 422 with errors
    r = admin_client.post("/report", data={"song_folder": "", "description": ""})
    assert r.status_code == 422
    assert "pick the song" in r.text.lower()

    # valid submission
    r = admin_client.post(
        "/report",
        data={"song_folder": "Queen - Bohemian Rhapsody", "description": "audio cuts out"},
    )
    assert r.status_code == 200
    assert "was submitted" in r.text

    # unknown song rejected
    r = admin_client.post("/report", data={"song_folder": "Nope - Nope", "description": "x"})
    assert r.status_code == 422

    # shows up in admin
    r = admin_client.get("/admin/reports")
    assert "audio cuts out" in r.text


def test_request_flow_validation_and_csv(admin_client):
    r = admin_client.post("/request", data={"band_name": "", "song_name": "x"})
    assert r.status_code == 422

    r = admin_client.post(
        "/request",
        data={"band_name": "Journey", "song_name": "Faithfully", "youtube_url": "not-a-url"},
    )
    assert r.status_code == 422

    r = admin_client.post(
        "/request",
        data={
            "band_name": "Journey",
            "song_name": "Faithfully",
            "youtube_url": "https://youtu.be/abc",
        },
    )
    assert r.status_code == 200
    assert "was submitted" in r.text

    r = admin_client.get("/admin/requests.csv", params={"scope": "all"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert body.endswith("\n")
    assert "band name,song name,youtube link,language,musicbrainz_id,lyrics_url\n" in body
    assert "Journey,Faithfully,https://youtu.be/abc,,,\n" in body


def test_non_admin_blocked_from_admin(admin_client):
    # create a normal user
    admin_client.post("/admin/users", data={"username": "bob", "password": "bobbobbob"})
    admin_client.post("/logout")

    r = admin_client.post(
        "/login", data={"username": "bob", "password": "bobbobbob"}, follow_redirects=False
    )
    assert r.status_code == 303

    assert admin_client.get("/admin/reports").status_code == 403
    # but bob can reach the input pages
    assert admin_client.get("/report").status_code == 200
    assert admin_client.get("/request").status_code == 200


def test_admin_cannot_delete_self(admin_client):
    users = admin_client.get("/admin/users").text
    assert "admin" in users
    # find own id is 1 (seeded first)
    r = admin_client.post("/admin/users/1/delete", follow_redirects=False)
    assert r.status_code == 303
    assert "error" in r.headers["location"]


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}
