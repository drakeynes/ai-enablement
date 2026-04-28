export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      agent_feedback: {
        Row: {
          agent_run_id: string
          corrected_output: Json | null
          created_at: string
          feedback_type: string
          id: string
          note: string | null
          original_output: Json | null
          provided_by: string | null
        }
        Insert: {
          agent_run_id: string
          corrected_output?: Json | null
          created_at?: string
          feedback_type: string
          id?: string
          note?: string | null
          original_output?: Json | null
          provided_by?: string | null
        }
        Update: {
          agent_run_id?: string
          corrected_output?: Json | null
          created_at?: string
          feedback_type?: string
          id?: string
          note?: string | null
          original_output?: Json | null
          provided_by?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "agent_feedback_agent_run_id_fkey"
            columns: ["agent_run_id"]
            isOneToOne: false
            referencedRelation: "agent_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "agent_feedback_provided_by_fkey"
            columns: ["provided_by"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      agent_runs: {
        Row: {
          agent_name: string
          confidence_score: number | null
          duration_ms: number | null
          ended_at: string | null
          error_message: string | null
          id: string
          input_summary: string | null
          llm_cost_usd: number | null
          llm_input_tokens: number | null
          llm_model: string | null
          llm_output_tokens: number | null
          metadata: Json
          output_summary: string | null
          started_at: string
          status: string
          trigger_metadata: Json | null
          trigger_type: string
        }
        Insert: {
          agent_name: string
          confidence_score?: number | null
          duration_ms?: number | null
          ended_at?: string | null
          error_message?: string | null
          id?: string
          input_summary?: string | null
          llm_cost_usd?: number | null
          llm_input_tokens?: number | null
          llm_model?: string | null
          llm_output_tokens?: number | null
          metadata?: Json
          output_summary?: string | null
          started_at?: string
          status: string
          trigger_metadata?: Json | null
          trigger_type: string
        }
        Update: {
          agent_name?: string
          confidence_score?: number | null
          duration_ms?: number | null
          ended_at?: string | null
          error_message?: string | null
          id?: string
          input_summary?: string | null
          llm_cost_usd?: number | null
          llm_input_tokens?: number | null
          llm_model?: string | null
          llm_output_tokens?: number | null
          metadata?: Json
          output_summary?: string | null
          started_at?: string
          status?: string
          trigger_metadata?: Json | null
          trigger_type?: string
        }
        Relationships: []
      }
      alerts: {
        Row: {
          acknowledged_at: string | null
          alert_type: string
          client_id: string | null
          context: Json | null
          created_at: string
          created_by_run_id: string | null
          description: string
          id: string
          resolved_at: string | null
          severity: string
          status: string
          team_member_id: string | null
          title: string
        }
        Insert: {
          acknowledged_at?: string | null
          alert_type: string
          client_id?: string | null
          context?: Json | null
          created_at?: string
          created_by_run_id?: string | null
          description: string
          id?: string
          resolved_at?: string | null
          severity: string
          status?: string
          team_member_id?: string | null
          title: string
        }
        Update: {
          acknowledged_at?: string | null
          alert_type?: string
          client_id?: string | null
          context?: Json | null
          created_at?: string
          created_by_run_id?: string | null
          description?: string
          id?: string
          resolved_at?: string | null
          severity?: string
          status?: string
          team_member_id?: string | null
          title?: string
        }
        Relationships: [
          {
            foreignKeyName: "alerts_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "alerts_created_by_run_id_fkey"
            columns: ["created_by_run_id"]
            isOneToOne: false
            referencedRelation: "agent_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "alerts_team_member_id_fkey"
            columns: ["team_member_id"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      call_action_items: {
        Row: {
          call_id: string
          completed_at: string | null
          description: string
          due_date: string | null
          extracted_at: string
          id: string
          owner_client_id: string | null
          owner_team_member_id: string | null
          owner_type: string
          status: string
        }
        Insert: {
          call_id: string
          completed_at?: string | null
          description: string
          due_date?: string | null
          extracted_at?: string
          id?: string
          owner_client_id?: string | null
          owner_team_member_id?: string | null
          owner_type?: string
          status?: string
        }
        Update: {
          call_id?: string
          completed_at?: string | null
          description?: string
          due_date?: string | null
          extracted_at?: string
          id?: string
          owner_client_id?: string | null
          owner_team_member_id?: string | null
          owner_type?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "call_action_items_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "call_action_items_owner_client_id_fkey"
            columns: ["owner_client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "call_action_items_owner_team_member_id_fkey"
            columns: ["owner_team_member_id"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      call_classification_history: {
        Row: {
          call_id: string
          changed_at: string
          changed_by: string | null
          field_name: string
          id: string
          new_value: string | null
          old_value: string | null
        }
        Insert: {
          call_id: string
          changed_at?: string
          changed_by?: string | null
          field_name: string
          id?: string
          new_value?: string | null
          old_value?: string | null
        }
        Update: {
          call_id?: string
          changed_at?: string
          changed_by?: string | null
          field_name?: string
          id?: string
          new_value?: string | null
          old_value?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "call_classification_history_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "call_classification_history_changed_by_fkey"
            columns: ["changed_by"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      call_participants: {
        Row: {
          call_id: string
          client_id: string | null
          display_name: string | null
          email: string
          id: string
          participant_role: string | null
          team_member_id: string | null
        }
        Insert: {
          call_id: string
          client_id?: string | null
          display_name?: string | null
          email: string
          id?: string
          participant_role?: string | null
          team_member_id?: string | null
        }
        Update: {
          call_id?: string
          client_id?: string | null
          display_name?: string | null
          email?: string
          id?: string
          participant_role?: string | null
          team_member_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "call_participants_call_id_fkey"
            columns: ["call_id"]
            isOneToOne: false
            referencedRelation: "calls"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "call_participants_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "call_participants_team_member_id_fkey"
            columns: ["team_member_id"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      calls: {
        Row: {
          call_category: string
          call_type: string | null
          classification_confidence: number | null
          classification_method: string | null
          duration_seconds: number | null
          external_id: string
          id: string
          ingested_at: string
          is_retrievable_by_client_agents: boolean
          primary_client_id: string | null
          raw_payload: Json
          recording_url: string | null
          source: string
          started_at: string
          summary: string | null
          title: string | null
          transcript: string | null
        }
        Insert: {
          call_category: string
          call_type?: string | null
          classification_confidence?: number | null
          classification_method?: string | null
          duration_seconds?: number | null
          external_id: string
          id?: string
          ingested_at?: string
          is_retrievable_by_client_agents?: boolean
          primary_client_id?: string | null
          raw_payload: Json
          recording_url?: string | null
          source?: string
          started_at: string
          summary?: string | null
          title?: string | null
          transcript?: string | null
        }
        Update: {
          call_category?: string
          call_type?: string | null
          classification_confidence?: number | null
          classification_method?: string | null
          duration_seconds?: number | null
          external_id?: string
          id?: string
          ingested_at?: string
          is_retrievable_by_client_agents?: boolean
          primary_client_id?: string | null
          raw_payload?: Json
          recording_url?: string | null
          source?: string
          started_at?: string
          summary?: string | null
          title?: string | null
          transcript?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "calls_primary_client_id_fkey"
            columns: ["primary_client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
        ]
      }
      client_health_scores: {
        Row: {
          client_id: string
          computed_at: string
          computed_by_run_id: string | null
          factors: Json
          id: string
          score: number
          tier: string
        }
        Insert: {
          client_id: string
          computed_at?: string
          computed_by_run_id?: string | null
          factors: Json
          id?: string
          score: number
          tier: string
        }
        Update: {
          client_id?: string
          computed_at?: string
          computed_by_run_id?: string | null
          factors?: Json
          id?: string
          score?: number
          tier?: string
        }
        Relationships: [
          {
            foreignKeyName: "client_health_scores_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "client_health_scores_computed_by_run_id_fkey"
            columns: ["computed_by_run_id"]
            isOneToOne: false
            referencedRelation: "agent_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      client_team_assignments: {
        Row: {
          assigned_at: string
          client_id: string
          id: string
          metadata: Json
          role: string
          team_member_id: string
          unassigned_at: string | null
        }
        Insert: {
          assigned_at?: string
          client_id: string
          id?: string
          metadata?: Json
          role: string
          team_member_id: string
          unassigned_at?: string | null
        }
        Update: {
          assigned_at?: string
          client_id?: string
          id?: string
          metadata?: Json
          role?: string
          team_member_id?: string
          unassigned_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "client_team_assignments_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "client_team_assignments_team_member_id_fkey"
            columns: ["team_member_id"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      clients: {
        Row: {
          archived_at: string | null
          created_at: string
          email: string
          full_name: string
          id: string
          journey_stage: string | null
          metadata: Json
          notes: string | null
          phone: string | null
          program_type: string | null
          slack_user_id: string | null
          start_date: string | null
          status: string
          tags: string[]
          timezone: string | null
          updated_at: string
        }
        Insert: {
          archived_at?: string | null
          created_at?: string
          email: string
          full_name: string
          id?: string
          journey_stage?: string | null
          metadata?: Json
          notes?: string | null
          phone?: string | null
          program_type?: string | null
          slack_user_id?: string | null
          start_date?: string | null
          status?: string
          tags?: string[]
          timezone?: string | null
          updated_at?: string
        }
        Update: {
          archived_at?: string | null
          created_at?: string
          email?: string
          full_name?: string
          id?: string
          journey_stage?: string | null
          metadata?: Json
          notes?: string | null
          phone?: string | null
          program_type?: string | null
          slack_user_id?: string | null
          start_date?: string | null
          status?: string
          tags?: string[]
          timezone?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      document_chunks: {
        Row: {
          chunk_index: number
          content: string
          created_at: string
          document_id: string
          embedding: string | null
          id: string
          metadata: Json
          token_count: number | null
        }
        Insert: {
          chunk_index: number
          content: string
          created_at?: string
          document_id: string
          embedding?: string | null
          id?: string
          metadata?: Json
          token_count?: number | null
        }
        Update: {
          chunk_index?: number
          content?: string
          created_at?: string
          document_id?: string
          embedding?: string | null
          id?: string
          metadata?: Json
          token_count?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "document_chunks_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      documents: {
        Row: {
          archived_at: string | null
          content: string
          created_at: string
          document_type: string
          external_id: string | null
          id: string
          is_active: boolean
          metadata: Json
          source: string
          tags: string[]
          title: string
          updated_at: string
        }
        Insert: {
          archived_at?: string | null
          content: string
          created_at?: string
          document_type: string
          external_id?: string | null
          id?: string
          is_active?: boolean
          metadata?: Json
          source: string
          tags?: string[]
          title: string
          updated_at?: string
        }
        Update: {
          archived_at?: string | null
          content?: string
          created_at?: string
          document_type?: string
          external_id?: string | null
          id?: string
          is_active?: boolean
          metadata?: Json
          source?: string
          tags?: string[]
          title?: string
          updated_at?: string
        }
        Relationships: []
      }
      escalations: {
        Row: {
          agent_name: string
          agent_run_id: string
          assigned_to: string | null
          context: Json
          created_at: string
          id: string
          proposed_action: Json | null
          reason: string
          resolution: Json | null
          resolution_note: string | null
          resolved_at: string | null
          resolved_by: string | null
          status: string
        }
        Insert: {
          agent_name: string
          agent_run_id: string
          assigned_to?: string | null
          context: Json
          created_at?: string
          id?: string
          proposed_action?: Json | null
          reason: string
          resolution?: Json | null
          resolution_note?: string | null
          resolved_at?: string | null
          resolved_by?: string | null
          status?: string
        }
        Update: {
          agent_name?: string
          agent_run_id?: string
          assigned_to?: string | null
          context?: Json
          created_at?: string
          id?: string
          proposed_action?: Json | null
          reason?: string
          resolution?: Json | null
          resolution_note?: string | null
          resolved_at?: string | null
          resolved_by?: string | null
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "escalations_agent_run_id_fkey"
            columns: ["agent_run_id"]
            isOneToOne: false
            referencedRelation: "agent_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "escalations_assigned_to_fkey"
            columns: ["assigned_to"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "escalations_resolved_by_fkey"
            columns: ["resolved_by"]
            isOneToOne: false
            referencedRelation: "team_members"
            referencedColumns: ["id"]
          },
        ]
      }
      nps_submissions: {
        Row: {
          client_id: string
          feedback: string | null
          id: string
          ingested_at: string
          score: number
          submitted_at: string
          survey_source: string | null
        }
        Insert: {
          client_id: string
          feedback?: string | null
          id?: string
          ingested_at?: string
          score: number
          submitted_at: string
          survey_source?: string | null
        }
        Update: {
          client_id?: string
          feedback?: string | null
          id?: string
          ingested_at?: string
          score?: number
          submitted_at?: string
          survey_source?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "nps_submissions_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
        ]
      }
      slack_channels: {
        Row: {
          client_id: string | null
          created_at: string
          ella_enabled: boolean
          id: string
          is_archived: boolean
          is_private: boolean
          metadata: Json
          name: string
          slack_channel_id: string
          updated_at: string
        }
        Insert: {
          client_id?: string | null
          created_at?: string
          ella_enabled?: boolean
          id?: string
          is_archived?: boolean
          is_private: boolean
          metadata?: Json
          name: string
          slack_channel_id: string
          updated_at?: string
        }
        Update: {
          client_id?: string | null
          created_at?: string
          ella_enabled?: boolean
          id?: string
          is_archived?: boolean
          is_private?: boolean
          metadata?: Json
          name?: string
          slack_channel_id?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "slack_channels_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "clients"
            referencedColumns: ["id"]
          },
        ]
      }
      slack_messages: {
        Row: {
          author_type: string
          id: string
          ingested_at: string
          message_subtype: string | null
          message_type: string
          raw_payload: Json
          sent_at: string
          slack_channel_id: string
          slack_thread_ts: string | null
          slack_ts: string
          slack_user_id: string
          text: string
        }
        Insert: {
          author_type: string
          id?: string
          ingested_at?: string
          message_subtype?: string | null
          message_type?: string
          raw_payload: Json
          sent_at: string
          slack_channel_id: string
          slack_thread_ts?: string | null
          slack_ts: string
          slack_user_id: string
          text: string
        }
        Update: {
          author_type?: string
          id?: string
          ingested_at?: string
          message_subtype?: string | null
          message_type?: string
          raw_payload?: Json
          sent_at?: string
          slack_channel_id?: string
          slack_thread_ts?: string | null
          slack_ts?: string
          slack_user_id?: string
          text?: string
        }
        Relationships: []
      }
      team_members: {
        Row: {
          archived_at: string | null
          created_at: string
          email: string
          full_name: string
          id: string
          is_active: boolean
          metadata: Json
          role: string
          slack_user_id: string | null
          updated_at: string
        }
        Insert: {
          archived_at?: string | null
          created_at?: string
          email: string
          full_name: string
          id?: string
          is_active?: boolean
          metadata?: Json
          role: string
          slack_user_id?: string | null
          updated_at?: string
        }
        Update: {
          archived_at?: string | null
          created_at?: string
          email?: string
          full_name?: string
          id?: string
          is_active?: boolean
          metadata?: Json
          role?: string
          slack_user_id?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      webhook_deliveries: {
        Row: {
          call_external_id: string | null
          headers: Json | null
          payload: Json | null
          processed_at: string | null
          processing_error: string | null
          processing_status: string
          received_at: string
          source: string
          webhook_id: string
        }
        Insert: {
          call_external_id?: string | null
          headers?: Json | null
          payload?: Json | null
          processed_at?: string | null
          processing_error?: string | null
          processing_status?: string
          received_at?: string
          source?: string
          webhook_id: string
        }
        Update: {
          call_external_id?: string | null
          headers?: Json | null
          payload?: Json | null
          processed_at?: string | null
          processing_error?: string | null
          processing_status?: string
          received_at?: string
          source?: string
          webhook_id?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      match_document_chunks: {
        Args: {
          client_id?: string
          document_types?: string[]
          include_global?: boolean
          match_count?: number
          min_similarity?: number
          query_embedding: string
          tags?: string[]
        }
        Returns: {
          chunk_id: string
          chunk_index: number
          content: string
          document_created_at: string
          document_id: string
          document_title: string
          document_type: string
          metadata: Json
          similarity: number
        }[]
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
