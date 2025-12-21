// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

/** Debounce the given function. */
export function debounce<T extends any[]>(func: (...args: T) => void, time: number = 1000): (...args: T) => void {
  let timeout: any | undefined = undefined;
  let perform = (...args: T) => {
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(() => {
      func(...args);
    }, time);
  };
  return perform;
}

export function startDrag(e1: MouseEvent | PointerEvent, callback: (dx: number, dy: number) => void) {
  e1.preventDefault();
  let x1 = e1.pageX;
  let y1 = e1.pageY;
  const isPointer = "pointerId" in e1;
  const pointerId = isPointer ? e1.pointerId : null;
  const target = (e1.currentTarget as HTMLElement | null) ?? null;
  if (isPointer && pointerId != null && target?.setPointerCapture) {
    target.setPointerCapture(pointerId);
  }
  const move = (e2: MouseEvent | PointerEvent) => {
    e2.preventDefault();
    let dx = e2.pageX - x1;
    let dy = e2.pageY - y1;
    callback(dx, dy);
  };
  const up = () => {
    if (isPointer && pointerId != null && target?.releasePointerCapture) {
      target.releasePointerCapture(pointerId);
    }
    if (isPointer) {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    } else {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    }
  };
  if (isPointer) {
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  } else {
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }
}

export function downloadBuffer(arrayBuffer: ArrayBuffer | Uint8Array<ArrayBuffer>, fileName: string) {
  let a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([arrayBuffer], { type: "application/octet-stream" }));
  a.download = fileName;
  a.click();
}

function parseCurrentDefaults(): Record<string, any> {
  let result = window.localStorage.getItem("embedding-atlas-defaults");
  if (result == null) {
    return {};
  }
  try {
    return JSON.parse(result);
  } catch {
    return {};
  }
}

export function getDefaults<T>(key: string, defaultValue: T, validate?: (value: T) => boolean): T {
  let v = parseCurrentDefaults()[key] ?? defaultValue;
  if (validate && !validate(v)) {
    return defaultValue;
  }
  return v;
}

export function setDefaults<T>(key: string, value: T) {
  let newRecords = parseCurrentDefaults();
  newRecords[key] = value;
  window.localStorage.setItem("embedding-atlas-defaults", JSON.stringify(newRecords));
}
