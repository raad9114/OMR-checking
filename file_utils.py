from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Iterable, List, Tuple

import cv2
import fitz
import numpy as np


def expand_upload_to_images(upload_path: str | Path, work_dir: str | Path) -> List[Tuple[Path, int]]:
    source = Path(upload_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix != ".pdf":
        return [(source, 1)]

    document = fitz.open(source)
    outputs: List[Tuple[Path, int]] = []
    for page_index in range(len(document)):
        page = document[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
        else:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        out = work / f"{source.stem}_page_{page_index + 1}.jpg"
        cv2.imwrite(str(out), image)
        outputs.append((out, page_index + 1))
    return outputs


def unique_folder(base: Path) -> Path:
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = base.parent / f"{base.name}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def make_zip(source_dir: str | Path, zip_path: str | Path) -> Path:
    source = Path(source_dir)
    destination = Path(zip_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in source.rglob("*"):
            if file.is_file():
                archive.write(file, file.relative_to(source))
    return destination
