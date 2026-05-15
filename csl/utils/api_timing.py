"""接口计时与结果收集工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
import inspect
from time import perf_counter
from typing import Any, Callable, List, Optional, Tuple, TypeVar, cast

from models.result_model import ApiCallRecord

TimedResult = Tuple[int, Any]
CallableType = TypeVar("CallableType", bound=Callable[..., TimedResult])


@dataclass
class ApiCallCollector:
    """接口调用结果收集器。"""

    case_id: str = ""
    session_id: str = ""
    records: List[ApiCallRecord] = field(default_factory=list)

    def set_session_id(self, session_id: str) -> None:
        """更新当前会话标识。

        Args:
            session_id: 会话 ID。

        Returns:
            None
        """
        self.session_id = session_id

    def add_record(
        self,
        api_name: str,
        request_method: str,
        request_path: str,
        request_identifier: str,
        elapsed_ms: float,
        success: bool,
        status_code: int,
        error: str,
        session_id: str = "",
    ) -> None:
        """追加单次接口调用记录。

        Args:
            api_name: 接口名称。
            request_method: 请求方法。
            request_path: 请求路径。
            request_identifier: 接口关联标识。
            elapsed_ms: 接口耗时，单位毫秒。
            success: 是否成功。
            status_code: HTTP 状态码。
            error: 错误信息。
            session_id: 当前会话 ID。

        Returns:
            None
        """
        effective_session_id = session_id or self.session_id
        self.records.append(
            ApiCallRecord(
                api_name=api_name,
                request_method=request_method,
                request_path=request_path,
                request_identifier=request_identifier,
                case_id=self.case_id,
                session_id=effective_session_id,
                elapsed_ms=round(elapsed_ms, 2),
                success=success,
                status_code=status_code,
                error=error,
            )
        )


def timed_api_call() -> Callable[[CallableType], Callable[..., Any]]:
    """为接口调用函数添加统一计时与记录能力。

    约定被装饰函数返回 `(status_code, data)`。
    装饰器对外只返回 `data`，并在存在 `api_collector` 时写入耗时记录。

    Returns:
        Callable[[CallableType], Callable[..., Any]]: 装饰器函数。
    """

    def decorator(func: CallableType) -> Callable[..., Any]:
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound_args = signature.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()
            arguments = bound_args.arguments
            collector = cast(Optional[ApiCallCollector], arguments.get("api_collector"))
            api_name = str(arguments.get("api_name") or func.__name__)
            request_method = str(arguments.get("method") or "").upper()
            request_path = str(arguments.get("path") or "")
            request_identifier = str(arguments.get("request_identifier") or "")
            session_id = str(arguments.get("session_id") or "")
            started_at = perf_counter()
            status_code = 0
            success = False
            error_message = ""
            try:
                status_code, result = func(*args, **kwargs)
                success = True
                return result
            except Exception as exc:
                response = getattr(exc, "response", None)
                status_code = int(response.status_code) if response is not None else 0
                error_message = str(exc)
                raise
            finally:
                if collector is not None:
                    collector.add_record(
                        api_name=api_name,
                        request_method=request_method,
                        request_path=request_path,
                        request_identifier=request_identifier,
                        elapsed_ms=(perf_counter() - started_at) * 1000,
                        success=success,
                        status_code=status_code,
                        error=error_message,
                        session_id=session_id,
                    )

        return wrapper

    return decorator
