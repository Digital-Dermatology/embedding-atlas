# Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import json
import os
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

from .image_assets import IMAGE_RELATIVE_PATH, ImageAsset
from .utils import cache_path, to_parquet_bytes


class DataSource:
    def __init__(
        self,
        identifier: str,
        dataset: pd.DataFrame,
        metadata: dict,
        image_assets: dict[str, dict[str, ImageAsset]] | None = None,
        image_relative_path: str = IMAGE_RELATIVE_PATH,
        feedback_dir: str | os.PathLike[str] | None = None,
    ):
        self.identifier = identifier
        self.dataset = dataset
        self.metadata = metadata
        self.cache_path = cache_path("cache", self.identifier)
        if feedback_dir is not None:
            base = Path(feedback_dir)
            if not base.is_absolute():
                base = Path.cwd() / base
            base.mkdir(parents=True, exist_ok=True)
            self.feedback_path = (base / self.identifier).resolve()
            self.feedback_path.mkdir(parents=True, exist_ok=True)
        else:
            self.feedback_path = cache_path("feedback", self.identifier)
        self.image_assets = image_assets or {}
        self.image_relative_path = image_relative_path

    def cache_set(self, name: str, data):
        path = self.cache_path / name
        with open(path, "w") as f:
            json.dump(data, f)

    def cache_get(self, name: str):
        path = self.cache_path / name
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        else:
            return None

    def append_feedback(self, name: str, data):
        self.feedback_path.mkdir(parents=True, exist_ok=True)
        path = self.feedback_path / f"{name}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")

    def make_archive(self, static_path: str):
        io = BytesIO()
        with zipfile.ZipFile(io, "w", zipfile.ZIP_DEFLATED) as zip:
            zip.writestr(
                "data/metadata.json",
                json.dumps(
                    self.metadata
                    | {"isStatic": True, "database": {"type": "wasm", "load": True}}
                ),
            )
            zip.writestr("data/dataset.parquet", to_parquet_bytes(self.dataset))
            for root, _, files in os.walk(static_path):
                for fn in files:
                    p = os.path.relpath(os.path.join(root, fn), static_path)
                    zip.write(os.path.join(root, fn), p)
            for root, _, files in os.walk(self.cache_path):
                for fn in files:
                    p = os.path.join(
                        "data/cache",
                        os.path.relpath(os.path.join(root, fn), str(self.cache_path)),
                    )
                    zip.write(os.path.join(root, fn), p)
            if self.feedback_path.exists():
                for root, _, files in os.walk(self.feedback_path):
                    for fn in files:
                        p = os.path.join(
                            "data/feedback",
                            os.path.relpath(
                                os.path.join(root, fn), str(self.feedback_path)
                            ),
                        )
                        zip.write(os.path.join(root, fn), p)
            for column, assets in self.image_assets.items():
                for filename, asset in assets.items():
                    content, _mime = asset.load()
                    path = os.path.join(
                        "data",
                        self.image_relative_path,
                        column,
                        filename,
                    )
                    zip.writestr(path, content)
        return io.getvalue()

    def get_image_asset(self, column: str, filename: str) -> ImageAsset | None:
        return self.image_assets.get(column, {}).get(filename)
