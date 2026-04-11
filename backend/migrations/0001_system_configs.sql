create table if not exists system_configs (
    id text primary key,
    llm_config_json jsonb not null default '{}'::jsonb,
    other_config_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
