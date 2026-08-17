import uuid


def gen_task_id() -> str:
    return uuid.uuid4().hex
