import type { PresignResponse } from "./schemas";

/**
 * Upload captured photos. G5: we keep a local object URL for display-back (no
 * GET-presign needed). The real bytes PUT to the presigned URL only when live;
 * in mock mode we skip the network and just return the stable object keys the
 * backend expects (`items/{id}/photo-{n}`, per BACKEND_MAP).
 */
export async function uploadPhotos(
  itemId: string,
  presign: PresignResponse,
  files: File[],
  live: boolean,
): Promise<string[]> {
  const keys: string[] = [];
  for (let i = 0; i < files.length; i++) {
    const target = presign.urls[i];
    if (!target) break;
    const key = `items/${itemId}/photo-${i + 1}`;
    if (live) {
      await fetch(target.url, {
        method: target.method || "PUT",
        body: files[i],
        headers: target.headers,
      });
    }
    keys.push(key);
  }
  return keys;
}
