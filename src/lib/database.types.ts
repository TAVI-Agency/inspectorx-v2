export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  catalog: {
    Tables: {
      country_codes: {
        Row: {
          code: string
          country: string
          id: string
          name: string | null
          product_type_id: string | null
          system: string
        }
        Insert: {
          code: string
          country: string
          id?: string
          name?: string | null
          product_type_id?: string | null
          system: string
        }
        Update: {
          code?: string
          country?: string
          id?: string
          name?: string | null
          product_type_id?: string | null
          system?: string
        }
        Relationships: [
          {
            foreignKeyName: "country_codes_product_type_id_fkey"
            columns: ["product_type_id"]
            isOneToOne: false
            referencedRelation: "product_types"
            referencedColumns: ["id"]
          },
        ]
      }
      product_types: {
        Row: {
          created_at: string
          hs_code: string | null
          id: string
          kind: string
          name_en: string | null
          name_ru: string
          name_uz: string | null
          parent_id: string | null
          unspsc_code: string | null
        }
        Insert: {
          created_at?: string
          hs_code?: string | null
          id?: string
          kind: string
          name_en?: string | null
          name_ru: string
          name_uz?: string | null
          parent_id?: string | null
          unspsc_code?: string | null
        }
        Update: {
          created_at?: string
          hs_code?: string | null
          id?: string
          kind?: string
          name_en?: string | null
          name_ru?: string
          name_uz?: string | null
          parent_id?: string | null
          unspsc_code?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "product_types_parent_id_fkey"
            columns: ["parent_id"]
            isOneToOne: false
            referencedRelation: "product_types"
            referencedColumns: ["id"]
          },
        ]
      }
      skus: {
        Row: {
          attribute: string | null
          barcode: string | null
          brand: string | null
          country: string
          id: string
          ikpu_code: string
          product_type_id: string
        }
        Insert: {
          attribute?: string | null
          barcode?: string | null
          brand?: string | null
          country?: string
          id?: string
          ikpu_code: string
          product_type_id: string
        }
        Update: {
          attribute?: string | null
          barcode?: string | null
          brand?: string | null
          country?: string
          id?: string
          ikpu_code?: string
          product_type_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "skus_product_type_id_fkey"
            columns: ["product_type_id"]
            isOneToOne: false
            referencedRelation: "product_types"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  pipeline: {
    Tables: {
      items: {
        Row: {
          category_slug: string | null
          expected_item: string
          id: string
          last_error: string | null
          requirement_id: string | null
          retry_count: number
          run_id: string
          status: string
          summary_text: string | null
          updated_at: string
        }
        Insert: {
          category_slug?: string | null
          expected_item: string
          id?: string
          last_error?: string | null
          requirement_id?: string | null
          retry_count?: number
          run_id: string
          status?: string
          summary_text?: string | null
          updated_at?: string
        }
        Update: {
          category_slug?: string | null
          expected_item?: string
          id?: string
          last_error?: string | null
          requirement_id?: string | null
          retry_count?: number
          run_id?: string
          status?: string
          summary_text?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "items_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      llm_calls: {
        Row: {
          cost_usd: number | null
          created_at: string
          id: string
          input_tokens: number | null
          item_id: string | null
          model: string
          output_tokens: number | null
          role: string
          run_id: string | null
        }
        Insert: {
          cost_usd?: number | null
          created_at?: string
          id?: string
          input_tokens?: number | null
          item_id?: string | null
          model: string
          output_tokens?: number | null
          role: string
          run_id?: string | null
        }
        Update: {
          cost_usd?: number | null
          created_at?: string
          id?: string
          input_tokens?: number | null
          item_id?: string | null
          model?: string
          output_tokens?: number | null
          role?: string
          run_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "llm_calls_item_id_fkey"
            columns: ["item_id"]
            isOneToOne: false
            referencedRelation: "items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "llm_calls_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      maps: {
        Row: {
          approved_at: string | null
          approved_by: string | null
          created_at: string
          group_ref: string
          id: string
          jurisdiction: string
          payload: Json
          status: string
        }
        Insert: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          group_ref: string
          id?: string
          jurisdiction: string
          payload: Json
          status?: string
        }
        Update: {
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          group_ref?: string
          id?: string
          jurisdiction?: string
          payload?: Json
          status?: string
        }
        Relationships: []
      }
      runs: {
        Row: {
          coverage_report: string | null
          finished_at: string | null
          id: string
          map_id: string
          started_at: string
          status: string
        }
        Insert: {
          coverage_report?: string | null
          finished_at?: string | null
          id?: string
          map_id: string
          started_at?: string
          status?: string
        }
        Update: {
          coverage_report?: string | null
          finished_at?: string | null
          id?: string
          map_id?: string
          started_at?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "runs_map_id_fkey"
            columns: ["map_id"]
            isOneToOne: false
            referencedRelation: "maps"
            referencedColumns: ["id"]
          },
        ]
      }
      verdicts: {
        Row: {
          created_at: string
          id: string
          item_id: string
          model: string | null
          reason: string | null
          step: string
          verdict: string
        }
        Insert: {
          created_at?: string
          id?: string
          item_id: string
          model?: string | null
          reason?: string | null
          step: string
          verdict: string
        }
        Update: {
          created_at?: string
          id?: string
          item_id?: string
          model?: string | null
          reason?: string | null
          step?: string
          verdict?: string
        }
        Relationships: [
          {
            foreignKeyName: "verdicts_item_id_fkey"
            columns: ["item_id"]
            isOneToOne: false
            referencedRelation: "items"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      act_paragraphs: {
        Row: {
          act_id: string
          created_at: string
          deep_link_url: string | null
          id: string
          paragraph_ref: string
          updated_at: string
          verbatim_en: string | null
          verbatim_ru: string | null
          verbatim_uz: string | null
          version_date: string | null
        }
        Insert: {
          act_id: string
          created_at?: string
          deep_link_url?: string | null
          id?: string
          paragraph_ref: string
          updated_at?: string
          verbatim_en?: string | null
          verbatim_ru?: string | null
          verbatim_uz?: string | null
          version_date?: string | null
        }
        Update: {
          act_id?: string
          created_at?: string
          deep_link_url?: string | null
          id?: string
          paragraph_ref?: string
          updated_at?: string
          verbatim_en?: string | null
          verbatim_ru?: string | null
          verbatim_uz?: string | null
          version_date?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "act_paragraphs_act_id_fkey"
            columns: ["act_id"]
            isOneToOne: false
            referencedRelation: "acts"
            referencedColumns: ["id"]
          },
        ]
      }
      acts: {
        Row: {
          act_type: string | null
          adopted_date: string | null
          created_at: string
          id: string
          jurisbase_act_id: string | null
          number: string | null
          status: Database["public"]["Enums"]["act_status"]
          title: string
          updated_at: string
          url: string | null
        }
        Insert: {
          act_type?: string | null
          adopted_date?: string | null
          created_at?: string
          id?: string
          jurisbase_act_id?: string | null
          number?: string | null
          status?: Database["public"]["Enums"]["act_status"]
          title: string
          updated_at?: string
          url?: string | null
        }
        Update: {
          act_type?: string | null
          adopted_date?: string | null
          created_at?: string
          id?: string
          jurisbase_act_id?: string | null
          number?: string | null
          status?: Database["public"]["Enums"]["act_status"]
          title?: string
          updated_at?: string
          url?: string | null
        }
        Relationships: []
      }
      authorities: {
        Row: {
          code: string | null
          contacts: Json
          created_at: string
          id: string
          name_en: string | null
          name_ru: string
          name_uz: string | null
          website: string | null
        }
        Insert: {
          code?: string | null
          contacts?: Json
          created_at?: string
          id?: string
          name_en?: string | null
          name_ru: string
          name_uz?: string | null
          website?: string | null
        }
        Update: {
          code?: string | null
          contacts?: Json
          created_at?: string
          id?: string
          name_en?: string | null
          name_ru?: string
          name_uz?: string | null
          website?: string | null
        }
        Relationships: []
      }
      calendar_tokens: {
        Row: {
          created_at: string
          token: string
          user_id: string
        }
        Insert: {
          created_at?: string
          token?: string
          user_id: string
        }
        Update: {
          created_at?: string
          token?: string
          user_id?: string
        }
        Relationships: []
      }
      change_events: {
        Row: {
          act_id: string | null
          created_at: string
          effective_date: string | null
          event_type: Database["public"]["Enums"]["change_event_type"]
          id: string
          importance: Database["public"]["Enums"]["importance_level"]
          jurisdiction: string
          now_text: string | null
          paragraph_id: string | null
          payload: Json
          processed_at: string | null
          source: Database["public"]["Enums"]["change_source"]
          summary: string | null
          title: string
          was_text: string | null
        }
        Insert: {
          act_id?: string | null
          created_at?: string
          effective_date?: string | null
          event_type: Database["public"]["Enums"]["change_event_type"]
          id?: string
          importance?: Database["public"]["Enums"]["importance_level"]
          jurisdiction?: string
          now_text?: string | null
          paragraph_id?: string | null
          payload?: Json
          processed_at?: string | null
          source?: Database["public"]["Enums"]["change_source"]
          summary?: string | null
          title: string
          was_text?: string | null
        }
        Update: {
          act_id?: string | null
          created_at?: string
          effective_date?: string | null
          event_type?: Database["public"]["Enums"]["change_event_type"]
          id?: string
          importance?: Database["public"]["Enums"]["importance_level"]
          jurisdiction?: string
          now_text?: string | null
          paragraph_id?: string | null
          payload?: Json
          processed_at?: string | null
          source?: Database["public"]["Enums"]["change_source"]
          summary?: string | null
          title?: string
          was_text?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "change_events_act_id_fkey"
            columns: ["act_id"]
            isOneToOne: false
            referencedRelation: "acts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "change_events_paragraph_id_fkey"
            columns: ["paragraph_id"]
            isOneToOne: false
            referencedRelation: "act_paragraphs"
            referencedColumns: ["id"]
          },
        ]
      }
      chosen_products: {
        Row: {
          created_at: string
          id: string
          product_id: string | null
          service_id: string | null
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          product_id?: string | null
          service_id?: string | null
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          product_id?: string | null
          service_id?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "chosen_products_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "chosen_products_service_id_fkey"
            columns: ["service_id"]
            isOneToOne: false
            referencedRelation: "services"
            referencedColumns: ["id"]
          },
        ]
      }
      content_requests: {
        Row: {
          comment: string | null
          created_at: string
          id: string
          kind: Database["public"]["Enums"]["content_request_kind"]
          product_id: string | null
          query_text: string | null
          service_id: string | null
          status: Database["public"]["Enums"]["content_request_status"]
          user_id: string | null
        }
        Insert: {
          comment?: string | null
          created_at?: string
          id?: string
          kind: Database["public"]["Enums"]["content_request_kind"]
          product_id?: string | null
          query_text?: string | null
          service_id?: string | null
          status?: Database["public"]["Enums"]["content_request_status"]
          user_id?: string | null
        }
        Update: {
          comment?: string | null
          created_at?: string
          id?: string
          kind?: Database["public"]["Enums"]["content_request_kind"]
          product_id?: string | null
          query_text?: string | null
          service_id?: string | null
          status?: Database["public"]["Enums"]["content_request_status"]
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "content_requests_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "content_requests_service_id_fkey"
            columns: ["service_id"]
            isOneToOne: false
            referencedRelation: "services"
            referencedColumns: ["id"]
          },
        ]
      }
      import_items: {
        Row: {
          created_at: string
          id: string
          idx: number
          raw: Json
          requirement_id: string | null
          resolution: string
          resolved_at: string | null
          resolved_by: string | null
          review_detail: string | null
          review_reason: string | null
          run_id: string
          status: string
        }
        Insert: {
          created_at?: string
          id?: string
          idx: number
          raw: Json
          requirement_id?: string | null
          resolution?: string
          resolved_at?: string | null
          resolved_by?: string | null
          review_detail?: string | null
          review_reason?: string | null
          run_id: string
          status: string
        }
        Update: {
          created_at?: string
          id?: string
          idx?: number
          raw?: Json
          requirement_id?: string | null
          resolution?: string
          resolved_at?: string | null
          resolved_by?: string | null
          review_detail?: string | null
          review_reason?: string | null
          run_id?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "import_items_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "import_items_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "import_items_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
          {
            foreignKeyName: "import_items_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "import_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      import_runs: {
        Row: {
          created_at: string
          error: string | null
          file_hash: string
          file_name: string
          gray_zones: string[]
          id: string
          loaded_count: number
          merged_count: number
          model: string
          raw_json: Json | null
          review_count: number
          status: string
          subject_kind: string
          subject_slug: string
        }
        Insert: {
          created_at?: string
          error?: string | null
          file_hash: string
          file_name: string
          gray_zones?: string[]
          id?: string
          loaded_count?: number
          merged_count?: number
          model: string
          raw_json?: Json | null
          review_count?: number
          status?: string
          subject_kind: string
          subject_slug: string
        }
        Update: {
          created_at?: string
          error?: string | null
          file_hash?: string
          file_name?: string
          gray_zones?: string[]
          id?: string
          loaded_count?: number
          merged_count?: number
          model?: string
          raw_json?: Json | null
          review_count?: number
          status?: string
          subject_kind?: string
          subject_slug?: string
        }
        Relationships: []
      }
      lawyer_notifications: {
        Row: {
          created_at: string
          id: string
          is_read: boolean
          kind: Database["public"]["Enums"]["lawyer_notification_kind"]
          lawyer_id: string
          read_at: string | null
          requirement_id: string | null
          review_id: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          is_read?: boolean
          kind: Database["public"]["Enums"]["lawyer_notification_kind"]
          lawyer_id: string
          read_at?: string | null
          requirement_id?: string | null
          review_id?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          is_read?: boolean
          kind?: Database["public"]["Enums"]["lawyer_notification_kind"]
          lawyer_id?: string
          read_at?: string | null
          requirement_id?: string | null
          review_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "lawyer_notifications_lawyer_id_fkey"
            columns: ["lawyer_id"]
            isOneToOne: false
            referencedRelation: "lawyer_profiles"
            referencedColumns: ["user_id"]
          },
          {
            foreignKeyName: "lawyer_notifications_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "lawyer_notifications_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "lawyer_notifications_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
          {
            foreignKeyName: "lawyer_notifications_review_id_fkey"
            columns: ["review_id"]
            isOneToOne: false
            referencedRelation: "requirement_reviews"
            referencedColumns: ["id"]
          },
        ]
      }
      lawyer_profiles: {
        Row: {
          created_at: string
          credentials: string
          display_name: string
          license_no: string | null
          specializations: string | null
          status: Database["public"]["Enums"]["lawyer_status"]
          updated_at: string
          user_id: string
          verified_at: string | null
        }
        Insert: {
          created_at?: string
          credentials: string
          display_name: string
          license_no?: string | null
          specializations?: string | null
          status?: Database["public"]["Enums"]["lawyer_status"]
          updated_at?: string
          user_id: string
          verified_at?: string | null
        }
        Update: {
          created_at?: string
          credentials?: string
          display_name?: string
          license_no?: string | null
          specializations?: string | null
          status?: Database["public"]["Enums"]["lawyer_status"]
          updated_at?: string
          user_id?: string
          verified_at?: string | null
        }
        Relationships: []
      }
      lifecycle_stages: {
        Row: {
          code: string
          created_at: string
          id: string
          name_en: string | null
          name_ru: string
          name_uz: string | null
          sort_order: number
        }
        Insert: {
          code: string
          created_at?: string
          id?: string
          name_en?: string | null
          name_ru: string
          name_uz?: string | null
          sort_order?: number
        }
        Update: {
          code?: string
          created_at?: string
          id?: string
          name_en?: string | null
          name_ru?: string
          name_uz?: string | null
          sort_order?: number
        }
        Relationships: []
      }
      photo_assets: {
        Row: {
          face_name: string
          height: number | null
          idx: number
          inspection_id: string
          kind: string
          mime: string | null
          problems: Json
          purged_at: string | null
          sha256: string | null
          storage_path: string
          usable: boolean
          width: number | null
        }
        Insert: {
          face_name?: string
          height?: number | null
          idx: number
          inspection_id: string
          kind: string
          mime?: string | null
          problems?: Json
          purged_at?: string | null
          sha256?: string | null
          storage_path: string
          usable?: boolean
          width?: number | null
        }
        Update: {
          face_name?: string
          height?: number | null
          idx?: number
          inspection_id?: string
          kind?: string
          mime?: string | null
          problems?: Json
          purged_at?: string | null
          sha256?: string | null
          storage_path?: string
          usable?: boolean
          width?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "photo_assets_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_fact_overrides: {
        Row: {
          author_user_id: string
          created_at: string
          id: string
          inspection_id: string
          note: string
          payload: Json
          slot_id: string
        }
        Insert: {
          author_user_id: string
          created_at?: string
          id?: string
          inspection_id: string
          note?: string
          payload: Json
          slot_id: string
        }
        Update: {
          author_user_id?: string
          created_at?: string
          id?: string
          inspection_id?: string
          note?: string
          payload?: Json
          slot_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_fact_overrides_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_facts: {
        Row: {
          asset_idx: number | null
          bbox: Json | null
          confidence: number | null
          id: number
          inspection_id: string
          payload: Json
          revision: number
          slot_id: string
          source: string
        }
        Insert: {
          asset_idx?: number | null
          bbox?: Json | null
          confidence?: number | null
          id?: never
          inspection_id: string
          payload?: Json
          revision?: number
          slot_id: string
          source: string
        }
        Update: {
          asset_idx?: number | null
          bbox?: Json | null
          confidence?: number | null
          id?: never
          inspection_id?: string
          payload?: Json
          revision?: number
          slot_id?: string
          source?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_facts_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_finding_actions: {
        Row: {
          action: string
          created_at: string
          finding_id: string
          id: string
          reason: string | null
          user_id: string
        }
        Insert: {
          action: string
          created_at?: string
          finding_id: string
          id?: string
          reason?: string | null
          user_id: string
        }
        Update: {
          action?: string
          created_at?: string
          finding_id?: string
          id?: string
          reason?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_finding_actions_finding_id_fkey"
            columns: ["finding_id"]
            isOneToOne: false
            referencedRelation: "photo_findings"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_finding_reviews: {
        Row: {
          comment_text: string
          created_at: string
          finding_id: string
          id: string
          lawyer_id: string
          official_replied_at: string | null
          official_reply: string | null
          published_at: string | null
          status: Database["public"]["Enums"]["review_status"]
          verdict: Database["public"]["Enums"]["review_verdict"]
        }
        Insert: {
          comment_text: string
          created_at?: string
          finding_id: string
          id?: string
          lawyer_id: string
          official_replied_at?: string | null
          official_reply?: string | null
          published_at?: string | null
          status?: Database["public"]["Enums"]["review_status"]
          verdict: Database["public"]["Enums"]["review_verdict"]
        }
        Update: {
          comment_text?: string
          created_at?: string
          finding_id?: string
          id?: string
          lawyer_id?: string
          official_replied_at?: string | null
          official_reply?: string | null
          published_at?: string | null
          status?: Database["public"]["Enums"]["review_status"]
          verdict?: Database["public"]["Enums"]["review_verdict"]
        }
        Relationships: [
          {
            foreignKeyName: "photo_finding_reviews_finding_id_fkey"
            columns: ["finding_id"]
            isOneToOne: false
            referencedRelation: "photo_findings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "photo_finding_reviews_lawyer_id_fkey"
            columns: ["lawyer_id"]
            isOneToOne: false
            referencedRelation: "lawyer_profiles"
            referencedColumns: ["user_id"]
          },
        ]
      }
      photo_findings: {
        Row: {
          basis: string
          checkpoint_id: string
          confidence_class: string
          decided_by: string
          evidence: Json
          evidence_crop_path: string | null
          group_key: string
          id: string
          inspection_id: string
          kind: string
          message: string
          recommendation: string | null
          requirement_id: string | null
          rule_ref: string
          severity: string
          status: string
          surface: string
        }
        Insert: {
          basis?: string
          checkpoint_id: string
          confidence_class?: string
          decided_by?: string
          evidence?: Json
          evidence_crop_path?: string | null
          group_key: string
          id?: string
          inspection_id: string
          kind: string
          message?: string
          recommendation?: string | null
          requirement_id?: string | null
          rule_ref: string
          severity: string
          status: string
          surface?: string
        }
        Update: {
          basis?: string
          checkpoint_id?: string
          confidence_class?: string
          decided_by?: string
          evidence?: Json
          evidence_crop_path?: string | null
          group_key?: string
          id?: string
          inspection_id?: string
          kind?: string
          message?: string
          recommendation?: string | null
          requirement_id?: string | null
          rule_ref?: string
          severity?: string
          status?: string
          surface?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_findings_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "photo_findings_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "photo_findings_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "photo_findings_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      photo_inspection_events: {
        Row: {
          at: string
          detail: Json
          id: number
          inspection_id: string
          stage: string
        }
        Insert: {
          at?: string
          detail?: Json
          id?: never
          inspection_id: string
          stage: string
        }
        Update: {
          at?: string
          detail?: Json
          id?: never
          inspection_id?: string
          stage?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_inspection_events_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_inspections: {
        Row: {
          attempts: number
          checked: number | null
          checked_at: string | null
          cost_usd: number | null
          created_at: string
          decided: number | null
          degraded_mode: string | null
          evaluated_at: string | null
          extraction_errors: Json | null
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          last_error: string | null
          markets: string[]
          model_versions: Json | null
          overall: string | null
          packaging_level: string
          policy_applied: Json | null
          product_id: string | null
          product_key: string
          prompt_version: string | null
          reader_coverage: Json | null
          revision: number
          ruleset_sha256: string
          ruleset_version: string | null
          signed_at: string | null
          signed_by: string | null
          source_kind: string
          stale_since: string | null
          status: string
          superseded_by: string | null
          user_id: string
        }
        Insert: {
          attempts?: number
          checked?: number | null
          checked_at?: string | null
          cost_usd?: number | null
          created_at?: string
          decided?: number | null
          degraded_mode?: string | null
          evaluated_at?: string | null
          extraction_errors?: Json | null
          heartbeat_at?: string | null
          id?: string
          idempotency_key: string
          last_error?: string | null
          markets?: string[]
          model_versions?: Json | null
          overall?: string | null
          packaging_level: string
          policy_applied?: Json | null
          product_id?: string | null
          product_key: string
          prompt_version?: string | null
          reader_coverage?: Json | null
          revision?: number
          ruleset_sha256: string
          ruleset_version?: string | null
          signed_at?: string | null
          signed_by?: string | null
          source_kind: string
          stale_since?: string | null
          status?: string
          superseded_by?: string | null
          user_id: string
        }
        Update: {
          attempts?: number
          checked?: number | null
          checked_at?: string | null
          cost_usd?: number | null
          created_at?: string
          decided?: number | null
          degraded_mode?: string | null
          evaluated_at?: string | null
          extraction_errors?: Json | null
          heartbeat_at?: string | null
          id?: string
          idempotency_key?: string
          last_error?: string | null
          markets?: string[]
          model_versions?: Json | null
          overall?: string | null
          packaging_level?: string
          policy_applied?: Json | null
          product_id?: string | null
          product_key?: string
          prompt_version?: string | null
          reader_coverage?: Json | null
          revision?: number
          ruleset_sha256?: string
          ruleset_version?: string | null
          signed_at?: string | null
          signed_by?: string | null
          source_kind?: string
          stale_since?: string | null
          status?: string
          superseded_by?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_inspections_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "photo_inspections_ruleset_sha256_fkey"
            columns: ["ruleset_sha256"]
            isOneToOne: false
            referencedRelation: "ruleset_versions"
            referencedColumns: ["sha256"]
          },
          {
            foreignKeyName: "photo_inspections_superseded_by_fkey"
            columns: ["superseded_by"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_model_calls: {
        Row: {
          cost_usd: number
          id: number
          inspection_id: string
          latency_ms: number
          model: string
          provider: string
          stage: string
          tokens_in: number
          tokens_out: number
        }
        Insert: {
          cost_usd?: number
          id?: never
          inspection_id: string
          latency_ms?: number
          model?: string
          provider?: string
          stage: string
          tokens_in?: number
          tokens_out?: number
        }
        Update: {
          cost_usd?: number
          id?: never
          inspection_id?: string
          latency_ms?: number
          model?: string
          provider?: string
          stage?: string
          tokens_in?: number
          tokens_out?: number
        }
        Relationships: [
          {
            foreignKeyName: "photo_model_calls_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_not_checkable: {
        Row: {
          checkpoint_key: string
          class: string
          id: number
          inspection_id: string
          reason: string
          rule_ref: string
        }
        Insert: {
          checkpoint_key: string
          class: string
          id?: never
          inspection_id: string
          reason: string
          rule_ref?: string
        }
        Update: {
          checkpoint_key?: string
          class?: string
          id?: never
          inspection_id?: string
          reason?: string
          rule_ref?: string
        }
        Relationships: [
          {
            foreignKeyName: "photo_not_checkable_inspection_id_fkey"
            columns: ["inspection_id"]
            isOneToOne: false
            referencedRelation: "photo_inspections"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_product_dimensions: {
        Row: {
          depth_mm: number | null
          height_mm: number
          packaging_level: string
          product_id: string
          updated_at: string
          user_id: string
          width_mm: number
        }
        Insert: {
          depth_mm?: number | null
          height_mm: number
          packaging_level: string
          product_id: string
          updated_at?: string
          user_id: string
          width_mm: number
        }
        Update: {
          depth_mm?: number | null
          height_mm?: number
          packaging_level?: string
          product_id?: string
          updated_at?: string
          user_id?: string
          width_mm?: number
        }
        Relationships: [
          {
            foreignKeyName: "photo_product_dimensions_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
        ]
      }
      photo_profiles: {
        Row: {
          hs_prefixes: string[]
          profile_id: string
          title_ru: string
        }
        Insert: {
          hs_prefixes: string[]
          profile_id: string
          title_ru: string
        }
        Update: {
          hs_prefixes?: string[]
          profile_id?: string
          title_ru?: string
        }
        Relationships: []
      }
      photo_quota: {
        Row: {
          limit_n: number
          period_start: string
          refunds_used: number
          reserved: number
          spent_usd: number
          used: number
          user_id: string
        }
        Insert: {
          limit_n?: number
          period_start: string
          refunds_used?: number
          reserved?: number
          spent_usd?: number
          used?: number
          user_id: string
        }
        Update: {
          limit_n?: number
          period_start?: string
          refunds_used?: number
          reserved?: number
          spent_usd?: number
          used?: number
          user_id?: string
        }
        Relationships: []
      }
      products: {
        Row: {
          complexity_index: number | null
          created_at: string
          hierarchy_path: Json
          hs_code: string
          id: string
          is_active: boolean
          name_en: string | null
          name_ru: string
          name_uz: string | null
          parent_id: string | null
          product_type_id: string | null
          updated_at: string
        }
        Insert: {
          complexity_index?: number | null
          created_at?: string
          hierarchy_path?: Json
          hs_code: string
          id?: string
          is_active?: boolean
          name_en?: string | null
          name_ru: string
          name_uz?: string | null
          parent_id?: string | null
          product_type_id?: string | null
          updated_at?: string
        }
        Update: {
          complexity_index?: number | null
          created_at?: string
          hierarchy_path?: Json
          hs_code?: string
          id?: string
          is_active?: boolean
          name_en?: string | null
          name_ru?: string
          name_uz?: string | null
          parent_id?: string | null
          product_type_id?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "products_parent_id_fkey"
            columns: ["parent_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          company: string | null
          created_at: string
          full_name: string
          id: string
          is_subscribed: boolean
          phone: string | null
          subscribed_until: string | null
          updated_at: string
        }
        Insert: {
          company?: string | null
          created_at?: string
          full_name?: string
          id: string
          is_subscribed?: boolean
          phone?: string | null
          subscribed_until?: string | null
          updated_at?: string
        }
        Update: {
          company?: string | null
          created_at?: string
          full_name?: string
          id?: string
          is_subscribed?: boolean
          phone?: string | null
          subscribed_until?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      requirement_applicability: {
        Row: {
          code: string | null
          created_at: string
          id: string
          product_type_id: string | null
          requirement_id: string
          scope: Database["public"]["Enums"]["applicability_scope"]
        }
        Insert: {
          code?: string | null
          created_at?: string
          id?: string
          product_type_id?: string | null
          requirement_id: string
          scope: Database["public"]["Enums"]["applicability_scope"]
        }
        Update: {
          code?: string | null
          created_at?: string
          id?: string
          product_type_id?: string | null
          requirement_id?: string
          scope?: Database["public"]["Enums"]["applicability_scope"]
        }
        Relationships: [
          {
            foreignKeyName: "requirement_applicability_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_applicability_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_applicability_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_categories: {
        Row: {
          definition_ru: string | null
          is_active: boolean
          name_en: string | null
          name_ru: string
          name_uz: string | null
          slug: string
          sort_order: number
        }
        Insert: {
          definition_ru?: string | null
          is_active?: boolean
          name_en?: string | null
          name_ru: string
          name_uz?: string | null
          slug: string
          sort_order?: number
        }
        Update: {
          definition_ru?: string | null
          is_active?: boolean
          name_en?: string | null
          name_ru?: string
          name_uz?: string | null
          slug?: string
          sort_order?: number
        }
        Relationships: []
      }
      requirement_change_impacts: {
        Row: {
          action_required: string | null
          change_event_id: string
          created_at: string
          id: string
          is_in_favor: boolean | null
          requirement_id: string
          reviewed_at: string | null
          reviewed_by: string | null
          status: Database["public"]["Enums"]["impact_status"]
        }
        Insert: {
          action_required?: string | null
          change_event_id: string
          created_at?: string
          id?: string
          is_in_favor?: boolean | null
          requirement_id: string
          reviewed_at?: string | null
          reviewed_by?: string | null
          status?: Database["public"]["Enums"]["impact_status"]
        }
        Update: {
          action_required?: string | null
          change_event_id?: string
          created_at?: string
          id?: string
          is_in_favor?: boolean | null
          requirement_id?: string
          reviewed_at?: string | null
          reviewed_by?: string | null
          status?: Database["public"]["Enums"]["impact_status"]
        }
        Relationships: [
          {
            foreignKeyName: "requirement_change_impacts_change_event_id_fkey"
            columns: ["change_event_id"]
            isOneToOne: false
            referencedRelation: "change_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_change_impacts_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_change_impacts_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_change_impacts_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_citations: {
        Row: {
          created_at: string
          is_primary: boolean
          paragraph_id: string
          requirement_id: string
          sort_order: number
        }
        Insert: {
          created_at?: string
          is_primary?: boolean
          paragraph_id: string
          requirement_id: string
          sort_order?: number
        }
        Update: {
          created_at?: string
          is_primary?: boolean
          paragraph_id?: string
          requirement_id?: string
          sort_order?: number
        }
        Relationships: [
          {
            foreignKeyName: "requirement_citations_paragraph_id_fkey"
            columns: ["paragraph_id"]
            isOneToOne: false
            referencedRelation: "act_paragraphs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_citations_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_citations_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_citations_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_contents: {
        Row: {
          created_at: string
          lang: Database["public"]["Enums"]["lang_code"]
          requirement_id: string
          sanction_summary: string | null
          title: string
          translation_origin:
            | Database["public"]["Enums"]["translation_origin"]
            | null
          updated_at: string
        }
        Insert: {
          created_at?: string
          lang: Database["public"]["Enums"]["lang_code"]
          requirement_id: string
          sanction_summary?: string | null
          title: string
          translation_origin?:
            | Database["public"]["Enums"]["translation_origin"]
            | null
          updated_at?: string
        }
        Update: {
          created_at?: string
          lang?: Database["public"]["Enums"]["lang_code"]
          requirement_id?: string
          sanction_summary?: string | null
          title?: string
          translation_origin?:
            | Database["public"]["Enums"]["translation_origin"]
            | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "requirement_contents_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_contents_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_contents_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_details: {
        Row: {
          court_cases: Json | null
          created_at: string
          description: string | null
          documents: Json
          how_to_comply: Json
          lang: Database["public"]["Enums"]["lang_code"]
          lawyer_instruction: Json | null
          requirement_id: string
          sanctions: Json
          status_note: string | null
          templates: Json | null
          translation_origin:
            | Database["public"]["Enums"]["translation_origin"]
            | null
          updated_at: string
        }
        Insert: {
          court_cases?: Json | null
          created_at?: string
          description?: string | null
          documents?: Json
          how_to_comply?: Json
          lang: Database["public"]["Enums"]["lang_code"]
          lawyer_instruction?: Json | null
          requirement_id: string
          sanctions?: Json
          status_note?: string | null
          templates?: Json | null
          translation_origin?:
            | Database["public"]["Enums"]["translation_origin"]
            | null
          updated_at?: string
        }
        Update: {
          court_cases?: Json | null
          created_at?: string
          description?: string | null
          documents?: Json
          how_to_comply?: Json
          lang?: Database["public"]["Enums"]["lang_code"]
          lawyer_instruction?: Json | null
          requirement_id?: string
          sanctions?: Json
          status_note?: string | null
          templates?: Json | null
          translation_origin?:
            | Database["public"]["Enums"]["translation_origin"]
            | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "requirement_details_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_details_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_details_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_faqs: {
        Row: {
          answer: string
          created_at: string
          id: string
          lang: Database["public"]["Enums"]["lang_code"]
          question: string
          requirement_id: string
          sort_order: number
          source_question_id: string | null
          trust_label: Database["public"]["Enums"]["trust_label"]
          updated_at: string
        }
        Insert: {
          answer: string
          created_at?: string
          id?: string
          lang?: Database["public"]["Enums"]["lang_code"]
          question: string
          requirement_id: string
          sort_order?: number
          source_question_id?: string | null
          trust_label?: Database["public"]["Enums"]["trust_label"]
          updated_at?: string
        }
        Update: {
          answer?: string
          created_at?: string
          id?: string
          lang?: Database["public"]["Enums"]["lang_code"]
          question?: string
          requirement_id?: string
          sort_order?: number
          source_question_id?: string | null
          trust_label?: Database["public"]["Enums"]["trust_label"]
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "requirement_faqs_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_faqs_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_faqs_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
          {
            foreignKeyName: "requirement_faqs_source_question_id_fkey"
            columns: ["source_question_id"]
            isOneToOne: false
            referencedRelation: "user_questions"
            referencedColumns: ["id"]
          },
        ]
      }
      requirement_photo: {
        Row: {
          checkability: Database["public"]["Enums"]["photo_checkability"]
          created_at: string
          hs_prefixes: string[]
          markets: string[]
          pack: string
          packaging_level: Database["public"]["Enums"]["photo_packaging_level"]
          requirement_id: string | null
          rule_ref: string
          ruleset_sha256: string | null
          scope: string
          source: Json
          title_ru: string
          updated_at: string
          why: string
        }
        Insert: {
          checkability: Database["public"]["Enums"]["photo_checkability"]
          created_at?: string
          hs_prefixes?: string[]
          markets?: string[]
          pack?: string
          packaging_level?: Database["public"]["Enums"]["photo_packaging_level"]
          requirement_id?: string | null
          rule_ref: string
          ruleset_sha256?: string | null
          scope?: string
          source?: Json
          title_ru?: string
          updated_at?: string
          why: string
        }
        Update: {
          checkability?: Database["public"]["Enums"]["photo_checkability"]
          created_at?: string
          hs_prefixes?: string[]
          markets?: string[]
          pack?: string
          packaging_level?: Database["public"]["Enums"]["photo_packaging_level"]
          requirement_id?: string | null
          rule_ref?: string
          ruleset_sha256?: string | null
          scope?: string
          source?: Json
          title_ru?: string
          updated_at?: string
          why?: string
        }
        Relationships: [
          {
            foreignKeyName: "requirement_photo_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_photo_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_photo_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_photo_check_contents: {
        Row: {
          check_id: string
          hint: string | null
          lang: string
          question: string | null
          title: string | null
        }
        Insert: {
          check_id: string
          hint?: string | null
          lang: string
          question?: string | null
          title?: string | null
        }
        Update: {
          check_id?: string
          hint?: string | null
          lang?: string
          question?: string | null
          title?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "requirement_photo_check_contents_check_id_fkey"
            columns: ["check_id"]
            isOneToOne: false
            referencedRelation: "requirement_photo_checks"
            referencedColumns: ["id"]
          },
        ]
      }
      requirement_photo_checks: {
        Row: {
          check_id: string
          created_at: string
          group_key: string
          hint_ru: string | null
          id: string
          kind: Database["public"]["Enums"]["photo_check_kind"]
          measure: string | null
          ord: number
          packaging_level: Database["public"]["Enums"]["photo_packaging_level"]
          params: Json
          question_ru: string | null
          rule_ref: string
          severity: Database["public"]["Enums"]["photo_severity"]
          subject: string
          target: string | null
          title_ru: string | null
        }
        Insert: {
          check_id: string
          created_at?: string
          group_key: string
          hint_ru?: string | null
          id?: string
          kind: Database["public"]["Enums"]["photo_check_kind"]
          measure?: string | null
          ord?: number
          packaging_level?: Database["public"]["Enums"]["photo_packaging_level"]
          params?: Json
          question_ru?: string | null
          rule_ref: string
          severity?: Database["public"]["Enums"]["photo_severity"]
          subject?: string
          target?: string | null
          title_ru?: string | null
        }
        Update: {
          check_id?: string
          created_at?: string
          group_key?: string
          hint_ru?: string | null
          id?: string
          kind?: Database["public"]["Enums"]["photo_check_kind"]
          measure?: string | null
          ord?: number
          packaging_level?: Database["public"]["Enums"]["photo_packaging_level"]
          params?: Json
          question_ru?: string | null
          rule_ref?: string
          severity?: Database["public"]["Enums"]["photo_severity"]
          subject?: string
          target?: string | null
          title_ru?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "requirement_photo_checks_rule_ref_fkey"
            columns: ["rule_ref"]
            isOneToOne: false
            referencedRelation: "requirement_photo"
            referencedColumns: ["rule_ref"]
          },
        ]
      }
      requirement_reviews: {
        Row: {
          comment_text: string
          created_at: string
          id: string
          lawyer_id: string
          official_replied_at: string | null
          official_reply: string | null
          published_at: string | null
          requirement_id: string
          status: Database["public"]["Enums"]["review_status"]
          verdict: Database["public"]["Enums"]["review_verdict"]
        }
        Insert: {
          comment_text: string
          created_at?: string
          id?: string
          lawyer_id: string
          official_replied_at?: string | null
          official_reply?: string | null
          published_at?: string | null
          requirement_id: string
          status?: Database["public"]["Enums"]["review_status"]
          verdict: Database["public"]["Enums"]["review_verdict"]
        }
        Update: {
          comment_text?: string
          created_at?: string
          id?: string
          lawyer_id?: string
          official_replied_at?: string | null
          official_reply?: string | null
          published_at?: string | null
          requirement_id?: string
          status?: Database["public"]["Enums"]["review_status"]
          verdict?: Database["public"]["Enums"]["review_verdict"]
        }
        Relationships: [
          {
            foreignKeyName: "requirement_reviews_lawyer_id_fkey"
            columns: ["lawyer_id"]
            isOneToOne: false
            referencedRelation: "lawyer_profiles"
            referencedColumns: ["user_id"]
          },
          {
            foreignKeyName: "requirement_reviews_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_reviews_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_reviews_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_revisions: {
        Row: {
          change_event_id: string | null
          change_note: string | null
          created_at: string
          created_by: string | null
          id: string
          requirement_id: string
          revision_no: number
          snapshot: Json
        }
        Insert: {
          change_event_id?: string | null
          change_note?: string | null
          created_at?: string
          created_by?: string | null
          id?: string
          requirement_id: string
          revision_no: number
          snapshot: Json
        }
        Update: {
          change_event_id?: string | null
          change_note?: string | null
          created_at?: string
          created_by?: string | null
          id?: string
          requirement_id?: string
          revision_no?: number
          snapshot?: Json
        }
        Relationships: [
          {
            foreignKeyName: "requirement_revisions_change_event_id_fkey"
            columns: ["change_event_id"]
            isOneToOne: false
            referencedRelation: "change_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_revisions_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_revisions_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_revisions_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_rules: {
        Row: {
          created_at: string
          id: string
          requirement_id: string
          rule: Json
          verified: boolean
        }
        Insert: {
          created_at?: string
          id?: string
          requirement_id: string
          rule: Json
          verified?: boolean
        }
        Update: {
          created_at?: string
          id?: string
          requirement_id?: string
          rule?: Json
          verified?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "requirement_rules_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_rules_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_rules_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirement_sources: {
        Row: {
          created_at: string
          import_item_id: string
          requirement_id: string
        }
        Insert: {
          created_at?: string
          import_item_id: string
          requirement_id: string
        }
        Update: {
          created_at?: string
          import_item_id?: string
          requirement_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "requirement_sources_import_item_id_fkey"
            columns: ["import_item_id"]
            isOneToOne: false
            referencedRelation: "import_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_sources_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_sources_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_sources_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirements: {
        Row: {
          addressee_roles: Database["public"]["Enums"]["party_role"][]
          authority_id: string | null
          category_slug: string | null
          confidence_score: number | null
          created_at: string
          created_by: string | null
          deontic: Database["public"]["Enums"]["deontic_type"]
          effective_from: string | null
          external_key: string | null
          flagged_at: string | null
          flagged_by_event_id: string | null
          id: string
          jurisdiction: string
          lifecycle_stage_id: string | null
          nature: Database["public"]["Enums"]["requirement_nature"] | null
          operation: Database["public"]["Enums"]["operation_domain"]
          origin: Database["public"]["Enums"]["requirement_origin"]
          published_at: string | null
          repealed_by_ref: string | null
          requirement_category:
            | Database["public"]["Enums"]["requirement_category"]
            | null
          review_flag: Database["public"]["Enums"]["review_flag"]
          reviewed_at: string | null
          reviewed_by: string | null
          status: Database["public"]["Enums"]["requirement_status"]
          transition_until: string | null
          transport_type: Database["public"]["Enums"]["transport_type"] | null
          trust_label: Database["public"]["Enums"]["trust_label"]
          updated_at: string
          valid_to: string | null
        }
        Insert: {
          addressee_roles?: Database["public"]["Enums"]["party_role"][]
          authority_id?: string | null
          category_slug?: string | null
          confidence_score?: number | null
          created_at?: string
          created_by?: string | null
          deontic: Database["public"]["Enums"]["deontic_type"]
          effective_from?: string | null
          external_key?: string | null
          flagged_at?: string | null
          flagged_by_event_id?: string | null
          id?: string
          jurisdiction?: string
          lifecycle_stage_id?: string | null
          nature?: Database["public"]["Enums"]["requirement_nature"] | null
          operation: Database["public"]["Enums"]["operation_domain"]
          origin?: Database["public"]["Enums"]["requirement_origin"]
          published_at?: string | null
          repealed_by_ref?: string | null
          requirement_category?:
            | Database["public"]["Enums"]["requirement_category"]
            | null
          review_flag?: Database["public"]["Enums"]["review_flag"]
          reviewed_at?: string | null
          reviewed_by?: string | null
          status?: Database["public"]["Enums"]["requirement_status"]
          transition_until?: string | null
          transport_type?: Database["public"]["Enums"]["transport_type"] | null
          trust_label?: Database["public"]["Enums"]["trust_label"]
          updated_at?: string
          valid_to?: string | null
        }
        Update: {
          addressee_roles?: Database["public"]["Enums"]["party_role"][]
          authority_id?: string | null
          category_slug?: string | null
          confidence_score?: number | null
          created_at?: string
          created_by?: string | null
          deontic?: Database["public"]["Enums"]["deontic_type"]
          effective_from?: string | null
          external_key?: string | null
          flagged_at?: string | null
          flagged_by_event_id?: string | null
          id?: string
          jurisdiction?: string
          lifecycle_stage_id?: string | null
          nature?: Database["public"]["Enums"]["requirement_nature"] | null
          operation?: Database["public"]["Enums"]["operation_domain"]
          origin?: Database["public"]["Enums"]["requirement_origin"]
          published_at?: string | null
          repealed_by_ref?: string | null
          requirement_category?:
            | Database["public"]["Enums"]["requirement_category"]
            | null
          review_flag?: Database["public"]["Enums"]["review_flag"]
          reviewed_at?: string | null
          reviewed_by?: string | null
          status?: Database["public"]["Enums"]["requirement_status"]
          transition_until?: string | null
          transport_type?: Database["public"]["Enums"]["transport_type"] | null
          trust_label?: Database["public"]["Enums"]["trust_label"]
          updated_at?: string
          valid_to?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "requirements_authority_id_fkey"
            columns: ["authority_id"]
            isOneToOne: false
            referencedRelation: "authorities"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirements_category_slug_fkey"
            columns: ["category_slug"]
            isOneToOne: false
            referencedRelation: "requirement_categories"
            referencedColumns: ["slug"]
          },
          {
            foreignKeyName: "requirements_flagged_by_event_id_fkey"
            columns: ["flagged_by_event_id"]
            isOneToOne: false
            referencedRelation: "change_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirements_lifecycle_stage_id_fkey"
            columns: ["lifecycle_stage_id"]
            isOneToOne: false
            referencedRelation: "lifecycle_stages"
            referencedColumns: ["id"]
          },
        ]
      }
      review_votes: {
        Row: {
          created_at: string
          review_id: string
          user_id: string
          vote: number
        }
        Insert: {
          created_at?: string
          review_id: string
          user_id: string
          vote: number
        }
        Update: {
          created_at?: string
          review_id?: string
          user_id?: string
          vote?: number
        }
        Relationships: [
          {
            foreignKeyName: "review_votes_review_id_fkey"
            columns: ["review_id"]
            isOneToOne: false
            referencedRelation: "requirement_reviews"
            referencedColumns: ["id"]
          },
        ]
      }
      ruleset_versions: {
        Row: {
          built_at: string
          checks_count: number
          is_current: boolean
          packs: Json
          sha256: string
          version: string
        }
        Insert: {
          built_at?: string
          checks_count?: number
          is_current?: boolean
          packs?: Json
          sha256: string
          version: string
        }
        Update: {
          built_at?: string
          checks_count?: number
          is_current?: boolean
          packs?: Json
          sha256?: string
          version?: string
        }
        Relationships: []
      }
      search_aliases: {
        Row: {
          alias: string
          created_at: string
          id: string
          is_default: boolean
          lang: Database["public"]["Enums"]["lang_code"]
          product_id: string | null
          service_id: string | null
        }
        Insert: {
          alias: string
          created_at?: string
          id?: string
          is_default?: boolean
          lang?: Database["public"]["Enums"]["lang_code"]
          product_id?: string | null
          service_id?: string | null
        }
        Update: {
          alias?: string
          created_at?: string
          id?: string
          is_default?: boolean
          lang?: Database["public"]["Enums"]["lang_code"]
          product_id?: string | null
          service_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "search_aliases_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "search_aliases_service_id_fkey"
            columns: ["service_id"]
            isOneToOne: false
            referencedRelation: "services"
            referencedColumns: ["id"]
          },
        ]
      }
      services: {
        Row: {
          admission_mode: Database["public"]["Enums"]["admission_mode"] | null
          authority_id: string | null
          complexity_index: number | null
          created_at: string
          id: string
          ikpu_code: string | null
          is_active: boolean
          name_en: string | null
          name_ru: string
          name_uz: string | null
          oked_code: string | null
          product_type_id: string | null
          updated_at: string
        }
        Insert: {
          admission_mode?: Database["public"]["Enums"]["admission_mode"] | null
          authority_id?: string | null
          complexity_index?: number | null
          created_at?: string
          id?: string
          ikpu_code?: string | null
          is_active?: boolean
          name_en?: string | null
          name_ru: string
          name_uz?: string | null
          oked_code?: string | null
          product_type_id?: string | null
          updated_at?: string
        }
        Update: {
          admission_mode?: Database["public"]["Enums"]["admission_mode"] | null
          authority_id?: string | null
          complexity_index?: number | null
          created_at?: string
          id?: string
          ikpu_code?: string | null
          is_active?: boolean
          name_en?: string | null
          name_ru?: string
          name_uz?: string | null
          oked_code?: string | null
          product_type_id?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "services_authority_id_fkey"
            columns: ["authority_id"]
            isOneToOne: false
            referencedRelation: "authorities"
            referencedColumns: ["id"]
          },
        ]
      }
      subscription_requests: {
        Row: {
          company: string | null
          contact: string
          created_at: string
          full_name: string
          handled_at: string | null
          id: string
          note: string | null
          status: Database["public"]["Enums"]["subscription_request_status"]
          user_id: string | null
        }
        Insert: {
          company?: string | null
          contact: string
          created_at?: string
          full_name: string
          handled_at?: string | null
          id?: string
          note?: string | null
          status?: Database["public"]["Enums"]["subscription_request_status"]
          user_id?: string | null
        }
        Update: {
          company?: string | null
          contact?: string
          created_at?: string
          full_name?: string
          handled_at?: string | null
          id?: string
          note?: string | null
          status?: Database["public"]["Enums"]["subscription_request_status"]
          user_id?: string | null
        }
        Relationships: []
      }
      user_notifications: {
        Row: {
          created_at: string
          id: string
          impact_id: string | null
          is_read: boolean
          kind: string
          payload: Json | null
          product_id: string | null
          read_at: string | null
          requirement_id: string
          service_id: string | null
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          impact_id?: string | null
          is_read?: boolean
          kind?: string
          payload?: Json | null
          product_id?: string | null
          read_at?: string | null
          requirement_id: string
          service_id?: string | null
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          impact_id?: string | null
          is_read?: boolean
          kind?: string
          payload?: Json | null
          product_id?: string | null
          read_at?: string | null
          requirement_id?: string
          service_id?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_notifications_impact_id_fkey"
            columns: ["impact_id"]
            isOneToOne: false
            referencedRelation: "requirement_change_impacts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_notifications_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_notifications_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_notifications_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_notifications_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
          {
            foreignKeyName: "user_notifications_service_id_fkey"
            columns: ["service_id"]
            isOneToOne: false
            referencedRelation: "services"
            referencedColumns: ["id"]
          },
        ]
      }
      user_questions: {
        Row: {
          allow_official_request: boolean
          answer_text: string | null
          answered_at: string | null
          created_at: string
          id: string
          is_urgent: boolean
          legal_review_only: boolean
          product_id: string | null
          question_text: string
          requirement_id: string | null
          response_file_url: string | null
          status: Database["public"]["Enums"]["question_status"]
          user_id: string
        }
        Insert: {
          allow_official_request?: boolean
          answer_text?: string | null
          answered_at?: string | null
          created_at?: string
          id?: string
          is_urgent?: boolean
          legal_review_only?: boolean
          product_id?: string | null
          question_text: string
          requirement_id?: string | null
          response_file_url?: string | null
          status?: Database["public"]["Enums"]["question_status"]
          user_id: string
        }
        Update: {
          allow_official_request?: boolean
          answer_text?: string | null
          answered_at?: string | null
          created_at?: string
          id?: string
          is_urgent?: boolean
          legal_review_only?: boolean
          product_id?: string | null
          question_text?: string
          requirement_id?: string | null
          response_file_url?: string | null
          status?: Database["public"]["Enums"]["question_status"]
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_questions_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_questions_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_questions_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_questions_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
    }
    Views: {
      lawyer_leaderboard: {
        Row: {
          credentials: string | null
          display_name: string | null
          helpful_total: number | null
          lawyer_id: string | null
          not_helpful_total: number | null
          rank: number | null
          requirements_reviewed: number | null
          reviews_published: number | null
        }
        Relationships: [
          {
            foreignKeyName: "requirement_reviews_lawyer_id_fkey"
            columns: ["lawyer_id"]
            isOneToOne: false
            referencedRelation: "lawyer_profiles"
            referencedColumns: ["user_id"]
          },
        ]
      }
      lawyer_stats: {
        Row: {
          helpful_total: number | null
          lawyer_id: string | null
          not_helpful_total: number | null
          requirements_reviewed: number | null
          reviews_published: number | null
        }
        Relationships: [
          {
            foreignKeyName: "requirement_reviews_lawyer_id_fkey"
            columns: ["lawyer_id"]
            isOneToOne: false
            referencedRelation: "lawyer_profiles"
            referencedColumns: ["user_id"]
          },
        ]
      }
      requirement_review_stats: {
        Row: {
          confirms: number | null
          disputes: number | null
          requirement_id: string | null
          total: number | null
        }
        Relationships: [
          {
            foreignKeyName: "requirement_reviews_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_reviews_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "requirements_with_status"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirement_reviews_requirement_id_fkey"
            columns: ["requirement_id"]
            isOneToOne: false
            referencedRelation: "user_deadline_events"
            referencedColumns: ["requirement_id"]
          },
        ]
      }
      requirements_with_status: {
        Row: {
          addressee_roles: Database["public"]["Enums"]["party_role"][] | null
          authority_id: string | null
          category_slug: string | null
          confidence_score: number | null
          created_at: string | null
          created_by: string | null
          deontic: Database["public"]["Enums"]["deontic_type"] | null
          effective_from: string | null
          external_key: string | null
          flagged_at: string | null
          flagged_by_event_id: string | null
          id: string | null
          jurisdiction: string | null
          lifecycle: string | null
          lifecycle_stage_id: string | null
          nature: Database["public"]["Enums"]["requirement_nature"] | null
          operation: Database["public"]["Enums"]["operation_domain"] | null
          origin: Database["public"]["Enums"]["requirement_origin"] | null
          published_at: string | null
          repealed_by_ref: string | null
          requirement_category:
            | Database["public"]["Enums"]["requirement_category"]
            | null
          review_flag: Database["public"]["Enums"]["review_flag"] | null
          reviewed_at: string | null
          reviewed_by: string | null
          status: Database["public"]["Enums"]["requirement_status"] | null
          transition_until: string | null
          transport_type: Database["public"]["Enums"]["transport_type"] | null
          trust_label: Database["public"]["Enums"]["trust_label"] | null
          updated_at: string | null
          valid_to: string | null
        }
        Insert: {
          addressee_roles?: Database["public"]["Enums"]["party_role"][] | null
          authority_id?: string | null
          category_slug?: string | null
          confidence_score?: number | null
          created_at?: string | null
          created_by?: string | null
          deontic?: Database["public"]["Enums"]["deontic_type"] | null
          effective_from?: string | null
          external_key?: string | null
          flagged_at?: string | null
          flagged_by_event_id?: string | null
          id?: string | null
          jurisdiction?: string | null
          lifecycle?: never
          lifecycle_stage_id?: string | null
          nature?: Database["public"]["Enums"]["requirement_nature"] | null
          operation?: Database["public"]["Enums"]["operation_domain"] | null
          origin?: Database["public"]["Enums"]["requirement_origin"] | null
          published_at?: string | null
          repealed_by_ref?: string | null
          requirement_category?:
            | Database["public"]["Enums"]["requirement_category"]
            | null
          review_flag?: Database["public"]["Enums"]["review_flag"] | null
          reviewed_at?: string | null
          reviewed_by?: string | null
          status?: Database["public"]["Enums"]["requirement_status"] | null
          transition_until?: string | null
          transport_type?: Database["public"]["Enums"]["transport_type"] | null
          trust_label?: Database["public"]["Enums"]["trust_label"] | null
          updated_at?: string | null
          valid_to?: string | null
        }
        Update: {
          addressee_roles?: Database["public"]["Enums"]["party_role"][] | null
          authority_id?: string | null
          category_slug?: string | null
          confidence_score?: number | null
          created_at?: string | null
          created_by?: string | null
          deontic?: Database["public"]["Enums"]["deontic_type"] | null
          effective_from?: string | null
          external_key?: string | null
          flagged_at?: string | null
          flagged_by_event_id?: string | null
          id?: string | null
          jurisdiction?: string | null
          lifecycle?: never
          lifecycle_stage_id?: string | null
          nature?: Database["public"]["Enums"]["requirement_nature"] | null
          operation?: Database["public"]["Enums"]["operation_domain"] | null
          origin?: Database["public"]["Enums"]["requirement_origin"] | null
          published_at?: string | null
          repealed_by_ref?: string | null
          requirement_category?:
            | Database["public"]["Enums"]["requirement_category"]
            | null
          review_flag?: Database["public"]["Enums"]["review_flag"] | null
          reviewed_at?: string | null
          reviewed_by?: string | null
          status?: Database["public"]["Enums"]["requirement_status"] | null
          transition_until?: string | null
          transport_type?: Database["public"]["Enums"]["transport_type"] | null
          trust_label?: Database["public"]["Enums"]["trust_label"] | null
          updated_at?: string | null
          valid_to?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "requirements_authority_id_fkey"
            columns: ["authority_id"]
            isOneToOne: false
            referencedRelation: "authorities"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirements_category_slug_fkey"
            columns: ["category_slug"]
            isOneToOne: false
            referencedRelation: "requirement_categories"
            referencedColumns: ["slug"]
          },
          {
            foreignKeyName: "requirements_flagged_by_event_id_fkey"
            columns: ["flagged_by_event_id"]
            isOneToOne: false
            referencedRelation: "change_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "requirements_lifecycle_stage_id_fkey"
            columns: ["lifecycle_stage_id"]
            isOneToOne: false
            referencedRelation: "lifecycle_stages"
            referencedColumns: ["id"]
          },
        ]
      }
      review_vote_counts: {
        Row: {
          helpful: number | null
          not_helpful: number | null
          review_id: string | null
        }
        Relationships: [
          {
            foreignKeyName: "review_votes_review_id_fkey"
            columns: ["review_id"]
            isOneToOne: false
            referencedRelation: "requirement_reviews"
            referencedColumns: ["id"]
          },
        ]
      }
      user_deadline_events: {
        Row: {
          event_date: string | null
          event_kind: string | null
          jurisdiction: string | null
          requirement_id: string | null
          title: string | null
          user_id: string | null
        }
        Relationships: []
      }
    }
    Functions: {
      create_photo_revision: {
        Args: { p_parent_id: string; p_payload: Json }
        Returns: string
      }
      fanout_change_notifications: {
        Args: { p_impact_ids: string[] }
        Returns: number
      }
      finalize_photo_inspection: {
        Args: {
          p_inspection_id: string
          p_outcome: string
          p_payload?: Json
          p_reason?: string
        }
        Returns: undefined
      }
      flag_stale_photo_inspections: { Args: never; Returns: number }
      ingest_change_event: {
        Args: { p_payload: Json; p_secret: string }
        Returns: string
      }
      is_subscriber: { Args: never; Returns: boolean }
      is_verified_lawyer: { Args: never; Returns: boolean }
      lifecycle_status: {
        Args: {
          p_effective_from: string
          p_today?: string
          p_transition_until: string
          p_valid_to: string
        }
        Returns: string
      }
      notify_admin_telegram: { Args: { message: string }; Returns: undefined }
      photo_checklist: {
        Args: { p_level: string; p_markets?: string[]; p_product_id: string }
        Returns: {
          check_id: string
          group_key: string
          hint_ru: string
          kind: Database["public"]["Enums"]["photo_check_kind"]
          measure: string
          params: Json
          question_ru: string
          requirement_id: string
          rule_ref: string
          severity: Database["public"]["Enums"]["photo_severity"]
          subject: string
          target: string
          title_ru: string
        }[]
      }
      photo_profile_for_product: {
        Args: { p_product_id: string }
        Returns: string
      }
      process_lifecycle_transitions: { Args: never; Returns: number }
      purge_expired_photo_assets: { Args: never; Returns: number }
      reap_stale_inspections: { Args: never; Returns: number }
      record_finding_action: {
        Args: { p_action: string; p_finding_id: string; p_reason?: string }
        Returns: string
      }
      replace_requirement_children: {
        Args: {
          p_applicability: Json
          p_contents: Json
          p_details: Json
          p_requirement_id: string
          p_rules: Json
        }
        Returns: undefined
      }
      request_photo_inspection: {
        Args: {
          p_asset_paths: string[]
          p_idempotency_key: string
          p_level: string
          p_markets: string[]
          p_product_id: string
          p_source_kind: string
        }
        Returns: string
      }
      request_photo_retake: {
        Args: {
          p_idempotency_key: string
          p_inspection_id: string
          p_new_asset_paths: string[]
        }
        Returns: string
      }
      review_votable: { Args: { rid: string }; Returns: boolean }
      sign_photo_inspection: {
        Args: { p_inspection_id: string }
        Returns: undefined
      }
    }
    Enums: {
      act_status: "active" | "repealed" | "pending"
      admission_mode: "license" | "permit" | "notification" | "free"
      applicability_scope:
        | "hs_code"
        | "hs_prefix"
        | "ikpu_code"
        | "ikpu_prefix"
        | "all_products"
        | "all_services"
        | "oked_code"
        | "oked_prefix"
        | "product_type"
      change_event_type: "new" | "amended" | "repealed" | "effective_soon"
      change_source: "jurisbase" | "manual"
      content_request_kind:
        | "fill_product"
        | "missing_product"
        | "missing_section"
      content_request_status: "new" | "planned" | "done"
      deontic_type: "obligation" | "prohibition" | "permission"
      impact_status: "pending_review" | "confirmed" | "dismissed"
      importance_level: "high" | "medium" | "low"
      lang_code: "ru" | "uz" | "en"
      lawyer_notification_kind:
        | "review_published"
        | "review_rejected"
        | "new_requirement"
      lawyer_status: "pending" | "verified" | "rejected"
      operation_domain:
        | "product"
        | "realization"
        | "import"
        | "export"
        | "transit"
        | "re_export"
        | "re_import"
        | "service"
      party_role:
        | "producer"
        | "importer"
        | "exporter"
        | "seller"
        | "carrier"
        | "all"
        | "service_provider"
      photo_check_kind: "presence" | "text_semantic" | "absence" | "geometry"
      photo_checkability: "checkable" | "partial" | "not_checkable"
      photo_packaging_level: "consumer" | "transport" | "both"
      photo_severity: "critical" | "major" | "minor" | "info"
      question_status:
        | "new"
        | "ai_answered"
        | "expert_answered"
        | "gr_sent"
        | "gr_answered"
        | "closed"
      requirement_category:
        | "sps"
        | "tbt"
        | "marking"
        | "licensing"
        | "fiscal"
        | "currency"
        | "customs"
        | "origin"
      requirement_nature: "one_time" | "recurring"
      requirement_origin: "migration_v1" | "ai_pipeline" | "manual"
      requirement_status: "draft" | "in_review" | "published" | "archived"
      review_flag: "none" | "flagged_by_change"
      review_status: "pending" | "published" | "rejected"
      review_verdict: "confirm" | "inaccurate" | "outdated" | "addition"
      subscription_request_status:
        | "new"
        | "contacted"
        | "activated"
        | "rejected"
      translation_origin: "verbatim" | "machine"
      transport_type: "avto" | "avia" | "train"
      trust_label:
        | "ai_draft"
        | "lawyer_verified"
        | "official_answer"
        | "validated"
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
  catalog: {
    Enums: {},
  },
  graphql_public: {
    Enums: {},
  },
  pipeline: {
    Enums: {},
  },
  public: {
    Enums: {
      act_status: ["active", "repealed", "pending"],
      admission_mode: ["license", "permit", "notification", "free"],
      applicability_scope: [
        "hs_code",
        "hs_prefix",
        "ikpu_code",
        "ikpu_prefix",
        "all_products",
        "all_services",
        "oked_code",
        "oked_prefix",
        "product_type",
      ],
      change_event_type: ["new", "amended", "repealed", "effective_soon"],
      change_source: ["jurisbase", "manual"],
      content_request_kind: [
        "fill_product",
        "missing_product",
        "missing_section",
      ],
      content_request_status: ["new", "planned", "done"],
      deontic_type: ["obligation", "prohibition", "permission"],
      impact_status: ["pending_review", "confirmed", "dismissed"],
      importance_level: ["high", "medium", "low"],
      lang_code: ["ru", "uz", "en"],
      lawyer_notification_kind: [
        "review_published",
        "review_rejected",
        "new_requirement",
      ],
      lawyer_status: ["pending", "verified", "rejected"],
      operation_domain: [
        "product",
        "realization",
        "import",
        "export",
        "transit",
        "re_export",
        "re_import",
        "service",
      ],
      party_role: [
        "producer",
        "importer",
        "exporter",
        "seller",
        "carrier",
        "all",
        "service_provider",
      ],
      photo_check_kind: ["presence", "text_semantic", "absence", "geometry"],
      photo_checkability: ["checkable", "partial", "not_checkable"],
      photo_packaging_level: ["consumer", "transport", "both"],
      photo_severity: ["critical", "major", "minor", "info"],
      question_status: [
        "new",
        "ai_answered",
        "expert_answered",
        "gr_sent",
        "gr_answered",
        "closed",
      ],
      requirement_category: [
        "sps",
        "tbt",
        "marking",
        "licensing",
        "fiscal",
        "currency",
        "customs",
        "origin",
      ],
      requirement_nature: ["one_time", "recurring"],
      requirement_origin: ["migration_v1", "ai_pipeline", "manual"],
      requirement_status: ["draft", "in_review", "published", "archived"],
      review_flag: ["none", "flagged_by_change"],
      review_status: ["pending", "published", "rejected"],
      review_verdict: ["confirm", "inaccurate", "outdated", "addition"],
      subscription_request_status: [
        "new",
        "contacted",
        "activated",
        "rejected",
      ],
      translation_origin: ["verbatim", "machine"],
      transport_type: ["avto", "avia", "train"],
      trust_label: [
        "ai_draft",
        "lawyer_verified",
        "official_answer",
        "validated",
      ],
    },
  },
} as const

