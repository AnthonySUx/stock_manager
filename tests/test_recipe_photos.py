"""Recipe photo storage and authenticated API coverage."""

from dataclasses import asdict
from io import BytesIO

import pytest
from PIL import Image

from stock_manager.api import media
from stock_manager.api.errors import APIError
from stock_manager.api.models import Recipe, RecipePhoto, RecipeUsageHistory


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    path = tmp_path / "media"
    monkeypatch.setenv("MEDIA_DIR", str(path))
    return path


@pytest.fixture
def photo_client(media_dir, request):
    return request.getfixturevalue("client")


def image_bytes(format="PNG", size=(20, 10), color="red", **options):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format, **options)
    return buf.getvalue()


def upload(client, recipe, *, color="red", raw=None, **fields):
    return client.post(
        f"/api/recipes/{recipe}/photos",
        files={"file": ("dish.png", image_bytes(color=color) if raw is None else raw)},
        data=fields,
    )


def make_recipe(client, steps=(10,), title="Dinner"):
    response = client.post("/api/recipes", json={
        "title": title, "category": "soup",
        "steps": [{"step_number": number, "instruction": "Mix"} for number in steps],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def source_photo(db, recipe_id, *, position=0, step=None, color="blue", hidden=False, path=None):
    row = RecipePhoto(
        recipe_id=recipe_id, origin="howtocook", step_number=step, position=position,
        hidden=hidden, source_path=path, **asdict(media.store_image(image_bytes(color=color))),
    )
    db.add(row)
    db.commit()
    return row.id


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_storage_resizes_and_deduplicates(media_dir, format):
    media.reload_config()
    data = image_bytes(format, (2200, 1100))
    stored = media.store_image(data)
    assert (stored.width, stored.height) == (1600, 800)
    assert media.store_image(data) == stored
    paths = list(media_dir.rglob("*.jpg"))
    assert len(paths) == 2
    for size, expected in [("full", (1600, 800)), ("thumb", (400, 200))]:
        path = media.image_path(stored.sha256, size)
        with Image.open(path) as result:
            assert result.format == "JPEG"
            assert result.size == expected
    assert media.image_path(stored.sha256).stat().st_size == stored.bytes


def test_storage_honors_orientation_and_strips_gps(media_dir):
    media.reload_config()
    exif = Image.Exif()
    exif[274] = 6
    exif[34853] = {1: "N", 2: (1, 2, 3), 3: "E", 4: (4, 5, 6)}
    data = image_bytes("JPEG", size=(90, 30), exif=exif)
    with Image.open(BytesIO(data)) as source:
        assert source.getexif().get_ifd(34853)[1] == "N"
    stored = media.store_image(data)
    assert (stored.width, stored.height) == (30, 90)
    for size in ("full", "thumb"):
        with Image.open(media.image_path(stored.sha256, size)) as output:
            assert not output.getexif()


@pytest.mark.parametrize(("raw", "status", "code"), [
    (b"fake", 422, "photo_type_unsupported"),
    (b"\xff\xd8\xffbroken", 422, "photo_invalid"),
    (b"x" * (media.MAX_IMAGE_BYTES + 1), 413, "photo_too_large"),
])
def test_upload_rejects_invalid_files(photo_client, raw, status, code):
    recipe = make_recipe(photo_client)
    response = upload(photo_client, recipe, raw=raw)
    assert response.status_code == status
    assert response.json()["code"] == code


def test_pixels_over_limit_are_rejected(media_dir, monkeypatch):
    media.reload_config()
    data = image_bytes(size=(15, 10))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(APIError) as raised:
        media.store_image(data)
    assert (raised.value.status_code, raised.value.code) == (422, "photo_invalid")
    assert not list(media_dir.rglob("*.jpg"))


def test_bad_media_path_fails_configuration(tmp_path, monkeypatch):
    path = tmp_path / "file"
    path.touch()
    monkeypatch.setenv("MEDIA_DIR", str(path))
    with pytest.raises(RuntimeError, match="writable directory"):
        media.reload_config()


def test_upload_list_patch_delete_and_history(photo_client, db_session, media_dir):
    client = photo_client
    recipe = make_recipe(client)
    url = f"/api/recipes/{recipe}"
    missing = upload(client, recipe, step_number=1)
    assert (missing.status_code, missing.json()["code"], missing.json()["params"]) == (
        422, "photo_step_invalid", {"step_numbers": [10]},
    )

    cook_first = client.post(f"{url}/cook", json={"notes": "Lunch"}).json()
    cook_second = client.post(f"{url}/cook", json={"notes": "Dinner"}).json()
    history_id = cook_second["usage_history_id"]
    assert db_session.get(RecipeUsageHistory, history_id).event_type == "cooked"

    gallery, step, cooked = [
        upload(client, recipe, **fields).json()
        for fields in ({}, {"step_number": 10}, {"usage_history_id": history_id})
    ]
    photos = [gallery, step, cooked]
    assert [row["group"] for row in photos] == ["gallery", "step", "cooked"]
    assert [row["position"] for row in photos] == [0, 0, 0]
    assert client.get(f"{url}/photos").json()["photos"] == photos
    for row in photos:
        res = client.patch(f"{url}/photos/{row['id']}", json={"caption": "Meal", "position": 2})
        assert res.status_code == 200
        assert (res.json()["caption"], res.json()["position"]) == ("Meal", 2)

    step_url = f"{url}/photos/{step['id']}"
    assert client.patch(step_url, json={"step_number": 1}).json()["params"] == {"step_numbers": [10]}
    moved = client.patch(step_url, json={"step_number": None}).json()
    assert (moved["group"], moved["position"]) == ("gallery", 3)
    assert client.patch(step_url, json={"step_number": 10}).json()["group"] == "step"
    history = client.get(f"{url}/cook-history").json()
    assert [r["id"] for r in history] == [history_id, cook_first["usage_history_id"]]
    assert [r["notes"] for r in history] == ["Dinner", "Lunch"]
    assert [p["id"] for p in history[0]["photos"]] == [cooked["id"]]
    assert client.get(f"{url}/cook-history?offset=1&limit=1").json() == history[1:]

    for photo in photos:
        assert client.delete(f"{url}/photos/{photo['id']}").status_code == 204
    assert not list(media_dir.rglob("*.jpg"))
    assert client.get(f"{url}/photos").json()["photos"] == []


@pytest.mark.parametrize(("group", "limit"), [("gallery", 12), ("step", 3), ("cooked", 6)])
def test_limits_count_only_user_photos(photo_client, db_session, group, limit):
    client = photo_client
    recipe = make_recipe(client)
    url = f"/api/recipes/{recipe}"
    fields = {}
    if group == "step":
        fields["step_number"] = 10
    elif group == "cooked":
        fields["usage_history_id"] = client.post(f"{url}/cook", json={}).json()["usage_history_id"]
    if group != "cooked":
        for position in range(limit + 1):
            source_photo(db_session, recipe, position=position, step=fields.get("step_number"))
    for _ in range(limit):
        assert upload(client, recipe, **fields).status_code == 201
    response = upload(client, recipe, **fields)
    assert response.status_code == 422
    assert response.json()["code"] == "photo_limit_reached"
    assert response.json()["params"] == {"group": group, "limit": limit}
    if group == "step":
        gallery = upload(client, recipe).json()
        moved = client.patch(f"{url}/photos/{gallery['id']}", json={"step_number": 10})
        assert moved.status_code == 422
        assert moved.json()["code"] == "photo_limit_reached"
    if group == "gallery":
        step = upload(client, recipe, step_number=10).json()
        moved = client.patch(f"{url}/photos/{step['id']}", json={"step_number": None})
        assert moved.status_code == 422
        assert moved.json()["code"] == "photo_limit_reached"


def test_invalid_associations_and_photo_scope(photo_client, db_session):
    client = photo_client
    recipe, other = make_recipe(client, steps=(10, -3, 10)), make_recipe(client)
    history = client.post(f"/api/recipes/{other}/cook", json={}).json()["usage_history_id"]
    outcome = upload(client, recipe, usage_history_id=history)
    assert (outcome.status_code, outcome.json()["code"]) == (422, "photo_cook_record_invalid")
    assert upload(client, recipe, step_number=10, usage_history_id=history).json()["code"] == "photo_group_invalid"
    assert upload(client, recipe, step_number=0).json()["params"] == {"step_numbers": [-3, 10]}
    recommended = RecipeUsageHistory(recipe_id=recipe, event_type="recommended")
    db_session.add(recommended)
    db_session.commit()
    assert upload(client, recipe, usage_history_id=recommended.id).json()["code"] == "photo_cook_record_invalid"
    photo = upload(client, recipe).json()
    assert client.patch(f"/api/recipes/{other}/photos/{photo['id']}", json={}).json()["code"] == "photo_not_found"
    assert client.get("/api/recipes/99999/photos").json()["code"] == "recipe_not_found"


def test_cover_rules_and_readonly_source(photo_client, db_session):
    client = photo_client
    recipe = make_recipe(client)
    url = f"/api/recipes/{recipe}"
    assert client.get(url).json()["cover_mode"] == "none"
    hidden = source_photo(db_session, recipe, position=0, hidden=True)
    original = source_photo(db_session, recipe, position=1)
    assert client.get(url).json()["cover"]["id"] == original
    originals = client.get(f"{url}/photos").json()["photos"]
    assert (originals[0]["id"], originals[0]["hidden"]) == (hidden, True)
    invalid = client.put(f"{url}/cover", json={"photo_id": hidden})
    assert (invalid.status_code, invalid.json()["code"]) == (422, "photo_cover_invalid")
    readonly = client.delete(f"{url}/photos/{original}")
    assert (readonly.status_code, readonly.json()["code"]) == (409, "photo_source_readonly")

    first = upload(client, recipe).json()
    recent = upload(client, recipe, step_number=10).json()
    assert client.get(url).json()["cover"]["id"] == recent["id"]
    assert client.patch(f"{url}/photos/{first['id']}", json={"hidden": False}).json()["code"] == (
        "photo_hidden_source_only"
    )
    chosen = client.put(f"{url}/cover", json={"photo_id": original}).json()
    assert (chosen["cover_mode"], chosen["cover"]["id"]) == ("chosen", original)
    assert client.get("/api/recipes").json()[0]["cover"]["id"] == original
    assert client.patch(f"{url}/photos/{original}", json={"hidden": True}).json()["hidden"]
    fallback = client.get(url).json()
    assert (fallback["cover_mode"], fallback["cover"]["id"]) == ("auto", recent["id"])
    assert not client.patch(f"{url}/photos/{original}", json={"hidden": False}).json()["hidden"]

    client.put(f"{url}/cover", json={"photo_id": first["id"]})
    assert client.delete(f"{url}/cover").json()["cover"]["id"] == recent["id"]
    client.put(f"{url}/cover", json={"photo_id": first["id"]})
    client.delete(f"{url}/photos/{first['id']}")
    assert client.get(url).json()["cover"]["id"] == recent["id"]


def test_source_photo_patch_allows_only_hidden(photo_client, db_session):
    client = photo_client
    recipe = make_recipe(client)
    photo_id = source_photo(db_session, recipe, position=4)
    photos_url = f"/api/recipes/{recipe}/photos"
    original = client.get(photos_url).json()
    photo_url = f"{photos_url}/{photo_id}"
    for changes in (
        {"step_number": 10}, {"position": 2}, {"caption": "New caption"},
        {"hidden": True, "position": 2}, {"position": None}, {"unknown": True},
    ):
        response = client.patch(photo_url, json=changes)
        assert (response.status_code, response.json()["code"]) == (409, "photo_source_readonly")
        assert client.get(photos_url).json() == original

    response = client.patch(photo_url, json={"hidden": True})
    assert response.status_code == 200
    assert response.json() == {**original["photos"][0], "hidden": True}


def test_user_photo_patch_keeps_request_validation(photo_client):
    recipe = make_recipe(photo_client)
    photo = upload(photo_client, recipe).json()
    url = f"/api/recipes/{recipe}/photos/{photo['id']}"
    response = photo_client.patch(url, json={"position": None})
    assert (response.status_code, response.json()["code"]) == (422, "validation_error")
    assert response.json()["params"]["errors"][0]["loc"] == ["body", "position"]


def test_image_auth_etag_and_thumbnail(photo_client, db_session, media_dir):
    client = photo_client
    photo = upload(photo_client, make_recipe(photo_client), raw=image_bytes(size=(900, 450))).json()
    sha = db_session.get(RecipePhoto, photo["id"]).sha256
    assert photo_client.get(photo["image_url"], headers={"Authorization": ""}).status_code == 401
    for key, size, pixels in [("image_url", "full", (900, 450)), ("thumb_url", "thumb", (400, 200))]:
        response = client.get(photo[key])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["etag"] == f'"{sha}-{size}"'
        assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
        assert str(media_dir) not in str(response.headers)
        with Image.open(BytesIO(response.content)) as image:
            assert image.size == pixels
        hit = client.get(photo[key], headers={"If-None-Match": response.headers["etag"]})
        assert (hit.status_code, hit.content) == (304, b"")


def test_disabled_media(client, monkeypatch):
    monkeypatch.delenv("MEDIA_DIR", raising=False)
    media.reload_config()
    recipe = make_recipe(client)
    response = client.get(f"/api/recipes/{recipe}/photos")
    assert (response.status_code, response.json()["code"]) == (503, "media_unavailable")
    assert client.get("/api/recipes").json()[0]["cover"] is None
    assert client.get(f"/api/recipes/{recipe}").json()["cover_mode"] == "none"


def test_cook_history_returns_notes_without_media(photo_client, monkeypatch):
    client = photo_client
    recipe = make_recipe(client)
    recipe_url = f"/api/recipes/{recipe}"
    record = client.post(f"{recipe_url}/cook", json={"notes": "Dinner"}).json()
    photo = upload(client, recipe, usage_history_id=record["usage_history_id"])
    assert photo.status_code == 201
    history_url = f"{recipe_url}/cook-history"
    with_media = client.get(history_url).json()
    assert len(with_media[0]["photos"]) == 1

    monkeypatch.delenv("MEDIA_DIR")
    media.reload_config()

    response = client.get(history_url)
    assert response.status_code == 200
    assert response.json() == [{
        "id": record["usage_history_id"],
        "created_at": with_media[0]["created_at"],
        "notes": "Dinner",
        "photos": [],
    }]
    assert client.get(f"{recipe_url}/photos").status_code == 503
    assert client.get(photo.json()["image_url"]).status_code == 503


def test_replacing_steps_moves_only_removed_numbers_to_end(photo_client):
    client = photo_client
    recipe = make_recipe(client, steps=(2, 10))
    url = f"/api/recipes/{recipe}"
    first = upload(client, recipe).json()
    moved = upload(client, recipe, step_number=2).json()
    kept = upload(client, recipe, step_number=10).json()
    response = client.patch(url, json={"steps": [
        {"step_number": 10, "instruction": "Keep"}, {"step_number": 30, "instruction": "New"},
    ]})
    assert response.status_code == 200
    photos = client.get(f"{url}/photos").json()["photos"]
    assert [(p["id"], p["step_number"], p["position"]) for p in photos] == [
        (first["id"], None, 0), (moved["id"], None, 1), (kept["id"], 10, 0),
    ]
    assert client.patch(url, json={"steps": []}).status_code == 200
    assert [p["group"] for p in client.get(f"{url}/photos").json()["photos"]] == ["gallery"] * 3


def test_fork_and_delete_share_files(photo_client, db_session, media_dir):
    client = photo_client
    source = Recipe(title="Source", source_type="howtocook")
    db_session.add(source)
    db_session.commit()
    original = source_photo(db_session, source.id, path="dishes/picture.png")
    hidden = source_photo(db_session, source.id, color="green", hidden=True)
    client.put(f"/api/recipes/{source.id}/cover", json={"photo_id": original})
    record = client.post(f"/api/recipes/{source.id}/cook", json={}).json()["usage_history_id"]
    upload(client, source.id, usage_history_id=record)
    before = set(media_dir.rglob("*.jpg"))
    fork = client.post(f"/api/recipes/{source.id}/fork").json()
    forked = client.get(f"/api/recipes/{fork['id']}/photos").json()["photos"]
    assert len(forked) == 1
    copy = db_session.get(RecipePhoto, forked[0]["id"])
    assert copy.origin == "howtocook"
    assert copy.source_path is None and copy.is_cover
    assert copy.sha256 == db_session.get(RecipePhoto, original).sha256
    assert set(media_dir.rglob("*.jpg")) == before
    assert client.delete(f"/api/recipes/{fork['id']}").status_code == 200
    assert db_session.get(RecipePhoto, copy.id) is None
    assert db_session.get(RecipePhoto, hidden).hidden
    assert set(media_dir.rglob("*.jpg")) == before

    recipe, other = make_recipe(client), make_recipe(client)
    first = upload(client, recipe, color="purple").json()
    second = upload(client, other, color="purple").json()
    paths = set(media_dir.rglob("*.jpg")) - before
    assert len(paths) == 2
    assert client.delete(f"/api/recipes/{recipe}").status_code == 200
    assert db_session.get(RecipePhoto, first["id"]) is None
    assert all(p.is_file() for p in paths)
    assert client.delete(f"/api/recipes/{other}").status_code == 200
    assert db_session.get(RecipePhoto, second["id"]) is None
    assert all(not p.exists() for p in paths)


def test_upload_commit_failure_cleans_only_unreferenced_files(photo_client, db_session, media_dir, monkeypatch):
    client = photo_client
    recipe = make_recipe(client)
    upload(client, recipe, color="red")
    original = set(media_dir.rglob("*.jpg"))
    calls = []

    def fail_commit():
        calls.append("commit")
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    for color in ("blue", "red"):
        with pytest.raises(RuntimeError, match="injected commit failure"):
            upload(client, recipe, color=color)
        assert set(media_dir.rglob("*.jpg")) == original
        assert db_session.query(RecipePhoto).count() == 1
    assert calls == ["commit", "commit"]


def test_delete_commits_before_cleanup(photo_client, db_session, monkeypatch):
    client = photo_client
    recipe = make_recipe(client)
    photo = upload(client, recipe).json()
    events = []
    commit = db_session.commit
    cleanup = media.delete_files_if_unused

    def tracked_commit():
        commit()
        events.append("commit")

    def tracked_cleanup(db, sha256):
        assert events == ["commit"]
        events.append("cleanup")
        cleanup(db, sha256)

    monkeypatch.setattr(db_session, "commit", tracked_commit)
    monkeypatch.setattr(media, "delete_files_if_unused", tracked_cleanup)
    response = client.delete(f"/api/recipes/{recipe}/photos/{photo['id']}")
    assert response.status_code == 204
    assert events == ["commit", "cleanup"]


def test_multipart_rejects_extra_files_and_invalid_fields(photo_client):
    recipe_id = make_recipe(photo_client)
    url = f"/api/recipes/{recipe_id}/photos"
    files = [("file", ("dish.png", image_bytes()))]
    for response in (
        photo_client.post(url, files=files * 2),
        photo_client.post(url, files=files, data={"step_number": "step 10"}),
        photo_client.post(url, files=files, data={"step_number": " " * 65}),
        photo_client.post(url, files=[("step_number", (None, "10"))]),
    ):
        assert (response.status_code, response.json()["code"]) == (422, "photo_upload_invalid")
