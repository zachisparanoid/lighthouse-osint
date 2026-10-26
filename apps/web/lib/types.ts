export * from "@lighthouse/shared-types";
import type {
  CaseStatus,
  CollectorCost,
  EntityType,
  JobStatus,
  KeyService,
  RelationshipType,
  Role,
} from "@lighthouse/shared-types";

export interface User {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
  totp_enabled: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  totp_required?: boolean;
}

export interface Case {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  status: CaseStatus;
  legal_basis: string;
  aup_accepted: boolean;
  aup_accepted_at: string | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

export interface CaseSummary extends Case {
  entity_count: number;
  edge_count: number;
  running_jobs: number;
  role: Role | null;
}

export interface Provenance {
  id: string;
  collector_name: string;
  source_url: string | null;
  raw_excerpt: Record<string, unknown> | null;
  retrieved_at: string;
  license_note: string | null;
}

export interface Entity {
  id: string;
  case_id: string;
  type: EntityType;
  value: string;
  label: string;
  attributes: Record<string, unknown>;
  first_seen: string | null;
  last_seen: string | null;
  confidence: number;
  source_count: number;
  tags: string[];
  conflicting: boolean;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface EntityDetail extends Entity {
  provenances: Provenance[];
}

export interface Edge {
  id: string;
  case_id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship: RelationshipType;
  confidence: number;
  attributes: Record<string, unknown>;
}

export interface GraphResponse {
  entities: Entity[];
  edges: Edge[];
  layout: Record<string, { x: number; y: number }>;
}

export interface Job {
  id: string;
  case_id: string;
  collector_name: string;
  target_entity_id: string | null;
  status: JobStatus;
  progress: number;
  result_summary: Record<string, unknown> | null;
  error: string | null;
  depth: number;
  parent_job_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ModuleInfo {
  name: string;
  title: string;
  description: string;
  accepts: string[];
  produces: string[];
  cost: CollectorCost;
  requires_key: string | null;
  key_present: boolean;
  enabled: boolean;
  rate_limit: string;
  source_note: string;
}

export interface ModuleSettings {
  disabled: string[];
  autoexpand_depth: number;
  autoexpand_budget: number;
}

export interface RescanConfig {
  enabled: boolean;
  interval_hours: number;
  seed_entity_id: string | null;
  depth: number;
  budget: number;
}

export interface ApiKey {
  id: string;
  service: KeyService;
  scope: string;
  label: string;
  hint: string | null;
  masked: string;
  is_valid: boolean | null;
  last_used_at: string | null;
  owner_case_id: string | null;
  owner_user_id: string | null;
  created_at: string;
}

export interface Report {
  id: string;
  case_id: string;
  title: string;
  config: Record<string, unknown>;
  format: string;
  status: string;
  file_path: string | null;
  artifacts: Record<string, string>;
  error: string | null;
  generated_at: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  case_id: string | null;
  ip: string | null;
  user_agent: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface Note {
  id: string;
  case_id: string;
  entity_id: string | null;
  author_id: string | null;
  body: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface CaseMember {
  user_id: string;
  email: string;
  case_role: Role;
}

/** A compact node delivered over WebSocket on graph_delta. */
export interface GraphNodeDelta {
  id: string;
  type: EntityType;
  value: string;
  label: string;
  confidence: number;
  conflicting: boolean;
  tags: string[];
  source_count: number;
}

export interface EdgeDelta {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship: RelationshipType;
  confidence: number;
}

export type WsEvent =
  | { type: "connected"; case_id: string }
  | { type: "job_progress"; job_id: string; collector: string; progress: number; message: string }
  | { type: "job_completed"; job_id: string; collector: string; status: JobStatus; error: string | null; summary: Record<string, unknown> | null }
  | { type: "graph_delta"; job_id: string; collector: string; new_entities: GraphNodeDelta[]; updated_entities: GraphNodeDelta[]; edges: EdgeDelta[] }
  | { type: "autoexpand_progress"; job_id: string; progress: number; nodes: number; jobs: number };
