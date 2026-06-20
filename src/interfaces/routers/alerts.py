"""价格预警 API：/api/alerts/*。

从 web_api.py 抽出，路径与原 @app.post 完全一致。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.schemas import AlertAddResponse, AlertsCheckResponse
from src.api.dependencies import get_tenant_config

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post("/add", response_model=AlertAddResponse)
async def add_price_alert(payload: dict, cfg = Depends(get_tenant_config)):
    ticker = str(payload.get("ticker") or "").strip().upper()
    direction = payload.get("direction", "above")
    price = float(payload.get("price") or 0)
    if not ticker or price <= 0:
        return {"ok": False, "error": "请填写完整的预警信息"}
    config = cfg.load()
    alerts = config.setdefault("price_alerts", [])
    alerts.append({"ticker": ticker, "direction": direction, "price": price})
    config["price_alerts"] = alerts
    cfg._save_encrypted(config)
    return {"ok": True, "alerts": alerts}


@router.post("/remove", response_model=AlertAddResponse)
async def remove_price_alert(payload: dict, cfg = Depends(get_tenant_config)):
    idx = int(payload.get("alert_id") or -1)
    config = cfg.load()
    alerts = config.get("price_alerts", [])
    if 0 <= idx < len(alerts):
        alerts.pop(idx)
        config["price_alerts"] = alerts
        cfg._save_encrypted(config)
    return {"ok": True, "alerts": alerts}


@router.post("/check", response_model=AlertsCheckResponse)
async def check_price_alerts():
    """检查所有用户的价格预警并推送 Telegram。由定时任务调用。"""
    results = []
    tenants_dir = Path("data/tenants")
    if not tenants_dir.exists():
        return {"checked": 0, "triggered": 0}

    from src.data.financial import FinancialData  # noqa: PLC0415
    fd = FinancialData()
    triggered_count = 0

    for tenant_dir in tenants_dir.iterdir():
        cfg_file = tenant_dir / "config.json"
        if not cfg_file.exists():
            continue
        # Only check tenants with Telegram configured
        try:
            from src.multi_tenant.config import PerUserConfig  # noqa: PLC0415
            tenant_id = tenant_dir.name
            cfg = PerUserConfig(tenant_id)
            config = cfg.load()
            alerts = config.get("price_alerts", [])
            tg = config.get("telegram", {})
            bot_token = tg.get("bot_token", "")
            chat_id = tg.get("chat_id", "")
            if not alerts or not bot_token:
                continue

            for alert in alerts:
                ticker = alert["ticker"]
                target = float(alert["price"])
                direction = alert["direction"]
                price_data = fd.get_price(ticker)
                if not price_data:
                    continue
                current = price_data["price"]
                triggered = (direction == "above" and current > target) or (direction == "below" and current < target)
                if triggered:
                    import requests as _req  # noqa: PLC0415
                    emoji = "📈" if direction == "above" else "📉"
                    msg = f"{emoji} 价格预警触发\n{ticker} 已{direction == 'above' and '涨破' or '跌破'} ${target}\n当前价: ${current}"
                    try:
                        _req.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                  json={"chat_id": chat_id, "text": msg})
                        triggered_count += 1
                        results.append({"ticker": ticker, "triggered": True, "price": current})
                    except Exception:
                        pass  # Telegram 发送失败静默忽略（网络问题）
        except Exception as _alerts_err:
            import logging as _logging  # noqa: PLC0415
            _logging.warning(f"价格预警检查失败 (tenant {tenant_dir.name}): {_alerts_err}")
            continue

    return {"checked": len(list(tenants_dir.iterdir())), "triggered": triggered_count, "results": results}