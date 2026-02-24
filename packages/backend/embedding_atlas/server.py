# Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import asyncio
import concurrent.futures
import json
import os
import math
import mimetypes
import re
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable
from datetime import datetime, timezone

import duckdb
import numpy as np
from fastapi import FastAPI, File, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .data_source import DataSource
from .image_assets import IMAGE_TOKEN_PREFIX
from .utils import arrow_to_bytes, to_parquet_bytes


def make_server(
    data_source: DataSource,
    static_path: str,
    duckdb_uri: str | None = None,
    upload_pipeline=None,
    upload_projection_model=None,
    vector_neighbor_column: str | None = None,
    id_column: str | None = None,
    max_neighbor_results: int = 50,
    frontend_route_prefixes: Iterable[str] | None = None,
):
    """Creates a server for hosting Embedding Atlas"""

    app = FastAPI()
    frontend_routes = {
        prefix.strip("/")
        for prefix in (frontend_route_prefixes or [])
        if prefix and prefix.strip("/")
    }
    index_path = Path(static_path) / "index.html" if frontend_routes else None
    if index_path is not None and not index_path.exists():
        index_path = None
        frontend_routes.clear()
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

    metadata_props = (
        data_source.metadata.get("props", {})
        if isinstance(data_source.metadata, dict)
        else {}
    )
    data_meta = (
        metadata_props.get("data", {}) if isinstance(metadata_props, dict) else {}
    )
    id_column = id_column or data_meta.get("id")
    dataset_df = data_source.dataset
    feedback_lock = threading.Lock()
    total_rows = len(dataset_df)
    if (
        vector_neighbor_column is not None
        and vector_neighbor_column not in dataset_df.columns
    ):
        vector_neighbor_column = None
    try:
        max_neighbor_results = max(1, int(max_neighbor_results))
    except (TypeError, ValueError):
        max_neighbor_results = 50
    json_scalar_types = (str, int, float, bool)

    MIME_EXTENSION_OVERRIDES = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/x-icon": ".ico",
    }

    def _extension_for_mime(mime: str | None) -> str:
        if not mime:
            return ".bin"
        lower = mime.lower()
        if lower in MIME_EXTENSION_OVERRIDES:
            return MIME_EXTENSION_OVERRIDES[lower]
        guess = mimetypes.guess_extension(lower)
        if guess:
            return guess
        return ".bin"

    def _persist_query_images(record_id: str, row) -> list[dict[str, str]]:
        if (
            row is None
            or data_source.image_assets is None
            or len(data_source.image_assets) == 0
        ):
            return []
        images: list[dict[str, str]] = []
        base_dir = data_source.feedback_path / "query-images" / record_id
        for column in data_source.image_assets.keys():
            try:
                token = row[column] if hasattr(row, "__getitem__") else None
            except Exception:
                token = None
            if not isinstance(token, str) or not token.startswith(IMAGE_TOKEN_PREFIX):
                continue
            suffix = token[len(IMAGE_TOKEN_PREFIX) :]
            if "/" not in suffix:
                continue
            token_column, filename = suffix.split("/", 1)
            filename = Path(filename).name
            asset = data_source.get_image_asset(token_column, filename)
            if asset is None:
                continue
            try:
                content, mime = asset.load()
            except Exception:
                continue
            extension = Path(filename).suffix
            if not extension:
                extension = _extension_for_mime(mime)
            base_dir.mkdir(parents=True, exist_ok=True)
            dest_name = filename if filename else f"{token_column}{extension}"
            dest_path = base_dir / dest_name
            if dest_path.exists():
                dest_path = base_dir / f"{Path(dest_name).stem}-{record_id}{extension}"
            with open(dest_path, "wb") as f:
                f.write(content)
            try:
                rel_path = dest_path.relative_to(data_source.feedback_path)
            except ValueError:
                rel_path = dest_path
            if hasattr(rel_path, "as_posix"):
                rel_path_str = rel_path.as_posix()
            else:
                rel_path_str = str(rel_path)
            images.append(
                {
                    "column": token_column,
                    "token": token,
                    "path": rel_path_str,
                    "mime": mime,
                }
            )
        return images

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

    def _is_safe_predicate(predicate: str) -> bool:
        if predicate is None:
            return True
        lowered = predicate.lower()
        if ";" in predicate:
            return False
        if "--" in predicate or "/*" in predicate or "*/" in predicate:
            return False
        if "attach " in lowered or "copy " in lowered:
            return False
        return True

    def _safe_float(value):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
        return None

    def _safe_int(value):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return int(value)
        return None

    def _clinical_feedback_summary(payload: dict, record: dict):
        answers = (
            payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
        )
        search = (
            payload.get("search") if isinstance(payload.get("search"), dict) else {}
        )
        top_results = search.get("topResults")
        distances = []
        if isinstance(top_results, list):
            for item in top_results:
                if isinstance(item, dict):
                    dist = _safe_float(item.get("distance"))
                    if dist is not None:
                        distances.append(dist)
        avg_distance = sum(distances) / len(distances) if distances else None
        min_distance = min(distances) if distances else None
        max_distance = max(distances) if distances else None
        benefit_score = _safe_int(answers.get("benefitScore"))
        total_results = _safe_int(search.get("totalResults"))
        selected = answers.get("selectedMostSimilar")
        if isinstance(selected, dict):
            selected_sample_id = selected.get("id")
            selected_sample_rank = _safe_int(selected.get("rank"))
            selected_sample_distance = _safe_float(selected.get("distance"))
            selected_sample_condition = selected.get("condition")
        else:
            selected_sample_id = None
            selected_sample_rank = None
            selected_sample_distance = None
            selected_sample_condition = None
        none_are_similar = bool(answers.get("noneAreSimilar", False))
        summary = {
            "id": record.get("id"),
            "receivedAt": record.get("receivedAt"),
            "dataset": record.get("dataset"),
            "route": record.get("route"),
            "client": record.get("client"),
            "searchSignature": payload.get("searchSignature"),
            "mode": search.get("mode"),
            "queryDisplay": search.get("queryDisplay"),
            "benefitScore": benefit_score,
            "differentialDiagnosisInTop10": selected_sample_id is not None,
            "selectedSampleId": selected_sample_id,
            "selectedSampleRank": selected_sample_rank,
            "selectedSampleDistance": selected_sample_distance,
            "selectedSampleCondition": selected_sample_condition,
            "noneAreSimilar": none_are_similar,
            "wantsComment": answers.get("wantsComment"),
            "comment": answers.get("comment"),
            "totalResults": total_results,
            "avgDistance": avg_distance,
            "minDistance": min_distance,
            "maxDistance": max_distance,
            "queryRowIndex": record.get("queryRowIndex"),
            "queryRowId": record.get("queryRowId"),
        }
        return summary

    def _locate_row_by_identifier(raw_identifier: str):
        if id_column is None or id_column not in dataset_df.columns:
            return None, None

        series = dataset_df[id_column]
        key = raw_identifier
        dtype = getattr(series.dtype, "kind", None)

        if dtype in {"i", "u"}:  # integer / unsigned
            try:
                key = int(raw_identifier)
            except ValueError:
                pass
        elif dtype == "f":
            try:
                key = float(raw_identifier)
            except ValueError:
                pass
        elif dtype == "b":
            lowered = raw_identifier.strip().lower()
            if lowered in {"true", "1", "t", "yes"}:
                key = True
            elif lowered in {"false", "0", "f", "no"}:
                key = False

        mask = series == key
        rows = series[mask]
        if len(rows) > 0:
            return rows.index[0], rows.iloc[0]

        try:
            str_mask = series.astype(str) == raw_identifier
            rows = series[str_mask]
            if len(rows) > 0:
                return rows.index[0], rows.iloc[0]
        except Exception:
            pass

        return None, None

    def _extract_client_ip_chain(req: Request) -> list[str]:
        """Return ordered list of IP-like values derived from proxy headers."""
        addresses: list[str] = []
        seen: set[str] = set()

        def _add(raw_value):
            if not raw_value:
                return
            cleaned = str(raw_value).strip().strip('"').strip("'")
            if not cleaned:
                return
            if cleaned.startswith("[") and "]" in cleaned:
                closing = cleaned.find("]")
                if closing > 0:
                    cleaned = cleaned[1:closing]
            if ":" in cleaned and cleaned.count(":") == 1 and "." in cleaned:
                host, port = cleaned.split(":", 1)
                if host and port.isdigit():
                    cleaned = host
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                addresses.append(cleaned)

        forwarded_for = req.headers.get("x-forwarded-for")
        if forwarded_for:
            for part in forwarded_for.split(","):
                _add(part)

        forwarded = req.headers.get("forwarded")
        if forwarded:
            for entry in forwarded.split(","):
                for segment in entry.split(";"):
                    key, _, value = segment.partition("=")
                    if key.strip().lower() == "for":
                        _add(value)
                        break

        for header_name in ("x-real-ip", "cf-connecting-ip", "true-client-ip"):
            _add(req.headers.get(header_name))

        if req.client and req.client.host:
            _add(req.client.host)

        return addresses

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

    @app.post("/data/clinical-feedback")
    async def post_clinical_feedback(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON payload."}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"error": "Invalid feedback payload."}, status_code=400)
        client_ips = _extract_client_ip_chain(request)
        record = {
            "id": str(uuid.uuid4()),
            "dataset": data_source.identifier,
            "receivedAt": datetime.now(timezone.utc).isoformat(),
            "client": client_ips[0] if client_ips else None,
            "clientIps": client_ips,
            "route": payload.get("route"),
            "payload": payload,
        }
        search_meta = (
            payload.get("search", {}) if isinstance(payload.get("search"), dict) else {}
        )
        query_value = search_meta.get("query")
        query_row_index = None
        query_row = None
        if query_value is not None:
            try:
                row_index, _row_id = _locate_row_by_identifier(str(query_value))
            except Exception:
                row_index = None
            if row_index is not None:
                query_row_index = int(row_index)
                try:
                    query_row = dataset_df.iloc[int(row_index)]
                except Exception:
                    query_row = None
        if query_row_index is not None:
            record["queryRowIndex"] = query_row_index
            if (
                id_column is not None
                and query_row is not None
                and id_column in query_row.index
            ):
                record["queryRowId"] = _json_scalar(query_row[id_column])
        summary_fields = [
            "id",
            "receivedAt",
            "dataset",
            "route",
            "client",
            "searchSignature",
            "mode",
            "queryDisplay",
            "benefitScore",
            "differentialDiagnosisInTop10",
            "selectedSampleId",
            "selectedSampleRank",
            "selectedSampleDistance",
            "selectedSampleCondition",
            "noneAreSimilar",
            "wantsComment",
            "comment",
            "totalResults",
            "avgDistance",
            "minDistance",
            "maxDistance",
            "queryRowIndex",
            "queryRowId",
        ]
        try:
            with feedback_lock:
                if query_row is not None:
                    query_images = _persist_query_images(record["id"], query_row)
                    if query_images:
                        record["queryImages"] = query_images
                summary = _clinical_feedback_summary(payload, record)
                data_source.append_feedback("clinical", record)
                data_source.append_feedback_csv("feedback", summary, summary_fields)
        except Exception:
            return JSONResponse({"error": "Failed to store feedback."}, status_code=500)
        return JSONResponse({"status": "ok"})

    @app.get("/data/archive.zip")
    async def make_archive():
        data = data_source.make_archive(static_path)
        return Response(content=data, media_type="application/zip")

    @app.post("/data/upload-neighbors")
    async def upload_neighbors(file: UploadFile = File(...), k: int = 16):
        if upload_pipeline is None:
            return JSONResponse(
                {"error": "Upload search unavailable."}, status_code=404
            )

        try:
            contents = await file.read()
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to read upload: {exc}"}, status_code=400
            )

        vector = None
        try:
            vector = upload_pipeline.embed_bytes(contents)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to embed image: {exc}"}, status_code=500
            )

        try:
            search_limit = max(1, min(int(k), max_neighbor_results))
        except (TypeError, ValueError):
            search_limit = max_neighbor_results
        try:
            indices, distances = upload_pipeline.find_nearest_neighbors(
                vector, k=search_limit
            )
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to process image: {exc}"}, status_code=500
            )

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

    @app.get("/data/text-neighbors")
    async def text_neighbors(q: str, k: int = 16):
        if upload_pipeline is None:
            return JSONResponse({"error": "Text search unavailable."}, status_code=404)
        if q is None or str(q).strip() == "":
            return JSONResponse({"neighbors": [], "query": None})

        try:
            vector = upload_pipeline.encode_text(str(q))
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to embed text: {exc}"}, status_code=500
            )

        try:
            search_limit = max(1, min(int(k), max_neighbor_results))
        except (TypeError, ValueError):
            search_limit = max_neighbor_results
        try:
            indices, distances = upload_pipeline.find_nearest_neighbors(
                vector, k=search_limit
            )
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to process text: {exc}"}, status_code=500
            )

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
        if coords is not None and len(coords) >= 2:
            query_point = {"x": float(coords[0]), "y": float(coords[1])}
        return JSONResponse({"neighbors": neighbors, "query": query_point})

    @app.post("/data/upload-embeddings")
    async def upload_embeddings(files: list[UploadFile] = File(...)):
        if upload_pipeline is None:
            return JSONResponse(
                {"error": "Upload embedding unavailable."}, status_code=404
            )

        if files is None or len(files) == 0:
            return JSONResponse({"error": "No files uploaded."}, status_code=400)

        try:
            max_items = max(1, int(os.environ.get("ATLAS_UPLOAD_BATCH_LIMIT", "64")))
        except ValueError:
            max_items = 64

        selected_files = list(files)[:max_items]
        truncated = len(files) > len(selected_files)

        points: list[dict[str, object]] = []
        errors: list[dict[str, str]] = []
        novelty_k = 10

        for index, file in enumerate(selected_files):
            label = file.filename or f"sample-{index + 1}"
            try:
                contents = await file.read()
            except Exception as exc:
                errors.append(
                    {"label": label, "message": f"Failed to read upload: {exc}"}
                )
                continue

            try:
                vector = upload_pipeline.embed_bytes(contents)
            except Exception as exc:
                errors.append({"label": label, "message": f"Failed to embed: {exc}"})
                continue

            coords = None
            try:
                coords = upload_pipeline.project_vector(vector)
            except Exception:
                coords = None

            if coords is None and upload_projection_model is not None:
                try:
                    transformed = upload_projection_model.transform(
                        vector.reshape(1, -1)
                    )
                    if getattr(transformed, "ndim", 0) >= 2:
                        transformed = transformed[0]
                    coords = transformed
                except Exception:
                    coords = None

            if coords is None or len(coords) < 2:
                errors.append(
                    {
                        "label": label,
                        "message": "Embedding did not produce coordinates.",
                    }
                )
                continue

            x_value = float(coords[0])
            y_value = float(coords[1])
            if not np.isfinite(x_value) or not np.isfinite(y_value):
                errors.append(
                    {"label": label, "message": "Non-finite coordinates returned."}
                )
                continue

            avg_distance = None
            try:
                nn_indices, nn_distances = upload_pipeline.find_nearest_neighbors(
                    vector, k=min(novelty_k, total_rows)
                )
                valid = [
                    float(d)
                    for d in (nn_distances or [])
                    if d is not None and np.isfinite(d)
                ]
                if len(valid) > 0:
                    avg_distance = float(np.mean(valid[:novelty_k]))
            except Exception:
                avg_distance = None

            points.append(
                {
                    "id": uuid.uuid4().hex,
                    "label": label,
                    "x": x_value,
                    "y": y_value,
                    "order": index,
                    "avgDistance": avg_distance,
                }
            )

        response: dict[str, object] = {"points": points, "errors": errors}
        if truncated:
            response["truncated"] = True
            response["limit"] = len(selected_files)
        return JSONResponse(response)

    @app.get("/data/point-neighbors")
    async def point_neighbors(id: str, k: int = 50):
        if (
            upload_pipeline is None
            or vector_neighbor_column is None
            or id_column is None
            or id_column not in dataset_df.columns
        ):
            return JSONResponse(
                {"error": "Point neighbor search unavailable."}, status_code=404
            )

        try:
            limit = max(1, min(int(k), max_neighbor_results))
        except (TypeError, ValueError):
            limit = max_neighbor_results

        row_index, actual_identifier = _locate_row_by_identifier(id)
        if row_index is None:
            return JSONResponse(
                {"error": f"Identifier '{id}' not found."}, status_code=404
            )

        try:
            vector_value = dataset_df.at[row_index, vector_neighbor_column]
        except KeyError:
            return JSONResponse({"error": "Vector column missing."}, status_code=500)

        try:
            vector = np.asarray(vector_value, dtype=np.float32).reshape(-1)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to load vector: {exc}"}, status_code=500
            )

        if vector.size == 0:
            return JSONResponse({"error": "Vector column is empty."}, status_code=500)

        neighbors_k = min(limit + 1, max_neighbor_results + 1, total_rows)
        try:
            indices, distances = upload_pipeline.find_nearest_neighbors(
                vector, k=neighbors_k
            )
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to compute neighbors: {exc}"}, status_code=500
            )

        id_values = dataset_df[id_column].tolist()
        neighbors = []
        has_more = False
        for idx_val, dist in zip(list(indices or []), list(distances or [])):
            if idx_val is None or idx_val < 0 or idx_val >= len(id_values):
                continue
            neighbor_id = id_values[idx_val]
            if neighbor_id == actual_identifier:
                continue
            neighbors.append(
                {
                    "id": _json_scalar(neighbor_id),
                    "distance": float(dist),
                }
            )
            if len(neighbors) >= limit:
                has_more = len(neighbors) >= limit and neighbors_k > limit
                break

        return JSONResponse({"neighbors": neighbors, "hasMore": has_more})

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

    duckdb_connection_holder: dict[str, duckdb.DuckDBPyConnection | None] = {
        "conn": None
    }
    duckdb_connection_lock = threading.Lock()

    def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
        conn = duckdb_connection_holder["conn"]
        if conn is not None:
            return conn
        with duckdb_connection_lock:
            conn = duckdb_connection_holder["conn"]
            if conn is None:
                duckdb_connection_holder["conn"] = make_duckdb_connection(
                    data_source.dataset
                )
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
            if format not in formats:
                return JSONResponse(
                    {"error": f"Unsupported export format '{format}'."},
                    status_code=400,
                )
            if predicate is not None and not _is_safe_predicate(str(predicate)):
                return JSONResponse(
                    {"error": "Unsafe predicate rejected."}, status_code=400
                )
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
    if index_path is not None and frontend_routes:
        for prefix in frontend_routes:
            target = f"/?atlas_route={prefix}"

            async def _redirect_get(prefix_target: str = target):
                return RedirectResponse(prefix_target, status_code=307)

            async def _redirect_head(prefix_target: str = target):
                return RedirectResponse(prefix_target, status_code=307)

            async def _redirect_subpath(_path: str, prefix_target: str = target):
                return RedirectResponse(prefix_target, status_code=307)

            app.add_api_route(
                f"/{prefix}",
                _redirect_get,
                methods=["GET"],
                include_in_schema=False,
                name=f"{prefix}-redirect-get",
            )
            app.add_api_route(
                f"/{prefix}",
                _redirect_head,
                methods=["HEAD"],
                include_in_schema=False,
                name=f"{prefix}-redirect-head",
            )
            app.add_api_route(
                f"/{prefix}/{{path:path}}",
                _redirect_subpath,
                methods=["GET", "HEAD"],
                include_in_schema=False,
                name=f"{prefix}-redirect-subpath",
            )

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
