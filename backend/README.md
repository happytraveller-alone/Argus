# Rust Backend

## Local Development

### 1. Environment

Set the usual runtime environment variables before starting the server, for example:

- `DATABASE_URL`
- `ZIP_STORAGE_PATH`
- `BIND_ADDR` (optional, defaults to `0.0.0.0:8000`)

### 2. Run the backend

```bash
cargo run --bin backend-rust
```

### 3. Run tests

```bash
cargo test
```

### 4. Build a release binary

```bash
cargo build --release --bin backend-rust
```
