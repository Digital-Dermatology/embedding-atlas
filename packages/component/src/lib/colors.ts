// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import { rgb } from "d3-color";

const category10 = [
  "#5B8FF9",
  "#5AD8A6",
  "#5D7092",
  "#F6BD16",
  "#E8684A",
  "#6DC8EC",
  "#9270CA",
  "#FF9D4D",
  "#269A99",
  "#FF6F91",
];

const category20 = [
  "#5B8FF9",
  "#5AD8A6",
  "#5D7092",
  "#F6BD16",
  "#E8684A",
  "#6DC8EC",
  "#9270CA",
  "#FF9D4D",
  "#269A99",
  "#FF6F91",
  "#9FE0C5",
  "#B47AEA",
  "#FFA8A8",
  "#A1C8FF",
  "#63D1C6",
  "#FFBE76",
  "#6E75A4",
  "#FF8F66",
  "#26C6DA",
  "#F4B3C2",
];

export function defaultCategoryColors(count: number): string[] {
  if (count < 1) {
    count = 1;
  }
  if (count <= category10.length) {
    return category10.slice(0, count);
  } else if (count <= category20.length) {
    return category20.slice(0, count);
  } else {
    let colors: string[] = [];
    for (let i = 0; i < count; i++) {
      colors[i] = category20[i % category20.length];
    }
    return colors;
  }
}

/** Parse color string into normalized sRGB values (all between 0 and 1). */
export function parseColorNormalizedRgb(str: string): { r: number; g: number; b: number; a: number } {
  let { r, g, b, opacity } = rgb(str);
  return { r: r / 255.0, g: g / 255.0, b: b / 255.0, a: opacity };
}
