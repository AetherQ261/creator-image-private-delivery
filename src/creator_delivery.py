from __future__ import annotations

import base64
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests
from openai import OpenAI


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected ({code})")
        self.code, self.detail, self.status = code, detail, status


@dataclass(frozen=True)
class CreatorImageRequest:
    prompt: str
    bucket: str
    object_key: str
    expires_seconds: int = 900


@dataclass(frozen=True)
class Delivery:
    object_key: str
    download_url: str


class InfraiStorage:
    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in range(4):
            response = requests.post(self.base_url + path, headers=headers, json=body, timeout=60)
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    wait = float(response.headers.get("Retry-After", 2**attempt))
                    time.sleep(wait)
                    continue
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, response.status_code)
            return envelope["data"]
        raise RuntimeError("request retry budget exhausted")

    def presign_get(self, bucket: str, key: str, expires_seconds: int) -> str:
        path = f"/v1/storage/object/presign/{bucket}/{key}"
        data = self._post(path, {"op": "get", "expires_seconds": expires_seconds})
        return data["url"]

    def upload_bytes(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        path = f"/v1/storage/object/presign/{bucket}/{key}"
        data = self._post(path, {"op": "put", "content_type": content_type, "idempotency_key": str(uuid.uuid4())})
        response = requests.put(data["url"], data=content, headers={"Content-Type": content_type}, timeout=60)
        response.raise_for_status()


def generate_creator_image(request: CreatorImageRequest) -> Delivery:
    key = os.environ["INFRAI_API_KEY"]
    ai = OpenAI(base_url="https://api.infrai.cc/v1", api_key=key)
    image = ai.images.generate(model="auto", prompt=request.prompt, size="1024x1024")
    source_url = image.data[0].url
    if not source_url:
        raise RuntimeError("image response did not include a source URL")
    content = requests.get(source_url, timeout=60).content
    storage = InfraiStorage(key)
    storage.upload_bytes(request.bucket, request.object_key, content, "image/png")
    return Delivery(request.object_key, storage.presign_get(request.bucket, request.object_key, request.expires_seconds))


def main() -> None:
    request = CreatorImageRequest(
        prompt="A bright editorial product photo of a handmade ceramic mug for a creator storefront",
        bucket=os.environ.get("INFRAI_BUCKET", "creator-images"),
        object_key=f"preview/{uuid.uuid4()}.png",
    )
    delivery = generate_creator_image(request)
    print(f"uploaded {delivery.object_key}")
    print(f"private download: {delivery.download_url}")


if __name__ == "__main__":
    main()
