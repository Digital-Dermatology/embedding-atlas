export type UploadedSamplePoint = {
  id: string;
  label?: string | null;
  x: number;
  y: number;
  previewUrl?: string | null;
  avgDistance?: number | null;
};
