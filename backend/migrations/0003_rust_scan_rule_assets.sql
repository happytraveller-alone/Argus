create table if not exists rust_scan_rule_assets (
    engine text not null,
    source_kind text not null,
    asset_path text not null,
    file_format text not null,
    sha256 text not null,
    content text not null,
    metadata_json jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (engine, source_kind, asset_path)
);

create index if not exists ix_rust_scan_rule_assets_engine_kind
    on rust_scan_rule_assets (engine, source_kind, is_active);
