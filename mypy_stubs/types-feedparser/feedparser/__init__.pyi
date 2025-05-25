from typing import Any, Dict, List, Optional, Union

class FeedParserDict(dict):
    def __getattr__(self, key: str) -> Any: ...
    def __setattr__(self, key: str, value: Any) -> None: ...

class _StubParser:
    bozo: bool
    entries: List[FeedParserDict]
    feed: FeedParserDict
    headers: Dict[str, str]
    href: str
    namespaces: Dict[str, str]
    version: str
    encoding: str
    bozo_exception: Optional[Exception]

def parse(
    url_file_stream_or_string: Union[str, bytes, Any],
    etag: Optional[str] = None,
    modified: Optional[str] = None,
    agent: Optional[str] = None,
    referrer: Optional[str] = None,
    handlers: Optional[List[Any]] = None,
    request_headers: Optional[Dict[str, str]] = None,
    response_headers: Optional[Dict[str, str]] = None,
) -> _StubParser: ...
