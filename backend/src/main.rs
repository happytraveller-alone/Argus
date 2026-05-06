use std::{collections::HashMap, sync::Arc};

use anyhow::Result;
use tokio::net::TcpListener;
use tokio::sync::watch;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use backend_rust::{
    app::build_router,
    bootstrap,
    config::AppConfig,
    db::cubesandbox_templates::TemplateKind,
    runtime::a3s_box::pool::{a3s_box_on_shutdown_destroy, A3sBoxFactory, A3sBoxTemplateKind},
    runtime::cubesandbox::{
        pool::{build_pool_client, cubesandbox_on_shutdown_destroy, CubesandboxFactory},
        wait_for_active_scans_drain, ShutdownGate,
    },
    runtime::sandbox_pool::SandboxPool,
    state::AppState,
};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::from_default_env())
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = AppConfig::from_env()?;
    let mut state = AppState::from_config(config.clone()).await?;
    // Startup/bootstrap happens before we start accepting requests.
    // It should not do heavy migrations, just minimal checks and clear status reporting.
    bootstrap::run(&state).await?;

    // ── Phase A.3.2: standby pool bootstrap ──────────────────────────────────
    //
    // Only instantiate the pool when cubesandbox is enabled.  When disabled,
    // `cubesandbox_pool` stays `None` and scan paths fall through to cold-start.
    if config.cubesandbox_enabled {
        // A.3 startup guard: total target must not exceed max_total_standby.
        // Includes cubesandbox (opengrep + codeql) AND a3s-box pool (Phase C.3).
        let opengrep_target = if config.opengrep_standby_pool_disabled {
            0
        } else {
            config.opengrep_standby_pool_size
        };
        let codeql_target = if config.codeql_standby_pool_disabled {
            0
        } else {
            config.codeql_standby_pool_size
        };
        let a3s_box_target = if config.a3s_box_standby_pool_disabled {
            0
        } else {
            config.a3s_box_standby_pool_size
        };
        let total_target = opengrep_target + codeql_target + a3s_box_target;
        if total_target > config.max_total_standby {
            anyhow::bail!(
                "standby pool config error: total_target={total_target} > \
                 max_total_standby={max}. \
                 Reduce OPENGREP_STANDBY_POOL_SIZE / CODEQL_STANDBY_POOL_SIZE or raise ARGUS_MAX_TOTAL_STANDBY.",
                max = config.max_total_standby
            );
        }

        let pool_client = build_pool_client(&state)?;
        let on_shutdown = cubesandbox_on_shutdown_destroy(Arc::clone(&pool_client));
        let factory = Arc::new(CubesandboxFactory {
            state: state.clone(),
            client: Arc::clone(&pool_client),
        });

        let mut capacities: HashMap<TemplateKind, usize> = HashMap::new();
        if !config.opengrep_standby_pool_disabled {
            capacities.insert(TemplateKind::OpengrepDedicated, config.opengrep_standby_pool_size);
        }
        if !config.codeql_standby_pool_disabled {
            capacities.insert(TemplateKind::CodeqlCpp, config.codeql_standby_pool_size);
        }

        // M3: semaphore must not exceed either limit — use min so neither
        // operator-declared budget (max_total_standby) nor cubemaster pressure
        // (cubemaster_capacity) is breached.
        let effective_max = config.max_total_standby.min(config.cubemaster_capacity);
        if effective_max == 0 {
            panic!("effective_max == 0 — increase max_total_standby or cubemaster_capacity");
        }
        tracing::info!(
            metric = "standby_pool_effective_max",
            max_total_standby = config.max_total_standby,
            cubemaster_capacity = config.cubemaster_capacity,
            effective_max,
        );
        let pool = Arc::new(SandboxPool::new(
            capacities,
            effective_max,
            factory,
            on_shutdown,
        ));

        // Eager warmup: spawn background refill tasks for all configured slots.
        // warmup() returns after spawning (non-blocking); actual VM creation
        // runs concurrently with the HTTP listener startup.
        pool.warmup().await;

        tracing::info!(
            opengrep_pool_size = config.opengrep_standby_pool_size,
            opengrep_pool_disabled = config.opengrep_standby_pool_disabled,
            max_total_standby = effective_max,
            "cubesandbox standby pool initialized"
        );

        state.cubesandbox_pool = Some(pool);

        // ── Phase C.3: a3s-box image-cache standby pool ──────────────────────
        //
        // Option C.β: each "standby" entry is a pre-warmed OCI image cache.
        // No running microVM is held; boot latency is NOT eliminated.
        // The pool eliminates the Docker→OCI conversion (30–60 s) on cold cache.
        if !config.a3s_box_standby_pool_disabled {
            let a3s_image = config.scanner_opengrep_a3s_box_image.clone();
            let a3s_factory = Arc::new(A3sBoxFactory { image: a3s_image });
            let a3s_on_shutdown = a3s_box_on_shutdown_destroy();

            let mut a3s_caps: HashMap<A3sBoxTemplateKind, usize> = HashMap::new();
            a3s_caps.insert(A3sBoxTemplateKind::OpengrepDedicated, config.a3s_box_standby_pool_size);

            // a3s-box does not talk to cubemaster; cap is max_total_standby only.
            let effective_max_a3s = config.max_total_standby;
            let a3s_pool = Arc::new(SandboxPool::new(
                a3s_caps,
                effective_max_a3s,
                a3s_factory,
                a3s_on_shutdown,
            ));
            a3s_pool.warmup().await;

            tracing::info!(
                a3s_box_pool_size = config.a3s_box_standby_pool_size,
                "a3s-box image-cache standby pool initialized (Option C.β)"
            );

            state.a3s_box_pool = Some(a3s_pool);
        } else {
            tracing::info!("a3s-box standby pool disabled; image-cache pre-warm not started");
        }
    } else {
        tracing::info!("cubesandbox disabled; standby pool not started");
    }

    let gate = ShutdownGate::new();
    let (shutdown_tx, _shutdown_rx) = watch::channel::<bool>(false);

    // Pass gate directly — build_router mounts a single Extension(ShutdownGate).
    // No secondary .layer() chain needed; single source of truth.
    let app = build_router(state.clone(), gate.clone());
    let listener = TcpListener::bind(config.bind_addr).await?;

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal(shutdown_tx, gate, state))
        .await?;

    tracing::info!("axum graceful shutdown complete");
    Ok(())
}

async fn shutdown_signal(tx: watch::Sender<bool>, gate: ShutdownGate, state: AppState) {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let sigterm = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let sigterm = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => { tracing::info!("received Ctrl+C, initiating graceful shutdown"); }
        _ = sigterm => { tracing::info!("received SIGTERM, initiating graceful shutdown"); }
    }

    gate.set();
    let _ = tx.send(true);

    // Wait for all in-flight scan tasks to finish their cleanup blocks before
    // allowing axum to exit. Without this, detached tokio::spawn scan futures
    // are aborted at their next .await when the runtime drops, meaning
    // best_effort_delete_sandbox never runs and sandboxes leak.
    // Hard timeout: 60 s — remaining orphans are reaped by reconcile / argus-shutdown.sh.
    wait_for_active_scans_drain(tokio::time::Duration::from_secs(60)).await;

    // Drain the standby pool: cancel refill tasks and destroy held sandboxes.
    if let Some(pool) = &state.cubesandbox_pool {
        tracing::info!("shutting down cubesandbox standby pool");
        pool.shutdown().await;
    }

    // Drain a3s-box pool (Phase C.3): no-op destroy (Option C.β — warm cache entries only).
    if let Some(pool) = &state.a3s_box_pool {
        tracing::info!("shutting down a3s-box image-cache standby pool");
        pool.shutdown().await;
    }
}
