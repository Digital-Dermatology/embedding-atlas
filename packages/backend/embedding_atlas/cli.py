# Copyright (c) 2025 Apple Inc. Licensed under MIT License.

"""Command line interface."""

import logging
import pathlib
import socket
import json
import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import inquirer
import numpy as np
import pandas as pd
import uvicorn
import joblib

from .data_source import DataSource
from .image_assets import (
    IMAGE_RELATIVE_PATH,
    IMAGE_TOKEN_PREFIX,
    extract_image_assets,
)
from .options import make_embedding_atlas_props
from .server import make_server
from .utils import Hasher, load_huggingface_data, load_pandas_data
from .upload_pipeline import create_upload_pipeline
from .version import __version__

logger = logging.getLogger(__name__)


def find_column_name(existing_names, candidate):
    if candidate not in existing_names:
        return candidate
    else:
        index = 1
        while True:
            s = f"{candidate}_{index}"
            if s not in existing_names:
                return s
            index += 1


def determine_and_load_data(filename: str, splits: list[str] | None = None):
    suffix = Path(filename).suffix.lower()
    hf_prefix = "hf://datasets/"

    # Override Hugging Face data if given full url
    if filename.startswith(hf_prefix):
        filename = filename.split(hf_prefix)[-1]

    # Hugging Face data
    if (len(filename.split("/")) <= 2) and (suffix == ""):
        df = load_huggingface_data(filename, splits)
    else:
        df = load_pandas_data(filename)

    return df


SOURCE_DIR_COLUMN_NAME = "__embedding_atlas_source_dir__"


def _values_to_numpy(series: pd.Series) -> np.ndarray:
    arrays = []
    for value in series:
        if isinstance(value, np.ndarray):
            arr = value.astype(np.float32, copy=False)
        elif isinstance(value, (list, tuple)):
            arr = np.asarray(value, dtype=np.float32)
        elif isinstance(value, str):
            parsed = None
            try:
                parsed = json.loads(value)
            except Exception:
                try:
                    parsed = ast.literal_eval(value)
                except Exception:
                    parsed = None
            if isinstance(parsed, (list, tuple)):
                arr = np.asarray(parsed, dtype=np.float32)
            elif isinstance(parsed, np.ndarray):
                arr = parsed.astype(np.float32, copy=False)
            else:
                raise ValueError(
                    "String value could not be parsed into a numeric array"
                )
        else:
            raise ValueError(f"Unsupported vector value type: {type(value)}")
        if arr.ndim != 1:
            raise ValueError("Vector values must be 1-dimensional")
        arrays.append(arr)
    try:
        matrix = np.vstack(arrays)
    except ValueError as exc:
        raise ValueError(f"Failed to stack vector column values: {exc}") from exc
    return matrix.astype(np.float32, copy=False)


@dataclass
class ProjectionInfo:
    x_column: str
    y_column: str
    reducer: Any


def _load_umap_model(model_path: Path):
    try:
        return joblib.load(model_path)
    except Exception as exc:
        logger.warning("Failed to load UMAP model %s: %s", model_path, exc)

    try:
        import pynndescent

        NNDescent = pynndescent.NNDescent
        if not hasattr(NNDescent, "quantization"):
            NNDescent.quantization = None  # type: ignore[attr-defined]
            logger.info(
                "Patched NNDescent with missing 'quantization' attribute"
            )
        if not hasattr(NNDescent, "_min_distance"):
            NNDescent._min_distance = None  # type: ignore[attr-defined]
            logger.info(
                "Patched NNDescent with missing '_min_distance' attribute"
            )
        return joblib.load(model_path)
    except Exception as exc:
        logger.warning(
            "Failed to load UMAP model %s even after NNDescent patch: %s",
            model_path,
            exc,
        )
        return None


def apply_saved_umap_projection(
    df: pd.DataFrame, vector_column: str, upload_config_path: str
) -> ProjectionInfo | None:
    if vector_column not in df.columns:
        return None
    config_path = Path(upload_config_path).resolve()
    if not config_path.exists():
        logger.warning(
            "Upload config %s not found; cannot load saved UMAP.", config_path
        )
        return None
    try:
        with config_path.open("r") as f:
            config = json.load(f)
    except Exception as exc:
        logger.warning("Failed to read upload config %s: %s", config_path, exc)
        return None
    umap_cfg = config.get("umap") or {}
    model_rel = umap_cfg.get("model")
    if not model_rel:
        logger.info("Upload config %s does not specify a UMAP model.", config_path)
        return None
    model_path = (config_path.parent / model_rel).resolve()
    if not model_path.exists():
        logger.warning("UMAP model %s referenced in config is missing.", model_path)
        return None
    try:
        reducer = _load_umap_model(model_path)
    except Exception as exc:
        logger.warning("Failed to load UMAP model %s: %s", model_path, exc)
        return None
    if reducer is None:
        return None
    try:
        vectors = _values_to_numpy(df[vector_column])
    except Exception as exc:
        logger.warning(
            "Could not convert vector column '%s' into numpy arrays: %s",
            vector_column,
            exc,
        )
        return None
    try:
        coords = reducer.transform(vectors)
    except Exception as exc:
        logger.warning("Saved UMAP model failed to transform vectors: %s", exc)
        return None
    if coords.ndim != 2 or coords.shape[1] < 2:
        logger.warning("UMAP transform output has unexpected shape %s", coords.shape)
        return None
    df["projection_x"] = coords[:, 0]
    df["projection_y"] = coords[:, 1]
    logger.info(
        "Applied saved UMAP model from %s to project vector column '%s'.",
        model_path,
        vector_column,
    )
    return ProjectionInfo(
        x_column="projection_x", y_column="projection_y", reducer=reducer
    )


def load_datasets(
    inputs: list[str], splits: list[str] | None = None, sample: int | None = None
) -> pd.DataFrame:
    existing_column_names = set()
    dataframes = []
    for fn in inputs:
        print("Loading data from " + fn)
        df = determine_and_load_data(fn, splits=splits)
        source_path_str: str | None = None
        if "://" not in fn:
            source_path = pathlib.Path(fn)
            try:
                if source_path.is_file():
                    source_path_str = str(source_path.resolve().parent)
                elif source_path.exists():
                    source_path_str = str(source_path.resolve())
            except OSError:
                source_path_str = None
        df[SOURCE_DIR_COLUMN_NAME] = source_path_str
        dataframes.append(df)
        for c in df.columns:
            existing_column_names.add(c)

    file_name_column = find_column_name(existing_column_names, "FILE_NAME")
    for df, fn in zip(dataframes, inputs):
        df[file_name_column] = fn

    df = pd.concat(dataframes)

    if sample:
        df = df.sample(n=sample, axis=0, random_state=np.random.RandomState(42))

    return df


def prompt_for_column(df: pd.DataFrame, message: str) -> str | None:
    question = [
        inquirer.List(
            "arg",
            message=message,
            choices=sorted(["(none)"] + [str(c) for c in df.columns]),
        ),
    ]
    r = inquirer.prompt(question)
    if r is None:
        return None
    text = r["arg"]  # type: ignore
    if text == "(none)":
        text = None
    return text


def find_available_port(start_port: int, max_attempts: int = 10, host="localhost"):
    """Find the next available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError("No available ports found in the given range")


@click.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option("--text", default=None, help="Column containing text data.")
@click.option("--image", default=None, help="Column containing image data.")
@click.option(
    "--vector", default=None, help="Column containing pre-computed vector embeddings."
)
@click.option(
    "--split",
    default=[],
    multiple=True,
    help="Dataset split name(s) to load from Hugging Face datasets. Can be specified multiple times for multiple splits.",
)
@click.option(
    "--enable-projection/--disable-projection",
    "enable_projection",
    default=True,
    help="Compute embedding projections from text/image/vector data. If disabled without pre-computed projections, the embedding view will be unavailable.",
)
@click.option(
    "--model",
    default=None,
    help="Model name for generating embeddings (e.g., 'all-MiniLM-L6-v2').",
)
@click.option(
    "--trust-remote-code",
    is_flag=True,
    default=False,
    help="Allow execution of remote code when loading models from Hugging Face Hub.",
)
@click.option(
    "--batch-size",
    type=int,
    default=None,
    help="Batch size for processing embeddings (default: 32 for text, 16 for images). Larger values use more memory but may be faster.",
)
@click.option(
    "--x",
    "x_column",
    help="Column containing pre-computed X coordinates for the embedding view.",
)
@click.option(
    "--y",
    "y_column",
    help="Column containing pre-computed Y coordinates for the embedding view.",
)
@click.option(
    "--neighbors",
    "neighbors_column",
    help='Column containing pre-computed nearest neighbors in format: {"ids": [n1, n2, ...], "distances": [d1, d2, ...]}. IDs should be zero-based row indices.',
)
@click.option(
    "--sample",
    default=None,
    type=int,
    help="Number of random samples to draw from the dataset. Useful for large datasets.",
)
@click.option(
    "--umap-n-neighbors",
    type=int,
    help="Number of neighbors to consider for UMAP dimensionality reduction (default: 15).",
)
@click.option(
    "--umap-min-dist",
    type=float,
    help="The min_dist parameter for UMAP.",
)
@click.option(
    "--umap-metric",
    default="cosine",
    help="Distance metric for UMAP computation (default: 'cosine').",
)
@click.option(
    "--umap-random-state", type=int, help="Random seed for reproducible UMAP results."
)
@click.option(
    "--duckdb",
    type=str,
    default="server",
    help="DuckDB connection mode: 'wasm' (run in browser), 'server' (run on this server), or URI (e.g., 'ws://localhost:3000').",
)
@click.option(
    "--host",
    default="localhost",
    help="Host address for the web server (default: localhost).",
)
@click.option(
    "--port", default=5055, help="Port number for the web server (default: 5055)."
)
@click.option(
    "--auto-port/--no-auto-port",
    "enable_auto_port",
    default=True,
    help="Automatically find an available port if the specified port is in use.",
)
@click.option(
    "--static", type=str, help="Custom path to frontend static files directory."
)
@click.option(
    "--export-application",
    type=str,
    help="Export the visualization as a standalone web application to the specified ZIP file and exit.",
)
@click.option(
    "--point-size",
    type=float,
    default=None,
    help="Size of points in the embedding view (default: automatically calculated based on density).",
)
@click.option(
    "--stop-words",
    type=str,
    default=None,
    help="Path to a file containing stop words to exclude from the text embedding. The file should be a data frame with column 'word'",
)
@click.option(
    "--labels",
    type=str,
    default=None,
    help="Path to a file containing labels for the embedding view. The file should be a data frame with columns 'x', 'y', 'text', and optionally 'level' and 'priority'",
)
@click.option(
    "--label-column",
    type=str,
    default=None,
    help="Column to use for generating automatic cluster labels. If not specified, falls back to the text column.",
)
@click.option(
    "--upload-config",
    type=str,
    default=None,
    help="Path to SkinMap embedding_pipeline_config.json for enabling upload-based nearest-neighbor search.",
)
@click.option(
    "--upload-device",
    type=str,
    default="cpu",
    help="Device identifier to use for upload embedding inference (e.g., 'cpu' or 'cuda').",
)
@click.version_option(version=__version__, package_name="embedding_atlas")
def main(
    inputs,
    text: str | None,
    image: str | None,
    vector: str | None,
    split: list[str] | None,
    enable_projection: bool,
    model: str | None,
    trust_remote_code: bool,
    batch_size: int | None,
    x_column: str | None,
    y_column: str | None,
    neighbors_column: str | None,
    sample: int | None,
    umap_n_neighbors: int | None,
    umap_min_dist: int | None,
    umap_metric: str | None,
    umap_random_state: int | None,
    static: str | None,
    duckdb: str,
    host: str,
    port: int,
    enable_auto_port: bool,
    export_application: str | None,
    point_size: float | None,
    stop_words: str | None,
    labels: str | None,
    label_column: str | None,
    upload_config: str | None,
    upload_device: str,
):
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: (%(name)s) %(message)s",
    )

    logger.info("Embedding Atlas %s starting.", __version__)
    df = load_datasets(inputs, splits=split, sample=sample)

    logger.info("Loaded %d rows with %d columns.", df.shape[0], df.shape[1])

    saved_projection: ProjectionInfo | None = None
    if enable_projection and (x_column is None or y_column is None):
        used_saved_projection = False
        if vector is not None and upload_config is not None:
            saved_projection = apply_saved_umap_projection(df, vector, upload_config)
            if saved_projection is not None:
                x_column, y_column = (
                    saved_projection.x_column,
                    saved_projection.y_column,
                )
                used_saved_projection = True
        if not used_saved_projection:
            # No x, y column selected, first see if text/image/vectors column is specified, if not, ask for it
            if text is None and image is None and vector is None:
                text = prompt_for_column(
                    df, "Select a column you want to run the embedding on"
                )
            umap_args = {}
            if umap_min_dist is not None:
                umap_args["min_dist"] = umap_min_dist
            if umap_n_neighbors is not None:
                umap_args["n_neighbors"] = umap_n_neighbors
            if umap_random_state is not None:
                umap_args["random_state"] = umap_random_state
            if umap_metric is not None:
                umap_args["metric"] = umap_metric
            # Run embedding and projection
            if text is not None or image is not None or vector is not None:
                from .projection import (
                    compute_image_projection,
                    compute_text_projection,
                    compute_vector_projection,
                )

                x_column = find_column_name(df.columns, "projection_x")
                y_column = find_column_name(df.columns, "projection_y")
                if neighbors_column is None:
                    neighbors_column = find_column_name(df.columns, "__neighbors")
                    new_neighbors_column = neighbors_column
                else:
                    # If neighbors_column is already specified, don't overwrite it.
                    new_neighbors_column = None
                if vector is not None:
                    compute_vector_projection(
                        df,
                        vector,
                        x=x_column,
                        y=y_column,
                        neighbors=new_neighbors_column,
                        umap_args=umap_args,
                    )
                    logger.info(
                        "Computed vector projection using column '%s' into (%s, %s).",
                        vector,
                        x_column,
                        y_column,
                    )
                elif text is not None:
                    compute_text_projection(
                        df,
                        text,
                        x=x_column,
                        y=y_column,
                        neighbors=new_neighbors_column,
                        model=model,
                        trust_remote_code=trust_remote_code,
                        batch_size=batch_size,
                        umap_args=umap_args,
                    )
                    logger.info(
                        "Computed text projection using column '%s' into (%s, %s).",
                        text,
                        x_column,
                        y_column,
                    )
                elif image is not None:
                    compute_image_projection(
                        df,
                        image,
                        x=x_column,
                        y=y_column,
                        neighbors=new_neighbors_column,
                        model=model,
                        trust_remote_code=trust_remote_code,
                        batch_size=batch_size,
                        umap_args=umap_args,
                    )
                    logger.info(
                        "Computed image projection using column '%s' into (%s, %s).",
                        image,
                        x_column,
                        y_column,
                    )
                else:
                    raise RuntimeError("unreachable")

    id_column = find_column_name(df.columns, "_row_index")
    df[id_column] = range(df.shape[0])
    logger.info("Assigned row id column '%s'.", id_column)

    source_dirs = (
        df[SOURCE_DIR_COLUMN_NAME] if SOURCE_DIR_COLUMN_NAME in df.columns else None
    )
    image_assets, image_columns = extract_image_assets(
        df, id_column, source_dirs=source_dirs
    )
    logger.info("Detected %d image asset columns.", len(image_columns))
    if SOURCE_DIR_COLUMN_NAME in df.columns:
        df = df.drop(columns=[SOURCE_DIR_COLUMN_NAME])

    stop_words_resolved = None
    if stop_words is not None:
        stop_words_df = load_pandas_data(stop_words)
        stop_words_resolved = stop_words_df["word"].to_list()

    labels_resolved = None
    if labels is not None:
        labels_df = load_pandas_data(labels)
        labels_resolved = labels_df.to_dict("records")

    if neighbors_column is not None and neighbors_column not in df.columns:
        neighbors_column = None

    props = make_embedding_atlas_props(
        row_id=id_column,
        x=x_column,
        y=y_column,
        neighbors=neighbors_column,
        text=text,
        point_size=point_size,
        stop_words=stop_words_resolved,
        labels=labels_resolved,
        label_column=label_column,
    )

    metadata = {
        "props": props,
    }
    if image_assets:
        props.setdefault("assets", {})
        props["assets"]["images"] = {
            "tokenPrefix": IMAGE_TOKEN_PREFIX,
            "relativePath": IMAGE_RELATIVE_PATH,
            "columns": sorted(image_columns),
        }

    hasher = Hasher()
    hasher.update(__version__)
    hasher.update(inputs)
    hasher.update(metadata)
    identifier = hasher.hexdigest()

    dataset = DataSource(
        identifier,
        df,
        metadata,
        image_assets=image_assets,
        image_relative_path=IMAGE_RELATIVE_PATH,
    )

    vector_neighbors_endpoint = None
    max_point_neighbors = 500

    upload_pipeline = None
    if upload_config is not None:

        logger.info("Initializing upload pipeline from %s.", upload_config)
        upload_pipeline = create_upload_pipeline(
            upload_config,
            device=upload_device,
        )
        if upload_pipeline is not None:
            metadata["uploadSearch"] = {
                "enabled": True,
                "endpoint": "upload-neighbors",
                "batchEndpoint": "upload-embeddings",
            }
            logger.info("Upload pipeline enabled.")
            props.setdefault("data", {})
            props["data"]["textSearchEndpoint"] = "text-neighbors"
            if vector is not None and vector in df.columns:
                vector_neighbors_endpoint = "point-neighbors"
                try:
                    max_point_neighbors = max(
                        1, int(os.environ.get("ATLAS_POINT_NEIGHBORS_K", "500"))
                    )
                except ValueError:
                    max_point_neighbors = 500
                props.setdefault("data", {})
                props["data"]["vectorNeighborsEndpoint"] = vector_neighbors_endpoint
        else:
            logger.warning(
                "Upload pipeline could not be initialized; image upload disabled."
            )

    if static is None:
        static = str((pathlib.Path(__file__).parent / "static").resolve())
        logger.info("Using bundled static assets at %s.", static)
    else:
        logger.info("Using custom static assets at %s.", static)

    if export_application is not None:
        with open(export_application, "wb") as f:
            f.write(dataset.make_archive(static))
        exit(0)

    app = make_server(
        dataset,
        static_path=static,
        duckdb_uri=duckdb,
        upload_pipeline=upload_pipeline,
        upload_projection_model=(
            saved_projection.reducer if saved_projection is not None else None
        ),
        vector_neighbor_column=(
            vector if vector_neighbors_endpoint is not None else None
        ),
        id_column=id_column,
        max_neighbor_results=max_point_neighbors,
    )

    if enable_auto_port:
        new_port = find_available_port(port, max_attempts=10, host=host)
        if new_port != port:
            logging.info(f"Port {port} is not available, using {new_port}")
    else:
        new_port = port
    logger.info("Starting server on %s:%d (duckdb=%s).", host, new_port, duckdb)
    uvicorn.run(app, port=new_port, host=host, access_log=False)


if __name__ == "__main__":
    main()
