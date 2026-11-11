"""将同步业务路由放到线程池，保持直接调用接口仍可 await。"""

from functools import wraps
from inspect import signature
from starlette.concurrency import run_in_threadpool


def threaded(function):
    """在线程池完整执行一个请求，避免同一 Session 并发使用。"""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        """等待请求线程返回结果。"""
        return await run_in_threadpool(function, *args, **kwargs)
    wrapped.__signature__ = signature(function, eval_str=True)
    return wrapped
