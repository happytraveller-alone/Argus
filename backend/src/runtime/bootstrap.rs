use anyhow::{bail, Context, Result};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    env,
    ffi::OsString,
    fs,
    os::unix::process::CommandExt,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::Duration,
};

const DEFAULT_VENV_PATH: &str = "/opt/backend-venv";
const DEFAULT_APP_ROOT: &str = "/app";
const DEFAULT_BACKEND_DOCKER_ENV_DIR: &str = "/docker/env/backend";
const LOCK_STAMP_FILENAME: &str = ".vulhunter-dev-lock.sha256";
const DEFAULT_PYPI_INDEX_CANDIDATES: &str = concat!(
    "https://mirrors.aliyun.com/pypi/simple/,",
    "https://pypi.tuna.tsinghua.edu.cn/simple,",
    "https://pypi.mirrors.ustc.edu.cn/simple/,",
    "https://pypi.org/simple"
);
const PACKAGE_SELECTOR: &str = "/usr/local/bin/package_source_selector.py";
const WAIT_DB_MAX_RETRIES: u32 = 30;
const WAIT_DB_SLEEP_SECONDS: u64 = 2;

fn is_true(value: Option<&String>) -> bool {
    matches!(
        value.as_deref().map(|val| val.trim()).filter(|v| !v.is_empty()),
        Some(val) if matches!(
            val.to_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        )
    )
}

fn read_env_var(key: &str) -> Option<String> {
    env::var(key).ok().filter(|val| !val.trim().is_empty())
}

fn python_database_url() -> String {
    read_env_var("PYTHON_DATABASE_URL")
        .or_else(|| read_env_var("DATABASE_URL"))
        .unwrap_or_default()
}

fn backend_venv_path() -> PathBuf {
    env::var("BACKEND_VENV_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(DEFAULT_VENV_PATH))
}

fn venv_bin<S: AsRef<str>>(name: S) -> PathBuf {
    backend_venv_path().join("bin").join(name.as_ref())
}

fn python_version() -> Result<String> {
    let output = Command::new("python3")
        .args(&[
            "-c",
            "import sys; print('.'.join(str(part) for part in sys.version_info[:3]))",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output()
        .context("failed to query python version")?;

    if !output.status.success() {
        bail!("python3 version command failed");
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn read_venv_version(venv_dir: &Path) -> Result<String> {
    let cfg_path = venv_dir.join("pyvenv.cfg");
    if !cfg_path.exists() {
        return Ok(String::new());
    }

    let content = fs::read_to_string(&cfg_path).context("read pyvenv.cfg")?;
    for line in content.lines() {
        if let Some(rest) = line.strip_prefix("version_info = ") {
            return Ok(rest.trim().to_string());
        }
    }

    Ok(String::new())
}

fn venv_can_run_backend(venv_dir: &Path) -> Result<bool> {
    let python_bin = venv_dir.join("bin").join("python");
    if !python_bin.exists() {
        return Ok(false);
    }

    let status = Command::new(python_bin)
        .args(&["-c", "import sqlalchemy, alembic, uvicorn"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .context("failed to run backend python smoke test")?;

    Ok(status.success())
}

fn ensure_backend_venv() -> Result<()> {
    let venv_dir = backend_venv_path();
    let current_version = read_venv_version(&venv_dir)?;
    let expected_version = python_version()?;

    if !current_version.is_empty()
        && current_version == expected_version
        && venv_can_run_backend(&venv_dir)?
    {
        return Ok(());
    }

    if current_version.is_empty() {
        println!("Creating backend virtualenv in {}...", venv_dir.display());
    } else {
        println!(
            "Recreating backend virtualenv in {} (current={}, expected={})...",
            venv_dir.display(),
            current_version,
            expected_version
        );
    }

    if let Some(parent) = venv_dir.parent() {
        fs::create_dir_all(parent).context("create venv parent")?;
    }

    Command::new("uv")
        .args(&[
            "venv",
            "--clear",
            venv_dir.to_str().context("venv path invalid")?,
        ])
        .status()
        .context("failed to create backend venv")?
        .success()
        .then_some(())
        .ok_or_else(|| anyhow::anyhow!("uv venv command failed"))?;

    Ok(())
}

fn compute_lock_hash(app_root: &Path) -> Result<String> {
    let pyproject = app_root.join("pyproject.toml");
    let lock_file = app_root.join("uv.lock");
    if !pyproject.exists() || !lock_file.exists() {
        return Ok(String::new());
    }

    let mut hasher = Sha256::new();
    hasher.update(fs::read(&pyproject).context("read pyproject.toml for hash")?);
    hasher.update(fs::read(&lock_file).context("read uv.lock for hash")?);

    Ok(format!("{:x}", hasher.finalize()))
}

fn get_ordered_pypi_candidates() -> Result<Vec<String>> {
    if let Some(explicit) = read_env_var("UV_INDEX_URL").or_else(|| read_env_var("PIP_INDEX_URL")) {
        return Ok(vec![explicit]);
    }

    let raw = env::var("PYPI_INDEX_CANDIDATES")
        .unwrap_or_else(|_| DEFAULT_PYPI_INDEX_CANDIDATES.to_string());
    let all_candidates: Vec<String> = raw
        .split(',')
        .map(|candidate| candidate.trim().to_string())
        .filter(|candidate| !candidate.is_empty())
        .collect();

    let selector_path = Path::new(PACKAGE_SELECTOR);
    if selector_path.exists() {
        let output = Command::new("python3")
            .args(&[
                PACKAGE_SELECTOR,
                "--candidates",
                &raw,
                "--kind",
                "pypi",
                "--timeout-seconds",
                "2",
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output()
            .context("running package_source_selector")?;

        if output.status.success() {
            let mut ranked: Vec<String> = String::from_utf8_lossy(&output.stdout)
                .lines()
                .map(|line| line.trim().to_string())
                .filter(|line| !line.is_empty())
                .collect();

            if !ranked.is_empty() {
                let mut seen = HashSet::new();
                ranked.retain(|candidate| seen.insert(candidate.clone()));
                for candidate in &all_candidates {
                    if seen.insert(candidate.clone()) {
                        ranked.push(candidate.clone());
                    }
                }
                return Ok(ranked);
            }
        }
    }

    Ok(all_candidates)
}

pub fn sync_backend_env_if_needed(app_root: &Path) -> Result<()> {
    let venv_dir = backend_venv_path();
    let stamp_file = venv_dir.join(LOCK_STAMP_FILENAME);

    env::set_var("VIRTUAL_ENV", &venv_dir);
    let path_env = env::var_os("PATH").unwrap_or_default();
    let venv_bin_dir = venv_dir.join("bin");
    let mut prefixed_path = OsString::from(venv_bin_dir.to_string_lossy().to_string());
    prefixed_path.push(":");
    prefixed_path.push(&path_env);
    env::set_var("PATH", &prefixed_path);

    ensure_backend_venv()?;

    let current_hash = compute_lock_hash(app_root)?;
    let previous_hash = if stamp_file.exists() {
        fs::read_to_string(&stamp_file)
            .unwrap_or_default()
            .trim()
            .to_string()
    } else {
        String::new()
    };

    if !current_hash.is_empty() && current_hash == previous_hash {
        println!("Python lockfile unchanged, skip uv sync");
        return Ok(());
    }

    println!("Syncing backend dependencies with uv...");
    fs::create_dir_all("/root/.cache/uv").context("create uv cache dir")?;

    let candidates = get_ordered_pypi_candidates()?;
    println!("PyPI index candidates: {:?}", candidates);

    for index_url in &candidates {
        println!("uv sync via {} ...", index_url);
        let status = Command::new("uv")
            .args(&["sync", "--active", "--frozen", "--no-dev"])
            .current_dir(app_root)
            .env("UV_INDEX_URL", &index_url)
            .env("PIP_INDEX_URL", &index_url)
            .status()
            .context("running uv sync")?;

        if status.success() {
            env::set_var("UV_INDEX_URL", index_url);
            env::set_var("PIP_INDEX_URL", index_url);
            if !current_hash.is_empty() {
                fs::write(&stamp_file, format!("{}\n", current_hash))
                    .context("write uv stamp file")?;
            }
            return Ok(());
        }

        println!(
            "uv sync failed via {} (exit {}), trying next index...",
            index_url,
            status.code().unwrap_or(-1)
        );
    }

    bail!(
        "uv sync failed on all {} PyPI indexes: {:?}",
        candidates.len(),
        candidates
    );
}

pub fn ensure_backend_env_files(app_root: &Path) -> Result<()> {
    let docker_env_dir = PathBuf::from(
        env::var("BACKEND_DOCKER_ENV_DIR")
            .unwrap_or_else(|_| DEFAULT_BACKEND_DOCKER_ENV_DIR.into()),
    );
    let docker_env_file = docker_env_dir.join(".env");
    let docker_env_example = docker_env_dir.join("env.example");
    let app_env_file = app_root.join(".env");

    let source_for_app_env = if docker_env_file.exists() {
        Some(docker_env_file.clone())
    } else if docker_env_example.exists() {
        fs::create_dir_all(&docker_env_dir).context("create docker env dir")?;
        fs::copy(&docker_env_example, &docker_env_file)
            .context("bootstrap docker env from example")?;
        println!(
            "Bootstrapped backend Docker env from template: {}",
            docker_env_file.display()
        );
        Some(docker_env_file.clone())
    } else {
        None
    };

    if let Some(source) = source_for_app_env {
        if !app_env_file.exists() {
            fs::copy(source, &app_env_file).context("prepare backend app env file")?;
            println!("Prepared backend app env file: {}", app_env_file.display());
        }
    }

    Ok(())
}

pub fn wait_for_db(max_retries: u32, sleep_seconds: u64) -> Result<()> {
    println!("Waiting for PostgreSQL...");
    let database_url = python_database_url();
    let script = "import asyncio, os\n\
from sqlalchemy import text\n\
from sqlalchemy.ext.asyncio import create_async_engine\n\
async def check_db():\n\
    engine = create_async_engine(os.environ.get('PYTHON_DATABASE_URL') or os.environ.get('DATABASE_URL', ''))\n\
    try:\n\
        async with engine.connect() as conn:\n\
            await conn.execute(text('SELECT 1'))\n\
        return True\n\
    except Exception:\n\
        return False\n\
    finally:\n\
        await engine.dispose()\n\
raise SystemExit(0 if asyncio.run(check_db()) else 1)\n";

    let python_bin = venv_bin("python");
    for retry in 0..max_retries {
        let status = Command::new(&python_bin)
            .args(&["-c", script])
            .env("PYTHON_DATABASE_URL", &database_url)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .context("running DB readiness check")?;

        if status.success() {
            println!("Database connection ready");
            return Ok(());
        }

        println!("Retry {}/{}...", retry + 1, max_retries);
        thread::sleep(Duration::from_secs(sleep_seconds));
    }

    bail!("Failed to connect to database");
}

pub fn run_database_migrations(app_root: &Path) -> Result<()> {
    println!("Running database migrations...");
    Command::new(venv_bin("alembic"))
        .args(&["upgrade", "head"])
        .current_dir(app_root)
        .status()
        .context("running alembic upgrade")?
        .success()
        .then_some(())
        .ok_or_else(|| anyhow::anyhow!("alembic upgrade failed"))?;
    Ok(())
}

pub fn run_optional_resets(app_root: &Path) -> Result<()> {
    if !is_true(env::var("RESET_STATIC_SCAN_TABLES_ON_DEPLOY").ok().as_ref()) {
        return Ok(());
    }

    println!("Resetting static scan tables...");
    Command::new(venv_bin("python"))
        .arg(app_root.join("scripts").join("reset_static_scan_tables.py"))
        .status()
        .context("running reset_static_scan_tables")?
        .success()
        .then_some(())
        .ok_or_else(|| anyhow::anyhow!("reset static scan tables failed"))?;
    Ok(())
}

pub fn exec_uvicorn(reload_enabled: bool) -> Result<()> {
    let uvicorn_bin = venv_bin("uvicorn");
    let mut args = vec![
        "app.main:app".to_string(),
        "--host".to_string(),
        "0.0.0.0".to_string(),
        "--port".to_string(),
        "8000".to_string(),
    ];
    if reload_enabled {
        args.insert(1, "--reload".to_string());
    }

    let err = Command::new(&uvicorn_bin).args(&args).exec();
    bail!("starting uvicorn failed: {err}")
}

pub fn run(mode: &str) -> Result<()> {
    let mode = mode.trim();
    if mode != "dev" && mode != "prod" {
        bail!("unexpected mode `{}`; expected `dev` or `prod`", mode);
    }

    let app_root =
        PathBuf::from(env::var("BACKEND_APP_ROOT").unwrap_or_else(|_| DEFAULT_APP_ROOT.into()));
    env::set_current_dir(&app_root).context("change to backend app root")?;

    ensure_backend_env_files(&app_root)?;

    if mode == "dev" {
        println!("Starting VulHunter backend dev container...");
        sync_backend_env_if_needed(&app_root)?;
    } else {
        println!("VulHunter 后端启动中...");
    }

    wait_for_db(WAIT_DB_MAX_RETRIES, WAIT_DB_SLEEP_SECONDS)?;
    run_database_migrations(&app_root)?;
    run_optional_resets(&app_root)?;

    println!("Starting uvicorn...");
    exec_uvicorn(mode == "dev")
}
