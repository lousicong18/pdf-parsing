"""OSS 客户端(可选). 支持 aliyun / aws s3 / minio."""

from typing import Optional

from src.utils import env


def is_oss_enabled() -> bool:
    return env.OSS_ENABLED == "on"


def upload_image(task_id: str, page: int, index: int, data: bytes) -> Optional[str]:
    """上传图片到 OSS,返回公网 URL. 未启用则返回 None."""
    if not is_oss_enabled():
        return None
    provider = env.OSS_PROVIDER.lower()
    if provider == "aliyun":
        return _upload_aliyun(task_id, page, index, data)
    if provider in ("aws", "s3", "minio"):
        return _upload_s3(task_id, page, index, data)
    raise ValueError(f"Unsupported OSS provider: {provider}")


def _object_key(task_id: str, page: int, index: int) -> str:
    return f"{env.OSS_PREFIX}{task_id}/{page}_{index}.png"


def _upload_aliyun(task_id: str, page: int, index: int, data: bytes) -> str:
    import oss2  # type: ignore[import-untyped]

    auth = oss2.Auth(env.OSS_ACCESS_KEY, env.OSS_SECRET_KEY)
    bucket = oss2.Bucket(auth, env.OSS_ENDPOINT, env.OSS_BUCKET)
    key = _object_key(task_id, page, index)
    headers = {"Content-Type": "image/png"}
    bucket.put_object(key, data, headers=headers)
    # 签名 URL 强制 inline(否则默认 attachment)
    params = {"response-content-disposition": "inline"}
    url = bucket.sign_url("GET", key, 3600, slash_safe=True, params=params)
    return url.replace("http://", "https://", 1)


def _upload_s3(task_id: str, page: int, index: int, data: bytes) -> str:
    import boto3  # type: ignore[import-untyped]

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{env.OSS_ENDPOINT}",
        aws_access_key_id=env.OSS_ACCESS_KEY,
        aws_secret_access_key=env.OSS_SECRET_KEY,
    )
    key = _object_key(task_id, page, index)
    client.put_object(
        Bucket=env.OSS_BUCKET, Key=key, Body=data,
        ContentType="image/png", ContentDisposition="inline",
    )
    return f"https://{env.OSS_BUCKET}.{env.OSS_ENDPOINT}/{key}"
