from io import BytesIO
import zipfile


def make_zip(entries: dict[str, bytes], compression: int = zipfile.ZIP_STORED) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_zip_upload_and_project_retrieval(client):
    response = client.post(
        "/api/projects",
        files={"file": ("sample-project.zip", make_zip({"src/main.py": b"print('safe')"}), "application/zip")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "sample-project"
    assert body["status"] == "uploaded"

    fetched = client.get(f"/api/projects/{body['project_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["project_id"]


def test_non_zip_rejected(client):
    response = client.post("/api/projects", files={"file": ("notes.txt", b"not an archive", "text/plain")})
    assert response.status_code == 400
    assert "Only .zip" in response.json()["detail"]


def test_path_traversal_zip_rejected(client):
    archive = make_zip({"../escape.py": b"bad"})
    response = client.post("/api/projects", files={"file": ("unsafe.zip", archive, "application/zip")})
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]


def test_oversized_zip_rejected(client):
    # This is intentionally below MAX_UPLOAD_BYTES (4 KiB) but expands beyond
    # MAX_UNCOMPRESSED_BYTES (4 KiB), proving expanded-size validation runs.
    archive = make_zip({"large.txt": b"x" * 8192}, compression=zipfile.ZIP_DEFLATED)
    assert len(archive) < 4096
    response = client.post("/api/projects", files={"file": ("large.zip", archive, "application/zip")})
    assert response.status_code == 400
    assert "expands beyond" in response.json()["detail"]
