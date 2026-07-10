"""閲覧用 Lambda のテスト。私有 S3 を short_id で読んで HTML を返し、不正 id は拒否する。

実 S3 に到達できないため s3_client は fake 注入する。
"""

from src import viewer


class FakeS3:
    def __init__(self, objects: dict[str, str]) -> None:
        self._objects = objects
        self.get_keys: list[str] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        del Bucket
        self.get_keys.append(Key)
        if Key not in self._objects:
            raise KeyError(Key)
        return {"Body": _Body(self._objects[Key])}


class _Body:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")


def test_有効なidの図解をtext_htmlで返す() -> None:
    s3 = FakeS3({"explainer/abc123.html": "<html>図解</html>"})

    result = viewer.lambda_handler(
        {"queryStringParameters": {"id": "abc123"}},
        None,
        s3_client=s3,
    )

    assert result["statusCode"] == 200
    assert result["headers"]["Content-Type"] == "text/html; charset=utf-8"
    assert result["body"] == "<html>図解</html>"
    assert s3.get_keys == ["explainer/abc123.html"]


def test_不正なidはS3を読まず400を返す() -> None:
    # パストラバーサルや任意キー参照(../ や .html 付き)を弾く
    s3 = FakeS3({})

    result = viewer.lambda_handler(
        {"queryStringParameters": {"id": "../secret"}},
        None,
        s3_client=s3,
    )

    assert result["statusCode"] == 400
    assert s3.get_keys == []


def test_存在しない図解は404を返す() -> None:
    s3 = FakeS3({})

    result = viewer.lambda_handler(
        {"queryStringParameters": {"id": "deadbeef"}},
        None,
        s3_client=s3,
    )

    assert result["statusCode"] == 404
