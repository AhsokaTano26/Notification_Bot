"""Tests for Uptime Kuma notification formatting."""

from src.plugins.uptime_kuma import _uptime_kuma_notification


def test_formats_certificate_expiry_message() -> None:
    markdown, plain_text = _uptime_kuma_notification(
        {
            "msg": (
                "[Tano博客（国内）][https://tano.asia] server certificate "
                "tano.asia will expire in 21 days"
            ),
        },
        b"",
    )

    assert "**🟡 Tano博客（国内） · 证书即将到期**" in markdown
    assert "地址：https://tano.asia" in markdown
    assert "证书域名：tano.asia" in markdown
    assert "剩余时间：21 天" in markdown
    assert "🟡 Tano博客（国内） · 证书即将到期" in plain_text


def test_formats_urgent_certificate_expiry_message() -> None:
    markdown, _ = _uptime_kuma_notification(
        {
            "msg": (
                "[Tano博客（国内）][https://tano.asia] server certificate "
                "tano.asia will expire in 7 days"
            ),
        },
        b"",
    )

    assert "**🔴 Tano博客（国内） · 证书即将到期**" in markdown
