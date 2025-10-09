// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

export interface ImageAssetsConfig {
  tokenPrefix: string;
  baseUrl?: string | null;
  relativePath?: string | null;
  columns?: string[];
}

let imageAssetsConfig: ImageAssetsConfig | null = null;
const TOKEN_PREFIX = "ea://image/";

function base64Encode(data: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < data.length; i++) {
    binary += String.fromCharCode(data[i]);
  }
  return btoa(binary);
}

function base64Decode(base64: string): Uint8Array {
  const binaryString = atob(base64);
  return new Uint8Array([...binaryString].map((char) => char.charCodeAt(0)));
}

function startsWith(data: Uint8Array, prefix: number[]): boolean {
  if (data.length < prefix.length) {
    return false;
  }
  for (let i = 0; i < prefix.length; i++) {
    if (data[i] != prefix[i]) {
      return false;
    }
  }
  return true;
}

function detectImageType(data: Uint8Array): string {
  if (startsWith(data, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
    return "image/png";
  } else if (startsWith(data, [0xff, 0xd8, 0xff])) {
    return "image/jpeg";
  } else if (startsWith(data, [0x49, 0x49, 0x2a, 0x00])) {
    return "image/tiff";
  } else if (startsWith(data, [0x42, 0x4d])) {
    return "image/bmp";
  } else if (
    startsWith(data, [0x47, 0x49, 0x46, 0x38, 0x37, 0x61]) ||
    startsWith(data, [0x47, 0x49, 0x46, 0x38, 0x39, 0x61])
  ) {
    return "image/gif";
  }
  // Unknown, fallback to generic type
  return "application/octet-stream";
}

function joinUrl(base: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  if (!base) {
    return path;
  }
  if (base.endsWith("/")) {
    base = base.slice(0, -1);
  }
  if (path.startsWith("/")) {
    path = path.slice(1);
  }
  if (path === "") {
    return base;
  }
  return `${base}/${path}`;
}

function resolveToken(value: string): string | null {
  let prefix = imageAssetsConfig?.tokenPrefix ?? TOKEN_PREFIX;
  if (!value.startsWith(prefix)) {
    return null;
  }
  let remainder = value.slice(prefix.length);
  let config = imageAssetsConfig;
  let base = "";
  if (config?.baseUrl) {
    base = config.baseUrl;
  } else if (config?.relativePath) {
    base = joinUrl("data", config.relativePath);
  }
  return joinUrl(base, remainder);
}

const imageUrlPattern = /\.(png|jpe?g|gif|webp|bmp|tiff)(\?|#|$)/i;

function isLikelyImageUrl(value: string): boolean {
  return imageUrlPattern.test(value);
}

function resolveHttpUrl(value: string): string | null {
  if (
    value.startsWith("http://") ||
    value.startsWith("https://") ||
    value.startsWith("blob:") ||
    value.startsWith("/") ||
    value.startsWith("./") ||
    value.startsWith("../")
  ) {
    return isLikelyImageUrl(value) ? value : null;
  }
  return null;
}

export function setImageAssets(config: ImageAssetsConfig | null) {
  imageAssetsConfig = config;
}

export function getImageAssets(): ImageAssetsConfig | null {
  return imageAssetsConfig;
}

export function isImageReference(value: any): boolean {
  if (value == null) {
    return false;
  }
  if (typeof value == "string") {
    if (value.startsWith("data:image/")) {
      return true;
    }
    if (value.startsWith(TOKEN_PREFIX)) {
      return true;
    }
    if (resolveToken(value) != null) {
      return true;
    }
    if (isLikelyImageUrl(value)) {
      return true;
    }
    return false;
  }
  if (value?.bytes instanceof Uint8Array) {
    return true;
  }
  if (value instanceof Uint8Array) {
    return true;
  }
  return false;
}

export function imageToDataUrl(img: any): string | null {
  if (img == null) {
    return null;
  }
  if (typeof img == "string") {
    if (img.startsWith("data:")) {
      return img;
    }
    let tokenUrl = resolveToken(img);
    if (tokenUrl != null) {
      return tokenUrl;
    }
    let httpUrl = resolveHttpUrl(img);
    if (httpUrl != null) {
      return httpUrl;
    }
    try {
      let decoded = base64Decode(img);
      let type = detectImageType(decoded);
      return `data:${type};base64,` + img;
    } catch (e) {
      return null;
    }
  } else {
    let bytes: Uint8Array | null = null;
    if (img.bytes && img.bytes instanceof Uint8Array) {
      bytes = img.bytes;
    }
    if (img instanceof Uint8Array) {
      bytes = img;
    }
    if (bytes != null) {
      let type = detectImageType(bytes);
      return `data:${type};base64,` + base64Encode(bytes);
    }
  }
  return null;
}
