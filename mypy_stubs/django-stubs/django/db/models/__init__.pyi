from typing import Any

class Model:
    id: int
    pk: int
    objects: Any

    def save(self, *args: Any, **kwargs: Any) -> None: ...
    def delete(self, *args: Any, **kwargs: Any) -> None: ...