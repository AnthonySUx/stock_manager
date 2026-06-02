export interface Item {
  id: number;
  name: string;
  category: string;
  owner: string;
  purchase_date: string;
  quantity_value: number;
  quantity_unit: string;
  location: string;
  unopened_expiration_date: string;
  opened_expiration_date: string | null;
  opened_date: string | null;
  current_expiration_date: string;
  status: 'active' | 'consumed' | 'expiring soon' | 'expired';
  notes: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ItemCreate {
  name: string;
  category: string;
  owner: string;
  purchase_date?: string;
  quantity_value: number;
  quantity_unit: string;
  location: string;
  unopened_expiration_date: string;
  opened_expiration_date?: string | null;
  opened_date?: string | null;
  current_expiration_date: string;
  notes?: string | null;
}

export interface ItemUpdate {
  name?: string;
  category?: string;
  owner?: string;
  purchase_date?: string;
  quantity_value?: number;
  quantity_unit?: string;
  location?: string;
  unopened_expiration_date?: string;
  opened_expiration_date?: string | null;
  opened_date?: string | null;
  current_expiration_date?: string;
  notes?: string | null;
}

export interface ConsumeRequest {
  quantity: number;
  add_to_restock: boolean;
}

export interface RestockItem {
  id: number;
  name: string;
  category: string | null;
  quantity_value: number | null;
  quantity_unit: string | null;
  source_item_id: number | null;
  status: 'pending' | 'done';
  notes: string | null;
  created_at?: string;
  done_at?: string | null;
}

export interface RestockItemCreate {
  name: string;
  category?: string;
  quantity_value?: number;
  quantity_unit?: string;
  source_item_id?: number;
  notes?: string;
}

export interface RestockItemUpdate {
  name?: string;
  category?: string;
  quantity_value?: number;
  quantity_unit?: string;
  status?: string;
  notes?: string;
}

export interface RestockDoneRequest {
  purchased_quantity: number;
  owner?: string;
  purchase_date?: string;
  location?: string;
  unopened_expiration_date?: string;
  opened_expiration_date?: string | null;
  opened_date?: string | null;
}

export interface Settings {
  default_database: string;
  expiration_reminder_days: string;
}

export interface HealthResponse {
  status: string;
  version: string;
}
