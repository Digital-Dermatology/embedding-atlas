# Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import asyncio
import concurrent.futures
import json
import os
import re
import threading
import uuid
from functools import lru_cache
from typing import Callable

import duckdb
from fastapi import FastAPI, File, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .data_source import DataSource
from .utils import arrow_to_bytes, to_parquet_bytes


def make_server(
    data_source: DataSource,
    static_path: str,
    duckdb_uri: str | None = None,
    upload_pipeline=None,
    upload_projection_model=None,
):
    """Creates a server for hosting Embedding Atlas"""

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    mount_bytes(
        app,
        "/data/dataset.parquet",
        "application/octet-stream",
        lambda: to_parquet_bytes(data_source.dataset),
    )

    metadata_props = data_source.metadata.get("props", {}) if isinstance(data_source.metadata, dict) else {}
    data_meta = metadata_props.get("data", {}) if isinstance(metadata_props, dict) else {}
    id_column = data_meta.get("id")
    dataset_df = data_source.dataset
    total_rows = len(dataset_df)
    json_scalar_types = (str, int, float, bool)

    def _json_scalar(value):
        if isinstance(value, json_scalar_types) or value is None:
            return value
        if hasattr(value, "item"):
            try:
                converted = value.item()
                if isinstance(converted, json_scalar_types) or converted is None:
                    return converted
            except Exception:
                pass
        if hasattr(value, "tolist"):
            try:
                converted = value.tolist()
                if isinstance(converted, json_scalar_types) or converted is None:
                    return converted
            except Exception:
                pass
        return str(value)

    @app.get("/data/metadata.json")
    async def get_metadata():
        if duckdb_uri is None or duckdb_uri == "wasm":
            db_meta = {"database": {"type": "wasm", "load": True}}
        elif duckdb_uri == "server":
            # Point to the server itself.
            # Note: We need to set URI explicitly for the REST connector
            db_meta = {"database": {"type": "rest", "uri": "/data/query"}}
        else:
            # Point to the given uri.
            if duckdb_uri.startswith("http"):
                db_meta = {
                    "database": {"type": "rest", "uri": duckdb_uri, "load": True}
                }
            elif duckdb_uri.startswith("ws"):
                db_meta = {
                    "database": {"type": "socket", "uri": duckdb_uri, "load": True}
                }
            else:
                raise ValueError("invalid DuckDB uri")
        return data_source.metadata | db_meta

    @app.post("/data/cache/{name}")
    async def post_cache(request: Request, name: str):
        data_source.cache_set(name, await request.json())

    @app.get("/data/cache/{name}")
    async def get_cache(name: str):
        obj = data_source.cache_get(name)
        if obj is None:
            return Response(status_code=404)
        return obj

    @app.get("/data/archive.zip")
    async def make_archive():
        data = data_source.make_archive(static_path)
        return Response(content=data, media_type="application/zip")

    @app.post("/data/upload-neighbors")
    async def upload_neighbors(file: UploadFile = File(...), k: int = 16):
        if upload_pipeline is None:
            return JSONResponse({"error": "Upload search unavailable."}, status_code=404)

        try:
            contents = await file.read()
        except Exception as exc:
            return JSONResponse({"error": f"Failed to read upload: {exc}"}, status_code=400)

        vector = None
        try:
            vector = upload_pipeline.embed_bytes(contents)
        except Exception as exc:
            return JSONResponse({"error": f"Failed to embed image: {exc}"}, status_code=500)

        search_limit = max(1, min(k, 1000))
        try:
            indices, distances = upload_pipeline.find_nearest_neighbors(vector, k=search_limit)
        except Exception as exc:
            return JSONResponse({"error": f"Failed to process image: {exc}"}, status_code=500)

        neighbors = []
        for idx, dist in zip(indices, distances):
            if idx is None or idx < 0 or idx >= total_rows:
                continue
            identifier = idx
            if id_column and id_column in dataset_df.columns:
                identifier = dataset_df.iloc[idx][id_column]
            neighbors.append(
                {
                    "id": _json_scalar(identifier),
                    "rowIndex": int(_json_scalar(idx)),
                    "distance": float(dist),
                }
            )
        query_point = None
        coords = None
        try:
            coords = upload_pipeline.project_vector(vector)
        except Exception:
            coords = None
        if coords is None and upload_projection_model is not None:
            try:
                transformed = upload_projection_model.transform(vector.reshape(1, -1))
                if transformed.ndim >= 2:
                    transformed = transformed[0]
                coords = transformed
            except Exception:
                coords = None
        if coords is not None and len(coords) >= 2:
            query_point = {"x": float(coords[0]), "y": float(coords[1])}
        return JSONResponse({"neighbors": neighbors, "query": query_point})

    @app.get("/data/images/{column}/{filename}")
    async def get_image(column: str, filename: str):
        asset = data_source.get_image_asset(column, filename)
        if asset is None:
            return Response(status_code=404)
        try:
            content, mime = asset.load()
        except FileNotFoundError:
            return Response(status_code=404)
        return Response(content=content, media_type=mime)

    duckdb_connection_holder: dict[str, duckdb.DuckDBPyConnection | None] = {"conn": None}
    duckdb_connection_lock = threading.Lock()

    def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
        conn = duckdb_connection_holder["conn"]
        if conn is not None:
            return conn
        with duckdb_connection_lock:
            conn = duckdb_connection_holder["conn"]
            if conn is None:
                duckdb_connection_holder["conn"] = make_duckdb_connection(data_source.dataset)
                conn = duckdb_connection_holder["conn"]
        return conn

    if duckdb_uri == "server":
        def handle_query(query: dict):
            sql = query["sql"]
            command = query["type"]
            conn = get_duckdb_connection()
            with conn.cursor() as cursor:
                try:
                    result = cursor.execute(sql)
                    if command == "exec":
                        return JSONResponse({})
                    elif command == "arrow":
                        buf = arrow_to_bytes(result.arrow())
                        return Response(
                            buf, headers={"Content-Type": "application/octet-stream"}
                        )
                    elif command == "json":
                        data = result.df().to_json(orient="records")
                        return Response(
                            data, headers={"Content-Type": "application/json"}
                        )
                    else:
                        raise ValueError(f"Unknown command {command}")
                except Exception as e:
                    return JSONResponse({"error": str(e)}, status_code=500)

        def handle_selection(query: dict):
            predicate = query.get("predicate", None)
            format = query["format"]
            formats = {
                "json": "(FORMAT JSON, ARRAY true)",
                "jsonl": "(FORMAT JSON)",
                "csv": "(FORMAT CSV)",
                "parquet": "(FORMAT parquet)",
            }
            conn = get_duckdb_connection()
            with conn.cursor() as cursor:
                filename = ".selection-" + str(uuid.uuid4()) + ".tmp"
                try:
                    if predicate is not None:
                        cursor.execute(
                            f"COPY (SELECT * FROM dataset WHERE {predicate}) TO '{filename}' {formats[format]}"
                        )
                    else:
                        cursor.execute(
                            f"COPY dataset TO '{filename}' {formats[format]}"
                        )
                    with open(filename, "rb") as f:
                        buffer = f.read()
                        return Response(
                            buffer,
                            headers={"Content-Type": "application/octet-stream"},
                        )
                except Exception as e:
                    return JSONResponse({"error": str(e)}, status_code=500)
                finally:
                    try:
                        os.unlink(filename)
                    except Exception:
                        pass

        executor = concurrent.futures.ThreadPoolExecutor()

        @app.get("/data/query")
        async def get_query(req: Request):
            data = json.loads(req.query_params["query"])
            return await asyncio.get_running_loop().run_in_executor(
                executor, lambda: handle_query(data)
            )

        @app.post("/data/query")
        async def post_query(req: Request):
            body = await req.body()
            data = json.loads(body)
            return await asyncio.get_running_loop().run_in_executor(
                executor, lambda: handle_query(data)
            )

        @app.post("/data/selection")
        async def post_selection(req: Request):
            body = await req.body()
            data = json.loads(body)
            return await asyncio.get_running_loop().run_in_executor(
                executor, lambda: handle_selection(data)
            )

    # Static files for the frontend
    app.mount("/", StaticFiles(directory=static_path, html=True))

    return app


def make_duckdb_connection(df):
    con = duckdb.connect(":memory:")
    _ = df  # used in the query
    con.sql("CREATE TABLE dataset AS (SELECT * FROM df)")
    return con


def parse_range_header(request: Request, content_length: int):
    value = request.headers.get("Range")
    if value is not None:
        m = re.match(r"^ *bytes *= *([0-9]+) *- *([0-9]+) *$", value)
        if m is not None:
            r0 = int(m.group(1))
            r1 = int(m.group(2)) + 1
            if r0 < r1 and r0 <= content_length and r1 <= content_length:
                return (r0, r1)
    return None


def mount_bytes(
    app: FastAPI, url: str, media_type: str, make_content: Callable[[], bytes]
):
    @lru_cache(maxsize=1)
    def get_content() -> bytes:
        return make_content()

    @app.head(url)
    async def head(request: Request):
        content = get_content()
        bytes_range = parse_range_header(request, len(content))
        if bytes_range is None:
            length = len(content)
        else:
            length = bytes_range[1] - bytes_range[0]
        return Response(
            headers={
                "Content-Length": str(length),
                "Content-Type": media_type,
            }
        )

    @app.get(url)
    async def get(request: Request):
        content = get_content()
        bytes_range = parse_range_header(request, len(content))
        if bytes_range is None:
            return Response(content=content)
        else:
            r0, r1 = bytes_range
            result = content[r0:r1]
            return Response(
                content=result,
                headers={
                    "Content-Length": str(r1 - r0),
                    "Content-Range": f"bytes {r0}-{r1 - 1}/{len(content)}",
                    "Content-Type": media_type,
                },
                media_type=media_type,
                status_code=206,
            )
