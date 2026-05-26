//! Stub auth crate for the monorepo_bazel_cargo fixture.

pub fn validate_token(token: &str) -> bool {
    !token.is_empty()
}
