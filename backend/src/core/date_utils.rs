use time::{OffsetDateTime, PrimitiveDateTime, UtcOffset};

#[derive(Debug, Clone, Copy)]
pub enum DateTimeInput {
    Naive(PrimitiveDateTime),
    Offset(OffsetDateTime),
}

impl DateTimeInput {
    fn to_offset(self) -> OffsetDateTime {
        match self {
            DateTimeInput::Naive(primitive) => primitive.assume_utc(),
            DateTimeInput::Offset(dt) => dt,
        }
    }

    fn components(self) -> (i32, u8, u8, u8, u8, u8) {
        match self {
            DateTimeInput::Naive(primitive) => (
                primitive.year(),
                primitive.month() as u8,
                primitive.day(),
                primitive.hour(),
                primitive.minute(),
                primitive.second(),
            ),
            DateTimeInput::Offset(offset_dt) => (
                offset_dt.year(),
                offset_dt.month() as u8,
                offset_dt.day(),
                offset_dt.hour(),
                offset_dt.minute(),
                offset_dt.second(),
            ),
        }
    }
}

impl From<PrimitiveDateTime> for DateTimeInput {
    fn from(value: PrimitiveDateTime) -> Self {
        DateTimeInput::Naive(value)
    }
}

impl From<OffsetDateTime> for DateTimeInput {
    fn from(value: OffsetDateTime) -> Self {
        DateTimeInput::Offset(value)
    }
}

/// Formats a `DateTimeInput` to an ISO-8601 string, mirroring Python's
/// `datetime.isoformat()` semantics.
pub fn format_iso(dt: DateTimeInput) -> String {
    match dt {
        DateTimeInput::Naive(primitive) => format_naive_iso(primitive),
        DateTimeInput::Offset(offset_dt) => format_offset_iso(offset_dt),
    }
}

fn format_naive_iso(primitive: PrimitiveDateTime) -> String {
    let mut iso = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        primitive.year(),
        primitive.month() as u8,
        primitive.day(),
        primitive.hour(),
        primitive.minute(),
        primitive.second()
    );
    let micros = primitive.nanosecond() / 1_000;
    if micros > 0 {
        iso.push('.');
        iso.push_str(&format!("{micros:06}"));
    }
    iso
}

fn format_offset_iso(offset_dt: OffsetDateTime) -> String {
    let mut iso = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        offset_dt.year(),
        offset_dt.month() as u8,
        offset_dt.day(),
        offset_dt.hour(),
        offset_dt.minute(),
        offset_dt.second()
    );
    let micros = offset_dt.nanosecond() / 1_000;
    if micros > 0 {
        iso.push('.');
        iso.push_str(&format!("{micros:06}"));
    }

    let offset = offset_dt.offset();
    iso.push_str(&format_offset(offset));
    iso
}

fn format_offset(offset: UtcOffset) -> String {
    let total_seconds = offset.whole_seconds();
    let sign = if total_seconds < 0 { '-' } else { '+' };
    let abs_seconds = total_seconds.abs();
    let hours = abs_seconds / 3_600;
    let minutes = (abs_seconds % 3_600) / 60;
    format!("{sign}{hours:02}:{minutes:02}")
}

/// Formats a `DateTimeInput` as `YYYY年MM月DD日 HH:MM:SS`.
pub fn format_chinese(dt: DateTimeInput) -> String {
    let (year, month, day, hour, minute, second) = dt.components();

    format!("{year:04}年{month:02}月{day:02}日 {hour:02}:{minute:02}:{second:02}")
}

/// Returns a Chinese relative time string like "3分钟前".
pub fn relative_time(dt: DateTimeInput, now: Option<DateTimeInput>) -> String {
    let dt = dt.to_offset();
    let now = now
        .map(DateTimeInput::to_offset)
        .unwrap_or_else(OffsetDateTime::now_utc);

    let seconds = (now - dt).whole_seconds();

    if seconds < 60 {
        "刚刚".to_string()
    } else if seconds < 3_600 {
        format!("{}分钟前", seconds / 60)
    } else if seconds < 86_400 {
        format!("{}小时前", seconds / 3_600)
    } else {
        format!("{}天前", seconds / 86_400)
    }
}

#[cfg(test)]
mod tests {
    use super::{format_chinese, format_iso, relative_time, DateTimeInput};
    use time::macros::{date, datetime, time};
    use time::{Duration, OffsetDateTime, PrimitiveDateTime, UtcOffset};

    #[test]
    fn test_format_iso() {
        let dt = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        assert_eq!(format_iso(dt), "2026-03-07T12:00:00+00:00");
    }

    #[test]
    fn test_format_iso_with_microseconds() {
        let dt = DateTimeInput::from(datetime!(2026-03-07 12:00:00.123456 UTC));
        let formatted = format_iso(dt);
        assert!(formatted.contains(".123456"));
    }

    #[test]
    fn test_format_iso_naive_datetime() {
        let primitive = PrimitiveDateTime::new(date!(2026 - 03 - 07), time!(12:00:00));
        let dt = DateTimeInput::from(primitive);
        assert_eq!(format_iso(dt), "2026-03-07T12:00:00");
    }

    #[test]
    fn test_format_iso_with_offset() {
        let primitive = PrimitiveDateTime::new(date!(2026 - 03 - 07), time!(12:00:00));
        let offset = UtcOffset::from_hms(8, 0, 0).unwrap();
        let dt = DateTimeInput::from(primitive.assume_offset(offset));
        assert_eq!(format_iso(dt), "2026-03-07T12:00:00+08:00");
    }

    #[test]
    fn test_format_chinese() {
        let dt = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        assert_eq!(format_chinese(dt), "2026年03月07日 12:00:00");
    }

    #[test]
    fn test_format_chinese_different_time() {
        let primitive = PrimitiveDateTime::new(date!(2025 - 12 - 31), time!(23:59:59));
        let dt = DateTimeInput::from(primitive);
        assert_eq!(format_chinese(dt), "2025年12月31日 23:59:59");
    }

    #[test]
    fn test_relative_time_just_now() {
        let now = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        let dt = DateTimeInput::from(datetime!(2026-03-07 11:59:30 UTC));
        assert_eq!(relative_time(dt, Some(now)), "刚刚");
    }

    #[test]
    fn test_relative_time_minutes() {
        let now = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        let dt = DateTimeInput::from(datetime!(2026-03-07 11:55:00 UTC));
        assert_eq!(relative_time(dt, Some(now)), "5分钟前");
    }

    #[test]
    fn test_relative_time_hours() {
        let now = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        let dt = DateTimeInput::from(datetime!(2026-03-07 10:00:00 UTC));
        assert_eq!(relative_time(dt, Some(now)), "2小时前");
    }

    #[test]
    fn test_relative_time_days() {
        let now = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        let dt = DateTimeInput::from(datetime!(2026-03-04 12:00:00 UTC));
        assert_eq!(relative_time(dt, Some(now)), "3天前");
    }

    #[test]
    fn test_relative_time_without_now() {
        let dt = DateTimeInput::from(OffsetDateTime::now_utc() - Duration::minutes(10));
        let result = relative_time(dt, None);
        assert!(result.contains("分钟前"));
    }

    #[test]
    fn test_relative_time_naive_datetime() {
        let now = DateTimeInput::from(PrimitiveDateTime::new(
            date!(2026 - 03 - 07),
            time!(12:00:00),
        ));
        let dt = DateTimeInput::from(PrimitiveDateTime::new(
            date!(2026 - 03 - 07),
            time!(10:00:00),
        ));
        assert_eq!(relative_time(dt, Some(now)), "2小时前");
    }

    #[test]
    fn test_relative_time_edge_cases() {
        let now = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC));
        let cases = [
            (Duration::seconds(59), "刚刚"),
            (Duration::seconds(60), "1分钟前"),
            (Duration::seconds(3_599), "59分钟前"),
            (Duration::hours(1), "1小时前"),
            (Duration::hours(23) + Duration::minutes(59), "23小时前"),
            (Duration::days(1), "1天前"),
        ];

        for (delta, expected) in cases {
            let dt = DateTimeInput::from(datetime!(2026-03-07 12:00:00 UTC) - delta);
            assert_eq!(relative_time(dt, Some(now)), expected);
        }
    }
}
