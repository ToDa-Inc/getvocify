import { api } from "@/shared/lib/api-client";

export interface GlossaryItem {
  id?: string;
  user_id?: string;
  target_word: string;
  phonetic_hints: string[];
  boost_factor: number;
  category: string;
  created_at?: string;
}

export interface GlossaryTemplate {
  id: string;
  name: string;
  description: string;
  item_count: number;
}

export const glossaryApi = {
  getGlossary: async () => {
    return api.get<GlossaryItem[]>("/glossary");
  },

  getTemplates: async () => {
    return api.get<GlossaryTemplate[]>("/glossary/templates");
  },

  importTemplate: async (templateId: string) => {
    return api.post<GlossaryItem[]>(`/glossary/import/${templateId}`);
  },

  suggestHints: async (word: string, category: string = "General") => {
    return api.get<{ word: string; hints: string[] }>(`/glossary/suggest/${word}?category=${category}`);
  },

  addItem: async (item: Partial<GlossaryItem>) => {
    return api.post<GlossaryItem>("/glossary", item);
  },

  updateItem: async (id: string, item: Partial<GlossaryItem>) => {
    return api.patch<GlossaryItem>(`/glossary/${id}`, item);
  },

  deleteItem: async (id: string) => {
    return api.delete(`/glossary/${id}`);
  },
};
