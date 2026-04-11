use anyhow::Result;
use sqlx::PgPool;

#[derive(Clone, Copy)]
struct LegacyMirrorTableSpec {
    name: &'static str,
    ddl: &'static str,
}

const LEGACY_MIRROR_TABLE_SPECS: &[LegacyMirrorTableSpec] = &[
    LegacyMirrorTableSpec {
        name: "users",
        ddl: r#"
        create table if not exists users (
            id varchar primary key,
            email varchar not null default '',
            hashed_password varchar not null default '',
            full_name varchar,
            is_active boolean not null default true,
            is_superuser boolean not null default false,
            phone varchar,
            avatar_url varchar,
            role varchar not null default 'member',
            github_username varchar,
            gitlab_username varchar,
            created_at timestamptz not null default now(),
            updated_at timestamptz
        )
        "#,
    },
    LegacyMirrorTableSpec {
        name: "user_configs",
        ddl: r#"
        create table if not exists user_configs (
            id varchar primary key,
            user_id varchar not null unique,
            llm_config text not null default '{}',
            other_config text not null default '{}',
            created_at timestamptz not null default now(),
            updated_at timestamptz
        )
        "#,
    },
    LegacyMirrorTableSpec {
        name: "projects",
        ddl: r#"
        create table if not exists projects (
            id varchar primary key,
            name varchar not null,
            description text,
            source_type varchar(20) not null default 'repository',
            repository_url varchar,
            repository_type varchar not null default 'other',
            default_branch varchar not null default 'main',
            programming_languages text not null default '[]',
            zip_file_hash varchar(64),
            owner_id varchar not null,
            is_active boolean not null default true,
            created_at timestamptz not null default now(),
            updated_at timestamptz
        )
        "#,
    },
    LegacyMirrorTableSpec {
        name: "project_info",
        ddl: r#"
        create table if not exists project_info (
            id varchar primary key,
            project_id varchar not null unique,
            language_info jsonb,
            description varchar,
            status varchar not null default 'pending',
            created_at timestamptz not null default now()
        )
        "#,
    },
    LegacyMirrorTableSpec {
        name: "project_management_metrics",
        ddl: r#"
        create table if not exists project_management_metrics (
            project_id varchar primary key,
            archive_size_bytes bigint default 0,
            archive_original_filename varchar,
            archive_uploaded_at timestamptz,
            total_tasks integer not null default 0,
            completed_tasks integer not null default 0,
            running_tasks integer not null default 0,
            agent_tasks integer not null default 0,
            opengrep_tasks integer not null default 0,
            gitleaks_tasks integer not null default 0,
            bandit_tasks integer not null default 0,
            phpstan_tasks integer not null default 0,
            critical integer not null default 0,
            high integer not null default 0,
            medium integer not null default 0,
            low integer not null default 0,
            verified_critical integer not null default 0,
            verified_high integer not null default 0,
            verified_medium integer not null default 0,
            verified_low integer not null default 0,
            last_completed_task_at timestamptz,
            status varchar not null default 'pending',
            error_message text,
            created_at timestamptz not null default now(),
            updated_at timestamptz
        )
        "#,
    },
    LegacyMirrorTableSpec {
        name: "prompt_skills",
        ddl: r#"
        create table if not exists prompt_skills (
            id varchar primary key,
            user_id varchar not null,
            name varchar(120) not null,
            content text not null,
            scope varchar(32) not null default 'global',
            agent_key varchar(64),
            is_active boolean not null default true,
            created_at timestamptz not null default now(),
            updated_at timestamptz
        )
        "#,
    },
];

pub async fn ensure_initialized(pool: &PgPool) -> Result<Vec<String>> {
    let mut ensured = Vec::new();
    for spec in LEGACY_MIRROR_TABLE_SPECS {
        sqlx::query(spec.ddl).execute(pool).await?;
        ensured.push(spec.name.to_string());
    }
    Ok(ensured)
}

#[cfg(test)]
pub(crate) fn ensured_table_names() -> Vec<&'static str> {
    LEGACY_MIRROR_TABLE_SPECS.iter().map(|spec| spec.name).collect()
}
