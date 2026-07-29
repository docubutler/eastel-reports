from __future__ import annotations

from typing import Any


class FakeInsertResult:
    def __init__(self, inserted_count: int) -> None:
        self.inserted_count = inserted_count


class FakeDeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


class FakeUpdateResult:
    matched_count = 1


class FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self.indexes: list[dict[str, Any]] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append({"keys": keys, **kwargs})
        return kwargs.get("name", "index")

    def insert_one(self, document: dict[str, Any]) -> None:
        self.documents.append(dict(document))

    def bulk_write(self, operations, ordered: bool = False) -> FakeInsertResult:
        for operation in operations:
            self.documents.append(dict(operation._doc))
        return FakeInsertResult(len(operations))

    def find_one(self, query: dict[str, Any], projection=None):
        for document in self.documents:
            if _matches(document, query):
                return document
        return None

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> FakeUpdateResult:
        for document in self.documents:
            if _matches(document, query):
                document.update(update.get("$set", {}))
                break
        return FakeUpdateResult()

    def delete_many(self, query: dict[str, Any]) -> FakeDeleteResult:
        before = len(self.documents)
        self.documents = [document for document in self.documents if not _matches(document, query)]
        return FakeDeleteResult(before - len(self.documents))


class FakeDb:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> FakeCollection:
        self.collections[name] = FakeCollection()
        return self.collections[name]

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in query.items())
