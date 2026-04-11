create table if not exists rust_projects (
    id uuid primary key,
    name text not null,
    description text not null default '',
    source_type text not null default 'zip',
    repository_type text not null default 'other',
    default_branch text not null default 'main',
    programming_languages_json jsonb not null default '[]'::jsonb,
    is_active boolean not null default true,
    language_info_json jsonb not null default '{}'::jsonb,
    info_status text not null default 'pending',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists rust_project_archives (
    project_id uuid primary key references rust_projects(id) on delete cascade,
    original_filename text not null,
    storage_path text not null,
    sha256 text not null,
    file_size bigint not null default 0,
    uploaded_at timestamptz not null default now()
);
