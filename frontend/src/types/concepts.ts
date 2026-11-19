export interface ConceptBlock {
  concept_id: string;
  category: string;
  name: string;
  simple_description: string;
  friendly_icon: string;
  default_params?: Record<string, any>;
  signal_key?: string;
}

export interface ConfluenceRecipe {
  recipe_id: string;
  name: string;
  tagline: string;
  methodologies: string[];
  blocks: string[]; // concept_ids
  plain_english_rule: string;
  risk_reward: string;
  win_rate_benchmark: string;
}
