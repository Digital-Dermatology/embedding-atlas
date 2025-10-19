// Copyright (c) 2025 Apple Inc. Licensed under MIT License.

import { rgb } from "d3-color";

const category10 = [
  "#5D69B1",
  "#ED645A",
  "#99C945",
  "#2F8AC4",
  "#CC61B0",
  "#52BCA3",
  "#E58606",
  "#764E9F",
  "#24796C",
  "#DAA51B",
];

const category20 = [
  "#5D69B1",
  "#ED645A",
  "#99C945",
  "#2F8AC4",
  "#CC61B0",
  "#52BCA3",
  "#E58606",
  "#764E9F",
  "#24796C",
  "#DAA51B",
  "#CC3A8E",
  "#A5AA99",
  "#5F4690",
  "#1D6996",
  "#38A6A5",
  "#0F8554",
  "#73AF48",
  "#E17C05",
  "#CC503E",
  "#94346E",
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
