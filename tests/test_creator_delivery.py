from creator_delivery import CreatorImageRequest


def test_creator_request_keeps_expiry_explicit():
    request = CreatorImageRequest("studio portrait", "bucket", "subscriber/a.png")
    assert request.expires_seconds == 900
    assert request.object_key.startswith("subscriber/")
