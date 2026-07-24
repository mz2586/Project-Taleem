// Typed client for the Guardian Portal API (/v1/guardian/*). Read-only; reuses the shared HTTP
// client (bearer auth + problem+json + offline ApiError). No aggregation logic here — the server
// already aggregates from the existing learning read models.

import { createApiClient, type TokenProvider } from "../apiClient";
import { API_BASE, DEV_GUARDIAN_TOKEN } from "./config";
import type { ChildOverview, GuardianDashboard, GuardianProfile } from "./types";

let tokenProvider: TokenProvider = () => DEV_GUARDIAN_TOKEN;

export function setGuardianTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

const client = createApiClient(API_BASE, () => tokenProvider());

export const guardianApi = {
  me: () => client.get<GuardianProfile>("/v1/guardian/me"),
  dashboard: () => client.get<GuardianDashboard>("/v1/guardian/dashboard"),
  child: (studentRef: string) =>
    client.get<ChildOverview>(`/v1/guardian/children/${encodeURIComponent(studentRef)}`),
};
