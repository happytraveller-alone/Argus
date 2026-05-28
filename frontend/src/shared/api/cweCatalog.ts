import { apiClient } from "@/shared/api/serverClient";

export type CweCatalogApiEntry = {
  id: string;
  numericId: number;
  nameEnOfficial: string;
  nameEnShort: string;
  nameZh: string;
  sourceVersion?: string;
  sourceDate?: string;
  sourceSha256?: string;
  translationSource?: string;
  translationReviewedAt?: string;
};

export type CweCatalogApiResponse = {
  data: CweCatalogApiEntry[];
  total: number;
  limit: number;
  offset: number;
  sourceVersion?: string;
  sourceDate?: string;
  sourceSha256?: string;
  translationSource?: string;
  translationReviewedAt?: string;
};

export async function fetchCweCatalog(params: {
  keyword?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<CweCatalogApiResponse> {
  const response = await apiClient.get("/cwe-catalog", { params });
  return response.data;
}
