export type CriterionKey = 'fluency' | 'completeness' | 'pronunciation' | 'prosody'

export interface DemoSummary {
  id: string
  short_id: string
  display_name: string
  role: string
  thumbnail_url: string
}

export interface Bootstrap {
  product: string
  descriptor: string
  demos: DemoSummary[]
  offline_ready: boolean
  recent_count: number
  chatgpt: {
    connected: boolean
    plan_usage_enabled: boolean
    selected_model: string | null
    account_label?: string
    models?: { slug: string; display_name: string }[]
  }
  scientific_scope: {
    frozen_research_overall_score: null
    machine_intelligibility: null
    holdout_processed: false
    product_overall_version: string
  }
}

export interface FeedbackBlock {
  text: string
  evidence_refs?: string[]
}

export interface CriterionView {
  key: CriterionKey
  label: string
  description: string
  value: number | null
  display_value: number | null
  unit: 'SCALE_1_5' | 'PERCENT'
  scale_max: 5 | 100
  available: boolean
  status: string
  badge: string
  caveat: string | null
}

export interface AssessmentResult {
  id: string
  pair_id: string
  display_name: string
  source_mode: string
  status: string
  target_topic: string
  target_text: string
  transcript: string
  criteria: {
    version: string
    items: Record<CriterionKey, CriterionView>
  }
  completeness: {
    coverage: number
    matched_word_count: number
    possible_asr_uncertainty: string[]
    asr_insertions: string[]
    warning: string
  }
  evidence: {
    fluency: Record<string, number | null>
    word_review_prompts: { word: string; interpretation: string }[]
  }
  feedback: {
    strength: FeedbackBlock
    focus_next: FeedbackBlock
    try_this: FeedbackBlock
    source: 'CHATGPT' | 'DETERMINISTIC'
  }
  media: { video_url: string; audio_url: string | null }
  model_failures: { public_message: string }[]
  provenance: {
    source_mode: string
    canonical_source: 'RAW_COMPLETED_DUET'
    audio_source_type: 'RAW_CROPPED'
    genuine_frozen_inference: boolean
    research_membership: false
  }
  machine_intelligibility: null
  overall_practice_score: {
    version: string
    value: number
    display_value: number
    scale_max: 5
    status: 'DESCRIPTIVE_PRODUCT_COMPOSITE'
    label: 'Overall Practice Score'
    methodology_note: string
    student_note: string
    presenter_designation: 'UNVALIDATED_PRODUCT_COMPOSITE'
    inputs: {
      pronunciation: number
      fluency: number
      prosody: number
      reading_completeness: number
    }
    machine_intelligibility_included: false
    research_validated: false
  } | null
  holdout_processed: false
}

export interface MediaItem {
  media_id: string
  friendly_title: string
  source_type: string
  import_timestamp: string
  duration_seconds: number
  resolution: { width: number; height: number }
  processing_state: string
  assessment_state: string
  has_result: boolean
  thumbnail_url: string | null
  video_url: string
}

export interface JobState {
  job_id: string
  state: 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'FAILED'
  message: string
  media_id: string
  result_id?: string
  error?: string
}
