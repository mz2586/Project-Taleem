// Guardian Portal view types — mirror the /v1/guardian responses (read-only aggregates).

export interface Streak {
  current: number;
  longest: number;
  last_active_day: number | null;
}

export interface SyncStatus {
  last_synced_at: number | null;
  is_stale: boolean;
  seconds_since_sync: number | null;
  pending_is_device_reported: boolean;
}

export interface GuardianProfile {
  guardian_ref: string;
  display_name: string;
  children: string[];
  child_count: number;
}

export interface ChildSummary {
  student_ref: string;
  progress: {
    objectives_mastered: number;
    objectives_in_progress: number;
    accuracy: number;
    total_attempts: number;
  };
  streak: Streak;
  sync_status: SyncStatus;
  open_interventions: number;
  achievements_count: number;
}

export interface GuardianDashboard {
  guardian_ref: string;
  child_count: number;
  children: ChildSummary[];
}

export interface TimelineSession {
  session_id: string;
  objectives: string[];
  attempts: number;
  correct: number;
  at: number;
}

export interface ChildOverview {
  student_ref: string;
  progress_overview: {
    objectives_mastered: number;
    objectives_in_progress: number;
    total_attempts: number;
    accuracy: number;
    misconceptions_detected: number;
    misconceptions_cleared: number;
  };
  knowledge_growth: Record<string, number>;
  attendance: { active_days: number; day_indices: number[] };
  learning_streaks: Streak;
  weekly_summary: { sessions: number; attempts: number; correct: number; accuracy: number };
  learning_timeline: TimelineSession[];
  assessment_history: { assessments?: unknown[] } & Record<string, unknown>;
  ai_teacher_activity: Record<string, unknown>;
  recommendations: Array<{ objective_code: string; reason: string }>;
  intervention_notifications: Array<{ id: string; type: string; message: string }>;
  offline_sync_status: SyncStatus;
  achievement_history: Array<{ id: string; name: string; description: string; earned_at: number }>;
}
