# 图片存储方案设计(混合模式)

## 问题

当前解析结果 md 中的图片链接是本地 API 路径(`/api/v1/tasks/{task_id}/images/{page}/{index}`),导致:
1. 后端重启后内存缓存丢失,图片 404
2. md 无法跨项目使用(另一项目无法访问本地 API)

## 目标

- 本地使用时图片正常展示
- 导出 md 时可携带图片(跨项目可用)
- 不显著增加 md 体积
- 架构可渐进演进

## 方案 C:混合模式

### 架构

```
┌─────────────────────────────────────────────────────────┐
│                      解析阶段                            │
│  图片 → 本地磁盘缓存(./.image_cache/{task_id}/{p}_{i}.png) │
│  md 中写入本地路径: /api/v1/tasks/{task_id}/images/{p}/{i} │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                      使用阶段                            │
│  GET /api/v1/tasks/{task_id}/images/{page}/{index}       │
│    1. 查内存缓存                                         │
│    2. 未命中 → 读磁盘缓存                                  │
│    3. 返回图片                                            │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼ (导出时可选)
┌─────────────────────────────────────────────────────────┐
│                   OSS 上传阶段(可选)                      │
│  配置 OSS_ENABLED=on 时:                                  │
│    1. 图片上传到 OSS                                      │
│    2. 返回公网 URL                                        │
│    3. md 中替换本地 URL → OSS URL                        │
└─────────────────────────────────────────────────────────┘
```

### 存储层

#### 1. 本地磁盘缓存(始终启用)

```python
# .image_cache/{task_id}/{page}_{index}.png
# 目录结构:
.image_cache/
  ├── task_001/
  │   ├── 0_0.png
  │   ├── 0_1.png
  │   └── 1_0.png
  └── task_002/
      └── 0_0.png
```

- 解析时同步写入磁盘
- GET 时内存未命中则读磁盘
- 任务删除时清理对应目录

#### 2. OSS 存储(可选,配置开关)

```env
# .env
OSS_ENABLED=false                    # 是否启用 OSS
OSS_PROVIDER=aliyun                  # aliyun / aws / minio
OSS_BUCKET=pdf-parser-images
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_ACCESS_KEY=xxx
OSS_SECRET_KEY=xxx
OSS_PREFIX=tasks/                    # 对象名前缀
```

### API 变更

#### 现有接口(保持不变)

```
GET /api/v1/tasks/{task_id}/images/{page}/{index}
```
- 返回单张图片
- 内存 → 磁盘 fallback

#### 新增接口

```
POST /api/v1/tasks/{task_id}/export
Body: { "mode": "local" | "oss" }
```

| mode | 行为 | md 中图片 URL |
|------|------|--------------|
| `local` | 保持当前行为 | `/api/v1/tasks/{task_id}/images/{p}/{i}` |
| `oss` | 上传图片到 OSS,返回新 md | `https://bucket.oss.com/tasks/{task_id}/{p}_{i}.png` |

返回:
```json
{
  "markdown": "...",
  "images": [
    {"local_url": "/api/v1/...", "oss_url": "https://..."}
  ],
  "oss_uploaded": 5
}
```

### 代码变更

#### `src/store/image_cache.py`

```python
import shutil
import threading
from pathlib import Path
from typing import Optional

from src.utils.env import project_root

_cache: dict[str, dict[int, dict[int, bytes]]] = {}
_lock = threading.Lock()
_IMG_DIR = project_root() / ".image_cache"


def _disk_path(task_id: str, page: int, index: int) -> Path:
    return _IMG_DIR / task_id / f"{page}_{index}.png"


def put(task_id: str, page: int, index: int, data: bytes) -> None:
    with _lock:
        _cache.setdefault(task_id, {}).setdefault(page, {})[index] = data
    # 异步写磁盘(可选优化)
    path = _disk_path(task_id, page, index)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def get(task_id: str, page: int, index: int) -> Optional[bytes]:
    with _lock:
        data = _cache.get(task_id, {}).get(page, {}).get(index)
    if data is not None:
        return data
    # 磁盘 fallback
    path = _disk_path(task_id, page, index)
    return path.read_bytes() if path.exists() else None


def get_all(task_id: str) -> dict[int, dict[int, bytes]]:
    """获取任务的所有图片(用于导出)."""
    result = {}
    img_dir = _IMG_DIR / task_id
    if img_dir.exists():
        for f in img_dir.glob("*_*.png"):
            page, index = map(int, f.stem.split("_"))
            result.setdefault(page, {})[index] = f.read_bytes()
    return result


def remove_task(task_id: str) -> None:
    """清理任务的所有图片."""
    with _lock:
        _cache.pop(task_id, None)
    img_dir = _IMG_DIR / task_id
    if img_dir.exists():
        shutil.rmtree(img_dir)
```

#### `src/utils/oss_client.py`(新增)

```python
"""OSS 客户端(可选)."""

from typing import Optional

from src.utils import env


def is_oss_enabled() -> bool:
    return env.OSS_ENABLED == "on"


def upload_image(task_id: str, page: int, index: int, data: bytes) -> Optional[str]:
    """上传图片到 OSS,返回公网 URL. 未启用则返回 None."""
    if not is_oss_enabled():
        return None
    # TODO: 根据 env.OSS_PROVIDER 选择实现
    # aliyun / aws / minio
    raise NotImplementedError("OSS provider not implemented")
```

#### `src/controller/export_controller.py`(扩展)

```python
@router.post("/tasks/{task_id}/export")
def export_task(task_id: str, mode: str = "local"):
    result = task_store.get(task_id)
    if not result:
        raise AppError(...)

    blocks = [...]  # 拼接所有 block content
    md = "\n\n".join(b.content for b in blocks)

    if mode == "oss":
        images = image_cache.get_all(task_id)
        for (page, index), data in images.items():
            oss_url = oss_client.upload_image(task_id, page, index, data)
            if oss_url:
                local_url = f"/api/v1/tasks/{task_id}/images/{page}/{index}"
                md = md.replace(local_url, oss_url)

    return {"markdown": md, ...}
```

### 配置示例

```env
# 默认:纯本地模式
OSS_ENABLED=off

# 启用 OSS 导出
OSS_ENABLED=on
OSS_PROVIDER=aliyun
OSS_BUCKET=pdf-parser-prod
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_ACCESS_KEY=LTAI5tXXXXX
OSS_SECRET_KEY=XXXXX
OSS_PREFIX=tasks/
```

### 演进路线

| 阶段 | 功能 | 配置 |
|------|------|------|
| P0 | 本地磁盘缓存,重启不丢 | 无(默认启用) |
| P1 | 导出 API(local 模式) | 无 |
| P2 | OSS 上传能力(导出 mode=oss 时上传并替换 URL) | OSS_ENABLED=on |

### 风险评估

| 风险 | 缓解 |
|------|------|
| 磁盘占满 | LRU 淘汰 / 定期清理过期任务 |
| OSS 上传失败 | 重试 3 次,失败保持 local URL |
| OSS 密钥泄露 | 走 KMS / 环境变量注入,不入库 |
| 跨项目图片权限 | OSS 读权限设为公开或签名 URL |

---

**结论**:先落地 P0(本地磁盘缓存),后续按需启用 OSS 导出能力。
